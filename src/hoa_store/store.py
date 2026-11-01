"""Projects on disk – one human-readable JSON file per project (spec section 8).

    <data folder>/projects/<id>.json   saved projects
    <data folder>/trash/<id>.json      deleted projects, kept until the user empties the folder
    <data folder>/backups/<id>.json    a project file as it was before its schema upgrade,
                                       moved to the trash with the project (spec 8.2)

File names come only from server-generated ids, never from user text, so no
name or upload can reach outside the data folder. Saves are atomic (write a
temporary file, then rename), serialised by a lock, and carry a revision
number, so a save based on a stale copy is refused instead of silently
overwriting newer work. Every error is a StoreError with a plain-language
message.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
import threading
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from hoa_engine.dues import rebase_dues
from hoa_engine.model import (
    MAX_ADOPTIONS,
    SCHEMA_VERSION,
    Adoption,
    Project,
    ProjectFormatError,
    current_adoption,
    project_to_dict,
    read_project,
)
from hoa_engine.validate import validate_run

ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
MAX_PROJECT_BYTES = 5 * 1024 * 1024  # a large project is well under 100 KB
APP_DIR_NAME = "HOAForecaster"


class StoreError(Exception):
    """Base class; every message is plain language, safe to show the user."""


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    pass


class BadProjectFile(StoreError):
    pass


class ReadOnly(StoreError):
    """An adopted plan cannot be changed, renamed or deleted (spec 5.2)."""


class Unusable(StoreError):
    """A scenario that cannot be worked out cannot be adopted."""


def _keeps_adopted_plans(before: Project, after: Project) -> None:
    """Refuse a save that would change an adopted plan, or adopt or un-adopt one – only
    `adopt` and `unadopt` do that (spec 5.2)."""
    kept = {s.name: s for s in after.scenarios}
    for s in before.scenarios:
        if s.adoption is not None and kept.get(s.name) != s:
            raise ReadOnly(
                f"{s.name} is an adopted plan and cannot be changed, renamed or deleted – start a "
                "new scenario from it instead"
            )
    was = {s.name for s in before.scenarios if s.adoption is not None}
    if any(s.adoption is not None and s.name not in was for s in after.scenarios):
        raise ReadOnly("a scenario is adopted with Adopt, not by saving it")


Times = dict[str, str]  # {"created": ISO 8601, "modified": ISO 8601}, UTC


@dataclass(frozen=True)
class StoredProject:
    id: str
    project: Project
    revision: int  # bumped on every save; a save must name the revision it started from
    times: Times  # the project
    scenario_times: dict[str, Times]  # by scenario name – a renamed scenario is a new one
    set_times: dict[str, Times] = field(default_factory=dict)  # by expense set name, the same
    # what the schema upgrade changed, shown until the user has read it (spec 8.2)
    upgrade_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str
    modified: str
    scenarios: int


def default_root() -> Path:
    """HOA_DATA_DIR if set, else the platform's per-user application data folder.

    HOA_DATA_DIR is the app's own data folder. It is never the private data
    repository – tests and the commit guard find that through HOA_PRIVATE_DIR.
    """
    if os.environ.get("HOA_DATA_DIR"):
        return Path(os.environ["HOA_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_DIR_NAME


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stamp(value: Any, fallback: str) -> str:
    """A stored timestamp if it is a real ISO 8601 time, else the fallback."""
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError:
            return fallback
        return value
    return fallback


def _times(value: Any, fallback: str) -> Times:
    raw = value if isinstance(value, dict) else {}
    return {
        "created": _stamp(raw.get("created"), fallback),
        "modified": _stamp(raw.get("modified"), fallback),
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)  # private to the user on POSIX
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise StoreError(
            "the project could not be written – the data folder is busy or full"
        ) from None
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_capped(path: Path, limit: int) -> bytes | None:
    """A data-folder file's bytes – None for a link, a missing file or an oversized one."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        return None
    return path.read_bytes()


def _loads(data: bytes) -> Any:
    """JSON from UTF-8 (a byte-order mark is fine), refusing NaN and Infinity."""

    def refuse(constant: str) -> None:
        raise ValueError(f"{constant} is not allowed")

    return json.loads(data.decode("utf-8-sig"), parse_constant=refuse)


