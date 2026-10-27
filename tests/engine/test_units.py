"""Unit tests for the engine's rules (spec sections 4–6), beyond the acceptance figures."""

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
    Assessment,
    DuesMode,
    DuesPath,
    ExpenseLine,
    Facts,
    Frequency,
    InvalidInputs,
    Project,
    ProjectFormatError,
    Rounding,
    Scenario,
    ScenarioResult,
    facts_from_dict,
    facts_to_dict,
    project_from_dict,
    project_to_dict,
    run,
    scenario_from_dict,
    scenario_to_dict,
)
from hoa_engine.dues import resolve_dues
from hoa_engine.model import current_adoption
from hoa_engine.upgrade import NO_SCENARIOS_NAME
from hoa_engine.validate import validate_facts, validate_run, validate_scenario

D = Decimal
DEMO = Path(__file__).resolve().parents[2] / "demo" / "fixtures" / "project.json"


def baseline(**changes: object) -> Facts:
    """A scenario's facts – the name the tests have always used."""
    b = Facts(
        start_year=2030,
        end_year=2034,
        starting_balance=D(100000),
        expense_lines=(
            ExpenseLine(2031, D(10000), "Roof", nominal=False, id="roof"),
            ExpenseLine(2031, D(5000), "Study total", nominal=True, id="study"),
            ExpenseLine(None, D(12000), "Operating", frequency=Frequency.YEARLY, id="operating"),
        ),
        expense_inflation=D("0.10"),
        expense_base_year=2030,
        ffb={y: D(200000) for y in range(2030, 2036)},
        operating_inflation=D(0),
        interest_rate=D("0.01"),
        units=10,
        current_dues=D(100),
        cushion=D(50000),
        target=D("0.5"),
    )
    return replace(b, **changes)


def rate(first: str, increase: str, **kw: object) -> Scenario:
    path = DuesPath(DuesMode.RATE, first_value=D(first), annual_increase=D(increase))
    return Scenario("S", baseline(), replace(path, **kw))


def explicit(values: list[int], **kw: object) -> Scenario:
    path = DuesPath(DuesMode.EXPLICIT, explicit={2030 + i: D(v) for i, v in enumerate(values)})
    return Scenario("S", baseline(), path, **kw)  # type: ignore[arg-type]


def on(b: Facts, s: Scenario) -> ScenarioResult:
    """The scenario run on facts `b`."""
    return run(replace(s, facts=b))


# ---------------------------------------------------------------- dues


def test_rate_mode_rounds_each_year_from_unrounded_growth() -> None:
    dues = resolve_dues(rate("100", "0.125"), range(2030, 2034))
    # 112.5 → 113 (half up), 126.5625 → 127, 142.38... → 142 – never 113 × 1.125
    assert dues == {2030: D(100), 2031: D(113), 2032: D(127), 2033: D(142)}


def test_rate_mode_without_rounding_keeps_cents() -> None:
    s = replace(rate("100", "0.125"), rounding=Rounding.NONE)
    assert resolve_dues(s, range(2030, 2032))[2031] == D("112.500")


def test_pinned_year_restarts_growth_and_is_never_rounded() -> None:
    s = rate("100", "0.10", overrides={2031: D("150.40")})
    dues = resolve_dues(s, range(2030, 2034))
    assert dues == {2030: D(100), 2031: D("150.40"), 2032: D(165), 2033: D(182)}


def test_pinning_the_start_year_replaces_the_first_value() -> None:
    s = rate("100", "0", overrides={2030: D(90)})
    assert resolve_dues(s, range(2030, 2032)) == {2030: D(90), 2031: D(90)}


def test_typed_first_value_is_not_rounded() -> None:
    assert resolve_dues(rate("100.40", "0"), range(2030, 2032)) == {
        2030: D("100.40"),
        2031: D(100),
    }


# ---------------------------------------------------------------- engine rules


def test_expense_lines_inflate_unless_nominal_and_are_kept_for_display() -> None:
    year = on(baseline(), rate("200", "0")).years[1]
    assert year.expenses == D(11000) + D(5000)
    assert [(line.description, amount) for line, amount in year.expense_lines] == [
        ("Roof", D("11000.0")),
        ("Study total", D(5000)),
    ]


def test_operating_shortfall_is_flagged_and_not_taken_from_reserves() -> None:
    year = on(baseline(), rate("90", "0")).years[0]  # 10 800 dues vs 12 000 operating
    assert year.operating_shortfall
    assert year.contribution == 0
    assert year.ending_balance == D(100000) + D(1000)  # balance + interest only


def test_zero_ffb_gives_zero_percent_funded() -> None:
    ffb = {y: D(0) for y in range(2030, 2036)}
    assert on(baseline(ffb=ffb), rate("200", "0")).years[0].percent_funded == 0


def test_needs_vote_on_dues_jump_from_current_dues() -> None:
    years = on(baseline(), explicit([121, 121, 146, 146, 146])).years
    assert [y.needs_vote for y in years] == [True, False, True, False, False]


