"""Project storage (spec section 8)."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from hoa_engine import project_from_dict, run
from hoa_engine.model import current_adoption
from hoa_store import store as store_module
from hoa_store.store import (
    BadProjectFile,
    Conflict,
    NotFound,
    ProjectStore,
    ReadOnly,
    StoreError,
    Unusable,
    default_root,
    parse_project_file,
)

DEMO_FILE = Path(__file__).resolve().parents[2] / "demo" / "fixtures" / "project.json"
DEMO = project_from_dict(json.loads(DEMO_FILE.read_text(encoding="utf-8")))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """A store clock that ticks one minute per reading, so timestamp changes are visible."""
    readings: list[str] = []

    def now() -> str:
        stamp = f"2026-10-20T10:{len(readings):02d}:00+00:00"
        readings.append(stamp)
        return stamp

    monkeypatch.setattr(store_module, "_now", now)
    yield readings


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path)


def _file(store: ProjectStore, project_id: str) -> Path:
    return store.projects / f"{project_id}.json"


def _edit_file(store: ProjectStore, project_id: str, **changes: object) -> None:
    path = _file(store, project_id)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.update(changes)
    path.write_text(json.dumps(raw), encoding="utf-8")


# ---------------------------------------------------------------- create and read


def test_a_created_project_reads_back_with_its_history(
    store: ProjectStore, clock: list[str]
) -> None:
    saved = store.create(DEMO)
    again = store.get(saved.id)
    assert again.project == DEMO
    assert again.revision == 1
    assert again.times == again.baseline_times == {"created": clock[0], "modified": clock[0]}
    assert set(again.scenario_times) == {s.name for s in DEMO.scenarios}


def test_the_file_is_readable_json_with_decimal_strings(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    raw = json.loads(_file(store, saved.id).read_text(encoding="utf-8"))
    assert raw["name"] == DEMO.name
    assert raw["schema_version"] == 2
    assert isinstance(raw["baseline"]["starting_balance"], str)


# ---------------------------------------------------------------- saving


def test_saving_stamps_only_what_changed(store: ProjectStore, clock: list[str]) -> None:
    saved = store.create(DEMO)
    first, second, *rest = DEMO.scenarios
    project = replace(
        DEMO,
        scenarios=(
            replace(first, description="Revised"),
            second,
            *rest,
            replace(first, name="New"),
        ),
    )
    again = store.save(saved.id, project, base_revision=1)
    created, saved_at = saved.times["created"], again.times["modified"]
    assert again.revision == 2
    assert again.times == {"created": created, "modified": saved_at}
    assert again.scenario_times[first.name] == {"created": created, "modified": saved_at}
    assert again.scenario_times[second.name] == saved.scenario_times[second.name]  # untouched
    assert again.scenario_times["New"] == {"created": saved_at, "modified": saved_at}
    assert again.baseline_times == saved.baseline_times  # the baseline did not change


def test_a_baseline_change_stamps_the_baseline_but_not_the_scenarios(
    store: ProjectStore, clock: list[str]
) -> None:
    saved = store.create(DEMO)
    edited = replace(DEMO, baseline=replace(DEMO.baseline, units=30))
    again = store.save(saved.id, edited, base_revision=1)
    assert again.baseline_times["modified"] == again.times["modified"] != saved.times["modified"]
    assert again.scenario_times == saved.scenario_times


def test_a_renamed_scenario_starts_a_new_history(store: ProjectStore, clock: list[str]) -> None:
    saved = store.create(DEMO)
    first, *rest = DEMO.scenarios
    again = store.save(
        saved.id, replace(DEMO, scenarios=(replace(first, name="Renamed"), *rest)), 1
    )
    assert first.name not in again.scenario_times
    assert again.scenario_times["Renamed"]["created"] == again.times["modified"]


def test_a_save_from_a_stale_copy_is_refused(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    store.save(saved.id, DEMO, base_revision=1)
    with pytest.raises(Conflict, match="saved elsewhere"):
        store.save(saved.id, DEMO, base_revision=1)


def test_simultaneous_saves_from_one_revision_let_exactly_one_through(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    outcomes: list[str] = []

    def save(n: int) -> None:
        try:
            store.save(saved.id, replace(DEMO, name=f"Tab {n}"), base_revision=1)
            outcomes.append("saved")
        except Conflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=save, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["conflict"] * 5 + ["saved"]
    assert store.get(saved.id).revision == 2


def test_a_failed_write_leaves_the_project_as_it_was(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = store.create(DEMO)

    def fail(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store_module.os, "replace", fail)
    with pytest.raises(StoreError, match="busy or full"):
        store.save(saved.id, replace(DEMO, name="Changed"), base_revision=1)
    with pytest.raises(StoreError, match="could not be deleted"):
        store.delete(saved.id)
    assert store.get(saved.id).project == DEMO
    assert not list(store.projects.glob(".tmp-*"))


def test_an_interrupted_write_cleans_up_and_passes_the_interruption_on(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = store.create(DEMO)

    def interrupt(*_: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(store_module.os, "replace", interrupt)
    with pytest.raises(KeyboardInterrupt):
        store.save(saved.id, DEMO, base_revision=1)
    assert not list(store.projects.glob(".tmp-*"))


# ---------------------------------------------------------------- listing


def test_listing_is_newest_first_and_reports_what_it_cannot_read(
    store: ProjectStore, clock: list[str]
) -> None:
    assert store.list_projects() == ([], [])
    a = store.create(replace(DEMO, name="A"))
    b = store.create(replace(DEMO, name="B"))
    store.save(a.id, replace(DEMO, name="A2"), base_revision=1)
    (store.projects / "0123456789ab.json").write_text("{broken", encoding="utf-8")
    (store.projects / "notes.json").write_text("{}", encoding="utf-8")  # not a project file name
    summaries, unreadable = store.list_projects()
    assert [s.id for s in summaries] == [a.id, b.id]
    assert summaries[0].name == "A2" and summaries[0].scenarios == len(DEMO.scenarios)
    assert unreadable == ["0123456789ab.json", "notes.json"]


def test_a_project_file_copied_in_by_hand_is_listed(store: ProjectStore) -> None:
    store.projects.mkdir(parents=True)
    raw = json.loads(DEMO_FILE.read_text(encoding="utf-8"))
    del raw["scenarios"]
    (store.projects / "abcdefabcdef.json").write_text(json.dumps(raw), encoding="utf-8")
    (summary,), _ = store.list_projects()
    assert summary.name == DEMO.name and summary.scenarios == 0
    assert summary.modified[:4].isdigit()  # the file's own time


# ---------------------------------------------------------------- bad ids and damaged files


@pytest.mark.parametrize("bad_id", ["../../etc", "ABCDEF123456", "0123456789a", "x" * 12, ""])
def test_ids_that_are_not_ours_never_reach_the_file_system(
    store: ProjectStore, bad_id: str
) -> None:
    with pytest.raises(NotFound):
        store.get(bad_id)
    with pytest.raises(NotFound):
        store.delete(bad_id)


def test_a_missing_project(store: ProjectStore) -> None:
    for action in (store.get, store.delete):
        with pytest.raises(NotFound):
            action("0123456789ab")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{broken", "the file is damaged"),
        pytest.param("[" * 100_000 + "]" * 100_000, "the file is damaged", id="deeply-nested"),
        ('{"name": "x"}', "missing 'baseline'"),
    ],
)
def test_a_damaged_saved_file_gets_a_plain_message(
    store: ProjectStore, content: str, message: str
) -> None:
    saved = store.create(DEMO)
    _file(store, saved.id).write_text(content, encoding="utf-8")
    with pytest.raises(BadProjectFile, match=message):
        store.get(saved.id)


@pytest.mark.parametrize("revision", ["x", 0, True])
def test_a_damaged_revision_gets_a_plain_message(store: ProjectStore, revision: object) -> None:
    saved = store.create(DEMO)
    _edit_file(store, saved.id, revision=revision)
    with pytest.raises(BadProjectFile, match="revision is damaged"):
        store.get(saved.id)


def test_damaged_timestamps_are_replaced_not_fatal(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    _edit_file(
        store,
        saved.id,
        times="soon",
        scenario_times=[1],
        baseline_times={"created": 5, "modified": "not a time"},
    )
    again = store.get(saved.id)
    assert again.project == DEMO
    assert again.times["created"][:4].isdigit()


def test_a_byte_order_mark_is_accepted(store: ProjectStore) -> None:
    saved = store.import_bytes(b"\xef\xbb\xbf" + DEMO_FILE.read_bytes())  # Notepad adds one
    path = _file(store, saved.id)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert store.get(saved.id).project == DEMO


# ---------------------------------------------------------------- delete and trash


def test_delete_moves_to_trash_and_drops_the_draft(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    store.save_draft(saved.id, "baseline", {"anything": 1}, base_revision=1)
    store.delete(saved.id)
    assert (store.trash / f"{saved.id}.json").is_file()
    assert store.get_drafts(saved.id) == {}
    with pytest.raises(NotFound):
        store.get(saved.id)


# ---------------------------------------------------------------- drafts


def test_each_screen_keeps_its_own_draft(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    assert store.get_drafts(saved.id) == {}
    store.save_draft(saved.id, "baseline", {"baseline": {"units": ""}}, base_revision=1)
    store.save_draft(saved.id, "scenario:Dues only", {"name": "x"}, base_revision=1)
    store.save_draft(saved.id, "baseline", {"baseline": {"units": "3"}}, base_revision=1)
    drafts = store.get_drafts(saved.id)
    assert set(drafts) == {"baseline", "scenario:Dues only"}
    assert drafts["baseline"].edits == {"baseline": {"units": "3"}}  # need not be valid
    assert drafts["baseline"].base_revision == 1


def test_a_save_keeps_other_drafts_but_late_autosaves_are_refused(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    store.save_draft(saved.id, "baseline", {"a": 1}, base_revision=1)
    store.save(saved.id, DEMO, base_revision=1)
    assert store.get_drafts(saved.id)["baseline"].base_revision == 1  # offered as begun earlier
    with pytest.raises(Conflict, match="saved since these edits began"):
        store.save_draft(saved.id, "baseline", {"a": 2}, base_revision=1)


def test_discarding_one_screen_or_all(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    store.save_draft(saved.id, "baseline", {"a": 1}, base_revision=1)
    store.save_draft(saved.id, "new-scenario", {"b": 1}, base_revision=1)
    store.discard_draft(saved.id, "baseline")
    store.discard_draft(saved.id, "baseline")  # already gone – harmless
    assert set(store.get_drafts(saved.id)) == {"new-scenario"}
    store.discard_draft(saved.id, "new-scenario")  # the last one – the file goes too
    assert not (store.drafts / f"{saved.id}.json").exists()
    store.save_draft(saved.id, "baseline", {"a": 1}, base_revision=1)
    store.discard_draft(saved.id)
    assert store.get_drafts(saved.id) == {}


@pytest.mark.parametrize(
    ("screen", "edits", "message"),
    [
        ("baseline", [1, 2], "must be a set of edits"),
        ("somewhere", {}, "must name its screen"),
        ("scenario:", {}, "must name its screen"),
        ("scenario:a\x07", {}, "must name its screen"),
        ("baseline", {"x": float("nan")}, "cannot be stored"),
        ("baseline", {"x": "y" * 60}, "larger than 5 MB"),
    ],
)
def test_unstorable_drafts_are_refused(
    store: ProjectStore,
    monkeypatch: pytest.MonkeyPatch,
    screen: str,
    edits: object,
    message: str,
) -> None:
    saved = store.create(DEMO)
    monkeypatch.setattr(store_module, "MAX_DRAFT_BYTES", 100)
    with pytest.raises(BadProjectFile, match=message):
        store.save_draft(saved.id, screen, edits, base_revision=1)  # type: ignore[arg-type]


def test_a_draft_needs_its_project(store: ProjectStore) -> None:
    with pytest.raises(NotFound):
        store.save_draft("0123456789ab", "baseline", {}, base_revision=1)


@pytest.mark.parametrize(
    "content",
    [
        "{broken",
        "[1, 2]",
        '{"screens": [1]}',
        '{"screens": {"baseline": 5}}',
        '{"screens": {"baseline": {"saved": "x", "base_revision": "1", "edits": {}}}}',
    ],
)
def test_damaged_drafts_are_not_offered(store: ProjectStore, content: str) -> None:
    saved = store.create(DEMO)
    store.drafts.mkdir(parents=True, exist_ok=True)
    (store.drafts / f"{saved.id}.json").write_text(content, encoding="utf-8")
    assert store.get_drafts(saved.id) == {}


# ---------------------------------------------------------------- export and import


def test_export_then_import_keeps_the_history_but_not_the_identity(
    store: ProjectStore, clock: list[str]
) -> None:
    saved = store.create(DEMO)
    store.save(saved.id, replace(DEMO, notes="Edited"), base_revision=1)
    original = store.get(saved.id)
    exported = json.loads(store.export_bytes(saved.id))
    assert "id" not in exported and "revision" not in exported
    copy = store.import_bytes(store.export_bytes(saved.id))
    assert copy.id != saved.id and copy.revision == 1
    assert copy.project == original.project
    assert (copy.times, copy.baseline_times, copy.scenario_times) == (
        original.times,
        original.baseline_times,
        original.scenario_times,
    )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\xff\xfe", "not a readable project file"),
        (b"{not json", "not a readable project file"),
        pytest.param(b"[" * 200_000 + b"]" * 200_000, "not a readable", id="deeply-nested"),
        (b'{"name": "x", "n": NaN}', "not a readable project file"),
        (b"[]", "not a project file"),
        (b'{"name": "x"}', "missing 'baseline'"),
    ],
)
def test_bad_project_files_are_refused_in_plain_language(data: bytes, message: str) -> None:
    with pytest.raises(BadProjectFile, match=message):
        parse_project_file(data)


def test_oversized_project_files_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store_module, "MAX_PROJECT_BYTES", 10)
    with pytest.raises(BadProjectFile, match="larger than 5 MB"):
        parse_project_file(DEMO_FILE.read_bytes())


# ---------------------------------------------------------------- first run


def test_first_run_seeds_the_demo_and_a_deleted_demo_stays_deleted(
    store: ProjectStore, tmp_path: Path
) -> None:
    assert ProjectStore(tmp_path / "other").seed(tmp_path / "missing.json") is None
    seeded = store.seed(DEMO_FILE)
    assert seeded is not None and seeded.project == DEMO
    store.delete(seeded.id)
    assert store.seed(DEMO_FILE) is None


# ---------------------------------------------------------------- data folder


@pytest.mark.parametrize(
    ("platform", "env", "expected_tail"),
    [
        ("win32", {"APPDATA": "C:/Users/x/AppData/Roaming"}, "Roaming/HOAForecaster"),
        ("darwin", {}, "Library/Application Support/HOAForecaster"),
        ("linux", {"XDG_DATA_HOME": "/home/x/.data"}, ".data/HOAForecaster"),
    ],
)
def test_default_data_folder_per_platform(
    monkeypatch: pytest.MonkeyPatch, platform: str, env: dict[str, str], expected_tail: str
) -> None:
    for key in ("HOA_DATA_DIR", "APPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(store_module.sys, "platform", platform)
    assert default_root().as_posix().endswith(expected_tail)


def test_hoa_data_dir_overrides_the_default_as_an_absolute_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOA_DATA_DIR", os.path.join("some", "folder"))
    assert default_root() == Path("some", "folder").resolve()


# ---------------------------------------------------------------- adopted plans (spec 5.2)


def _adopted(store: ProjectStore) -> tuple[str, int]:
    created = store.create(DEMO)
    stored = store.adopt(created.id, "Dues only", date(2026, 11, 3), "Vote", created.revision)
    return created.id, stored.revision


def test_adopting_freezes_the_plan_with_the_baseline_it_runs_on(store: ProjectStore) -> None:
    pid, revision = _adopted(store)
    stored = store.get(pid)
    plan = stored.project.scenarios[0]
    assert plan.adoption is not None
    assert (plan.adoption.adopted_on, plan.adoption.note, plan.adoption.sequence) == (
        date(2026, 11, 3),
        "Vote",
        2,  # the demo already has an adopted plan
    )
    before = run(stored.project.baseline, plan).summary
    # a later baseline edit – deleting every expense line – leaves the plan's figures alone
    edited = replace(stored.project, baseline=replace(stored.project.baseline, expense_lines=()))
    after = store.save(pid, edited, revision)
    assert run(after.project.baseline, after.project.scenarios[0]).summary == before


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: replace(p, scenarios=p.scenarios[1:]),  # deleted
        lambda p: replace(p, scenarios=(replace(p.scenarios[0], name="Renamed"), *p.scenarios[1:])),
        lambda p: replace(
            p, scenarios=(replace(p.scenarios[0], description="x"), *p.scenarios[1:])
        ),
        lambda p: replace(p, scenarios=(replace(p.scenarios[0], adoption=None), *p.scenarios[1:])),
    ],
)
def test_a_save_cannot_change_an_adopted_plan(store: ProjectStore, edit: object) -> None:
    pid, revision = _adopted(store)
    with pytest.raises(ReadOnly, match="Dues only is an adopted plan"):
        store.save(pid, edit(store.get(pid).project), revision)  # type: ignore[operator]  # a lambda per case


def test_a_save_cannot_adopt_a_scenario(store: ProjectStore) -> None:
    pid, revision = _adopted(store)
    project = store.get(pid).project
    plan = project.scenarios[0]
    sneaked = replace(project.scenarios[1], adoption=replace(plan.adoption, sequence=2))  # type: ignore[arg-type]  # adoption is set above
    with pytest.raises(ReadOnly, match="adopted with Adopt"):
        store.save(
            pid, replace(project, scenarios=(plan, sneaked, *project.scenarios[2:])), revision
        )


def test_the_latest_adoption_is_current_and_un_adopting_restores_the_one_before(
    store: ProjectStore,
) -> None:
    pid, revision = _adopted(store)
    stored = store.adopt(pid, "Steady increase", date(2020, 1, 1), "", revision)
    current = current_adoption(stored.project.scenarios)
    assert current is not None and current.name == "Steady increase"  # whatever its date
    stored = store.unadopt(pid, stored.revision)
    back = next(s for s in stored.project.scenarios if s.name == "Steady increase")
    assert back.adoption is None
    assert current_adoption(stored.project.scenarios).name == "Dues only"  # type: ignore[union-attr]  # one is left


def test_adoption_refuses_what_it_cannot_adopt(store: ProjectStore) -> None:
    pid, revision = _adopted(store)
    with pytest.raises(ReadOnly, match="already an adopted plan"):
        store.adopt(pid, "Dues only", date(2026, 1, 1), "", revision)
    with pytest.raises(NotFound, match="save it first"):
        store.adopt(pid, "Nobody", date(2026, 1, 1), "", revision)
    project = store.get(pid).project
    broken = replace(project.scenarios[1], changes=replace(project.scenarios[1].changes, ffb={}))
    broken = replace(broken, changes=replace(broken.changes, values={"end_year": 2050}))
    revision = store.save(
        pid,
        replace(project, scenarios=(project.scenarios[0], broken, *project.scenarios[2:])),
        revision,
    ).revision
    with pytest.raises(Unusable, match="has problems"):
        store.adopt(pid, broken.name, date(2026, 1, 1), "", revision)


def test_un_adopting_needs_an_adopted_plan(store: ProjectStore) -> None:
    created = store.create(
        replace(DEMO, scenarios=tuple(s for s in DEMO.scenarios if not s.adoption))
    )
    with pytest.raises(NotFound, match="no adopted plan"):
        store.unadopt(created.id, created.revision)


def test_a_project_too_large_to_open_again_is_never_written(store: ProjectStore) -> None:
    created = store.create(DEMO)
    huge = replace(DEMO, notes="x" * (6 * 1024 * 1024))
    with pytest.raises(BadProjectFile, match="larger than 5 MB"):
        store.save(created.id, huge, created.revision)
    assert store.get(created.id).project == DEMO  # still readable, unchanged


def test_adoption_stops_at_the_most_adoptions_a_project_can_hold(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = store.create(DEMO)  # the demo has one adopted plan already
    monkeypatch.setattr(store_module, "MAX_ADOPTIONS", 1)
    with pytest.raises(Unusable, match="as many adopted plans as it can hold"):
        store.adopt(created.id, "Dues only", date(2026, 1, 1), "", created.revision)
