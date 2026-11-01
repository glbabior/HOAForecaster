"""Where everything sits in an exported workbook – shared by the writer and the reader.

The layout follows the reference workbook (Method, Compare, Charts, one Plan
sheet per scenario), generalised to any horizon, the three dues modes and any
number of special assessments. The reference workbook's Inputs and Expenses
sheets are part of every Plan sheet, since each scenario holds all of its own
inputs (spec 7.6); a Project sheet holds the association's name and notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

METHOD, PROJECT, COMPARE, CHARTS = "Method", "Project", "Compare", "Charts"
SHEET_ORDER = (METHOD, PROJECT, COMPARE, CHARTS)
RESERVED = {*SHEET_ORDER, "History"}  # Excel reserves "History"
# the shared sheets of a workbook exported before each scenario held its own inputs
OLD_SHEETS = ("Inputs", "Expenses")

HEADER_ROW = 4  # years run across this row on Plan sheets

# ---------------------------------------------------------------- Project sheet

FIRST_PROJECT_ROW = 5  # the first row of values (row 4 is the column header)
NAME_LABEL, NOTES_LABEL = "Association", "Project notes"
PROJECT_ROW = {"name": FIRST_PROJECT_ROW, "notes": FIRST_PROJECT_ROW + 1}

# ---------------------------------------------------------------- a scenario's facts


@dataclass(frozen=True)
class FactRow:
    key: str  # Facts field
    label: str
    kind: str  # "money", "rate", "year", "count"


FACT_ROWS = (
    FactRow("starting_balance", "Starting reserve balance (January 1 of the start year)", "money"),
    FactRow("start_year", "Start year", "year"),
    FactRow("end_year", "End year", "year"),
    FactRow("units", "Number of units", "count"),
    FactRow("current_dues", "Current dues per unit per month", "money"),
    FactRow(
        "operating_inflation",
        "Operating cost inflation per year (monthly and yearly lines without their own)",
        "rate",
    ),
    FactRow("expense_inflation", "Reserve expense inflation per year", "rate"),
    FactRow("expense_base_year", "Expense base year (dollars of the reserve study)", "year"),
    FactRow("interest_rate", "Interest earned on reserves per year", "rate"),
    FactRow("cushion", "Minimum working cushion", "money"),
    FactRow("target", "Percent-funded target", "rate"),
    FactRow("max_dues_increase", "Largest dues increase without an owner vote", "rate"),
    FactRow("max_assessment_share", "Largest assessment without a vote, share of budget", "rate"),
)

# ---------------------------------------------------------------- a scenario's expenses


@dataclass(frozen=True)
class ExpenseColumn:
    key: str  # ExpenseLine field
    heading: str


# A–I hold a line's inputs; the year columns follow
EXPENSE_COLUMNS = (
    ExpenseColumn("description", "Item"),
    ExpenseColumn("frequency", "How often"),
    ExpenseColumn("amount", "Amount (a month, for monthly lines)"),
    ExpenseColumn("year", "Year, or first year"),
    ExpenseColumn("end_year", "Last year (blank – to the end)"),
    ExpenseColumn("interval", "Every … years"),
    ExpenseColumn(
        "useful_life", "Useful life (one-time costs – every few years uses its interval)"
    ),
    ExpenseColumn("inflation", "Own inflation (blank – the operating rate)"),
    ExpenseColumn("nominal", "Already in that year's dollars?"),
    ExpenseColumn("id", "Line id"),
)
EXPENSE_COL = {c.key: i for i, c in enumerate(EXPENSE_COLUMNS, start=1)}
EXPENSE_YEAR_COL = len(EXPENSE_COLUMNS) + 1  # the start year
# how each frequency is written in the How often column
FREQUENCY_TEXT = {
    "monthly": "monthly",
    "yearly": "yearly",
    "every": "every few years",
    "once": "once",
}
FFB_LABEL = "Fully Funded Balance at start of year"

# ---------------------------------------------------------------- Plan sheets

PLAN_FIRST_COL = 3  # column C is the start year
PLAN_ROWS: dict[str, tuple[int, str]] = {
    "dues": (5, "Dues per unit per month ($)"),
    "sa": (6, "Special assessment per unit ($, this year)"),
    "total_dues": (8, "Total dues collected"),
    "operating": (9, "Operating expenses"),
    "contribution": (10, "Reserve contribution from dues"),
    "sa_total": (11, "Special assessment to reserves"),
    "owners": (12, "Total collected from owners (dues + assessment)"),
    "interest": (13, "Interest earned"),
    "expenses": (14, "Reserve expenses (once and every few years)"),
    "start": (16, "Starting reserve balance"),
    "end": (17, "Ending reserve balance"),
    "ffb": (18, "Fully Funded Balance (start of next year)"),
    "pf": (19, "Percent funded at year end"),
    "low": (20, "Below minimum cushion?"),
    "met": (21, "Meets percent-funded target?"),
    "vote": (22, "Needs owner vote?"),
    "short": (23, "Operating shortfall?"),
    "own_dues": (25, "Owner cost – dues per unit per year"),
    "own_cost": (26, "Owner cost – dues + assessment per unit"),
    "increase": (27, "Increase vs current dues (per unit per year)"),
    "cum_cost": (28, "Cumulative owner cost per unit"),
    "cum_extra": (29, "Cumulative extra cost vs current dues"),
    "extra": (30, "Extra vs current dues, with assessment (per unit per year)"),
    "target": (31, "Percent-funded target (this scenario)"),
    "mode": (33, "How dues are set"),
    "first": (34, "First-year dues (grown dues only)"),
    "rate": (35, "Yearly dues increase (grown dues only)"),  # per year, from the list below
    "pinned": (36, "Pinned dues (blank = grow from the year before)"),
    "grown": (37, "Dues before rounding"),
    "rounding": (38, "Rounding of grown dues"),
}
ROW = {k: row for k, (row, _) in PLAN_ROWS.items()}
ASSESS_HEADING = "Special assessments – one row each (blank rows are spare)"
ASSESS_HEADING_ROW = 40
ASSESS_FIRST_ROW = 42  # row 41 holds the column headings
ASSESS_SPARE_ROWS = 5
ASSESS_NOTE_COL, ASSESS_YEAR_COL, ASSESS_AMOUNT_COL = 1, 3, 4
CHARTS_LABEL = "Charts – "  # starts the label above a Plan sheet's charts
CHART_HEIGHT_ROWS = 22


# a sheet exported before yearly increases had periods – one rate in the first year column
OLD_RATE_LABEL = "Annual dues increase (grown dues only)"
# below the assessments, the yearly dues increases (spec 5.1) – one row each, with spare rows
INCREASES_HEADING = (
    "Yearly dues increases – one row each: the years whose dues rise by it (blank From – the "
    "start, blank To – the end; blank rows are spare)"
)
INCREASE_FROM_COL, INCREASE_TO_COL, INCREASE_RATE_COL = 3, 4, 5
INCREASE_SPARE_ROWS = 3


def assess_last_row(n_assessments: int) -> int:
    return ASSESS_FIRST_ROW + n_assessments + ASSESS_SPARE_ROWS - 1


def increases_heading_row(n_assessments: int) -> int:
    return assess_last_row(n_assessments) + 2


def increases_first_row(n_assessments: int) -> int:
    return increases_heading_row(n_assessments) + 2  # the row between holds the column headings


def increases_last_row(n_assessments: int, n_increases: int) -> int:
    return increases_first_row(n_assessments) + n_increases + INCREASE_SPARE_ROWS - 1


def plan_chart_row(n_assessments: int, n_increases: int) -> int:
    """Top-left row of a Plan sheet's first chart, below the assessments and increases."""
    return increases_last_row(n_assessments, n_increases) + 3


