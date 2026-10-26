"""Starting the app – `uv run hoaforecaster` – and its one-app-per-data-folder lock."""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from hoa_app import __main__ as launcher
from hoa_app.api import STOP_HEADER, TOKEN_HEADER
from hoa_app.lock import DataFolderLock, FolderInUse
from hoa_store.store import ProjectStore


@pytest.fixture(autouse=True)
def scratch_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test here on its own data folder – never the real app's, which a launch would stop."""
    monkeypatch.setenv("HOA_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


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
    should_exit = False

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


class _Pipe:
    """A server's stdin – what the launcher hands it."""

    handed: ClassVar[list[bytes]] = []

    def write(self, data: bytes) -> None:
        _Pipe.handed.append(data)

    def close(self) -> None:
        pass


class FakeChild:
    """A server process that exits with each code in turn."""

    codes: ClassVar[list[int]] = []
    commands: ClassVar[list[list[str]]] = []

    def __init__(self, command: list[str], cwd: Path | None = None, stdin: Any = None) -> None:
        assert cwd == launcher.ROOT  # never the folder it was started from
        FakeChild.commands.append(command)
        self.stdin = _Pipe() if stdin is not None else None

    def wait(self) -> int:
        return FakeChild.codes.pop(0)

    def poll(self) -> int | None:
        return None  # still running


@pytest.fixture
def children(web: Path, monkeypatch: pytest.MonkeyPatch) -> type[FakeChild]:
    _build(web / "dist")
    future = time.time() + 60
    os.utime(web / "dist" / "index.html", (future, future))
    FakeChild.codes, FakeChild.commands, _Pipe.handed = [], [], []
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
    assert first[-4:] == ["--serve", "--port", "9998", "--stop-key-on-stdin"]  # with a browser
    assert all("--no-browser" in c for c in later)  # later ones: the page reloads itself


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


# ---------------------------------------------------------------- launching again


def _held(root: Path) -> DataFolderLock:
    """The running copy's launcher – it holds its lock for as long as it runs."""
    return DataFolderLock(root, launcher.LAUNCHER_LOCK)


def _record(root: Path, port: int = 9995, key: str = "k") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / launcher.RUNNING).write_text(
        json.dumps({"pid": 1, "port": port, "stop_key": key}), encoding="utf-8"
    )


