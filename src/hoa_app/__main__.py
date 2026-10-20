"""Start HOAForecaster – `uv run hoaforecaster` (spec section 10.1).

One command: builds the screens with npm the first time (or after `web/` changes),
opens the projects in the data folder (HOA_DATA_DIR, or the per-user application
data folder), copies the demo project in on the very first run, and serves the app
on 127.0.0.1 only, opening it in the browser once the server is listening.
"""

from __future__ import annotations

import argparse
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
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hoaforecaster", description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)

    if not ensure_built():
        return 1
    if not port_free(args.port):
        print(
            f"Port {args.port} is in use – HOAForecaster may already be running. "
            f"Open http://{HOST}:{args.port}/ or start with --port and another number.",
            file=sys.stderr,
        )
        return 1

    root = default_root()
    try:
        lock = DataFolderLock(root)
    except FolderInUse:
        print(f"HOAForecaster is already running with the data folder {root}", file=sys.stderr)
        return 1
    with lock:
        store = ProjectStore(root)
        store.seed(DEMO)
        app = create_app(store, secrets.token_urlsafe(32), WEB_DIST)
        url = f"http://{HOST}:{args.port}/"
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=args.port, log_level="warning"))
        print(f"HOAForecaster – {url}  (data folder {root}; press Ctrl+C to stop)")
        if not args.no_browser:
            threading.Thread(target=open_when_ready, args=(server, url), daemon=True).start()
        server.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
