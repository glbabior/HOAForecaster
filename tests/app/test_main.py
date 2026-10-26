"""Starting the app – `uv run hoaforecaster` – and its one-app-per-data-folder lock."""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from hoa_app import __main__ as launcher
from hoa_app.api import TOKEN_HEADER
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
    assert launcher.main(["--serve", "--port", "9999"]) == 0
    config = FakeServer.instance.config  # type: ignore[attr-defined]
    assert (config.host, config.port) == ("127.0.0.1", 9999)
    assert FakeServer.ran and started == ["http://127.0.0.1:9999/"]
    summaries, _ = ProjectStore(tmp_path / "data").list_projects()
    assert [s.name for s in summaries] == ["Maple Row Condominiums (fictional demo)"]


def test_no_browser_when_asked(started: list[str]) -> None:
    assert launcher.main(["--serve", "--no-browser"]) == 0
    assert started == []


def test_a_second_app_on_the_same_data_folder_is_refused(
    started: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with DataFolderLock(tmp_path / "data"):
        assert launcher.main(["--serve", "--no-browser"]) == 1
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


# ---------------------------------------------------------------- restarting


class FakeChild:
    """A server process that exits with each code in turn."""

    codes: ClassVar[list[int]] = []
    commands: ClassVar[list[list[str]]] = []

    def __init__(self, command: list[str], cwd: Path | None = None) -> None:
        assert cwd == launcher.ROOT  # never the folder it was started from
        FakeChild.commands.append(command)

    def wait(self) -> int:
        return FakeChild.codes.pop(0)

    def poll(self) -> int | None:
        return None  # still running


@pytest.fixture
def children(web: Path, monkeypatch: pytest.MonkeyPatch) -> type[FakeChild]:
    _build(web / "dist")
    future = time.time() + 60
    os.utime(web / "dist" / "index.html", (future, future))
    FakeChild.codes, FakeChild.commands = [], []
    monkeypatch.setattr(launcher.subprocess, "Popen", FakeChild)
    return FakeChild


def test_the_launcher_starts_a_fresh_server_each_time_one_asks_to_restart(
    children: type[FakeChild], monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[bool] = []
    monkeypatch.setattr(launcher, "ensure_built", lambda: built.append(True) or True)
    children.codes = [launcher.RESTART, launcher.RESTART, 0]
    assert launcher.main(["--port", "9998"]) == 0
    assert len(children.commands) == 3 and len(built) == 3  # rebuilt before every start
    first, *later = children.commands
    assert first[-3:] == ["--serve", "--port", "9998"]  # the first opens the browser
    assert all(c[-1] == "--no-browser" for c in later)  # later ones: the page reloads itself


def test_a_server_that_fails_ends_the_launcher_with_its_code(children: type[FakeChild]) -> None:
    children.codes = [1]
    assert launcher.main(["--port", "9996", "--no-browser"]) == 1


def test_a_restart_waits_for_the_old_servers_port_to_come_free(
    children: type[FakeChild], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    children.codes = [launcher.RESTART]
    free = iter([True, True, False])  # free at the start, then held by someone else
    monkeypatch.setattr(launcher, "port_free", lambda _: next(free, False))
    monkeypatch.setattr(launcher, "FREE_WAIT", 0.3)
    assert launcher.main(["--port", "9996", "--no-browser"]) == 1
    assert len(children.commands) == 1  # never a second server beside the first
    assert "is in use" in capsys.readouterr().err


def test_a_port_that_comes_free_in_time_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    free = iter([False, False, True])
    monkeypatch.setattr(launcher, "port_free", lambda _: next(free))
    assert launcher.wait_port_free(1, timeout=5)


def test_ctrl_c_lets_the_server_stop_and_then_stops(
    children: type[FakeChild], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Interrupted(FakeChild):
        waits = 0

        def wait(self) -> int:
            Interrupted.waits += 1
            if Interrupted.waits == 1:
                raise KeyboardInterrupt
            return 0

    monkeypatch.setattr(launcher.subprocess, "Popen", Interrupted)
    assert launcher.main(["--port", "9996", "--no-browser"]) == 0
    assert Interrupted.waits == 2  # it waited for the server to end


def test_a_server_asked_to_restart_stops_and_says_so(
    started: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    timers: list[float] = []

    class Deadline:  # the real one would end this test run after STOP_GRACE seconds
        daemon = False

        def __init__(self, seconds: float, *_: Any, **__: Any) -> None:
            timers.append(seconds)

        def start(self) -> None:
            assert self.daemon  # a clean stop must not wait for it

    class Restarting(FakeServer):
        should_exit = False

        def run(self) -> None:
            client = TestClient(self.config.app, base_url="http://127.0.0.1")
            answer = client.post("/api/restart", headers={TOKEN_HEADER: "t"})
            assert answer.status_code == 202
            assert self.should_exit  # the page's request stops this server

    monkeypatch.setattr(launcher.secrets, "token_urlsafe", lambda _: "t")
    monkeypatch.setattr(launcher.threading, "Timer", Deadline)
    monkeypatch.setattr(launcher.uvicorn, "Server", Restarting)
    assert launcher.main(["--serve", "--no-browser"]) == launcher.RESTART
    assert timers == [launcher.STOP_GRACE]


def test_the_server_runs_only_the_apps_own_code(children: type[FakeChild]) -> None:
    children.codes = [0]
    assert launcher.main(["--port", "9996", "--no-browser"]) == 0
    assert children.commands[0][1:4] == ["-P", "-m", "hoa_app"]  # nothing from the start folder


def test_a_restart_loop_is_stopped(
    children: type[FakeChild], capsys: pytest.CaptureFixture[str]
) -> None:
    children.codes = [launcher.RESTART] * (launcher.MAX_RESTARTS + 1)
    assert launcher.main(["--port", "9996", "--no-browser"]) == 1
    assert len(children.commands) == launcher.MAX_RESTARTS + 1
    assert "more than 5 times in a minute" in capsys.readouterr().err


@pytest.mark.parametrize("port", ["80", "70000", "nine"])
def test_a_port_out_of_range_is_refused_plainly(port: str) -> None:
    with pytest.raises(SystemExit):
        launcher.main(["--port", port])


def test_a_failed_rebuild_before_a_restart_stops_the_launcher(
    children: type[FakeChild], monkeypatch: pytest.MonkeyPatch
) -> None:
    builds = iter([True, False])
    monkeypatch.setattr(launcher, "ensure_built", lambda: next(builds))
    children.codes = [launcher.RESTART]
    assert launcher.main(["--port", "9996", "--no-browser"]) == 1
    assert len(children.commands) == 1


def test_ctrl_c_between_servers_stops_quietly(
    children: type[FakeChild], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted() -> bool:
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher, "ensure_built", interrupted)
    assert launcher.main(["--port", "9996", "--no-browser"]) == 0
    assert children.commands == []


def test_ctrl_c_stops_a_server_without_a_traceback(
    started: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Interrupted(FakeServer):
        def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(launcher.uvicorn, "Server", Interrupted)
    assert launcher.main(["--serve", "--no-browser"]) == 0
