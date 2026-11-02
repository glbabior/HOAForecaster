"""The project's facts, expenses and expense sets, and the schema 3 upgrade (spec 3, 4.3, 5.2,
8.2)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hoa_engine import (
    Adoption,
    DuesMode,
    DuesPath,
    Increase,
    InvalidInputs,
    Project,
    ProjectFormatError,
    Scenario,
    expenses_of,
    project_from_dict,
    project_to_dict,
    read_project,
    run,
    scenario_from_dict,
    with_expenses,
)
from hoa_engine.dues import rebase_dues, resolve_dues
from hoa_engine.model import MAX_SET_NAME, MAX_SETS, blank_facts, check_project, same_set
from hoa_engine.upgrade import upgrade_v3_project
from hoa_engine.validate import validate_scenario

D = Decimal
SCHEMA_3 = Path(__file__).parent / "fixtures" / "demo_schema3.json"


def _v3() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads(SCHEMA_3.read_text(encoding="utf-8"))
    return raw


def _upgraded() -> tuple[Project, list[str]]:
    return read_project(_v3())


# ---------------------------------------------------------------- the schema 3 upgrade


def test_the_first_scenario_not_adopted_gives_the_project_its_facts_and_expenses() -> None:
    raw = _v3()
    project, _ = _upgraded()
    assert project.facts == scenario_from_dict(raw["scenarios"][0]).facts  # Dues only
    assert project.expenses_from == "Expenses from Dues only"
    assert not project.expenses_edited


def test_each_different_set_of_expenses_is_saved_once_named_after_its_first_scenario() -> None:
    project, _ = _upgraded()
    assert [e.name for e in project.expense_sets] == [
        "Expenses from Dues only",  # shared by five scenarios
        "Expenses from Insurance shock",
        "Expenses from Adopted – two-part assessment",
        "Expenses from Worked-out Fully Funded Balance",
    ]
    for raw in _v3()["scenarios"]:
        facts = scenario_from_dict(raw).facts
        assert facts is not None
        assert sum(expenses_of(facts) == replace(e, name="") for e in project.expense_sets) == 1


def test_adopted_plans_keep_their_facts_and_figures_and_say_which_set_they_were() -> None:
    project, _ = _upgraded()
    for raw in _v3()["scenarios"]:
        before = scenario_from_dict(raw)
        if before.adoption is None:
            continue
        after = next(s for s in project.scenarios if s.name == before.name)
        assert after.facts == before.facts
        assert after.adoption is not None
        assert after.adoption.expenses_from == f"Expenses from {before.name}"
        assert run(project.runnable(after)) == run(before)


def test_scenarios_on_the_project_facts_keep_their_figures_and_the_others_are_named() -> None:
    project, report = _upgraded()
    changed = set()
    for raw in _v3()["scenarios"]:
        before = scenario_from_dict(raw)
        after = next(s for s in project.scenarios if s.name == before.name)
        if before.adoption is None:
            assert after.facts is None  # it uses the project's now
        if run(project.runnable(after)) != run(before):
            changed.add(before.name)
    assert changed == {"Insurance shock", "Worked-out Fully Funded Balance"}
    assert report == [
        "Insurance shock – its interest rate, its owner-vote limits, its source notes, 3 expense "
        "lines, its Fully Funded Balance – its figures change – its expenses are saved as the set "
        "'Expenses from Insurance shock'; loading it does not bring back its other facts",
        "Worked-out Fully Funded Balance – 4 expense lines, its Fully Funded Balance – its figures "
        "change – it now matches Dues only exactly – its expenses are saved as the set "
        "'Expenses from Worked-out Fully Funded Balance'",
    ]


def test_the_upgrade_names_facts_alone_and_every_kind_of_expense_difference() -> None:
    project, _ = _upgraded()
    base = project.facts
    first = base.expense_lines[0]
    on = [
        (
            replace(base, units=base.units + 1, start_year=base.start_year + 1),
            ["its years", "its number of units"],
        ),
        (
            replace(
                base,
                expense_lines=(
                    first,
                    *base.expense_lines[1:],
                    first.__class__(2030, D(1), id="new"),
                ),
            ),
            ["1 expense line"],
        ),
        (
            replace(base, expense_lines=tuple(reversed(base.expense_lines))),
            ["the order of its expense lines"],
        ),
        (replace(base, expense_base_year=base.expense_base_year - 1), ["its expense base year"]),
    ]
    for facts, words in on:
        s = replace(project.scenarios[0], facts=facts)
        upgraded, report = upgrade_v3_project(
            "P", "", (replace(s, name="First", facts=base), replace(s, name="Other"))
        )
        sentence = report[0]
        assert sentence.startswith("Other – " + ", ".join(words))
        expenses_differ = not same_set(expenses_of(facts), expenses_of(base))
        assert ("saved as the set 'Expenses from Other'" in sentence) == expenses_differ
        assert len(upgraded.expense_sets) == 1 + expenses_differ


def test_every_scenario_adopted_gives_the_first_ones_facts() -> None:
    project, _ = _upgraded()
    adopted = next(s for s in project.scenarios if s.adoption is not None)
    later = replace(adopted, name="Later", adoption=replace(adopted.adoption, sequence=9))  # type: ignore[arg-type]
    upgraded, report = upgrade_v3_project("P", "", (adopted, later))
    assert upgraded.facts == adopted.facts
    assert report == []  # adopted plans keep their own, so nothing changes
    assert all(s.facts is not None for s in upgraded.scenarios)


def test_a_project_without_scenarios_starts_from_the_defaults() -> None:
    upgraded, report = read_project({**_v3(), "scenarios": []})
    assert upgraded.facts == blank_facts(date.today().year + 1)
    assert (upgraded.scenarios, upgraded.expense_sets, upgraded.expenses_from, report) == (
        (),
        (),
        None,
        [],
    )


def test_set_names_stay_unique_and_short_enough() -> None:
    project, _ = _upgraded()
    s = project.scenarios[0]
    long = "x" * 200
    other = replace(project.facts, expense_base_year=project.facts.expense_base_year - 1)
    third = replace(project.facts, expense_base_year=project.facts.expense_base_year - 2)
    upgraded, _ = upgrade_v3_project(
        "P",
        "",
        (
            replace(s, name=long, facts=project.facts),
            replace(s, name=long + "y", facts=other),
            replace(s, name=long + "z", facts=third),
        ),
    )
    names = [e.name for e in upgraded.expense_sets]
    assert len(set(names)) == 3
    assert all(len(n) <= MAX_SET_NAME for n in names)
    assert names[1].endswith(" (2)") and names[2].endswith(" (3)")


def test_a_schema_3_scenario_without_facts_is_refused() -> None:
    raw = _v3()
    raw["scenarios"][0]["facts"] = None
    with pytest.raises(ProjectFormatError, match="missing its facts"):
        read_project(raw)


def test_older_schemas_upgrade_all_the_way() -> None:
    schema2 = json.loads(
        (Path(__file__).parent / "fixtures" / "demo_schema2.json").read_text(encoding="utf-8")
    )
    project, _ = read_project(schema2)
    check_project(project)
    assert project.facts is not None and project.expense_sets


# ---------------------------------------------------------------- the schema 4 file


def test_a_project_file_round_trips() -> None:
    project, _ = _upgraded()
    raw = json.loads(json.dumps(project_to_dict(project)))
    assert raw["schema_version"] == 4
    assert [s["facts"] is None for s in raw["scenarios"]] == [
        s.adoption is None for s in project.scenarios
    ]
    assert read_project(raw) == (project, [])
    edited = replace(project, expenses_edited=True)
    assert project_from_dict(project_to_dict(edited)) == edited


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["scenarios"][0].update(facts=d["facts"]), "facts of its own"),
        (lambda d: d["scenarios"][5].update(facts=None), "missing the facts it was adopted with"),
        (lambda d: d.update(expenses_from="Nowhere"), "not a saved set"),
        (lambda d: d.update(expenses_from=None, expenses_edited=True), "cannot have been edited"),
        (lambda d: d["expense_sets"].append(dict(d["expense_sets"][0])), "names must be unique"),
        (lambda d: d["expense_sets"][0].update(name="  "), "needs a name"),
        (lambda d: d["expense_sets"][0].update(name="x" * (MAX_SET_NAME + 1)), "at most"),
        (lambda d: d.update(expense_sets=[d["expense_sets"][0]] * (MAX_SETS + 1)), "at most 200"),
        (lambda d: d.update(expense_sets="many"), "should be a list"),
        (lambda d: d.update(scenarios="many"), "should be a list"),
        (lambda d: d.update(schema_version=5), "not supported"),
    ],
)
def test_a_bad_project_file_is_refused(change: Any, message: str) -> None:
    raw = json.loads(json.dumps(project_to_dict(_upgraded()[0])))
    change(raw)
    with pytest.raises(ProjectFormatError, match=message):
        read_project(raw)


def test_an_adoption_keeps_the_set_its_expenses_came_from() -> None:
    raw = json.loads(json.dumps(project_to_dict(_upgraded()[0])))
    adoption = raw["scenarios"][5]["adoption"]
    adoption.update(expenses_edited=True)
    plan = read_project(raw)[0].scenarios[5]
    assert plan.adoption == Adoption(
        adopted_on=date(2026, 10, 14),
        note=plan.adoption.note if plan.adoption else "",
        sequence=1,
        expenses_from="Expenses from Adopted – two-part assessment",
        expenses_edited=True,
    )
    adoption.update(expenses_from=None)  # edited since no set means nothing
    assert read_project(raw)[0].scenarios[5].adoption.expenses_edited is False  # type: ignore[union-attr]


# ---------------------------------------------------------------- expense sets


def test_loading_a_set_swaps_the_expenses_and_their_base_year_and_nothing_else() -> None:
    project, _ = _upgraded()
    shock = next(e for e in project.expense_sets if e.name == "Expenses from Insurance shock")
    later = replace(shock, expense_base_year=2027, sources={"expense_base_year": "Study update"})
    loaded = with_expenses(project.facts, later)
    assert same_set(expenses_of(loaded), later)
    assert loaded.expense_inflation == project.facts.expense_inflation  # an assumption – stays
    assert loaded.interest_rate == project.facts.interest_rate
    kept = {k: v for k, v in project.facts.sources.items() if k not in ("ffb", "expense_base_year")}
    assert loaded.sources == {**kept, "expense_base_year": "Study update"}
    # loading the first set back gives the same figures as before (spec 9)
    back = with_expenses(loaded, project.expense_sets[0])
    plan = project.scenarios[0]
    again, before = run(replace(plan, facts=back)), run(project.runnable(plan))
    assert (again.summary, again.ffb) == (before.summary, before.ffb)
    assert [(y.operating, y.expenses, y.ending_balance) for y in again.years] == [
        (y.operating, y.expenses, y.ending_balance) for y in before.years
    ]


def test_a_set_keeps_blank_operating_years_as_the_start_year_and_its_inflation() -> None:
    project, _ = _upgraded()
    blank = [
        line.id
        for line in project.facts.expense_lines
        if line.frequency.operating and line.year is None
    ]
    assert blank  # the demo has operating lines from the start year
    saved = expenses_of(project.facts, "Saved")
    pinned = {line.id: line.year for line in saved.expense_lines}
    assert all(pinned[i] == project.facts.start_year for i in blank)
    assert saved.saved_inflation == project.facts.expense_inflation
    # loaded a year later, the operating lines still start when they did
    moved = replace(project.facts, start_year=project.facts.start_year + 1)
    assert all(
        line.year == project.facts.start_year
        for line in with_expenses(moved, saved).expense_lines
        if line.id in blank
    )


def test_loading_keeps_the_fully_funded_balance_years_a_set_lacks() -> None:
    project, _ = _upgraded()
    f = project.facts
    short = replace(expenses_of(f, "Short"), ffb={f.start_year: D(1)})
    loaded = with_expenses(f, short)
    assert loaded.ffb == {**f.ffb, f.start_year: D(1)}


def test_sets_are_the_same_whatever_their_name_line_order_or_inflation_but_not_notes() -> None:
    project, _ = _upgraded()
    s = expenses_of(project.facts, "A")
    reordered = replace(
        s, name="B", expense_lines=tuple(reversed(s.expense_lines)), saved_inflation=D("0.09")
    )
    assert same_set(s, reordered)
    first = s.expense_lines[0]
    noted = replace(s, expense_lines=(replace(first, source="Other note"), *s.expense_lines[1:]))
    assert not same_set(s, noted)


# ---------------------------------------------------------------- dues on another horizon


def test_a_grown_path_moved_to_a_later_start_carries_on_from_what_it_charged() -> None:
    project, _ = _upgraded()
    plan = project.runnable(next(s for s in project.scenarios if s.name == "Dues only"))
    assert plan.facts is not None
    start = plan.facts.start_year
    charged = resolve_dues(plan, range(start, start + 4))
    moved = rebase_dues(plan, plan.facts, start + 3)
    assert moved.dues.first_value == charged[start + 3]
    assert moved.dues.increases == plan.dues.increases
    # unchanged – the same start, a start outside the old horizon, typed dues, a path with problems
    assert rebase_dues(plan, plan.facts, start) is plan
    assert rebase_dues(plan, plan.facts, plan.facts.end_year + 1) is plan
    typed = next(s for s in project.scenarios if s.dues.mode.value == "explicit")
    assert rebase_dues(typed, plan.facts, start + 3) is typed
    broken = replace(plan, name="")
    assert rebase_dues(broken, plan.facts, start + 3) is broken


def test_the_upgrade_carries_a_scenarios_dues_onto_the_projects_start_year() -> None:
    project, _ = _upgraded()
    first = project.runnable(project.scenarios[0])
    assert first.facts is not None
    earlier = replace(first.facts, start_year=first.facts.start_year - 2)
    early = replace(first, name="Early", facts=earlier)
    upgraded, report = upgrade_v3_project("P", "", (first, early))
    moved = upgraded.scenarios[1]
    charged = resolve_dues(early, range(earlier.start_year, first.facts.start_year + 1))
    assert moved.dues.first_value == charged[first.facts.start_year]
    assert report[0].startswith("Early – its years")


def test_a_scenario_runs_on_the_projects_facts_unless_it_keeps_its_own() -> None:
    project, _ = _upgraded()
    plan = next(s for s in project.scenarios if s.facts is None)
    adopted = next(s for s in project.scenarios if s.facts is not None)
    assert project.runnable(plan).facts == project.facts
    assert project.runnable(adopted) is adopted
    assert len(project.runnable_scenarios()) == len(project.scenarios)
    with pytest.raises(InvalidInputs, match="no facts to run on"):
        run(plan)


def test_a_blank_projects_facts_are_the_spec_defaults() -> None:
    f = blank_facts(2027)
    assert (f.start_year, f.end_year, f.expense_base_year) == (2027, 2040, 2026)
    assert sorted(f.ffb) == list(range(2027, 2042))
    assert (f.expense_inflation, f.operating_inflation, f.interest_rate, f.target) == (
        D("0.03"),
        D("0.03"),
        D("0.02"),
        D("0.7"),
    )
    assert f.expense_lines == () and f.units == 1


def test_a_long_scenario_name_is_shortened_in_the_report() -> None:
    project, _ = _upgraded()
    base = project.facts
    s = replace(project.scenarios[0], facts=replace(base, units=base.units + 1))
    _, report = upgrade_v3_project("P", "", (replace(s, facts=base), replace(s, name="x" * 500)))
    assert report[0].startswith("x" * (MAX_SET_NAME - 1) + "… – its number of units")
    assert len(report[0]) < 300


def test_the_report_says_figures_stay_the_same_when_only_words_or_order_differ() -> None:
    project, _ = _upgraded()
    base = project.facts
    first, *rest = base.expense_lines
    reworded = replace(
        base, expense_lines=(replace(first, description="Renamed", source="Note"), *rest)
    )
    reordered = replace(base, expense_lines=tuple(reversed(base.expense_lines)))
    s = project.scenarios[0]
    for facts, words, new_set in (
        (reworded, "1 expense line", True),
        (reordered, "the order of its expense lines", False),
    ):
        upgraded, report = upgrade_v3_project(
            "P", "", (replace(s, name="First", facts=base), replace(s, name="Other", facts=facts))
        )
        assert report[0].startswith(f"Other – {words} – its figures stay the same")
        assert len(upgraded.expense_sets) == 1 + new_set


def test_carrying_dues_on_tidies_the_periods_and_pinned_years_to_the_new_start() -> None:
    project, _ = _upgraded()
    f = replace(project.facts, start_year=2027, end_year=2040)
    increases = (
        Increase(D("0.08"), 2028, 2030),  # over by the new start – dropped
        Increase(D("0.03"), 2031, 2034),  # starts after it – kept
        Increase(D("0.02"), 2035, None),
    )
    path = DuesPath(DuesMode.RATE, first_value=D(700), increases=increases)
    path = replace(path, overrides={2029: D(800), 2033: D(900)})
    plan = Scenario("P", f, path)
    moved = rebase_dues(plan, f, 2030)
    # 2029 pinned at 800, then +8% – 864 in 2030, now its first-year value
    assert moved.dues.first_value == 864
    assert moved.dues.increases == increases[1:]
    assert moved.dues.overrides == {2033: D(900)}
    later = replace(f, start_year=2030, end_year=2043)
    assert validate_scenario(replace(moved, facts=later), later) == []
    # a period running into the new start starts with it
    straddling = replace(plan, dues=replace(path, increases=(Increase(D("0.03")),), overrides={}))
    assert rebase_dues(straddling, f, 2030).dues.increases == (Increase(D("0.03")),)
    long = (Increase(D("0.03"), 2028, None),)
    across = rebase_dues(
        replace(straddling, dues=replace(straddling.dues, increases=long)), f, 2030
    )
    assert across.dues.increases == (Increase(D("0.03")),)