# Below the charts, the scenario's own inputs – each block found by its heading on import.
FACTS_HEADING = "This scenario's facts and assumptions"
VALUE_COL, SOURCE_COL = PLAN_FIRST_COL, PLAN_FIRST_COL + 1
PLAN_FFB_HEADING = "This scenario's Fully Funded Balance"
# the heading before v1.9 – said the figures were the study's even when worked out; still read
PLAN_FFB_HEADING_BEFORE = "This scenario's Fully Funded Balance (from the reserve study)"
PLAN_FFB_YEARS_LABEL = "Start of year"  # the year row above FFB_LABEL; years from VALUE_COL
# the row below FFB_LABEL – where the figures come from, set in the app (spec 4.2), since it
# decides which cells hold formulas
FFB_MODE_LABEL = "Fully Funded Balance from"
FFB_TYPED, FFB_WORKED_OUT = "the reserve study's figures", "this sheet's expenses' useful lives"
# the row below that while worked out – the typed figures, kept for switching back
FFB_KEPT_LABEL = "Reserve study's figures (kept, not used while worked out)"
EXPENSES_HEADING = (
    "This scenario's expenses – one row each (blank rows are spare). To add more, insert rows "
    "inside the list and copy a whole row into them, so its year formulas come with it"
)
EXPENSE_SPARE_ROWS = 3
PLAN_OPERATING_LABEL = "TOTAL operating expenses (monthly and yearly lines)"
PLAN_RESERVE_LABEL = "TOTAL reserve expenses (once and every few years)"
ADOPTED_ON_LABEL, ADOPTION_NOTE_LABEL, ADOPTION_ORDER_LABEL = (
    "Adopted on",
    "Adoption note",
    "Adoption order (the highest is the current plan)",
)  # below the reserve total, on an adopted plan's sheet only


def plan_inputs_row(n_assessments: int, n_increases: int) -> int:
    """The row of the facts heading, below the two charts."""
    return plan_chart_row(n_assessments, n_increases) + 2 * CHART_HEIGHT_ROWS + 1


MODE_TYPED, MODE_GROWN = "typed for each year", "grown from the first year"
ROUND_DOLLAR, ROUND_NONE = "whole dollars", "none – cents kept"

# ---------------------------------------------------------------- sheet names

_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
MAX_SHEET_NAME = 31


def sheet_names(scenario_names: list[str]) -> list[str]:
    """Excel-safe, unique sheet names for the scenarios, in order."""
    used = {n.lower() for n in RESERVED}
    out = []
    for name in scenario_names:
        base = _BAD_SHEET_CHARS.sub(" ", name).strip().strip("'").strip() or "Scenario"
        candidate, n = _trim(base, MAX_SHEET_NAME), 2
        while candidate.lower() in used:
            suffix = f" ({n})"
            candidate = _trim(base, MAX_SHEET_NAME - len(suffix)) + suffix
            n += 1
        used.add(candidate.lower())
        out.append(candidate)
    return out


def _excel_length(name: str) -> int:
    return len(name.encode("utf-16-le")) // 2  # Excel counts UTF-16 code units


def _trim(name: str, length: int) -> str:
    while _excel_length(name) > length:
        name = name[:-1]
    # a sheet name may not end with an apostrophe, even after shortening
    return name.rstrip().rstrip("'").rstrip() or "Scenario"


def quote(sheet: str) -> str:
    """A sheet name as it must appear inside a formula."""
    return "'" + sheet.replace("'", "''") + "'"
