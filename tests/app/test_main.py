"""Starting the app – `uv run hoaforecaster` – and its one-app-per-data-folder lock."""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hoa_app import __main__ as launcher
from hoa_app.lock import DataFolderLock, FolderInUse
from hoa_store.store import ProjectStore


def test_one_app_per_data_folder(tmp_path: Path) -> None:
    with DataFolderLock(tmp_path), pytest.raises(FolderInUse):
        DataFolderLock(tmp_path)
    again = DataFolderLock(tmp_path)  # released on exit
    again.release()
    again.release()  # releasing twice is harmless


# ---------------------------------------------------------------- building the screens


@pytest.fixture
def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "web"
    (root / "src").mkdir(parents=True)
    (root / "package.json").write_text("{}", encoding="utf-8")
    (root / "src" / "main.tsx").write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher, "WEB", root)
    monkeypatch.setattr(launcher, "WEB_DIST", root / "dist")
    return root


def _build(dist: Path) -> None:
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")


def test_an_up_to_date_build_is_used_as_is(web: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _build(web / "dist")
    future = time.time() + 60
    os.utime(web / "dist" / "index.html", (future, future))
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("built again"))
    assert launcher.ensure_built()


def test_a_missing_or_stale_build_is_made_with_npm(
    web: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    steps: list[list[str]] = []

    class Done:
        returncode = 0

    def run(cmd: list[str], cwd: Path, check: bool) -> Done:
        steps.append(cmd[1:])
        if cmd[1:] == ["run", "build"]:
            _build(web / "dist")
        return Done()

    monkeypatch.setattr(launcher.shutil, "which", lambda _: "npm")
    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.ensure_built()
    assert steps == [["ci", "--no-audit", "--no-fund"], ["run", "build"]]

    (web / "node_modules").mkdir()  # installed already – only rebuild
    past = time.time() - 60
    os.utime(web / "dist" / "index.html", (past, past))
    steps.clear()
    assert launcher.ensure_built()
    assert steps == [["run", "build"]]


def test_a_failed_build_is_reported(
    web: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Failed:
        returncode = 1

    monkeypatch.setattr(launcher.shutil, "which", lambda _: "npm")
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: Failed())
    assert not launcher.ensure_built()
    assert "npm ci" in capsys.readouterr().err


def test_without_npm_it_says_what_to_install(
    web: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(launcher.shutil, "which", lambda _: None)
    assert not launcher.ensure_built()
    assert "Install Node.js" in capsys.readouterr().err
    assert launcher.main(["--no-browser"]) == 1


# ---------------------------------------------------------------- starting


class FakeServer:
    started = False
    ran = False

    def __init__(self, config: Any) -> None:
        self.config = config
        FakeServer.instance = self  # type: ignore[attr-defined]

    def run(self) -> None:
        FakeServer.ran = True


@pytest.fixture
def started(web: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    _build(web / "dist")
    future = time.time() + 60
    os.utime(web / "dist" / "index.html", (future, future))
    monkeypatch.setenv("HOA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(launcher.uvicorn, "Server", FakeServer)
    opened: list[str] = []
    monkeypatch.setattr(
        launcher.threading,
        "Thread",
        lambda target, args, daemon: _Now(lambda: opened.append(args[1])),
    )
    yield opened


class _Now:
    def __init__(self, action: Any) -> None:
        self.action = action

    def start(self) -> None:
        self.action()


def test_the_app_starts_on_this_computer_only_and_seeds_the_demo(
    started: list[str], tmp_path: Path
) -> None:
    assert launcher.main(["--port", "9999"]) == 0
    config = FakeServer.instance.config  # type: ignore[attr-defined]
    assert (config.host, config.port) == ("127.0.0.1", 9999)
    assert FakeServer.ran and started == ["http://127.0.0.1:9999/"]
    summaries, _ = ProjectStore(tmp_path / "data").list_projects()
    assert [s.name for s in summaries] == ["Maple Row Condominiums (fictional demo)"]


def test_no_browser_when_asked(started: list[str]) -> None:
    assert launcher.main(["--no-browser"]) == 0
    assert started == []


def test_a_second_app_on_the_same_data_folder_is_refused(
    started: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with DataFolderLock(tmp_path / "data"):
        assert launcher.main(["--no-browser"]) == 1
    assert "already running" in capsys.readouterr().err


def test_a_busy_port_is_reported_before_anything_starts(
    started: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert not launcher.port_free(port)
        assert launcher.main(["--port", str(port)]) == 1
    assert "is in use" in capsys.readouterr().err


def test_the_browser_opens_only_once_the_server_listens(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)

    class Server:
        started = True

    launcher.open_when_ready(Server(), "http://127.0.0.1:1/")  # type: ignore[arg-type]
    Server.started = False
    launcher.open_when_ready(Server(), "http://127.0.0.1:2/", timeout=0.2)  # type: ignore[arg-type]
    assert opened == ["http://127.0.0.1:1/"]
