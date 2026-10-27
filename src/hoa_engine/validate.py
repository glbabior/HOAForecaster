"""Input checks (spec section 4). Each returns a list of plain-language problems."""

from __future__ import annotations

from decimal import Decimal

from hoa_engine.model import DuesMode, ExpenseLine, Facts, Frequency, Scenario

MIN_YEARS, MAX_YEARS = 5, 30
MAX_RATE = Decimal("0.5")
MAX_BASE_YEAR_AGE = 50  # a reserve study older than this is a typo
MAX_LINE_DISTANCE = 50  # an expense year this far before or after the horizon is a typo
MAX_LINES = 1000  # expense lines in a scenario – far beyond any study


def _rate(name: str, value: Decimal | None) -> list[str]:
    if value is None or 0 <= value <= MAX_RATE:
        return []
    return [f"{name} must be between 0% and 50%"]


def _money(name: str, value: Decimal) -> list[str]:
    return [] if value >= 0 else [f"{name} cannot be negative"]


_EVERY_FEW = "every few years"


def line_name(line: ExpenseLine) -> str:
    """'the 2031 expense 'Gate'', 'the monthly expense 'Water'' – for problems."""
    when = {
        Frequency.ONCE: "" if line.year is None else f"{line.year} ",
        Frequency.MONTHLY: "monthly ",
        Frequency.YEARLY: "yearly ",
        Frequency.EVERY: "",
    }[line.frequency]
    tail = f" {_EVERY_FEW}" if line.frequency is Frequency.EVERY else ""
    return f"the {when}expense '{line.description}'{tail}"


def _line(line: ExpenseLine, b: Facts) -> list[str]:
    name = line_name(line)
    problems = _money(name, line.amount)
    # a year far from the horizon is a typo, and would grow amounts past any usable number
    low, high = b.start_year - MAX_LINE_DISTANCE, b.end_year + MAX_LINE_DISTANCE
    if any(y is not None and not low <= y <= high for y in (line.year, line.end_year)):
        problems.append(f"{name} has a year outside {low}–{high}")
    if line.frequency in (Frequency.ONCE, Frequency.EVERY) and line.year is None:
        problems.append(f"{name} needs a year")
    if line.frequency is Frequency.EVERY and (line.interval is None or line.interval < 1):
        problems.append(f"{name} needs a number of years between occurrences, at least 1")
    if line.year is not None and line.end_year is not None and line.end_year < line.year:
        problems.append(f"{name} ends before it starts")
    problems += _rate(f"the inflation rate of {name}", line.inflation)
    return problems


def horizon_problem(b: Facts) -> str | None:
    """The problem with an impossible horizon – one whose years cannot even be walked."""
    span = b.end_year - b.start_year + 1
    if MIN_YEARS <= span <= MAX_YEARS:
        return None
    return f"the horizon must be {MIN_YEARS}–{MAX_YEARS} full years, not {span}"


def validate_facts(b: Facts) -> list[str]:
    problems = []
    horizon = horizon_problem(b)
    if horizon:
        return [horizon]  # nothing else can be checked over an impossible horizon
    if len(b.expense_lines) > MAX_LINES:
        return [f"there are more than {MAX_LINES:,} expense lines"]
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
    problems += _money("current dues", b.current_dues)
    problems += _money("minimum cushion", b.cushion)
    for line in b.expense_lines:
        problems += _line(line, b)
    ids = [line.id for line in b.expense_lines if line.id]
    if len(set(ids)) != len(ids):
        problems.append("two expense lines share an identifier")
    for year, value in sorted(b.ffb.items()):
        problems += _money(f"Fully Funded Balance for {year}", value)
    if b.units < 1:
        problems.append("there must be at least one unit")
    return problems


def validate_run(s: Scenario) -> list[str]:
    """Everything that stops the scenario from running."""
    horizon = horizon_problem(s.facts)
    if horizon:
        return [horizon]  # its years cannot be walked
    return validate_facts(s.facts) + validate_scenario(s, s.facts)


def validate_scenario(s: Scenario, b: Facts) -> list[str]:
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
