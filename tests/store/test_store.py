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
from hoa_engine.dues import resolve_dues
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
    assert again.times == {"created": clock[0], "modified": clock[0]}
    assert set(again.scenario_times) == {s.name for s in DEMO.scenarios}


def test_the_file_is_readable_json_with_decimal_strings(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    raw = json.loads(_file(store, saved.id).read_text(encoding="utf-8"))
    assert raw["name"] == DEMO.name
    assert raw["schema_version"] == 4
    assert "baseline" not in raw and "baseline_times" not in raw
    assert isinstance(raw["facts"]["starting_balance"], str)
    assert raw["scenarios"][0]["facts"] is None  # it uses the project's


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


def test_a_change_to_one_scenario_stamps_only_that_scenario(
    store: ProjectStore, clock: list[str]
) -> None:
    saved = store.create(DEMO)
    first, *rest = DEMO.scenarios
    edited = replace(first, description="Changed")
    again = store.save(saved.id, replace(DEMO, scenarios=(edited, *rest)), base_revision=1)
    assert again.scenario_times[first.name]["modified"] == again.times["modified"]
    assert all(again.scenario_times[s.name] == saved.scenario_times[s.name] for s in rest)


def test_a_change_to_the_projects_facts_stamps_no_scenario(
    store: ProjectStore, clock: list[str]
) -> None:
    saved = store.create(DEMO)
    again = store.save(saved.id, replace(DEMO, facts=replace(DEMO.facts, units=30)), 1)
    assert again.times["modified"] != saved.times["modified"]
    assert again.scenario_times == saved.scenario_times


def test_expense_sets_keep_their_times_like_scenarios(
    store: ProjectStore, clock: list[str]
) -> None:
    saved = store.create(DEMO)
    first, second, *rest = DEMO.expense_sets
    assert set(saved.set_times) == {e.name for e in DEMO.expense_sets}
    renamed = replace(first, name="Renamed")
    edited = replace(second, expense_base_year=second.expense_base_year - 1)
    again = store.save(
        saved.id, replace(DEMO, expense_sets=(renamed, edited, *rest), expenses_from=None), 1
    )
    # a rename keeps its history
    assert again.set_times["Renamed"]["created"] == saved.set_times[first.name]["created"]
    assert again.set_times[second.name]["modified"] == again.times["modified"]
    assert all(again.set_times[e.name] == saved.set_times[e.name] for e in rest)


def test_a_renamed_scenario_keeps_its_history(store: ProjectStore, clock: list[str]) -> None:
    saved = store.create(DEMO)
    first, *rest = DEMO.scenarios
    renamed = replace(first, name="Renamed", description="And edited")
    again = store.save(saved.id, replace(DEMO, scenarios=(renamed, *rest)), 1)
    assert first.name not in again.scenario_times
    assert again.scenario_times["Renamed"] == {
        "created": saved.scenario_times[first.name]["created"],
        "modified": again.times["modified"],
    }
    # renamed back – still the same scenario, so it keeps its created time
    back = store.save(
        saved.id, replace(DEMO, scenarios=(replace(renamed, name=first.name), *rest)), 2
    )
    assert back.scenario_times[first.name]["created"] == saved.scenario_times[first.name]["created"]


def test_two_renames_in_one_save_start_new_histories(store: ProjectStore, clock: list[str]) -> None:
    saved = store.create(DEMO)
    first, second, *rest = DEMO.scenarios
    project = replace(
        DEMO, scenarios=(replace(first, name="One"), replace(second, name="Two"), *rest)
    )
    again = store.save(saved.id, project, 1)
    for name in ("One", "Two"):  # which became which cannot be told
        assert again.scenario_times[name]["created"] == again.times["modified"]


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


def test_an_oversized_project_file_is_neither_listed_nor_opened(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored = store.create(DEMO)
    monkeypatch.setattr(store_module, "MAX_PROJECT_BYTES", 100)
    assert store.list_projects() == ([], [f"{stored.id}.json"])
    with pytest.raises(BadProjectFile, match="damaged"):
        store.get(stored.id)


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
        ('{"name": "x", "scenarios": [{"name": "y"}]}', "the project is missing 'facts'"),
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
        scenario_times={"Dues only": {"created": 5, "modified": "not a time"}},
    )
    again = store.get(saved.id)
    assert again.project == DEMO
    assert again.times["created"][:4].isdigit()
    assert again.scenario_times["Dues only"]["modified"][:4].isdigit()


def test_a_byte_order_mark_is_accepted(store: ProjectStore) -> None:
    saved = store.import_bytes(b"\xef\xbb\xbf" + DEMO_FILE.read_bytes())  # Notepad adds one
    path = _file(store, saved.id)
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert store.get(saved.id).project == DEMO


# ---------------------------------------------------------------- delete and trash


def test_delete_moves_to_trash(store: ProjectStore) -> None:
    saved = store.create(DEMO)
    store.delete(saved.id)
    assert (store.trash / f"{saved.id}.json").is_file()
    with pytest.raises(NotFound):
        store.get(saved.id)


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
    assert (copy.times, copy.scenario_times) == (original.times, original.scenario_times)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\xff\xfe", "not a readable project file"),
        (b"{not json", "not a readable project file"),
        pytest.param(b"[" * 200_000 + b"]" * 200_000, "not a readable", id="deeply-nested"),
        (b'{"name": "x", "n": NaN}', "not a readable project file"),
        (b"[]", "not a project file"),
        (b'{"name": "x", "scenarios": [{"name": "y"}]}', "the project is missing 'facts'"),
        (b'{"name": "x", "schema_version": 2}', "missing 'baseline'"),
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


def _adopted(store: ProjectStore, created: object = None) -> tuple[str, int]:
    created = created or store.create(DEMO)
    assert isinstance(created, store_module.StoredProject)
    stored = store.adopt(created.id, "Dues only", date(2026, 11, 3), "Vote", created.revision)
    return created.id, stored.revision


def test_adopting_makes_the_plan_read_only_with_its_inputs_as_they_were(
    store: ProjectStore,
) -> None:
    created = store.create(DEMO)
    before = next(s for s in DEMO.scenarios if s.name == "Dues only")
    pid, revision = _adopted(store, created)
    stored = store.get(pid)
    plan = next(s for s in stored.project.scenarios if s.name == "Dues only")
    assert plan.adoption is not None
    assert (plan.adoption.adopted_on, plan.adoption.note, plan.adoption.sequence) == (
        date(2026, 11, 3),
        "Vote",
        2,  # the demo already has an adopted plan
    )
    # it keeps the project's facts as they were, and the set they came from
    assert plan.facts == DEMO.facts
    assert (plan.adoption.expenses_from, plan.adoption.expenses_edited) == (
        DEMO.expenses_from,
        DEMO.expenses_edited,
    )
    assert replace(plan, adoption=None, facts=None) == before  # nothing else about it changed
    assert run(plan).summary == run(DEMO.runnable(before)).summary
    # a later change to the project's facts leaves it as it was
    changed = store.save(
        pid, replace(stored.project, facts=replace(DEMO.facts, units=99)), revision
    )
    kept = next(s for s in changed.project.scenarios if s.name == "Dues only")
    assert kept.facts == DEMO.facts


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


def test_reordering_scenarios_changes_none_of_them_and_can_move_an_adopted_plan(
    store: ProjectStore,
) -> None:
    pid, revision = _adopted(store)
    before = store.get(pid)
    moved = replace(before.project, scenarios=tuple(reversed(before.project.scenarios)))
    after = store.save(pid, moved, revision)
    assert [s.name for s in after.project.scenarios] == [
        s.name for s in reversed(before.project.scenarios)
    ]
    assert after.scenario_times == before.scenario_times  # spec 7.1 – order is not a change


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
    with pytest.raises(NotFound, match="no scenario of that name"):
        store.adopt(pid, "Nobody", date(2026, 1, 1), "", revision)
    project = store.get(pid).project
    broken = replace(project, facts=replace(project.facts, ffb={}))
    revision = store.save(pid, broken, revision).revision
    with pytest.raises(Unusable, match="has problems"):
        store.adopt(pid, project.scenarios[1].name, date(2026, 1, 1), "", revision)


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


def test_un_adopting_drops_the_frozen_facts_and_carries_the_dues_on(store: ProjectStore) -> None:
    pid, revision = _adopted(store)
    project = store.get(pid).project
    # the project's years move on two years after the plan was adopted
    later = replace(project.facts, start_year=project.facts.start_year + 2)
    revision = store.save(pid, replace(project, facts=later), revision).revision
    plan = next(s for s in store.get(pid).project.scenarios if s.name == "Dues only")
    assert plan.facts is not None
    charged = resolve_dues(plan, range(plan.facts.start_year, later.start_year + 1))
    back = next(s for s in store.unadopt(pid, revision).project.scenarios if s.name == "Dues only")
    assert (back.facts, back.adoption) == (None, None)
    assert back.dues.first_value == charged[later.start_year]


# ---------------------------------------------------------------- the schema 3 upgrade (8.2)

SCHEMA_3 = Path(__file__).resolve().parents[1] / "engine" / "fixtures" / "demo_schema3.json"


def _schema_3_project(store: ProjectStore) -> str:
    """The demo as an older version saved it – a schema 3 file in the data folder."""
    saved = store.create(DEMO)
    original = json.loads(SCHEMA_3.read_text(encoding="utf-8"))
    _file(store, saved.id).write_text(
        json.dumps({**original, "id": saved.id, "revision": 7}), encoding="utf-8"
    )
    return saved.id


def test_an_older_file_is_upgraded_once_keeping_the_original_and_what_changed(
    store: ProjectStore,
) -> None:
    pid = _schema_3_project(store)
    before = _file(store, pid).read_bytes()
    opened = store.get(pid)
    assert opened.revision == 7  # the same project, in today's form
    assert [n.split(" – ")[0] for n in opened.upgrade_notes] == [
        "Insurance shock",
        "Worked-out Fully Funded Balance",
    ]
    assert json.loads(_file(store, pid).read_text(encoding="utf-8"))["schema_version"] == 4
    backup = store.root / "backups" / f"{pid}.json"
    assert backup.read_bytes() == before
    assert store.get(pid).upgrade_notes == opened.upgrade_notes  # shown until read
    read = store.dismiss_notes(pid, 7)
    assert (read.upgrade_notes, read.revision) == ((), 8)
    assert store.get(pid).upgrade_notes == ()
    store.delete(pid)  # the backup goes to the trash with it
    assert not backup.exists()
    assert (store.trash / f"{pid}.before-upgrade.json").read_bytes() == before


def test_a_backup_is_never_overwritten_and_damaged_notes_are_none(store: ProjectStore) -> None:
    pid = _schema_3_project(store)
    backup = store.root / "backups" / f"{pid}.json"
    backup.parent.mkdir(parents=True)
    backup.write_text("the first backup", encoding="utf-8")
    store.get(pid)
    assert backup.read_text(encoding="utf-8") == "the first backup"
    for damaged in ("not a list", ["x" * 3000], [1], ["n"] * 201):
        _edit_file(store, pid, upgrade_notes=damaged)
        assert store.get(pid).upgrade_notes == ()


def test_an_imported_older_project_file_says_what_its_upgrade_changed(
    store: ProjectStore,
) -> None:
    imported = store.import_bytes(SCHEMA_3.read_bytes())
    assert len(imported.upgrade_notes) == 2
    exported = json.loads(store.export_bytes(imported.id))
    assert exported["schema_version"] == 4 and "upgrade_notes" not in exported
    assert set(exported["set_times"]) == {e.name for e in imported.project.expense_sets}


def test_an_upgrade_never_writes_over_a_save_made_since_it_read_the_file(
    store: ProjectStore,
) -> None:
    pid = _schema_3_project(store)
    path = _file(store, pid)
    raw = json.loads(path.read_text(encoding="utf-8"))
    stale, notes = store_module.read_project(raw)  # read before another request upgraded it
    opened = store.get(pid)  # that other request – upgraded, then saved over
    saved = store.save(pid, replace(opened.project, notes="Saved meanwhile"), opened.revision)
    found = replace(opened, project=stale)
    again = store._upgraded(path, found, notes)
    assert again.project.notes == "Saved meanwhile"
    assert store.get(pid).revision == saved.revision


def test_an_upgrade_too_large_to_save_still_opens(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _schema_3_project(store)

    def too_large(_: object) -> None:
        raise store_module.BadProjectFile("too large")

    monkeypatch.setattr(store, "_write_stored", too_large)
    opened = store.get(pid)
    assert opened.project.facts is not None and len(opened.upgrade_notes) == 2
    assert json.loads(_file(store, pid).read_text(encoding="utf-8"))["schema_version"] == 3


def test_a_project_is_deleted_even_when_its_backup_cannot_be_moved(
    store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _schema_3_project(store)
    store.get(pid)  # upgraded, its backup kept
    real = os.replace

    def busy(src: object, dst: object) -> None:
        if str(dst).endswith(".before-upgrade.json"):
            raise OSError("busy")
        real(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(store_module.os, "replace", busy)
    store.delete(pid)
    with pytest.raises(NotFound):
        store.get(pid)
    assert (store.root / "backups" / f"{pid}.json").exists()  # left behind, harmless
