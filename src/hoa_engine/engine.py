"""`run(baseline, scenario)` – the year-by-year projection and its summary (spec section 6)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from hoa_engine.dues import resolve_dues
from hoa_engine.model import Baseline, ExpenseLine, Frequency, Scenario, baseline_for
from hoa_engine.validate import validate_run

ZERO = Decimal(0)


class InvalidInputs(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class YearResult:
    year: int
    dues: Decimal  # per unit per month
    assessment_per_unit: Decimal
    total_dues: Decimal
    operating: Decimal
    operating_lines: tuple[tuple[ExpenseLine, Decimal], ...]  # monthly and yearly lines this year
    contribution: Decimal
    assessment: Decimal  # all units
    total_from_owners: Decimal
    interest: Decimal
    expenses: Decimal
    expense_lines: tuple[tuple[ExpenseLine, Decimal], ...]  # reserve lines with this year's amount
    starting_balance: Decimal
    ending_balance: Decimal
    ffb_next: Decimal
    percent_funded: Decimal
    target: Decimal
    low_flag: bool
    target_met: bool
    needs_vote: bool
    operating_shortfall: bool
    owner_dues_year: Decimal
    owner_cost_year: Decimal
    dues_increase_vs_current: Decimal  # dues only, per unit per year
    extra_vs_current: Decimal  # dues increase plus assessment, per unit per year
    cumulative_owner_cost: Decimal
    cumulative_extra: Decimal


@dataclass(frozen=True)
class Summary:
    dues_y1: Decimal
    dues_y4: Decimal
    dues_y9: Decimal | None  # None when the horizon is shorter than 9 years
    total_assessments: Decimal
    lowest_balance: Decimal
    lowest_balance_year: int
    low_years: int
    balance_y4: Decimal
    pf_y4: Decimal
    balance_y9: Decimal | None
    pf_y9: Decimal | None
    balance_end: Decimal
    pf_end: Decimal
    first_target_year: int | None
    outlay_first5: Decimal
    outlay_total: Decimal
    extra_first4: Decimal
    extra_total: Decimal
    avg_owner_cost: Decimal
    avg_extra: Decimal
    vote_years: int
    shortfall_years: int


@dataclass(frozen=True)
class ScenarioResult:
    years: tuple[YearResult, ...]
    summary: Summary


def falls_in(line: ExpenseLine, year: int) -> bool:
    """Whether the line has an amount in `year` (spec 4.1)."""
    if line.frequency is Frequency.ONCE:
        return year == line.year
    if line.end_year is not None and year > line.end_year:
        return False
    if line.frequency is Frequency.EVERY:
        assert line.year is not None and line.interval  # validate_baseline guarantees both
        return year >= line.year and (year - line.year) % line.interval == 0
    return line.year is None or year >= line.year


def line_amount(line: ExpenseLine, year: int, b: Baseline) -> Decimal:
    """The line's amount in `year`, in that year's dollars."""
    if line.frequency.operating:
        rate = b.operating_inflation if line.inflation is None else line.inflation
        first = b.start_year if line.year is None else line.year
        per_year = line.amount * 12 if line.frequency is Frequency.MONTHLY else line.amount
        return per_year * (1 + rate) ** (year - first)
    if line.nominal:
        return line.amount
    return line.amount * (1 + b.expense_inflation) ** (year - b.expense_base_year)


def _needs_vote(
    b: Baseline, dues: Decimal, prior_dues: Decimal, assessment: Decimal, budget: Decimal
) -> bool:
    dues_jump = (
        b.max_dues_increase is not None
        and prior_dues > 0
        and dues / prior_dues - 1 > b.max_dues_increase
    )
    big_assessment = b.max_assessment_share is not None and assessment > (
        b.max_assessment_share * budget
    )
    return dues_jump or big_assessment


def project_years(b: Baseline, s: Scenario) -> tuple[YearResult, ...]:
    dues_by_year = resolve_dues(s, b.years)
    assessment_by_year: dict[int, Decimal] = {}
    for a in s.assessments:
        assessment_by_year[a.year] = assessment_by_year.get(a.year, ZERO) + a.amount
    out = []
    balance = b.starting_balance
    prior_dues = b.current_dues
    cumulative_cost = cumulative_extra = ZERO
    for y in b.years:
        dues = dues_by_year[y]
        per_unit = assessment_by_year.get(y, ZERO)
        total_dues = dues * b.units * 12
        falling = [line for line in b.expense_lines if falls_in(line, y)]
        operating_lines = tuple(
            (line, line_amount(line, y, b)) for line in falling if line.frequency.operating
        )
        lines = tuple(
            (line, line_amount(line, y, b)) for line in falling if not line.frequency.operating
        )
        operating = sum((amount for _, amount in operating_lines), ZERO)
        contribution = max(ZERO, total_dues - operating)
        assessment = per_unit * b.units
        interest = balance * b.interest_rate
        expenses = sum((amount for _, amount in lines), ZERO)
        ending = balance + contribution + assessment + interest - expenses
        ffb_next = b.ffb[y + 1]
        percent_funded = ZERO if ffb_next == 0 else ending / ffb_next
        owner_dues = dues * 12
        dues_increase = (dues - b.current_dues) * 12
        cumulative_cost += owner_dues + per_unit
        cumulative_extra += dues_increase + per_unit
        out.append(
            YearResult(
                year=y,
                dues=dues,
                assessment_per_unit=per_unit,
                total_dues=total_dues,
                operating=operating,
                operating_lines=operating_lines,
                contribution=contribution,
                assessment=assessment,
                total_from_owners=total_dues + assessment,
                interest=interest,
                expenses=expenses,
                expense_lines=lines,
                starting_balance=balance,
                ending_balance=ending,
                ffb_next=ffb_next,
                percent_funded=percent_funded,
                target=b.target,
                low_flag=ending < b.cushion,
                target_met=percent_funded >= b.target,
                needs_vote=_needs_vote(b, dues, prior_dues, assessment, operating + contribution),
                operating_shortfall=total_dues < operating,
                owner_dues_year=owner_dues,
                owner_cost_year=owner_dues + per_unit,
                dues_increase_vs_current=dues_increase,
                extra_vs_current=dues_increase + per_unit,
                cumulative_owner_cost=cumulative_cost,
                cumulative_extra=cumulative_extra,
            )
        )
        balance = ending
        prior_dues = dues
    return tuple(out)


def summarise(years: tuple[YearResult, ...]) -> Summary:
    n = len(years)
    y4, end = years[3], years[-1]
    y9 = years[8] if n >= 9 else None
    lowest = min(years, key=lambda r: r.ending_balance)  # first year on a tie
    first_met = next((r.year for r in years if r.target_met), None)
    return Summary(
        dues_y1=years[0].dues,
        dues_y4=y4.dues,
        dues_y9=None if y9 is None else y9.dues,
        total_assessments=sum((r.assessment_per_unit for r in years), ZERO),
        lowest_balance=lowest.ending_balance,
        lowest_balance_year=lowest.year,
        low_years=sum(r.low_flag for r in years),
        balance_y4=y4.ending_balance,
        pf_y4=y4.percent_funded,
        balance_y9=None if y9 is None else y9.ending_balance,
        pf_y9=None if y9 is None else y9.percent_funded,
        balance_end=end.ending_balance,
        pf_end=end.percent_funded,
        first_target_year=first_met,
        outlay_first5=years[4].cumulative_owner_cost,
        outlay_total=end.cumulative_owner_cost,
        extra_first4=years[3].cumulative_extra,
        extra_total=end.cumulative_extra,
        avg_owner_cost=end.cumulative_owner_cost / n,
        avg_extra=end.cumulative_extra / n,
        vote_years=sum(r.needs_vote for r in years),
        shortfall_years=sum(r.operating_shortfall for r in years),
    )


def run(baseline: Baseline, scenario: Scenario) -> ScenarioResult:
    """Project one scenario against the baseline. Raises InvalidInputs on bad inputs."""
    # A fixed context, so a caller's decimal settings can never change the figures.
    with localcontext(prec=28, rounding=ROUND_HALF_EVEN):
        problems = validate_run(baseline, scenario)
        if problems:
            raise InvalidInputs(problems)
        years = project_years(baseline_for(baseline, scenario), scenario)
        return ScenarioResult(years=years, summary=summarise(years))