def test_a_rise_of_exactly_the_limit_needs_no_vote() -> None:
    years = on(baseline(), explicit([120, 144, 144, 144, 144])).years  # +20% twice
    assert not any(y.needs_vote for y in years)


def test_needs_vote_on_assessment_over_budget_share() -> None:
    # budget in 2030 = operating 12 000 + contribution 2 400 = 14 400; 5% = 720 for all units
    over = [Assessment(2030, D(73))]  # 730 total
    under = [Assessment(2030, D(72))]  # 720 total – not more than the limit
    assert on(baseline(), explicit([120] * 5, assessments=over)).years[0].needs_vote
    assert not on(baseline(), explicit([120] * 5, assessments=under)).years[0].needs_vote


def test_no_vote_rules_when_limits_are_absent() -> None:
    b = baseline(max_dues_increase=None, max_assessment_share=None)
    s = explicit([500] * 5, assessments=(Assessment(2030, D(99999)),))
    assert not any(y.needs_vote for y in on(b, s).years)


def test_no_dues_jump_rule_from_zero_dues() -> None:
    years = on(baseline(current_dues=D(0)), explicit([500] * 5)).years
    assert not years[0].needs_vote


def test_assessments_in_the_same_year_add_up() -> None:
    s = explicit([100] * 5, assessments=(Assessment(2031, D(10)), Assessment(2031, D(15))))
    year = on(baseline(), s).years[1]
    assert year.assessment_per_unit == 25
    assert year.assessment == 250


def test_summary_for_a_five_year_horizon() -> None:
    s = explicit([100, 200, 300, 400, 500])
    summary = on(baseline(cushion=D(0)), s).summary
    assert summary.dues_y1 == 100 and summary.dues_y4 == 400
    assert summary.dues_y9 is None and summary.balance_y9 is None and summary.pf_y9 is None
    assert summary.outlay_first5 == (100 + 200 + 300 + 400 + 500) * 12
    assert summary.extra_first4 == (0 + 100 + 200 + 300) * 12
    assert summary.avg_owner_cost == summary.outlay_total / 5
    assert summary.low_years == 0
    assert summary.shortfall_years == 0  # 2030 dues exactly cover operating – not a shortfall


def test_first_target_year() -> None:
    assert on(baseline(), explicit([2000] * 5)).summary.first_target_year == 2030


def test_lowest_balance_and_its_year() -> None:
    # dues exactly cover operating, so the balance moves by interest and the 2031 expenses only –
    # 2030 101 000; 2031 101 000 × 1.01 − 16 000 = 86 010; later years grow from there
    summary = on(baseline(), explicit([100] * 5)).summary
    assert summary.lowest_balance == D("86010.00")
    assert summary.lowest_balance_year == 2031


def test_extra_cost_vs_current_dues_includes_the_assessment() -> None:
    s = explicit([110] * 5, assessments=(Assessment(2031, D(25)),))
    years = on(baseline(), s).years
    assert [y.dues_increase_vs_current for y in years[:2]] == [120, 120]
    assert [y.extra_vs_current for y in years[:2]] == [120, 145]
    assert years[1].cumulative_extra == 265


def test_invalid_inputs_raise_with_every_problem() -> None:
    b = baseline(units=0)
    with pytest.raises(InvalidInputs) as err:
        on(b, explicit([100] * 4))
    assert err.value.problems == [
        "there must be at least one unit",
        "dues are missing for 2034",
    ]


# ---------------------------------------------------------------- validation


def test_an_impossible_horizon_is_reported_alone() -> None:
    # nothing else can be checked over it, and a huge one must not be walked year by year
    assert validate_facts(baseline(end_year=10**9)) == [
        f"the horizon must be 5–30 full years, not {10**9 - 2030 + 1}"
    ]


def test_validate_facts_reports_each_rule() -> None:
    b = baseline(
        expense_inflation=D("0.6"),
        target=D(0),
        starting_balance=D(-1),
        expense_lines=(ExpenseLine(2031, D(-5), "Gate"),),
        ffb={2030: D(-1)},
    )
    problems = validate_facts(b)
    assert problems[0] == "Fully Funded Balance is missing for 2031, 2032, 2033, 2034, 2035"
    assert "expense inflation must be between 0% and 50%" in problems
    assert "the percent-funded target must be above 0% and at most 100%" in problems
    assert "starting balance cannot be negative" in problems
    assert "the 2031 expense 'Gate' cannot be negative" in problems
    assert "Fully Funded Balance for 2030 cannot be negative" in problems


def test_validate_facts_accepts_the_defaults() -> None:
    assert validate_facts(baseline()) == []


