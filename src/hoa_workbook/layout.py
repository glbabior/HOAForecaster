"""Where everything sits in an exported workbook – shared by the writer and the reader.

The layout follows the reference workbook (Method, Inputs, Compare, Charts,
Expenses, one Plan sheet per scenario), generalised to any horizon, the three
dues modes and any number of special assessments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

METHOD, COMPARE, INPUTS, CHARTS, EXPENSES = "Method", "Compare", "Inputs", "Charts", "Expenses"
SHEET_ORDER = (METHOD, INPUTS, COMPARE, CHARTS, EXPENSES)
RESERVED = {*SHEET_ORDER, "History"}  # Excel reserves "History"

HEADER_ROW = 4  # years run across this row on Expenses and Plan sheets
FIRST_INPUT_ROW = 5  # Inputs – first row of values (row 4 is the column header)

# ---------------------------------------------------------------- Inputs sheet


@dataclass(frozen=True)
class InputRow:
    key: str  # Baseline field, or "name" for the project name
    label: str
    kind: str  # "text", "money", "rate", "year", "count"


INPUT_ROWS = (
    InputRow("name", "Association", "text"),
    InputRow("starting_balance", "Starting reserve balance (January 1 of the start year)", "money"),
    InputRow("start_year", "Start year", "year"),
    InputRow("end_year", "End year", "year"),
    InputRow("units", "Number of units", "count"),
    InputRow("current_dues", "Current dues per unit per month", "money"),
    InputRow(
        "operating_inflation",
        "Operating cost inflation per year (monthly and yearly lines without their own)",
        "rate",
    ),
    InputRow("expense_inflation", "Reserve expense inflation per year", "rate"),
    InputRow("expense_base_year", "Expense base year (dollars of the reserve study)", "year"),
    InputRow("interest_rate", "Interest earned on reserves per year", "rate"),
    InputRow("cushion", "Minimum working cushion", "money"),
    InputRow("target", "Percent-funded target", "rate"),
    InputRow("max_dues_increase", "Largest dues increase without an owner vote", "rate"),
    InputRow("max_assessment_share", "Largest assessment without a vote, share of budget", "rate"),
    InputRow("notes", "Project notes", "text"),
)
INPUT_ROW = {r.key: FIRST_INPUT_ROW + i for i, r in enumerate(INPUT_ROWS)}


def input_ref(key: str) -> str:
    return f"{INPUTS}!$B${INPUT_ROW[key]}"


# ---------------------------------------------------------------- Expenses sheet


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
    ExpenseColumn("inflation", "Own inflation (blank – Inputs)"),
    ExpenseColumn("nominal", "Already in that year's dollars?"),
    ExpenseColumn("id", "Line id"),
)
EXPENSE_COL = {c.key: i for i, c in enumerate(EXPENSE_COLUMNS, start=1)}
FIRST_EXPENSE_ROW = 5
EXPENSE_YEAR_COL = len(EXPENSE_COLUMNS) + 1  # the start year
OPERATING_TOTAL_LABEL = "TOTAL operating expenses (monthly and yearly lines)"
EXPENSE_TOTAL_LABEL = "TOTAL projected reserve expenses (once and every few years)"
# how each frequency is written in the How often column
FREQUENCY_TEXT = {
    "monthly": "monthly",
    "yearly": "yearly",
    "every": "every few years",
    "once": "once",
}
FFB_HEADER_LABEL = "Year"
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
    "expenses": (14, "Reserve expenses (Expenses sheet)"),
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
    "target": (31, "Percent-funded target (Inputs)"),
    "mode": (33, "How dues are set"),
    "first": (34, "First-year dues (grown dues only)"),
    "rate": (35, "Annual dues increase (grown dues only)"),
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


def assess_last_row(n_assessments: int) -> int:
    return ASSESS_FIRST_ROW + n_assessments + ASSESS_SPARE_ROWS - 1


def plan_chart_row(n_assessments: int) -> int:
    """Top-left row of a Plan sheet's first chart, below the assessment list."""
    return assess_last_row(n_assessments) + 3


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
