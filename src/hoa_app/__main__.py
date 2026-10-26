"""Start HOAForecaster – `uv run hoaforecaster` (spec section 10.1).

One command: builds the screens with npm the first time (or after `web/` changes),
opens the projects in the data folder (HOA_DATA_DIR, or the per-user application
data folder), copies the demo project in on the very first run, and serves the app
on 127.0.0.1 only, opening it in the browser once the server is listening.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn

from hoa_app.api import STOP_HEADER, STOP_PATH, create_app
from hoa_app.lock import DataFolderLock, FolderInUse
from hoa_store.store import ProjectStore, default_root

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
WEB_DIST = WEB / "dist"
DEMO = ROOT / "demo" / "fixtures" / "project.json"
HOST = "127.0.0.1"  # never anything else – the app is for this computer only


def _sources_newer_than_build() -> bool:
    built = (WEB_DIST / "index.html").stat().st_mtime
    watched = [WEB / "package.json", WEB / "index.html", *(WEB / "src").rglob("*")]
    return any(p.is_file() and p.stat().st_mtime > built for p in watched)


def ensure_built() -> bool:
    """Build web/dist when it is missing or older than web/src. False if that is impossible."""
    if (WEB_DIST / "index.html").is_file() and not _sources_newer_than_build():
        return True
    npm = shutil.which("npm")
    if npm is None or not (WEB / "package.json").is_file():
        print(
            "The screens are not built and npm was not found. Install Node.js "
            "(https://nodejs.org), then start again.",
            file=sys.stderr,
        )
        return False
    print("Building the screens – this takes a minute the first time…")
    for step in (["ci", "--no-audit", "--no-fund"], ["run", "build"]):
        if step[0] == "ci" and (WEB / "node_modules").is_dir():
            continue
        if subprocess.run([npm, *step], cwd=WEB, check=False).returncode != 0:
            print(f"npm {' '.join(step)} failed – see the messages above.", file=sys.stderr)
            return False
    return True


def port_free(port: int) -> bool:
    """Whether the server could bind the port now – tested the way it binds. On macOS and Linux
    the server sets SO_REUSEADDR, so a closed connection still waiting out its TIME_WAIT does not
    hold the port; on Windows that option would let a second server bind beside a live one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if sys.platform != "win32":  # pragma: no cover – tested where it applies
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((HOST, port))
        except OSError:
            return False
    return True


def open_when_ready(server: uvicorn.Server, url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.1)
    if server.started:
        webbrowser.open(url)


RESTART = 75  # the server's exit code asking the launcher to start a fresh one
STOP_GRACE = 5.0  # seconds a server asked to restart has to stop before it ends itself
DRAIN = 3  # seconds a stopping server gives requests in flight – well inside STOP_GRACE
FREE_WAIT = 10.0  # seconds the launcher waits for the old server's port to come free
# more restarts than this in a minute means something keeps asking – stop instead of looping
MAX_RESTARTS, RESTART_WINDOW = 5, 60.0
# while the app runs, its launcher holds LAUNCHER_LOCK and keeps RUNNING beside it – the port and
# the key that stops it – so starting the app again can stop the running copy cleanly first
LAUNCHER_LOCK = ".launcher.lock"
RUNNING = ".running.json"
RECORD_LIMIT = 4096  # bytes – a record is under a hundred; anything longer is not one
TAKEOVER_WAIT = 15.0  # seconds a new launch waits for the running copy to end once it agreed
REACH_WAIT = 120.0  # seconds a new launch keeps asking a copy still building or starting up


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """An answer pointing elsewhere is a refusal – the stop key never follows it."""

    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


# straight to this computer – a proxy set for the web, or a redirect, never sees the stop key
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())


def _port(text: str) -> int:
    port = int(text)
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("the port must be a number from 1024 to 65535")
    return port


def _port_in_use(port: int) -> int:
    print(
        f"Port {port} is in use – HOAForecaster may already be running (a copy started before "
        "this version, or one whose window was ended from Task Manager: close it). "
        f"Open http://{HOST}:{port}/ or start with --port and another number.",
        file=sys.stderr,
    )
    return 1


def wait_port_free(port: int, timeout: float = FREE_WAIT) -> bool:
    deadline = time.monotonic() + timeout
    while not port_free(port):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
    return True