def test_validate_scenario_reports_each_rule() -> None:
    b = baseline()
    s = Scenario(
        " ",
        b,
        DuesPath(
            DuesMode.RATE,
            first_value=D(-1),
            annual_increase=D("0.9"),
            overrides={2040: D(-2)},
        ),
        assessments=(Assessment(2029, D(-3)),),
    )
    assert validate_scenario(s, b) == [
        "the scenario needs a name",
        "first-year dues cannot be negative",
        "the annual dues increase must be between 0% and 50%",
        "pinned dues year 2040 is outside 2030–2034",
        "pinned dues for 2040 cannot be negative",
        "the 2029 assessment is outside 2030–2034",
        "the 2029 assessment cannot be negative",
    ]
    bad_explicit = explicit([100, -1, 100, 100, 100])
    assert validate_scenario(bad_explicit, b) == ["dues for 2031 cannot be negative"]


# ---------------------------------------------------------------- JSON form


def test_demo_project_round_trips_through_json() -> None:
    raw = json.loads(DEMO.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 3
    project = project_from_dict(raw)
    assert project_to_dict(project) == raw
    for s in project.scenarios:
        assert facts_from_dict(facts_to_dict(s.facts)) == s.facts
        assert scenario_from_dict(scenario_to_dict(s)) == s


def test_absent_governance_limits_round_trip() -> None:
    b = baseline(max_dues_increase=None, max_assessment_share=None)
    assert facts_to_dict(b)["max_dues_increase"] is None
    assert facts_from_dict(facts_to_dict(b)) == b


def test_floats_are_refused_in_json() -> None:
    raw = facts_to_dict(baseline())
    raw["interest_rate"] = 0.01
    with pytest.raises(ProjectFormatError, match="not float"):
        facts_from_dict(raw)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("interest_rate", "NaN", "not a usable number"),
        ("cushion", "Infinity", "not a usable number"),
        ("cushion", "1e999999", "not a usable number"),
        ("cushion", "lots", "not a number"),
        ("cushion", ["1"], "expected a number written as a string"),
        ("units", True, "expected a whole number"),
        ("units", "ten", "bad value"),
    ],
)
def test_unusable_values_are_refused_in_plain_language(
    key: str, value: object, message: str
) -> None:
    raw = facts_to_dict(baseline())
    raw[key] = value
    with pytest.raises(ProjectFormatError, match=message):
        facts_from_dict(raw)


def test_missing_fields_are_named() -> None:
    raw = scenario_to_dict(explicit([100] * 5))
    del raw["dues"]
    with pytest.raises(ProjectFormatError, match="the scenario is missing 'dues'"):
        scenario_from_dict(raw)


def test_nominal_must_be_a_real_boolean() -> None:
    raw = facts_to_dict(baseline())
    raw["expense_lines"][0]["nominal"] = "false"
    with pytest.raises(ProjectFormatError, match="expected true or false"):
        facts_from_dict(raw)


def test_fractional_whole_numbers_are_refused() -> None:
    raw = facts_to_dict(baseline())
    raw["units"] = 24.9
    with pytest.raises(ProjectFormatError, match="expected a whole number"):
        facts_from_dict(raw)


def test_expense_base_year_must_be_plausible() -> None:
    assert validate_facts(baseline(expense_base_year=1900)) == [
        "the expense base year must be between 1980 and 2034"
    ]


def test_number_strings_may_carry_surrounding_spaces() -> None:
    raw = facts_to_dict(baseline())
    raw["cushion"] = " 50000 "
    assert facts_from_dict(raw).cushion == 50000


def test_project_files_from_an_unknown_schema_version_are_refused() -> None:
    raw = json.loads(DEMO.read_text(encoding="utf-8"))
    raw["schema_version"] = 99
    with pytest.raises(ProjectFormatError, match="schema version 99 is not supported"):
        project_from_dict(raw)
    raw["schema_version"] = 3
    assert project_to_dict(project_from_dict(raw))["schema_version"] == 3


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"name": 5}, "expected text"),
        ({"notes": "bell\x07"}, "control characters"),
    ],
)
def test_project_text_must_be_plain_text(change: dict[str, object], message: str) -> None:
    raw = {**json.loads(DEMO.read_text(encoding="utf-8")), **change}
    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(raw)


def test_duplicate_scenario_names_are_refused() -> None:
    raw = json.loads(DEMO.read_text(encoding="utf-8"))
    raw["scenarios"].append(raw["scenarios"][0])
    with pytest.raises(ProjectFormatError, match="scenario names must be unique – 'Dues only'"):
        project_from_dict(raw)


def test_sources_must_be_notes() -> None:
    raw = facts_to_dict(baseline())
    raw["sources"] = ["a list"]
    with pytest.raises(ProjectFormatError, match="sources should be a set of notes"):
        facts_from_dict(raw)


# ---------------------------------------------------------------- expense frequencies (4.1)


def lines_only(*lines: ExpenseLine, **changes: object) -> Facts:
    return baseline(expense_lines=lines, **changes)


