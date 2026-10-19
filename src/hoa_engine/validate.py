"""Input checks (spec section 4). Each returns a list of plain-language problems."""

from __future__ import annotations

from decimal import Decimal

from hoa_engine.model import Baseline, DuesMode, Scenario

MIN_YEARS, MAX_YEARS = 5, 30
MAX_RATE = Decimal("0.5")
MAX_BASE_YEAR_AGE = 50  # a reserve study older than this is a typo


def _rate(name: str, value: Decimal | None) -> list[str]:
    if value is None or 0 <= value <= MAX_RATE:
        return []
    return [f"{name} must be between 0% and 50%"]


def _money(name: str, value: Decimal) -> list[str]:
    return [] if value >= 0 else [f"{name} cannot be negative"]


def validate_baseline(b: Baseline) -> list[str]:
    problems = []
    span = b.end_year - b.start_year + 1
    if not MIN_YEARS <= span <= MAX_YEARS:
        problems.append(f"the horizon must be {MIN_YEARS}–{MAX_YEARS} full years, not {span}")
        return problems  # nothing else can be checked over an impossible horizon
    missing = [y for y in range(b.start_year, b.end_year + 2) if y not in b.ffb]
    if missing:
        problems.append("Fully Funded Balance is missing for " + ", ".join(str(y) for y in missing))
    if not b.start_year - MAX_BASE_YEAR_AGE <= b.expense_base_year <= b.end_year:
        problems.append(
            f"the expense base year must be between {b.start_year - MAX_BASE_YEAR_AGE} "
            f"and {b.end_year}"
        )
    problems += _rate("expense inflation", b.expense_inflation)
    problems += _rate("operating inflation", b.operating_inflation)
    problems += _rate("interest rate", b.interest_rate)
    problems += _rate("the dues-increase limit", b.max_dues_increase)
    problems += _rate("the assessment limit", b.max_assessment_share)
    if not 0 < b.target <= 1:
        problems.append("the percent-funded target must be above 0% and at most 100%")
    problems += _money("starting balance", b.starting_balance)
    problems += _money("operating expenses", b.operating_start)
    problems += _money("current dues", b.current_dues)
    problems += _money("minimum cushion", b.cushion)
    for line in b.expense_lines:
        problems += _money(f"the {line.year} expense '{line.description}'", line.amount)
    for year, value in sorted(b.ffb.items()):
        problems += _money(f"Fully Funded Balance for {year}", value)
    if b.units < 1:
        problems.append("there must be at least one unit")
    return problems


def validate_scenario(s: Scenario, b: Baseline) -> list[str]:
    problems = []
    years = b.years
    if not s.name.strip():
        problems.append("the scenario needs a name")
    if s.dues.mode is DuesMode.EXPLICIT:
        missing = [y for y in years if y not in s.dues.explicit]
        if missing:
            problems.append("dues are missing for " + ", ".join(str(y) for y in missing))
        for year, value in sorted(s.dues.explicit.items()):
            problems += _money(f"dues for {year}", value)
    else:
        problems += _money("first-year dues", s.dues.first_value)
        problems += _rate("the annual dues increase", s.dues.annual_increase)
        for year, value in sorted(s.dues.overrides.items()):
            if year not in years:
                problems.append(f"pinned dues year {year} is outside {years.start}–{years[-1]}")
            problems += _money(f"pinned dues for {year}", value)
    for a in s.assessments:
        if a.year not in years:
            problems.append(f"the {a.year} assessment is outside {years.start}–{years[-1]}")
        problems += _money(f"the {a.year} assessment", a.amount)
    return problems
