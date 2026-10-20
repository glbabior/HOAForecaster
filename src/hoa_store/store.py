"""Projects on disk – one human-readable JSON file per project (spec section 8).

    <data folder>/projects/<id>.json   saved projects
    <data folder>/drafts/<id>.json     autosaved unsaved edits per screen, restored after a crash
    <data folder>/trash/<id>.json      deleted projects, kept until the user empties the folder

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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hoa_engine.model import Project, ProjectFormatError, project_from_dict, project_to_dict

ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
SCREEN_PATTERN = re.compile(r"^(baseline|new-scenario|scenario:[^\x00-\x1f\x7f]{1,200})$")
MAX_PROJECT_BYTES = 5 * 1024 * 1024  # a large project is well under 100 KB
MAX_DRAFT_BYTES = MAX_PROJECT_BYTES
APP_DIR_NAME = "HOAForecaster"


class StoreError(Exception):
    """Base class; every message is plain language, safe to show the user."""


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    pass


class BadProjectFile(StoreError):
    pass


Times = dict[str, str]  # {"created": ISO 8601, "modified": ISO 8601}, UTC


@dataclass(frozen=True)
class StoredProject:
    id: str
    project: Project
    revision: int  # bumped on every save; a save must name the revision it started from
    times: Times  # the project
    baseline_times: Times
    scenario_times: dict[str, Times]  # by scenario name – a renamed scenario is a new one


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str
    modified: str
    scenarios: int


@dataclass(frozen=True)
class Draft:
    saved: str
    base_revision: int  # the revision the edits started from
    edits: dict[str, Any]


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


def parse_project_file(data: bytes) -> tuple[Project, dict[str, Any]]:
    """A project from file bytes and the raw object it came from (for its timestamps)."""
    if len(data) > MAX_PROJECT_BYTES:
        raise BadProjectFile("the file is larger than 5 MB – not a project file")
    try:
        raw = _loads(data)
    except (ValueError, RecursionError):  # bad UTF-8 or JSON, NaN, huge or deeply nested values
        raise BadProjectFile("the file is not a readable project file (JSON)") from None
    if not isinstance(raw, dict):
        raise BadProjectFile("the file is not a project file")
    try:
        return project_from_dict(raw), raw
    except ProjectFormatError as e:
        raise BadProjectFile(str(e)) from None


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.projects = root / "projects"
        self.drafts = root / "drafts"
        self.trash = root / "trash"
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
            project = project_from_dict(raw)
        except ProjectFormatError as e:
            raise BadProjectFile(f"the saved project cannot be read – {e}") from None
        revision = raw.get("revision", 1)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise BadProjectFile("the saved project cannot be read – its revision is damaged")
        unknown = _now()
        stored = raw.get("scenario_times")
        stored = stored if isinstance(stored, dict) else {}
        return StoredProject(
            id=project_id,
            project=project,
            revision=revision,
            times=_times(raw.get("times"), unknown),
            baseline_times=_times(raw.get("baseline_times"), unknown),
            scenario_times={s.name: _times(stored.get(s.name), unknown) for s in project.scenarios},
        )

    # ------------------------------------------------------------ writing

    def create(self, project: Project, history: dict[str, Any] | None = None) -> StoredProject:
        """A new project. `history` carries timestamps from an exported file; missing or
        invalid ones become now."""
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
            self._write(
                project_id,
                project,
                revision=1,
                times=_times(history.get("times"), now),
                baseline_times=_times(history.get("baseline_times"), now),
                scenario_times={s.name: _times(stored.get(s.name), now) for s in project.scenarios},
            )
            return self.get(project_id)

    def save(self, project_id: str, project: Project, base_revision: int) -> StoredProject:
        """Replace a project. Refused if it was saved again since `base_revision` was read."""
        with self._lock:
            current = self.get(project_id)
            if current.revision != base_revision:
                raise Conflict(
                    "the project was saved elsewhere since you opened it – reload to see the "
                    "newer version before saving"
                )
            now = _now()
            before = {s.name: s for s in current.project.scenarios}
            scenario_times = {}
            for s in project.scenarios:
                old = current.scenario_times.get(s.name)
                if old is None:  # new, or renamed – a rename starts a new history
                    scenario_times[s.name] = {"created": now, "modified": now}
                else:
                    changed = before[s.name] != s
                    scenario_times[s.name] = {**old, "modified": now} if changed else old
            baseline_times = current.baseline_times
            if current.project.baseline != project.baseline:
                baseline_times = {**baseline_times, "modified": now}
            self._write(
                project_id,
                project,
                revision=current.revision + 1,
                times={**current.times, "modified": now},
                baseline_times=baseline_times,
                scenario_times=scenario_times,
            )
            # other screens' drafts stay; they now show as begun before this save
            return self.get(project_id)

    def delete(self, project_id: str) -> None:
        """Move a project to the trash folder; its draft is discarded."""
        with self._lock:
            path = self._path(self.projects, project_id)
            if not path.is_file():
                raise NotFound("no such project")
            self.trash.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.replace(path, self._path(self.trash, project_id))
            except OSError:
                raise StoreError(
                    "the project could not be deleted – the data folder is busy"
                ) from None
            self.discard_draft(project_id)

    def _write(
        self,
        project_id: str,
        project: Project,
        *,
        revision: int,
        times: Times,
        baseline_times: Times,
        scenario_times: dict[str, Times],
    ) -> None:
        payload = {
            **project_to_dict(project),
            "id": project_id,
            "revision": revision,
            "times": times,
            "baseline_times": baseline_times,
            "scenario_times": scenario_times,
        }
        _atomic_write(self._path(self.projects, project_id), _dump(payload))

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
                "baseline_times": stored.baseline_times,
                "scenario_times": stored.scenario_times,
            }
        )

    def import_bytes(self, data: bytes) -> StoredProject:
        """A new project from a project file, keeping its valid timestamps. The file's own id
        is never used."""
        project, raw = parse_project_file(data)
        return self.create(project, history=raw)

    # ------------------------------------------------------------ drafts

    # One file per project holding one draft per screen – "baseline", or "scenario:<name>" –
    # so editing one screen never overwrites another screen's unsaved edits.

    def _read_drafts(self, project_id: str) -> dict[str, Any]:
        raw = _loads_object(_read_capped(self._path(self.drafts, project_id), MAX_DRAFT_BYTES))
        screens = raw.get("screens") if raw else None
        return screens if isinstance(screens, dict) else {}

    def _write_drafts(self, project_id: str, screens: dict[str, Any]) -> None:
        if not screens:
            self._path(self.drafts, project_id).unlink(missing_ok=True)
            return
        try:
            data = _dump({"screens": screens})
        except (ValueError, TypeError, RecursionError):
            raise BadProjectFile("the draft cannot be stored – not saved") from None
        if len(data) > MAX_DRAFT_BYTES:
            raise BadProjectFile("the draft is larger than 5 MB – not saved")
        _atomic_write(self._path(self.drafts, project_id), data)

    def save_draft(
        self, project_id: str, screen: str, edits: dict[str, Any], base_revision: int
    ) -> None:
        """Autosave of one screen's unsaved edits – any JSON object, even one not yet valid.

        Refused when the project was saved since the edits began, so a late autosave can
        never resurrect edits that a save already superseded."""
        if not isinstance(edits, dict):
            raise BadProjectFile("a draft must be a set of edits – not saved")
        if not SCREEN_PATTERN.fullmatch(screen):
            raise BadProjectFile("a draft must name its screen – not saved")
        with self._lock:
            current = self.get(project_id)  # a draft belongs to an existing project
            if base_revision != current.revision:
                raise Conflict("the project was saved since these edits began – reload first")
            screens = self._read_drafts(project_id)
            screens[screen] = {"saved": _now(), "base_revision": base_revision, "edits": edits}
            self._write_drafts(project_id, screens)

    def get_drafts(self, project_id: str) -> dict[str, Draft]:
        """Every screen's autosaved edits – a damaged draft is simply not offered."""
        drafts = {}
        for screen, raw in self._read_drafts(project_id).items():
            if not isinstance(raw, dict):
                continue
            saved, base, edits = raw.get("saved"), raw.get("base_revision"), raw.get("edits")
            if isinstance(saved, str) and isinstance(base, int) and isinstance(edits, dict):
                drafts[screen] = Draft(saved, base, edits)
        return drafts

    def discard_draft(self, project_id: str, screen: str | None = None) -> None:
        """Drop one screen's draft, or – with no screen – every draft of the project."""
        with self._lock:
            if screen is None:
                self._path(self.drafts, project_id).unlink(missing_ok=True)
                return
            screens = self._read_drafts(project_id)
            if screens.pop(screen, None) is not None:
                self._write_drafts(project_id, screens)

    # ------------------------------------------------------------ first run

    def seed(self, demo_file: Path) -> StoredProject | None:
        """Copy the demo project in on the very first run – once the projects folder exists,
        never again, so a user who deletes the demo does not get it back."""
        if self.projects.exists() or not demo_file.is_file():
            return None
        return self.import_bytes(demo_file.read_bytes())