def test_monthly_lines_are_twelve_months_grown_from_their_first_year_at_their_own_rate() -> None:
    water = ExpenseLine(2031, D(100), "Water", frequency=Frequency.MONTHLY, inflation=D("0.1"))
    years = on(lines_only(water, operating_inflation=D("0.5")), rate("0", "0")).years
    assert [y.operating for y in years] == [0, 1200, D("1320.0"), D("1452.00"), D("1597.200")]
    assert [(line.description, amount) for line, amount in years[1].operating_lines] == [
        ("Water", D(1200))
    ]
    assert years[1].expense_lines == ()  # operating lines are not reserve expenses


def test_yearly_lines_follow_the_operating_rate_from_the_start_year_until_their_last_year() -> None:
    insurance = ExpenseLine(None, D(1000), "Insurance", frequency=Frequency.YEARLY, end_year=2032)
    years = on(lines_only(insurance, operating_inflation=D("0.1")), rate("0", "0")).years
    assert [y.operating for y in years] == [1000, D("1100.0"), D("1210.00"), 0, 0]


def test_every_few_years_lines_are_reserve_expenses_on_their_interval() -> None:
    paint = ExpenseLine(2030, D(1000), "Paint", frequency=Frequency.EVERY, interval=2)
    years = on(lines_only(paint), rate("200", "0")).years
    # base year 2030, 10% reserve inflation, 2030 · 2032 · 2034
    assert [y.expenses for y in years] == [1000, 0, D("1210.00"), 0, D("1464.1000")]
    assert all(y.operating == 0 for y in years)


def test_every_few_years_lines_stop_after_their_last_year_and_may_be_nominal() -> None:
    paint = ExpenseLine(
        2031, D(500), "Paint", nominal=True, frequency=Frequency.EVERY, interval=1, end_year=2032
    )
    assert [y.expenses for y in on(lines_only(paint), rate("200", "0")).years] == [
        0,
        500,
        500,
        0,
        0,
    ]


def test_operating_lines_feed_the_contribution_shortfall_and_vote_budget() -> None:
    # dues 10 × 100 × 12 = 12 000; operating 1 000 a month = 12 000 – exactly covered
    rent = ExpenseLine(None, D(1000), "Rent", frequency=Frequency.MONTHLY)
    year = on(lines_only(rent), rate("100", "0")).years[0]
    assert (year.operating, year.contribution, year.operating_shortfall) == (12000, 0, False)


def test_expense_lines_are_checked() -> None:
    problems = validate_facts(
        lines_only(
            ExpenseLine(None, D(1), "Roof"),
            ExpenseLine(2031, D(1), "Paint", frequency=Frequency.EVERY),
            ExpenseLine(2031, D(1), "Gutters", frequency=Frequency.EVERY, interval=0),
            ExpenseLine(2032, D(1), "Gas", frequency=Frequency.MONTHLY, end_year=2031),
            ExpenseLine(None, D(1), "Cover", frequency=Frequency.YEARLY, inflation=D("0.6")),
            ExpenseLine(None, D(-1), "Fee", frequency=Frequency.YEARLY, id="a"),
            ExpenseLine(None, D(1), "Fee", frequency=Frequency.YEARLY, id="a"),
        )
    )
    assert problems == [
        "the expense 'Roof' needs a year",
        "the expense 'Paint' every few years needs a number of years between occurrences, "
        "at least 1",
        "the expense 'Gutters' every few years needs a number of years between occurrences, "
        "at least 1",
        "the monthly expense 'Gas' ends before it starts",
        "the inflation rate of the yearly expense 'Cover' must be between 0% and 50%",
        "the yearly expense 'Fee' cannot be negative",
        "two expense lines share an identifier",
    ]


def test_a_line_year_far_from_the_horizon_is_a_problem_not_a_crash() -> None:
    # 1.5 to the power of a trillion years would overflow every calculation
    far = ExpenseLine(-(10**12), D(1), "Gas", frequency=Frequency.MONTHLY, inflation=D("0.5"))
    late = ExpenseLine(2031, D(1), "Gas", frequency=Frequency.EVERY, interval=1, end_year=2085)
    assert validate_facts(lines_only(far, late)) == [
        "the monthly expense 'Gas' has a year outside 1980–2084",
        "the expense 'Gas' every few years has a year outside 1980–2084",
    ]
    with pytest.raises(InvalidInputs):
        on(lines_only(far), rate("100", "0"))


def test_a_line_keeps_only_the_fields_its_frequency_uses() -> None:
    raw = facts_to_dict(baseline())
    raw["expense_lines"][0].update(end_year=2032, interval=3, inflation="0.2")
    raw["expense_lines"][2].update(nominal=True, interval=3)
    b = facts_from_dict(raw)
    assert b.expense_lines[0] == baseline().expense_lines[0]
    assert b.expense_lines[2] == baseline().expense_lines[2]
    assert "nominal" not in facts_to_dict(b)["expense_lines"][2]