def _loads_object(data: bytes | None) -> dict[str, Any] | None:
    """A JSON object, or None for anything unreadable – bad text, bad JSON, deep nesting."""
    if data is None:
        return None
    try:
        raw = _loads(data)
    except (ValueError, RecursionError):
        return None
    return raw if isinstance(raw, dict) else None


def _dump(payload: dict[str, Any]) -> bytes:
    text = json.dumps(payload, indent=1, ensure_ascii=False, allow_nan=False)
    return (text + "\n").encode("utf-8")


MAX_NOTES = 200  # sentences in an upgrade report – one per scenario at most
MAX_NOTE_TEXT = 2000


def _notes(value: Any) -> tuple[str, ...]:
    """Stored upgrade notes – anything damaged is no notes."""
    if not isinstance(value, list) or len(value) > MAX_NOTES:
        return ()
    if not all(isinstance(n, str) and len(n) <= MAX_NOTE_TEXT for n in value):
        return ()
    return tuple(value)


def _kept_times(
    before: dict[str, Any], after: list[tuple[str, Any]], old: dict[str, Times], now: str
) -> dict[str, Times]:
    """Timestamps for named things after a save – a new one is created now, a changed one
    modified now, and one name swapped for another is a rename that keeps its history."""
    names = {n for n, _ in after}
    gone = [n for n in before if n not in names]
    new = [n for n, _ in after if n not in before]
    renamed = {new[0]: gone[0]} if len(gone) == 1 and len(new) == 1 else {}
    out = {}
    for name, item in after:
        was = renamed.get(name, name)
        times = old.get(was)
        if times is None:
            out[name] = {"created": now, "modified": now}
        else:
            out[name] = {**times, "modified": now} if before[was] != item else times
    return out