def record_running(root: Path, port: int, stop_key: str) -> bool:
    """Note this launcher's port and stop key, written whole. False if it could not be. The
    folder is the user's own (on Windows, its permissions come from the user's profile)."""
    text = json.dumps({"pid": os.getpid(), "port": port, "stop_key": stop_key})
    part = root / f"{RUNNING}.{os.getpid()}.tmp"
    try:
        part.unlink(missing_ok=True)
        # a new file of its own – never one planted there, nor a link to one
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(part, flags, 0o600), "w", encoding="utf-8") as f:
            f.write(text)
        for _ in range(20):
            try:
                os.replace(part, root / RUNNING)
                return True
            except PermissionError:  # on Windows, while a new launch has it open to read
                time.sleep(0.05)
        part.unlink(missing_ok=True)
    except OSError:
        pass
    return False


def _record(root: Path) -> dict[str, Any] | None:
    try:
        with open(root / RUNNING, "rb") as f:
            raw = f.read(RECORD_LIMIT + 1)
        data = None if len(raw) > RECORD_LIMIT else json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError):  # missing, damaged, or nested to no end
        return None
    return data if isinstance(data, dict) else None


def read_running(root: Path) -> tuple[int, str] | None:
    """The running copy's port and stop key, or None when there is no usable record."""
    data = _record(root) or {}
    port, key = data.get("port"), data.get("stop_key")
    if type(port) is not int or not 1024 <= port <= 65535:
        return None
    if not isinstance(key, str) or not key:
        return None
    return port, key


def forget_running(root: Path) -> None:
    """Remove the record – only this process's own, never a newer launcher's."""
    if (_record(root) or {}).get("pid") == os.getpid():
        with contextlib.suppress(OSError):
            (root / RUNNING).unlink()


def ask_to_stop(port: int, stop_key: str) -> bool:
    """Ask the server on this computer's port to stop for good. True once it has agreed."""
    request = urllib.request.Request(
        f"http://{HOST}:{port}{STOP_PATH}", method="POST", headers={STOP_HEADER: stop_key}
    )
    try:
        with _direct.open(request, timeout=STOP_GRACE) as answer:
            return bool(answer.status == 202)
    except (OSError, http.client.HTTPException):  # not listening, refused, or not HTTP at all
        return False


def _launcher_lock(root: Path) -> DataFolderLock | None:
    try:
        return DataFolderLock(root, LAUNCHER_LOCK)
    except FolderInUse:
        return None


def take_over(root: Path, port: int) -> DataFolderLock | None:
    """The launcher's lock on this data folder – first stopping, cleanly, the copy already running
    on it: asking its server to stop (again and again while that copy is still building or
    starting its server), then waiting until its launcher has ended and its port is free. None,
    having said why, if it could not be stopped – never a second copy beside it."""
    lock = _launcher_lock(root)
    if lock is not None:
        return lock
    print("HOAForecaster is already running – stopping it first…")
    reach = time.monotonic() + REACH_WAIT
    while True:
        running = read_running(root)
        if running is not None and ask_to_stop(*running):
            port = running[0]
            break
        lock = _launcher_lock(root)
        if lock is not None:  # it ended by itself meanwhile – give its port a moment too
            wait_port_free(port)
            return lock
        if time.monotonic() >= reach:
            print(
                f"The running HOAForecaster (data folder {root}) could not be stopped – close its "
                "window, then start again.",
                file=sys.stderr,
            )
            return None
        time.sleep(0.5)
    deadline = time.monotonic() + TAKEOVER_WAIT
    while lock is None:
        if time.monotonic() >= deadline:
            print(
                f"The running HOAForecaster did not stop within {TAKEOVER_WAIT:.0f} seconds – "
                "close its window, then start again.",
                file=sys.stderr,
            )
            return None
        time.sleep(0.2)
        lock = _launcher_lock(root)
    if not wait_port_free(port, max(0.0, deadline - time.monotonic())):
        lock.release()
        print(
            f"The running HOAForecaster stopped, but port {port} is still in use – start "
            "again in a moment.",
            file=sys.stderr,
        )
        return None
    return lock