@pytest.mark.parametrize(
    ("ids", "message"),
    [
        (["a", "a", "b"], "identifiers must be unique – a"),
        (["a", "b c", "d"], "not a usable"),
        (["a", "Roof", "d"], "not a usable"),  # upper case could match 'roof' in Excel
        (["a", "12", "d"], "not a usable"),  # Excel could read it as a number
    ],
)
def test_line_identifiers_must_be_unique_and_plain(ids: list[str], message: str) -> None:
    raw = facts_to_dict(baseline())
    for line, line_id in zip(raw["expense_lines"], ids, strict=True):
        line["id"] = line_id
    with pytest.raises(ProjectFormatError, match=message):
        facts_from_dict(raw)


def _version_1(operating: str) -> dict[str, Any]:
    """The test baseline as a schema 1 project, before expense frequencies."""
    raw = facts_to_dict(baseline())
    raw["expense_lines"] = [
        {k: v for k, v in line.items() if k in ("year", "amount", "description", "nominal")}
        | {"source": ""}
        for line in raw["expense_lines"][:2]
    ]
    raw["operating_start"] = operating
    raw["sources"] = {"operating_start": "Budget"}
    scenario = {k: v for k, v in scenario_to_dict(rate("120", "0.05")).items() if k != "facts"}
    return {"schema_version": 1, "name": "P", "baseline": raw, "scenarios": [scenario]}


def test_a_version_1_project_opens_with_the_same_figures() -> None:
    project = project_from_dict(_version_1("12000"))
    b = project.scenarios[0].facts
    operating = b.expense_lines[0]
    assert (operating.frequency, operating.year, operating.inflation) == (
        Frequency.YEARLY,
        None,
        None,
    )
    assert (operating.amount, operating.source, b.sources) == (D(12000), "Budget", {})
    assert [line.id for line in b.expense_lines] == ["operating", "line-1", "line-2"]
    upgraded, expected = run(project.scenarios[0]), on(baseline(), project.scenarios[0])
    assert upgraded.summary == expected.summary
    assert [(y.operating, y.expenses, y.ending_balance) for y in upgraded.years] == [
        (y.operating, y.expenses, y.ending_balance) for y in expected.years
    ]
    assert project_to_dict(project)["schema_version"] == 3


def test_a_version_1_project_without_operating_costs_gets_no_operating_line() -> None:
    b = project_from_dict(_version_1("0")).scenarios[0].facts
    assert [line.frequency for line in b.expense_lines] == [Frequency.ONCE, Frequency.ONCE]
    assert b.sources == {}


def test_a_version_1_project_must_have_lines_as_objects() -> None:
    raw = _version_1("0")
    raw["baseline"]["expense_lines"] = ["roof"]
    with pytest.raises(ProjectFormatError, match="list of objects"):
        project_from_dict(raw)
    raw["baseline"] = "a baseline"
    with pytest.raises(ProjectFormatError, match="the baseline should be an object"):
        project_from_dict(raw)


def test_expense_lines_must_be_a_list() -> None:
    raw = facts_to_dict(baseline())
    raw["expense_lines"] = {"roof": {}}
    with pytest.raises(ProjectFormatError, match="expense lines should be a list"):
        facts_from_dict(raw)


# ---------------------------------------------------------------- a scenario's own inputs


def test_each_scenario_runs_on_its_own_facts() -> None:
    low, high = rate("200", "0"), replace(rate("200", "0"), facts=baseline(interest_rate=D("0.05")))
    assert run(low).years[0].interest == 1000
    assert run(high).years[0].interest == 5000


def test_a_scenario_without_governance_limits_needs_no_vote() -> None:
    jump = rate("200", "0.5")
    assert run(jump).summary.vote_years == 5
    assert on(baseline(max_dues_increase=None), jump).summary.vote_years == 0


def test_a_scenario_is_checked_on_its_own_horizon() -> None:
    longer = baseline(end_year=2036)
    with pytest.raises(InvalidInputs) as e:
        on(longer, rate("200", "0"))
    assert e.value.problems == ["Fully Funded Balance is missing for 2036, 2037"]
    ok = replace(longer, ffb={**longer.ffb, 2036: D(1), 2037: D(1)})
    assert [y.year for y in on(ok, rate("200", "0")).years] == list(range(2030, 2037))
    typed = replace(explicit([100] * 5), facts=baseline(start_year=2029))
    assert "dues are missing for 2029" in validate_run(typed)


def test_an_impossible_horizon_of_a_scenario_is_reported_alone() -> None:
    huge = replace(explicit([100] * 5), facts=baseline(end_year=10**9))
    assert validate_run(huge) == [f"the horizon must be 5–30 full years, not {10**9 - 2030 + 1}"]


def test_absurd_numbers_of_lines_are_refused() -> None:
    many = tuple(ExpenseLine(2031, D(1), id=f"l{i}") for i in range(1001))
    assert validate_facts(baseline(expense_lines=many)) == [
        "there are more than 1,000 expense lines"
    ]


def test_a_scenario_without_facts_is_refused() -> None:
    raw = scenario_to_dict(rate("1", "0"))
    del raw["facts"]
    with pytest.raises(ProjectFormatError, match="the scenario is missing 'facts'"):
        scenario_from_dict(raw)


