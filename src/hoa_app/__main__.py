"""Start HOAForecaster – `uv run hoaforecaster` (spec section 10.1).

One command: builds the screens with npm the first time (or after `web/` changes),
opens the projects in the data folder (HOA_DATA_DIR, or the per-user application
data folder), copies the demo project in on the very first run, and serves the app
on 127.0.0.1 only, opening it in the browser once the server is listening.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from hoa_app.api import create_app
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


def _port(text: str) -> int:
    port = int(text)
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("the port must be a number from 1024 to 65535")
    return port


def _port_in_use(port: int) -> int:
    print(
        f"Port {port} is in use – HOAForecaster may already be running. "
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


def serve(port: int, browser: bool) -> int:
    """Run one server until it stops – 0 when stopped, RESTART when the page asked for a fresh
    one. Holds the data folder's lock while it runs."""
    root = default_root()
    try:
        lock = DataFolderLock(root)
    except FolderInUse:
        print(f"HOAForecaster is already running with the data folder {root}", file=sys.stderr)
        return 1
    restarting = threading.Event()
    with lock:
        store = ProjectStore(root)
        store.seed(DEMO)
        url = f"http://{HOST}:{port}/"

        def restart() -> None:
            restarting.set()
            server.should_exit = True
            # if it has not stopped in time, end this process so it can never linger; a daemon,
            # so a clean stop does not wait for it
            deadline = threading.Timer(STOP_GRACE, os._exit, args=(RESTART,))
            deadline.daemon = True
            deadline.start()

        app = create_app(store, secrets.token_urlsafe(32), WEB_DIST, on_restart=restart)
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
    return RESTART if restarting.is_set() else 0


def supervise(port: int, browser: bool) -> int:
    """Run the server as a child process, and start a fresh one each time it exits asking to
    restart – only once the old process has ended and its port is free, rebuilding the screens
    first if they changed. The browser opens only on the first start; the page reloads itself
    after a restart. Restarting more than MAX_RESTARTS times a minute stops instead."""
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
            child = subprocess.Popen([*command, *([] if browser else ["--no-browser"])], cwd=ROOT)
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
    args = parser.parse_args(argv)
    if args.serve:
        return serve(args.port, not args.no_browser)
    if not port_free(args.port):  # at once, rather than after waiting for it to come free
        return _port_in_use(args.port)
    return supervise(args.port, not args.no_browser)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