def serve(port: int, browser: bool, stop_key: str | None = None) -> int:
    """Run one server until it stops – 0 when stopped, RESTART when the page asked for a fresh
    one. Holds the data folder's lock while it runs. With `stop_key` (the launcher's), a new
    launch can stop it for good."""
    root = default_root()
    try:
        lock = DataFolderLock(root)
    except FolderInUse:
        print(f"HOAForecaster is already running with the data folder {root}", file=sys.stderr)
        return 1
    restarting, stopping = threading.Event(), threading.Event()
    with lock:
        store = ProjectStore(root)
        store.seed(DEMO)
        url = f"http://{HOST}:{port}/"

        def end_now() -> None:
            # asked when it fires, so stopping for good still wins over a restart asked earlier
            os._exit(0 if stopping.is_set() else RESTART)

        def stop_soon() -> None:
            server.should_exit = True
            # if it has not stopped in time, end this process so it can never linger; a daemon,
            # so a clean stop does not wait for it
            deadline = threading.Timer(STOP_GRACE, end_now)
            deadline.daemon = True
            deadline.start()

        def restart() -> None:
            restarting.set()
            stop_soon()

        def stop() -> None:  # the app was started again – stop for good
            stopping.set()
            stop_soon()

        app = create_app(
            store,
            secrets.token_urlsafe(32),
            WEB_DIST,
            on_restart=restart,
            stop_key=stop_key,
            on_stop=stop if stop_key else None,
        )
        config = uvicorn.Config(
            app, host=HOST, port=port, log_level="warning", timeout_graceful_shutdown=DRAIN
        )
        server = uvicorn.Server(config)
        print(f"HOAForecaster – {url}  (data folder {root}; press Ctrl+C to stop)")
        if browser:
            threading.Thread(target=open_when_ready, args=(server, url), daemon=True).start()
        try:
            server.run()
        except KeyboardInterrupt:  # Ctrl+C – it has stopped; no traceback
            return 0
    if stopping.is_set():  # stopping for good wins over a restart asked at the same moment
        print("HOAForecaster was started again – this copy has stopped.")
        return 0
    return RESTART if restarting.is_set() else 0


def supervise(port: int, browser: bool, stop_key: str) -> int:
    """Run the server as a child process, and start a fresh one each time it exits asking to
    restart – only once the old process has ended and its port is free, rebuilding the screens
    first if they changed. The browser opens only on the first start; the page reloads itself
    after a restart. Restarting more than MAX_RESTARTS times a minute stops instead. Each
    server is handed `stop_key` through a pipe – never on its command line."""
    restarts: list[float] = []
    child: subprocess.Popen[bytes] | None = None
    while True:
        try:
            if not ensure_built():
                return 1
            if not wait_port_free(port):
                return _port_in_use(port)
            # -P: never import from the folder it was started in, only from the app's own code
            command = [sys.executable, "-P", "-m", "hoa_app", "--serve", "--port", str(port)]
            if not browser:
                command.append("--no-browser")
            command.append("--stop-key-on-stdin")
            child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE)
            assert child.stdin is not None  # a pipe, as asked
            # a server that ended at once has closed its end – its own exit code says why
            with contextlib.suppress(OSError):
                child.stdin.write(f"{stop_key}\n".encode())
                child.stdin.close()
            code = child.wait()  # returns only once the old server's process has ended
        except KeyboardInterrupt:  # Ctrl+C reaches the child too – let it stop, then stop
            if child is not None and child.poll() is None:
                child.wait()
            return 0
        if code != RESTART:
            return code
        now = time.monotonic()
        restarts = [t for t in restarts if now - t < RESTART_WINDOW] + [now]
        if len(restarts) > MAX_RESTARTS:
            print(
                f"HOAForecaster was asked to restart more than {MAX_RESTARTS} times in a minute "
                "– stopped. Start it again when you are ready.",
                file=sys.stderr,
            )
            return 1
        print("Restarting HOAForecaster…")
        browser = False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hoaforecaster", description=__doc__)
    parser.add_argument("--port", type=_port, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    # the server itself, run by the launcher as a child process
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--stop-key-on-stdin", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.serve:
        key = sys.stdin.readline().strip() if args.stop_key_on_stdin else ""
        return serve(args.port, not args.no_browser, key or None)
    root = default_root()
    try:
        lock = take_over(root, args.port)
    except KeyboardInterrupt:  # Ctrl+C while the running copy stops – stop quietly
        return 0
    if lock is None:
        return 1
    with lock:
        if not port_free(args.port):  # at once, rather than after waiting for it to come free
            return _port_in_use(args.port)
        stop_key = secrets.token_urlsafe(32)
        if not record_running(root, args.port, stop_key):
            print(
                "Could not note how to stop this copy – starting the app again will not stop it.",
                file=sys.stderr,
            )
        try:
            return supervise(args.port, not args.no_browser, stop_key)
        finally:
            forget_running(root)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