def test_unusable_facts_are_refused_in_plain_language() -> None:
    raw = scenario_to_dict(rate("1", "0"))
    del raw["facts"]["units"]
    with pytest.raises(ProjectFormatError, match="set of facts and assumptions is missing 'units'"):
        scenario_from_dict(raw)


# ---------------------------------------------------------------- adopted plans (5.2)


def adopted(s: Scenario, sequence: int = 1) -> Scenario:
    return replace(s, adoption=Adoption(date(2026, 11, 3), "Vote", sequence))


def test_an_adopted_plan_runs_on_its_own_inputs() -> None:
    plan = adopted(rate("200", "0"))
    assert run(plan).summary == run(replace(plan, adoption=None)).summary


def test_adoptions_round_trip_and_the_latest_is_current() -> None:
    first, second = adopted(rate("1", "0"), 1), replace(adopted(rate("2", "0"), 2), name="T")
    project = Project("P", (second, first, replace(rate("3", "0"), name="U")))
    again = project_from_dict(project_to_dict(project))
    assert again == project
    assert "baseline" not in project_to_dict(project)["scenarios"][0]["adoption"]
    assert current_adoption(again.scenarios) == second
    assert current_adoption((rate("1", "0"),)) is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"sequence": 0}, "order must be 1 to 10,000"),
        ({"sequence": 10_001}, "order must be 1 to 10,000"),
        ({"note": "x" * 2001}, "at most 2,000 characters"),
        ({"date": "20261103"}, "not a date written YYYY-MM-DD"),
        ({"date": "soon"}, "not a date written YYYY-MM-DD"),
        ("adopted", "adoption should be an object"),
    ],
)
def test_unusable_adoptions_are_refused(change: object, message: str) -> None:
    raw = scenario_to_dict(adopted(rate("1", "0")))
    raw["adoption"] = {**raw["adoption"], **change} if isinstance(change, dict) else change
    with pytest.raises(ProjectFormatError, match=message):
        scenario_from_dict(raw)


def test_two_plans_cannot_share_an_adoption_order() -> None:
    plans = (adopted(rate("1", "0")), replace(adopted(rate("2", "0")), name="T"))
    with pytest.raises(ProjectFormatError, match="same adoption order"):
        project_from_dict(project_to_dict(Project("P", plans)))


# ---------------------------------------------------------------- the schema 2 upgrade (8.2)


def _plain(s: Scenario) -> dict[str, Any]:
    """A scenario in schema 2 form, before its changes – no facts of its own."""
    return {k: v for k, v in scenario_to_dict(s).items() if k != "facts"}


def _version_2(*scenarios: dict[str, Any], b: Facts | None = None) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "name": "P",
        "notes": "N",
        "baseline": facts_to_dict(b or baseline()),
        "scenarios": list(scenarios),
    }


def _upgraded(raw: dict[str, Any]) -> Project:
    project = project_from_dict(raw)
    assert project_to_dict(project)["schema_version"] == 3
    return project


def test_a_version_2_scenario_receives_the_baseline_it_saw() -> None:
    plain = _plain(rate("200", "0"))
    (s,) = _upgraded(_version_2(plain)).scenarios
    assert s.facts == baseline()
    assert (s.name, s.dues) == ("S", rate("200", "0").dues)


def test_a_version_2_scenario_gets_its_changes_applied() -> None:
    raw = _plain(rate("200", "0"))
    raw["changes"] = {
        "values": {"interest_rate": "0.05", "start_year": 2030, "max_dues_increase": None},
        "sources": {"interest_rate": "Bank", "cushion": ""},  # a blank note is no change
        "expense_lines": {
            "roof": {"frequency": "once", "year": 2032, "amount": "1", "description": "Later"},
            "study": None,
            "gate": {"frequency": "once", "year": 2033, "amount": "7", "description": "Gate"},
            "gone": None,  # a leave-out of a line the baseline no longer has does nothing
        },
        "ffb": {"2031": "100000"},
    }
    b = replace(baseline(), sources={"cushion": "Board"})
    (s,) = _upgraded(_version_2(raw, b=b)).scenarios
    f = s.facts
    assert (f.interest_rate, f.max_dues_increase) == (D("0.05"), None)
    assert f.sources == {"cushion": "Board", "interest_rate": "Bank"}
    # a changed line in its baseline line's place, the baseline's next, its own last
    assert [line.id for line in f.expense_lines] == ["roof", "operating", "gate"]
    assert (f.expense_lines[0].year, f.expense_lines[0].description) == (2032, "Later")
    assert (f.ffb[2030], f.ffb[2031]) == (D(200000), D(100000))


def test_a_version_2_adopted_plan_keeps_its_frozen_baseline() -> None:
    raw = _plain(rate("200", "0"))
    frozen = baseline(interest_rate=D("0.03"), units=12)
    raw["changes"] = {"values": {"units": 12}}  # already in the frozen copy – applying it again
    raw["adoption"] = {"date": "2026-11-03", "note": "Vote", "sequence": 1}
    raw["adoption"]["baseline"] = facts_to_dict(frozen)
    (s,) = _upgraded(_version_2(raw, b=baseline(units=99))).scenarios
    assert s.facts == frozen
    assert s.adoption == Adoption(date(2026, 11, 3), "Vote", 1)


