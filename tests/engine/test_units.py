"""Unit tests for the engine's rules (spec sections 4–6), beyond the acceptance figures."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hoa_engine import (
    Assessment,
    Baseline,
    DuesMode,
    DuesPath,
    ExpenseLine,
    Frequency,
    InvalidInputs,
    ProjectFormatError,
    Rounding,
    Scenario,
    baseline_from_dict,
    baseline_to_dict,
    project_from_dict,
    project_to_dict,
    run,
    scenario_from_dict,
    scenario_to_dict,
)
from hoa_engine.dues import resolve_dues
from hoa_engine.validate import validate_baseline, validate_scenario

D = Decimal
DEMO = Path(__file__).resolve().parents[2] / "demo" / "fixtures" / "project.json"


def baseline(**changes: object) -> Baseline:
    b = Baseline(
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
    return Scenario("S", replace(path, **kw))


def explicit(values: list[int], **kw: object) -> Scenario:
    path = DuesPath(DuesMode.EXPLICIT, explicit={2030 + i: D(v) for i, v in enumerate(values)})
    return Scenario("S", path, **kw)


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
    year = run(baseline(), rate("200", "0")).years[1]
    assert year.expenses == D(11000) + D(5000)
    assert [(line.description, amount) for line, amount in year.expense_lines] == [
        ("Roof", D("11000.0")),
        ("Study total", D(5000)),
    ]


def test_operating_shortfall_is_flagged_and_not_taken_from_reserves() -> None:
    year = run(baseline(), rate("90", "0")).years[0]  # 10 800 dues vs 12 000 operating
    assert year.operating_shortfall
    assert year.contribution == 0
    assert year.ending_balance == D(100000) + D(1000)  # balance + interest only


def test_zero_ffb_gives_zero_percent_funded() -> None:
    ffb = {y: D(0) for y in range(2030, 2036)}
    assert run(baseline(ffb=ffb), rate("200", "0")).years[0].percent_funded == 0


def test_needs_vote_on_dues_jump_from_current_dues() -> None:
    years = run(baseline(), explicit([121, 121, 146, 146, 146])).years
    assert [y.needs_vote for y in years] == [True, False, True, False, False]


def test_a_rise_of_exactly_the_limit_needs_no_vote() -> None:
    years = run(baseline(), explicit([120, 144, 144, 144, 144])).years  # +20% twice
    assert not any(y.needs_vote for y in years)


def test_needs_vote_on_assessment_over_budget_share() -> None:
    # budget in 2030 = operating 12 000 + contribution 2 400 = 14 400; 5% = 720 for all units
    over = [Assessment(2030, D(73))]  # 730 total
    under = [Assessment(2030, D(72))]  # 720 total – not more than the limit
    assert run(baseline(), explicit([120] * 5, assessments=over)).years[0].needs_vote
    assert not run(baseline(), explicit([120] * 5, assessments=under)).years[0].needs_vote


def test_no_vote_rules_when_limits_are_absent() -> None:
    b = baseline(max_dues_increase=None, max_assessment_share=None)
    s = explicit([500] * 5, assessments=(Assessment(2030, D(99999)),))
    assert not any(y.needs_vote for y in run(b, s).years)


def test_no_dues_jump_rule_from_zero_dues() -> None:
    years = run(baseline(current_dues=D(0)), explicit([500] * 5)).years
    assert not years[0].needs_vote


def test_assessments_in_the_same_year_add_up() -> None:
    s = explicit([100] * 5, assessments=(Assessment(2031, D(10)), Assessment(2031, D(15))))
    year = run(baseline(), s).years[1]
    assert year.assessment_per_unit == 25
    assert year.assessment == 250


def test_summary_for_a_five_year_horizon() -> None:
    s = explicit([100, 200, 300, 400, 500])
    summary = run(baseline(cushion=D(0)), s).summary
    assert summary.dues_y1 == 100 and summary.dues_y4 == 400
    assert summary.dues_y9 is None and summary.balance_y9 is None and summary.pf_y9 is None
    assert summary.outlay_first5 == (100 + 200 + 300 + 400 + 500) * 12
    assert summary.extra_first4 == (0 + 100 + 200 + 300) * 12
    assert summary.avg_owner_cost == summary.outlay_total / 5
    assert summary.low_years == 0
    assert summary.shortfall_years == 0  # 2030 dues exactly cover operating – not a shortfall


def test_first_target_year() -> None:
    assert run(baseline(), explicit([2000] * 5)).summary.first_target_year == 2030


def test_lowest_balance_and_its_year() -> None:
    # dues exactly cover operating, so the balance moves by interest and the 2031 expenses only –
    # 2030 101 000; 2031 101 000 × 1.01 − 16 000 = 86 010; later years grow from there
    summary = run(baseline(), explicit([100] * 5)).summary
    assert summary.lowest_balance == D("86010.00")
    assert summary.lowest_balance_year == 2031


def test_extra_cost_vs_current_dues_includes_the_assessment() -> None:
    s = explicit([110] * 5, assessments=(Assessment(2031, D(25)),))
    years = run(baseline(), s).years
    assert [y.dues_increase_vs_current for y in years[:2]] == [120, 120]
    assert [y.extra_vs_current for y in years[:2]] == [120, 145]
    assert years[1].cumulative_extra == 265


def test_invalid_inputs_raise_with_every_problem() -> None:
    b = baseline(units=0)
    with pytest.raises(InvalidInputs) as err:
        run(b, explicit([100] * 4))
    assert err.value.problems == [
        "there must be at least one unit",
        "dues are missing for 2034",
    ]


# ---------------------------------------------------------------- validation


def test_an_impossible_horizon_is_reported_alone() -> None:
    # nothing else can be checked over it, and a huge one must not be walked year by year
    assert validate_baseline(baseline(end_year=10**9)) == [
        f"the horizon must be 5–30 full years, not {10**9 - 2030 + 1}"
    ]


def test_validate_baseline_reports_each_rule() -> None:
    b = baseline(
        expense_inflation=D("0.6"),
        target=D(0),
        starting_balance=D(-1),
        expense_lines=(ExpenseLine(2031, D(-5), "Gate"),),
        ffb={2030: D(-1)},
    )
    problems = validate_baseline(b)
    assert problems[0] == "Fully Funded Balance is missing for 2031, 2032, 2033, 2034, 2035"
    assert "expense inflation must be between 0% and 50%" in problems
    assert "the percent-funded target must be above 0% and at most 100%" in problems
    assert "starting balance cannot be negative" in problems
    assert "the 2031 expense 'Gate' cannot be negative" in problems
    assert "Fully Funded Balance for 2030 cannot be negative" in problems


def test_validate_baseline_accepts_the_defaults() -> None:
    assert validate_baseline(baseline()) == []


def test_validate_scenario_reports_each_rule() -> None:
    b = baseline()
    s = Scenario(
        " ",
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
    project = json.loads(DEMO.read_text(encoding="utf-8"))
    b = baseline_from_dict(project["baseline"])
    assert baseline_from_dict(baseline_to_dict(b)) == b
    for raw in project["scenarios"]:
        s = scenario_from_dict(raw)
        assert scenario_from_dict(scenario_to_dict(s)) == s


def test_absent_governance_limits_round_trip() -> None:
    b = baseline(max_dues_increase=None, max_assessment_share=None)
    assert baseline_to_dict(b)["max_dues_increase"] is None
    assert baseline_from_dict(baseline_to_dict(b)) == b


def test_floats_are_refused_in_json() -> None:
    raw = baseline_to_dict(baseline())
    raw["interest_rate"] = 0.01
    with pytest.raises(ProjectFormatError, match="not float"):
        baseline_from_dict(raw)


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
    raw = baseline_to_dict(baseline())
    raw[key] = value
    with pytest.raises(ProjectFormatError, match=message):
        baseline_from_dict(raw)


def test_missing_fields_are_named() -> None:
    raw = scenario_to_dict(explicit([100] * 5))
    del raw["dues"]
    with pytest.raises(ProjectFormatError, match="the scenario is missing 'dues'"):
        scenario_from_dict(raw)


def test_nominal_must_be_a_real_boolean() -> None:
    raw = baseline_to_dict(baseline())
    raw["expense_lines"][0]["nominal"] = "false"
    with pytest.raises(ProjectFormatError, match="expected true or false"):
        baseline_from_dict(raw)


def test_fractional_whole_numbers_are_refused() -> None:
    raw = baseline_to_dict(baseline())
    raw["units"] = 24.9
    with pytest.raises(ProjectFormatError, match="expected a whole number"):
        baseline_from_dict(raw)


def test_expense_base_year_must_be_plausible() -> None:
    assert validate_baseline(baseline(expense_base_year=1900)) == [
        "the expense base year must be between 1980 and 2034"
    ]


def test_number_strings_may_carry_surrounding_spaces() -> None:
    raw = baseline_to_dict(baseline())
    raw["cushion"] = " 50000 "
    assert baseline_from_dict(raw).cushion == 50000


def test_project_files_from_an_unknown_schema_version_are_refused() -> None:
    raw = json.loads(DEMO.read_text(encoding="utf-8"))
    raw["schema_version"] = 99
    with pytest.raises(ProjectFormatError, match="schema version 99 is not supported"):
        project_from_dict(raw)
    raw["schema_version"] = 2
    assert project_to_dict(project_from_dict(raw))["schema_version"] == 2


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
    raw = baseline_to_dict(baseline())
    raw["sources"] = ["a list"]
    with pytest.raises(ProjectFormatError, match="sources should be a set of notes"):
        baseline_from_dict(raw)


# ---------------------------------------------------------------- expense frequencies (4.1)


def lines_only(*lines: ExpenseLine, **changes: object) -> Baseline:
    return baseline(expense_lines=lines, **changes)


def test_monthly_lines_are_twelve_months_grown_from_their_first_year_at_their_own_rate() -> None:
    water = ExpenseLine(2031, D(100), "Water", frequency=Frequency.MONTHLY, inflation=D("0.1"))
    years = run(lines_only(water, operating_inflation=D("0.5")), rate("0", "0")).years
    assert [y.operating for y in years] == [0, 1200, D("1320.0"), D("1452.00"), D("1597.200")]
    assert [(line.description, amount) for line, amount in years[1].operating_lines] == [
        ("Water", D(1200))
    ]
    assert years[1].expense_lines == ()  # operating lines are not reserve expenses


def test_yearly_lines_follow_the_operating_rate_from_the_start_year_until_their_last_year() -> None:
    insurance = ExpenseLine(None, D(1000), "Insurance", frequency=Frequency.YEARLY, end_year=2032)
    years = run(lines_only(insurance, operating_inflation=D("0.1")), rate("0", "0")).years
    assert [y.operating for y in years] == [1000, D("1100.0"), D("1210.00"), 0, 0]


def test_every_few_years_lines_are_reserve_expenses_on_their_interval() -> None:
    paint = ExpenseLine(2030, D(1000), "Paint", frequency=Frequency.EVERY, interval=2)
    years = run(lines_only(paint), rate("200", "0")).years
    # base year 2030, 10% reserve inflation, 2030 · 2032 · 2034
    assert [y.expenses for y in years] == [1000, 0, D("1210.00"), 0, D("1464.1000")]
    assert all(y.operating == 0 for y in years)


def test_every_few_years_lines_stop_after_their_last_year_and_may_be_nominal() -> None:
    paint = ExpenseLine(
        2031, D(500), "Paint", nominal=True, frequency=Frequency.EVERY, interval=1, end_year=2032
    )
    assert [y.expenses for y in run(lines_only(paint), rate("200", "0")).years] == [
        0,
        500,
        500,
        0,
        0,
    ]


def test_operating_lines_feed_the_contribution_shortfall_and_vote_budget() -> None:
    # dues 10 × 100 × 12 = 12 000; operating 1 000 a month = 12 000 – exactly covered
    rent = ExpenseLine(None, D(1000), "Rent", frequency=Frequency.MONTHLY)
    year = run(lines_only(rent), rate("100", "0")).years[0]
    assert (year.operating, year.contribution, year.operating_shortfall) == (12000, 0, False)


def test_expense_lines_are_checked() -> None:
    problems = validate_baseline(
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
    assert validate_baseline(lines_only(far, late)) == [
        "the monthly expense 'Gas' has a year outside 1980–2084",
        "the expense 'Gas' every few years has a year outside 1980–2084",
    ]
    with pytest.raises(InvalidInputs):
        run(lines_only(far), rate("100", "0"))


def test_a_line_keeps_only_the_fields_its_frequency_uses() -> None:
    raw = baseline_to_dict(baseline())
    raw["expense_lines"][0].update(end_year=2032, interval=3, inflation="0.2")
    raw["expense_lines"][2].update(nominal=True, interval=3)
    b = baseline_from_dict(raw)
    assert b.expense_lines[0] == baseline().expense_lines[0]
    assert b.expense_lines[2] == baseline().expense_lines[2]
    assert "nominal" not in baseline_to_dict(b)["expense_lines"][2]


@pytest.mark.parametrize(
    ("ids", "message"),
    [(["a", "a", "b"], "identifiers must be unique – a"), (["a", "b c", "d"], "not a usable")],
)
def test_line_identifiers_must_be_unique_and_plain(ids: list[str], message: str) -> None:
    raw = baseline_to_dict(baseline())
    for line, line_id in zip(raw["expense_lines"], ids, strict=True):
        line["id"] = line_id
    with pytest.raises(ProjectFormatError, match=message):
        baseline_from_dict(raw)


def _version_1(operating: str) -> dict[str, Any]:
    """The test baseline as a schema 1 project, before expense frequencies."""
    raw = baseline_to_dict(baseline())
    raw["expense_lines"] = [
        {k: v for k, v in line.items() if k in ("year", "amount", "description", "nominal")}
        | {"source": ""}
        for line in raw["expense_lines"][:2]
    ]
    raw["operating_start"] = operating
    raw["sources"] = {"operating_start": "Budget"}
    scenario = scenario_to_dict(rate("120", "0.05"))
    return {"schema_version": 1, "name": "P", "baseline": raw, "scenarios": [scenario]}


def test_a_version_1_project_opens_with_the_same_figures() -> None:
    project = project_from_dict(_version_1("12000"))
    b = project.baseline
    operating = b.expense_lines[0]
    assert (operating.frequency, operating.year, operating.inflation) == (
        Frequency.YEARLY,
        None,
        None,
    )
    assert (operating.amount, operating.source, b.sources) == (D(12000), "Budget", {})
    assert [line.id for line in b.expense_lines] == ["operating", "line-1", "line-2"]
    upgraded, expected = run(b, project.scenarios[0]), run(baseline(), project.scenarios[0])
    assert upgraded.summary == expected.summary
    assert [(y.operating, y.expenses, y.ending_balance) for y in upgraded.years] == [
        (y.operating, y.expenses, y.ending_balance) for y in expected.years
    ]
    assert project_to_dict(project)["schema_version"] == 2


def test_a_version_1_project_without_operating_costs_gets_no_operating_line() -> None:
    b = project_from_dict(_version_1("0")).baseline
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
    raw = baseline_to_dict(baseline())
    raw["expense_lines"] = {"roof": {}}
    with pytest.raises(ProjectFormatError, match="expense lines should be a list"):
        baseline_from_dict(raw)