def test_the_launcher_records_how_to_stop_it_and_hands_its_server_the_key(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    class Looking(FakeChild):
        def wait(self) -> int:
            seen.append(launcher.read_running(scratch_data))
            seen.append(launcher._launcher_lock(scratch_data))  # held while it runs
            return 0

    monkeypatch.setattr(launcher.secrets, "token_urlsafe", lambda _: "k")
    monkeypatch.setattr(launcher.subprocess, "Popen", Looking)
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert seen == [(9995, "k"), None]
    assert children.commands[0][-1] == "--stop-key-on-stdin"  # never the key itself
    assert "k" not in children.commands[0]
    assert _Pipe.handed == [b"k\n"]
    assert launcher.read_running(scratch_data) is None  # forgotten when it ends
    _held(scratch_data).release()  # and its lock let go


def test_a_server_reads_its_stop_key_and_stops_for_good_with_it(
    started: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Stopped(FakeServer):
        def run(self) -> None:
            client = TestClient(self.config.app, base_url="http://127.0.0.1")
            assert client.post("/api/stop", headers={STOP_HEADER: "k"}).status_code == 202
            assert self.should_exit

    monkeypatch.setattr(launcher.sys, "stdin", io.StringIO("k\n"))
    monkeypatch.setattr(launcher.threading, "Timer", _Deadline)
    monkeypatch.setattr(launcher.uvicorn, "Server", Stopped)
    assert launcher.main(["--serve", "--no-browser", "--stop-key-on-stdin"]) == 0
    assert "started again" in capsys.readouterr().out


def test_stopping_for_good_wins_over_a_restart_asked_at_the_same_moment(
    started: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Both(FakeServer):
        def run(self) -> None:
            client = TestClient(self.config.app, base_url="http://127.0.0.1")
            assert client.post("/api/restart", headers={TOKEN_HEADER: "k"}).status_code == 202
            assert client.post("/api/stop", headers={STOP_HEADER: "k"}).status_code == 202

    monkeypatch.setattr(launcher.secrets, "token_urlsafe", lambda _: "k")
    monkeypatch.setattr(launcher.sys, "stdin", io.StringIO("k\n"))
    monkeypatch.setattr(launcher.threading, "Timer", _Deadline)
    monkeypatch.setattr(launcher.uvicorn, "Server", Both)
    assert launcher.main(["--serve", "--no-browser", "--stop-key-on-stdin"]) == 0


def test_a_server_without_a_key_cannot_be_stopped_from_outside(
    started: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Unstoppable(FakeServer):
        def run(self) -> None:
            client = TestClient(self.config.app, base_url="http://127.0.0.1")
            assert client.post("/api/stop", headers={STOP_HEADER: ""}).status_code == 403

    monkeypatch.setattr(launcher.uvicorn, "Server", Unstoppable)
    assert launcher.main(["--serve", "--no-browser"]) == 0


class _Deadline:  # the real one would end this test run after STOP_GRACE seconds
    daemon = False

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def start(self) -> None:
        assert self.daemon


def test_a_relaunch_stops_the_running_copy_first_and_carries_on(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _held(scratch_data)
    _record(scratch_data)
    asked: list[tuple[int, str]] = []

    def stop(port: int, key: str) -> bool:
        asked.append((port, key))
        old.release()  # it stops, and its launcher ends
        return True

    monkeypatch.setattr(launcher, "ask_to_stop", stop)
    children.codes = [0]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert asked == [(9995, "k")]
    assert len(children.commands) == 1  # then this launch started its own server


def test_a_copy_still_building_is_asked_again_until_its_server_is_up(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _held(scratch_data)
    _record(scratch_data)
    answers = iter([False, False, True])  # nothing listening yet, then its server agrees

    def stop(port: int, key: str) -> bool:
        agreed = next(answers)
        if agreed:
            old.release()
        return agreed

    monkeypatch.setattr(launcher, "ask_to_stop", stop)
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    children.codes = [0]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert len(children.commands) == 1


def test_a_copy_that_ends_by_itself_while_asked_is_not_waited_for(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _held(scratch_data)  # no record yet – its launcher is still starting

    def gone(_: float) -> None:
        old.release()

    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: pytest.fail("no record"))
    monkeypatch.setattr(launcher.time, "sleep", gone)
    children.codes = [0]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0


def test_a_copy_that_cannot_be_reached_is_left_alone_and_said_so(
    children: type[FakeChild],
    scratch_data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _record(scratch_data)
    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: False)
    monkeypatch.setattr(launcher, "REACH_WAIT", 0.0)
    with _held(scratch_data):
        assert launcher.main(["--port", "9995", "--no-browser"]) == 1
    assert "could not be stopped" in capsys.readouterr().err
    assert children.commands == []  # never a second copy beside it


def test_a_copy_that_agrees_but_never_ends_is_not_waited_for_forever(
    children: type[FakeChild],
    scratch_data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _record(scratch_data)
    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: True)
    monkeypatch.setattr(launcher, "TAKEOVER_WAIT", 0.3)
    with _held(scratch_data):
        assert launcher.main(["--port", "9995", "--no-browser"]) == 1
    assert "did not stop" in capsys.readouterr().err
    assert children.commands == []


def test_a_stopped_copy_whose_port_stays_busy_is_reported(
    children: type[FakeChild],
    scratch_data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old = _held(scratch_data)
    _record(scratch_data)
    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: old.release() or True)
    monkeypatch.setattr(launcher, "port_free", lambda _: False)
    monkeypatch.setattr(launcher, "TAKEOVER_WAIT", 0.3)
    assert launcher.main(["--port", "9995", "--no-browser"]) == 1
    assert "is still in use" in capsys.readouterr().err
    _held(scratch_data).release()  # this launch let its lock go


def test_ctrl_c_while_the_running_copy_stops_ends_quietly(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: False)
    monkeypatch.setattr(launcher.time, "sleep", interrupted)
    with _held(scratch_data):
        assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert children.commands == []


def test_a_record_left_by_a_copy_that_has_gone_is_replaced(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(scratch_data, key="old")
    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: pytest.fail("nothing to stop"))
    children.codes = [0]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert launcher.read_running(scratch_data) is None


def test_the_app_still_starts_when_its_record_cannot_be_written(
    children: type[FakeChild],
    scratch_data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(launcher, "record_running", lambda *_: False)
    children.codes = [0]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert "will not stop it" in capsys.readouterr().err


def test_a_record_held_open_elsewhere_is_retried_then_given_up(
    scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch_data.mkdir(parents=True)
    tries: list[int] = []

    def busy(*_: Any) -> None:
        tries.append(1)
        raise PermissionError

    monkeypatch.setattr(launcher.os, "replace", busy)
    monkeypatch.setattr(launcher.time, "sleep", lambda _: None)
    assert not launcher.record_running(scratch_data, 9995, "k")
    assert len(tries) == 20
    assert list(scratch_data.iterdir()) == []  # its part-written file is gone


def test_a_record_that_cannot_be_written_at_all_is_reported(tmp_path: Path) -> None:
    assert not launcher.record_running(tmp_path / "missing", 9995, "k")


def test_a_record_is_never_written_through_a_planted_file(scratch_data: Path) -> None:
    scratch_data.mkdir(parents=True)
    planted = scratch_data / f"{launcher.RUNNING}.{os.getpid()}.tmp"
    planted.write_text("someone else's", encoding="utf-8")
    assert launcher.record_running(scratch_data, 9995, "k")
    assert launcher.read_running(scratch_data) == (9995, "k")


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        "[" * 100_000,  # nested to no end
        json.dumps({"port": 9995, "stop_key": "k" * launcher.RECORD_LIMIT}),  # too long
        '{"port": 80, "stop_key": "k"}',
        '{"port": "9995", "stop_key": "k"}',
        '{"port": true, "stop_key": "k"}',
        '{"port": 9995, "stop_key": ""}',
        '{"port": 9995}',
    ],
    ids=[
        "text",
        "list",
        "nested",
        "long",
        "low-port",
        "port-text",
        "port-bool",
        "no-key",
        "keyless",
    ],
)
def test_a_damaged_record_is_never_trusted(scratch_data: Path, text: str) -> None:
    scratch_data.mkdir(parents=True)
    (scratch_data / launcher.RUNNING).write_text(text, encoding="utf-8")
    assert launcher.read_running(scratch_data) is None
    launcher.forget_running(scratch_data)  # nor removed – it is not this process's
    assert (scratch_data / launcher.RUNNING).exists()


def test_a_launcher_never_removes_a_newer_launchers_record(scratch_data: Path) -> None:
    _record(scratch_data)  # pid 1 – not this process
    launcher.forget_running(scratch_data)
    assert launcher.read_running(scratch_data) == (9995, "k")
    launcher.forget_running(scratch_data / "nowhere")  # nothing there – nothing to do


def test_asking_a_server_to_stop_posts_its_key_to_this_computer_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[Any] = []

    class Answer:
        status = 202

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def urlopen(request: Any, timeout: float) -> Answer:
        sent.append((request.full_url, request.get_method(), request.get_header("X-hoa-stop")))
        return Answer()

    monkeypatch.setattr(launcher._direct, "open", urlopen)
    assert launcher.ask_to_stop(9995, "k")
    assert sent == [("http://127.0.0.1:9995/api/stop", "POST", "k")]


def test_a_proxy_set_for_the_web_never_sees_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy, _ = _answering(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
    server, _ = _answering(b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n")
    with proxy, server:
        for name in ("http_proxy", "HTTP_PROXY"):
            monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.getsockname()[1]}")
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.delenv("NO_PROXY", raising=False)
        assert launcher.ask_to_stop(server.getsockname()[1], "k")  # straight there


def _answering(reply: bytes) -> tuple[socket.socket, threading.Thread]:
    """A listener on a spare port that answers every connection with `reply`."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()

    def answer() -> None:
        with contextlib.suppress(OSError):
            while True:
                conn, _ = listener.accept()
                with conn:
                    conn.recv(65536)
                    conn.sendall(reply)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    return listener, thread


def test_an_answer_pointing_elsewhere_never_takes_the_key_with_it() -> None:
    elsewhere, _ = _answering(b"HTTP/1.1 202 Accepted\r\nContent-Length: 0\r\n\r\n")
    target = elsewhere.getsockname()[1]
    redirect = (
        f"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1:{target}/x\r\nContent-Length: 0\r\n\r\n"
    ).encode()
    listener, _ = _answering(redirect)
    with listener, elsewhere:
        assert not launcher.ask_to_stop(listener.getsockname()[1], "k")


def test_an_answer_that_is_not_http_is_a_refusal() -> None:
    listener, _ = _answering(b"\x00 not http at all\r\n\r\n")
    with listener:
        assert not launcher.ask_to_stop(listener.getsockname()[1], "k")


def test_asking_a_server_that_is_not_there_fails_quietly() -> None:
    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert not launcher.ask_to_stop(port, "k")


@pytest.mark.parametrize(("stop", "code"), [(False, launcher.RESTART), (True, 0)])
def test_a_server_that_will_not_stop_ends_itself_with_what_was_asked_last(
    started: list[str], monkeypatch: pytest.MonkeyPatch, stop: bool, code: int
) -> None:
    timers: list[Any] = []

    class Deadline:
        daemon = False

        def __init__(self, seconds: float, action: Any) -> None:
            timers.append(action)

        def start(self) -> None:
            pass

    class Asked(FakeServer):
        def run(self) -> None:
            client = TestClient(self.config.app, base_url="http://127.0.0.1")
            client.post("/api/restart", headers={TOKEN_HEADER: "k"})
            if stop:  # a new launch's stop, after the page's restart
                client.post("/api/stop", headers={STOP_HEADER: "k"})

    ended: list[int] = []
    monkeypatch.setattr(launcher.secrets, "token_urlsafe", lambda _: "k")
    monkeypatch.setattr(launcher.sys, "stdin", io.StringIO("k\n"))
    monkeypatch.setattr(launcher.threading, "Timer", Deadline)
    monkeypatch.setattr(launcher.os, "_exit", ended.append)
    monkeypatch.setattr(launcher.uvicorn, "Server", Asked)
    launcher.main(["--serve", "--no-browser", "--stop-key-on-stdin"])
    timers[0]()  # the first deadline fires – after both were asked
    assert ended == [code]


def test_a_server_that_ends_before_reading_its_key_is_reported_by_its_own_code(
    children: type[FakeChild], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Closed(_Pipe):
        def write(self, data: bytes) -> None:
            raise BrokenPipeError

    class EndedAtOnce(FakeChild):
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            self.stdin = Closed()

    monkeypatch.setattr(launcher.subprocess, "Popen", EndedAtOnce)
    children.codes = [1]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 1


def test_a_copy_that_ended_by_itself_has_its_port_waited_for(
    children: type[FakeChild], scratch_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _held(scratch_data)
    waited: list[int] = []
    monkeypatch.setattr(launcher, "ask_to_stop", lambda port, key: False)
    monkeypatch.setattr(launcher.time, "sleep", lambda _: old.release())
    monkeypatch.setattr(launcher, "wait_port_free", lambda port, *_: waited.append(port) or True)
    children.codes = [0]
    assert launcher.main(["--port", "9995", "--no-browser"]) == 0
    assert waited[0] == 9995