def test_a_version_2_project_without_scenarios_gets_one_at_current_dues() -> None:
    project = _upgraded(_version_2())
    assert (project.name, project.notes) == ("P", "N")
    (s,) = project.scenarios
    assert s.name == NO_SCENARIOS_NAME
    assert s.facts == baseline()
    assert (s.dues.mode, s.dues.first_value, s.dues.annual_increase) == (
        DuesMode.RATE,
        D(100),
        D(0),
    )
    assert run(s).years[0].dues == 100


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"scenarios": "all"}, "scenarios should be a list of objects"),
        ({"scenarios": ["S"]}, "scenarios should be a list of objects"),
        ({"baseline": {"start_year": 2030}}, "missing 'end_year'"),
    ],
)
def test_unusable_version_2_projects_are_refused(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict({**_version_2(_plain(rate("1", "0"))), **change})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"values": {"name": "x"}}, "'name' is not a baseline input a scenario can change"),
        ({"values": {"cushion": None}}, "only a governance limit can be changed to no limit"),
        ({"values": {"units": "2.5"}}, "bad value"),
        ({"expense_lines": []}, "expense line changes should be an object"),
        ({"expense_lines": {"a b": None}}, "not a usable expense line identifier"),
        ("all", "changes should be an object"),
    ],
)
def test_unusable_version_2_changes_are_refused(changes: object, message: str) -> None:
    raw = _plain(rate("1", "0"))
    raw["changes"] = changes
    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(_version_2(raw))


def test_a_version_2_adoption_must_be_an_object() -> None:
    raw = _plain(rate("1", "0"))
    raw["adoption"] = "adopted"
    with pytest.raises(ProjectFormatError, match="an adoption should be an object"):
        project_from_dict(_version_2(raw))


def test_a_version_2_file_cannot_grow_too_large_while_it_is_upgraded() -> None:
    # each scenario gets its own copy of the baseline's lines – a small crafted file must not
    # turn into one too large to hold
    line = {"id": "x", "frequency": "once", "year": 2030, "amount": "1", "description": ""}
    many = [{**line, "id": f"l{i}"} for i in range(1001)]
    raw = _version_2(_plain(rate("200", "0")))
    raw["baseline"]["expense_lines"] = many
    with pytest.raises(ProjectFormatError, match="more than 1,000 expense lines"):
        project_from_dict(raw)
    raw["baseline"]["expense_lines"] = many[:500]
    scenarios = [{**_plain(rate("200", "0")), "name": f"S{i}"} for i in range(101)]
    with pytest.raises(ProjectFormatError, match="too large to upgrade"):
        project_from_dict({**raw, "scenarios": scenarios})
    changes = {"expense_lines": {f"c{i}": None for i in range(1001)}}
    with pytest.raises(ProjectFormatError, match="changes more than 1,000"):
        project_from_dict(_version_2({**_plain(rate("200", "0")), "changes": changes}))


def test_a_project_holds_at_most_200_scenarios() -> None:
    plain = scenario_to_dict(rate("200", "0"))
    raw = project_to_dict(Project("P", ()))
    raw["scenarios"] = [{**plain, "name": f"S{i}"} for i in range(201)]
    with pytest.raises(ProjectFormatError, match="at most 200 scenarios"):
        project_from_dict(raw)
    raw["scenarios"] = raw["scenarios"][:200]
    assert len(project_from_dict(raw).scenarios) == 200


def test_the_schema_2_demo_upgrades_to_todays_demo() -> None:
    old = json.loads((Path(__file__).parent / "fixtures" / "demo_schema2.json").read_text("utf-8"))
    today = json.loads(DEMO.read_text(encoding="utf-8"))
    upgraded, now = project_from_dict(old), project_from_dict(today)
    # today's demo has one scenario more – the worked-out Fully Funded Balance (spec 4.2)
    assert upgraded == replace(now, scenarios=now.scenarios[: len(upgraded.scenarios)])


def test_version_2_lines_of_a_scenarios_own_never_share_an_id_with_a_different_line() -> None:
    def own(amount: str) -> dict[str, Any]:
        line = {"frequency": "once", "year": 2030, "amount": amount, "description": "Own"}
        return {**_plain(rate("200", "0")), "changes": {"expense_lines": {"own-1": line}}}

    a, b, c = own("1"), {**own("2"), "name": "T"}, {**own("1"), "name": "U"}
    first, second, third = _upgraded(_version_2(a, b, c)).scenarios
    ids = [[line.id for line in s.facts.expense_lines] for s in (first, second, third)]
    assert ids[0][-1] == "own-1" and ids[2][-1] == "own-1"  # the same line, copied – one id
    assert ids[1][-1] not in ("own-1", *ids[1][:-1])  # a different line – an id of its own
    assert second.facts.expense_lines[-1].amount == D(2)