def parse_project_file(data: bytes) -> tuple[Project, dict[str, Any], list[str]]:
    """A project from file bytes, the raw object it came from (for its timestamps) and, for an
    older file, what its upgrade changed."""
    if len(data) > MAX_PROJECT_BYTES:
        raise BadProjectFile("the file is larger than 5 MB – not a project file")
    try:
        raw = _loads(data)
    except (ValueError, RecursionError):  # bad UTF-8 or JSON, NaN, huge or deeply nested values
        raise BadProjectFile("the file is not a readable project file (JSON)") from None
    if not isinstance(raw, dict):
        raise BadProjectFile("the file is not a project file")
    try:
        project, notes = read_project(raw)
    except ProjectFormatError as e:
        raise BadProjectFile(str(e)) from None
    return project, raw, notes


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.projects = root / "projects"
        self.trash = root / "trash"
        self.backups = root / "backups"
        # one write at a time, so a revision check and its write cannot interleave
        self._lock = threading.RLock()

    def _path(self, folder: Path, project_id: str) -> Path:
        if not ID_PATTERN.fullmatch(project_id):
            raise NotFound("no such project")
        return folder / f"{project_id}.json"

    # ------------------------------------------------------------ reading

    def list_projects(self) -> tuple[list[ProjectSummary], list[str]]:
        """Saved projects, newest first, and the file names that are not readable projects."""
        summaries, unreadable = [], []
        if not self.projects.is_dir():
            return [], []
        for path in sorted(self.projects.glob("*.json")):
            raw = None
            if ID_PATTERN.fullmatch(path.stem):  # other names are never ours – reported, not read
                raw = _loads_object(_read_capped(path, MAX_PROJECT_BYTES))
            name = raw.get("name") if raw else None
            if not isinstance(name, str):
                unreadable.append(path.name)
                continue
            # a project file copied in by hand has no store metadata – use the file's time
            fallback = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(
                timespec="seconds"
            )
            scenarios = raw.get("scenarios") if raw else None
            summaries.append(
                ProjectSummary(
                    id=path.stem,
                    name=name,
                    modified=_times(raw.get("times") if raw else None, fallback)["modified"],
                    scenarios=len(scenarios) if isinstance(scenarios, list) else 0,
                )
            )
        summaries.sort(key=lambda s: s.modified, reverse=True)
        return summaries, unreadable

    def get(self, project_id: str) -> StoredProject:
        path = self._path(self.projects, project_id)
        if not path.is_file():
            raise NotFound("no such project")
        raw = _loads_object(_read_capped(path, MAX_PROJECT_BYTES))
        if raw is None:
            raise BadProjectFile("the saved project cannot be read – the file is damaged")
        try:
            project, notes = read_project(raw)
        except ProjectFormatError as e:
            raise BadProjectFile(f"the saved project cannot be read – {e}") from None
        revision = raw.get("revision", 1)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise BadProjectFile("the saved project cannot be read – its revision is damaged")
        unknown = _now()
        stored = raw.get("scenario_times")
        stored = stored if isinstance(stored, dict) else {}
        sets = raw.get("set_times")
        sets = sets if isinstance(sets, dict) else {}
        found = StoredProject(
            id=project_id,
            project=project,
            revision=revision,
            times=_times(raw.get("times"), unknown),
            scenario_times={s.name: _times(stored.get(s.name), unknown) for s in project.scenarios},
            set_times={e.name: _times(sets.get(e.name), unknown) for e in project.expense_sets},
            upgrade_notes=_notes(raw.get("upgrade_notes")),
        )
        if raw.get("schema_version") != SCHEMA_VERSION:
            return self._upgraded(path, found, notes)
        return found

    def _upgraded(self, path: Path, found: StoredProject, notes: list[str]) -> StoredProject:
        """An older project file, saved in today's form the first time it is opened – the
        original kept in the backups folder, and what changed kept to show (spec 8.2)."""
        with self._lock:
            backup = self._path(self.backups, found.id)
            if not backup.exists():  # the file was just read, so it can be copied as it is
                _atomic_write(backup, path.read_bytes())
            upgraded = replace(found, upgrade_notes=tuple(notes))
            self._write_stored(upgraded)
            return upgraded

    # ------------------------------------------------------------ writing

    def create(
        self,
        project: Project,
        history: dict[str, Any] | None = None,
        notes: tuple[str, ...] = (),
    ) -> StoredProject:
        """A new project. `history` carries timestamps from an exported file; missing or
        invalid ones become now. `notes` say what an upgrade of that file changed."""
        with self._lock:
            project_id = secrets.token_hex(6)
            while any(  # pragma: no cover – 1 in 2^48
                self._path(f, project_id).exists() for f in (self.projects, self.trash)
            ):
                project_id = secrets.token_hex(6)
            now = _now()
            history = history or {}
            stored = history.get("scenario_times")
            stored = stored if isinstance(stored, dict) else {}
            sets = history.get("set_times")
            sets = sets if isinstance(sets, dict) else {}
            self._write_stored(
                StoredProject(
                    id=project_id,
                    project=project,
                    revision=1,
                    times=_times(history.get("times"), now),
                    scenario_times={
                        s.name: _times(stored.get(s.name), now) for s in project.scenarios
                    },
                    set_times={e.name: _times(sets.get(e.name), now) for e in project.expense_sets},
                    upgrade_notes=notes,
                )
            )
            return self.get(project_id)

    def _current(self, project_id: str, base_revision: int) -> StoredProject:
        current = self.get(project_id)
        if current.revision != base_revision:
            raise Conflict(
                "the project was saved elsewhere since you opened it – reload to see the "
                "newer version before saving"
            )
        return current

    def save(self, project_id: str, project: Project, base_revision: int) -> StoredProject:
        """Replace a project. Refused if it was saved again since `base_revision` was read, or if
        it would change an adopted plan – those change only by adopting and un-adopting."""
        with self._lock:
            current = self._current(project_id, base_revision)
            _keeps_adopted_plans(current.project, project)
            return self._replace(current, project)

    def adopt(
        self, project_id: str, name: str, adopted_on: date, note: str, base_revision: int
    ) -> StoredProject:
        """Adopt a scenario as the board's plan (spec 5.2) – read-only, and the current adopted
        plan from now on."""
        with self._lock:
            current = self._current(project_id, base_revision)
            project = current.project
            s = next((s for s in project.scenarios if s.name == name), None)
            if s is None:
                raise NotFound("there is no scenario of that name")
            if s.adoption is not None:
                raise ReadOnly(f"{name} is already an adopted plan")
            if validate_run(project.runnable(s)):
                raise Unusable(f"{name} has problems in its inputs – fix them before adopting it")
            order = max((x.adoption.sequence for x in project.scenarios if x.adoption), default=0)
            if order >= MAX_ADOPTIONS:
                raise Unusable("the project has as many adopted plans as it can hold")
            # it keeps the project's facts and expenses as they are now, and where they came from
            adoption = Adoption(
                adopted_on,
                note,
                order + 1,
                expenses_from=project.expenses_from,
                expenses_edited=project.expenses_edited,
            )
            adopted = replace(s, facts=project.facts, adoption=adoption)
            scenarios = tuple(adopted if x is s else x for x in project.scenarios)
            return self._replace(current, replace(project, scenarios=scenarios))

    def unadopt(self, project_id: str, base_revision: int) -> StoredProject:
        """Un-adopt the current adopted plan (spec 5.2) – it is an ordinary scenario again, and
        the plan adopted before it is current."""
        with self._lock:
            current = self._current(project_id, base_revision)
            project = current.project
            plan = current_adoption(project.scenarios)
            if plan is None:
                raise NotFound("the project has no adopted plan")
            # the project's facts again, its dues carried on to their start year (spec 5)
            assert plan.facts is not None  # an adopted plan keeps its own
            back = replace(
                rebase_dues(plan, plan.facts, project.facts.start_year), facts=None, adoption=None
            )
            scenarios = tuple(back if x is plan else x for x in project.scenarios)
            return self._replace(current, replace(project, scenarios=scenarios))

    def dismiss_notes(self, project_id: str, base_revision: int) -> StoredProject:
        """The upgrade notes have been read – they are not shown again."""
        with self._lock:
            current = self._current(project_id, base_revision)
            self._write_stored(replace(current, revision=current.revision + 1, upgrade_notes=()))
            return self.get(project_id)

    def _replace(self, current: StoredProject, project: Project) -> StoredProject:
        """Write `project` over `current` – the caller holds the lock and has checked it."""
        now = _now()
        scenario_times = _kept_times(
            {s.name: s for s in current.project.scenarios},
            [(s.name, s) for s in project.scenarios],
            current.scenario_times,
            now,
        )
        set_times = _kept_times(
            {e.name: e for e in current.project.expense_sets},
            [(e.name, e) for e in project.expense_sets],
            current.set_times,
            now,
        )
        self._write_stored(
            replace(
                current,
                project=project,
                revision=current.revision + 1,
                times={**current.times, "modified": now},
                scenario_times=scenario_times,
                set_times=set_times,
            )
        )
        return self.get(current.id)

    def delete(self, project_id: str) -> None:
        """Move a project to the trash folder."""
        with self._lock:
            path = self._path(self.projects, project_id)
            if not path.is_file():
                raise NotFound("no such project")
            self.trash.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.replace(path, self._path(self.trash, project_id))
                backup = self._path(self.backups, project_id)
                if backup.is_file():  # kept until the project is deleted, then with it
                    os.replace(backup, self.trash / f"{project_id}.before-upgrade.json")
            except OSError:
                raise StoreError(
                    "the project could not be deleted – the data folder is busy"
                ) from None

    def _write_stored(self, stored: StoredProject) -> None:
        payload = {
            **project_to_dict(stored.project),
            "id": stored.id,
            "revision": stored.revision,
            "times": stored.times,
            "scenario_times": stored.scenario_times,
            "set_times": stored.set_times,
            "upgrade_notes": list(stored.upgrade_notes),
        }
        data = _dump(payload)
        if len(data) > MAX_PROJECT_BYTES:  # it could never be opened again
            raise BadProjectFile(
                "the project would be larger than 5 MB – too large to save; remove some "
                "scenarios or expense lines first"
            )
        _atomic_write(self._path(self.projects, stored.id), data)

    # ------------------------------------------------------------ export and import

    def export_bytes(self, project_id: str) -> bytes:
        """The project as a portable file – what "Export project" downloads. It keeps the
        project's history (timestamps) but not its id or revision, which belong to this
        data folder."""
        stored = self.get(project_id)
        return _dump(
            {
                **project_to_dict(stored.project),
                "times": stored.times,
                "scenario_times": stored.scenario_times,
                "set_times": stored.set_times,
            }
        )

    def import_bytes(self, data: bytes) -> StoredProject:
        """A new project from a project file, keeping its valid timestamps. The file's own id
        is never used."""
        project, raw, notes = parse_project_file(data)
        return self.create(project, history=raw, notes=tuple(notes))

    # ------------------------------------------------------------ first run

    def seed(self, demo_file: Path) -> StoredProject | None:
        """Copy the demo project in on the very first run – once the projects folder exists,
        never again, so a user who deletes the demo does not get it back."""
        if self.projects.exists() or not demo_file.is_file():
            return None
        return self.import_bytes(demo_file.read_bytes())