def test_a_renamed_version_2_line_skips_ids_already_taken() -> None:
    def own(**lines: str) -> dict[str, Any]:
        made = {
            i: {"frequency": "once", "year": 2030, "amount": a, "description": "Own"}
            for i, a in lines.items()
        }
        return {**_plain(rate("200", "0")), "changes": {"expense_lines": made}}

    first = own(**{"own-1": "1", "line-1": "5"})
    second = {**own(**{"own-1": "2"}), "name": "T"}
    _, renamed = _upgraded(_version_2(first, second)).scenarios
    assert renamed.facts.expense_lines[-1].id == "line-2"


# ---------------------------------------------------------------- the worked-out FFB (4.2)


def _components() -> Facts:
    every = Frequency.EVERY
    return baseline(
        ffb={},  # not needed when worked out
        ffb_from_lines=True,
        expense_lines=(
            # recoated every 10 years, next in 2032 – 8 years old at the start of 2030
            ExpenseLine(2032, D(1000), "Roof", frequency=every, interval=10, id="roof"),
            # 30 years left of a 50-year life; its amount is in 2060's dollars
            ExpenseLine(2060, D(1000), "Siding", nominal=True, useful_life=50, id="siding"),
            ExpenseLine(2031, D(9999), "No life given", id="unknown"),
            # first fitted in 2040 with a 5-year life – not in service yet
            ExpenseLine(2040, D(700), "New gate", useful_life=5, id="gate"),
            # every 2 years from 2030, the last time in 2031
            ExpenseLine(2030, D(100), "Pump", frequency=every, interval=2, end_year=2031, id="p"),
            ExpenseLine(None, D(5000), "Water", frequency=Frequency.YEARLY, id="water"),
        ),
    )


def test_the_ffb_is_worked_out_from_each_reserve_lines_age_and_useful_life() -> None:
    f = _components()
    ffb = run(Scenario("S", f, rate("100", "0").dues)).ffb
    g = D("1.1")  # reserve inflation from the 2030 base year
    siding = lambda y: D(1000) / g ** (2060 - y) * (50 - (2060 - y)) / 50  # noqa: E731
    expected = {
        2030: D(1000) * 8 / 10 + siding(2030) + D(100),  # the pump is due – fully deteriorated
        2031: D(1000) * g * 9 / 10 + siding(2031) + D(100) * g * 1 / 2,
        2032: D(1000) * g**2 + siding(2032),  # due again – the pump is retired after 2031
        2033: D(1000) * g**3 * 1 / 10 + siding(2033),  # renewed in 2032 – a year old
        2034: D(1000) * g**4 * 2 / 10 + siding(2034),
        2035: D(1000) * g**5 * 3 / 10 + siding(2035),
    }
    assert ffb == expected


def test_a_worked_out_ffb_feeds_percent_funded_and_needs_no_typed_figures() -> None:
    f = _components()
    assert validate_facts(f) == []
    s = Scenario("S", f, rate("100", "0").dues)
    result = run(s)
    for y in result.years:
        assert y.ffb_next == result.ffb[y.year + 1]
        assert y.percent_funded == y.ending_balance / y.ffb_next
    typed = replace(f, ffb_from_lines=False)
    assert any("Fully Funded Balance is missing" in p for p in validate_facts(typed))
    # typed, the result carries the typed figures
    assert run(replace(s, facts=baseline())).ffb == baseline().ffb


def test_a_useful_life_must_be_at_least_a_year_and_belongs_to_once_lines() -> None:
    f = baseline(expense_lines=(ExpenseLine(2031, D(1), "Gate", useful_life=0, id="g"),))
    assert "the 2031 expense 'Gate' needs a useful life of at least 1 year" in validate_facts(f)
    raw = facts_to_dict(_components())
    assert raw["ffb_from_lines"] is True
    lines = {line["id"]: line for line in raw["expense_lines"]}
    assert lines["siding"]["useful_life"] == 50
    assert "useful_life" not in lines["roof"]  # an every-few-years line's life is its interval
    raw["expense_lines"][0]["useful_life"] = 7  # a stale field is dropped on reading
    again = facts_from_dict(raw)
    assert again == _components()
    assert again.expense_lines[0].life == 10 and again.expense_lines[5].life is None


def test_a_nominal_every_few_years_lines_cost_is_deflated_from_its_next_occurrence() -> None:
    # the same $1,000 falls in 2032, 2042, … – so in 2033 it is a year past and 9 years ahead
    line = ExpenseLine(2032, D(1000), "Pump", frequency=Frequency.EVERY, interval=10, nominal=True)
    f = baseline(ffb={}, ffb_from_lines=True, expense_lines=(line,))
    ffb = run(Scenario("S", f, rate("100", "0").dues)).ffb
    g = D("1.1")
    assert ffb[2030] == D(1000) / g**2 * 8 / 10
    assert ffb[2033] == D(1000) / g**9 * 1 / 10
