"""Write a project as an Excel workbook with live formulas (spec section 7.6).

Every result cell is a formula over the Inputs, Expenses and Plan input rows,
so the workbook recalculates on its own when a board member edits it. This
module never runs the engine; its formulas are a second, independent
implementation of section 6, and the tests hold the two to the same figures.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.cell import Cell
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as col_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from hoa_engine.model import Baseline, DuesMode, Project, Rounding, Scenario
from hoa_engine.validate import validate_baseline
from hoa_workbook import charts
from hoa_workbook.layout import (
    ASSESS_AMOUNT_COL,
    ASSESS_FIRST_ROW,
    ASSESS_HEADING,
    ASSESS_HEADING_ROW,
    ASSESS_NOTE_COL,
    ASSESS_YEAR_COL,
    CHARTS,
    COMPARE,
    EXPENSE_COLUMNS,
    EXPENSE_TOTAL_LABEL,
    EXPENSE_YEAR_COL,
    EXPENSES,
    FFB_HEADER_LABEL,
    FFB_LABEL,
    FIRST_EXPENSE_ROW,
    FIRST_INPUT_ROW,
    HEADER_ROW,
    INPUT_ROWS,
    INPUTS,
    METHOD,
    MODE_GROWN,
    MODE_TYPED,
    PLAN_FIRST_COL,
    PLAN_ROWS,
    ROUND_DOLLAR,
    ROUND_NONE,
    ROW,
    SHEET_ORDER,
    assess_last_row,
    input_ref,
    plan_chart_row,
    quote,
    sheet_names,
)

FONT = "Arial"
BLUE, GREEN, BLACK = "0000FF", "008000", "000000"
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEADER_FILL = PatternFill("solid", fgColor="DCE6F0")
TOTAL_FILL = PatternFill("solid", fgColor="F2F2F2")
LOW_FILL = PatternFill("solid", fgColor="F4CCCC")
YES_FILL = PatternFill("solid", fgColor="D9EAD3")
WARN_FILL = PatternFill("solid", fgColor="FCE5CD")
CUR = "$#,##0;($#,##0);-"
CUR_CENTS = "$#,##0.00;($#,##0.00);-"
PCT = "0.0%"
YEAR = "0"
AUTHOR = "HOAForecaster"
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _font(bold: bool = False, color: str = BLACK, size: int = 10, italic: bool = False) -> Font:
    return Font(name=FONT, bold=bold, color=color, size=size, italic=italic)


def _text(cell: Cell, value: str, **font: Any) -> None:
    """User text is always written as text – a leading = + - @ never starts a formula."""
    cell.value = value
    cell.data_type = "s"
    cell.font = _font(**font)
    if value[:1] in FORMULA_STARTS:
        cell.quotePrefix = True  # stays text even if the cell is edited or saved as CSV


def _input(cell: Cell, value: Decimal | int | None, fmt: str) -> None:
    if value is not None:
        cell.value = int(value) if isinstance(value, int) else _number(value)
    cell.font, cell.fill, cell.number_format = _font(color=BLUE), YELLOW, fmt


def _number(value: Decimal) -> int | float:
    # Excel stores IEEE doubles; whole amounts stay exact integers
    return int(value) if value == value.to_integral_value() else float(value)


def _formula(cell: Cell, formula: str, fmt: str, color: str = BLACK, bold: bool = False) -> None:
    cell.value = formula
    cell.number_format = fmt
    cell.font = _font(bold=bold, color=color)
    cell.alignment = Alignment(horizontal="right")


def _header(ws: Worksheet, row: int, first: int, last: int) -> None:
    for c in range(first, last + 1):
        ws.cell(row, c).fill = HEADER_FILL
        ws.cell(row, c).font = _font(bold=True)


def _widths(ws: Worksheet, widths: Sequence[float]) -> None:
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[col_letter(i)].width = w


def _comment(cell: Cell, text: str) -> None:
    if text:
        cell.comment = Comment(text, AUTHOR, width=320, height=110)


ROW_NOTES = {
    "operating": "Operating expenses in the start year, grown at the operating inflation rate on "
    "Inputs. Any dues above operating cost go to reserves.",
    "contribution": "Total dues less operating expenses, never below zero. A shortfall is flagged "
    "below, not taken from reserves.",
    "pf": "Year-end balance divided by the reserve study's Fully Funded Balance at the start of "
    "the following year. Under 30% is weak, 30–70% fair, over 70% strong.",
}


@dataclass(frozen=True)
class _Plan:
    scenario: Scenario
    sheet: str


# ---------------------------------------------------------------- Inputs


def _inputs(wb: Workbook, project: Project) -> None:
    b = project.baseline
    ws = wb.create_sheet(INPUTS)
    _widths(ws, [52, 18, 80])
    _text(ws["A1"], f"{project.name} – Inputs", bold=True, size=13)
    _text(
        ws["A2"],
        "Blue text on yellow – inputs to edit. Black – formulas. Green – pulled from another "
        "sheet. Update inputs as facts are confirmed and everything else recalculates.",
        italic=True,
        size=9,
    )
    for col, heading in enumerate(("Assumption", "Value", "Source / note"), start=1):
        ws.cell(FIRST_INPUT_ROW - 1, col, heading)
    _header(ws, FIRST_INPUT_ROW - 1, 1, 3)
    formats = {"money": CUR, "rate": PCT, "year": YEAR, "count": "0"}
    for i, row in enumerate(INPUT_ROWS):
        r = FIRST_INPUT_ROW + i
        _text(ws.cell(r, 1), row.label)
        if row.kind == "text":
            _text(ws.cell(r, 2), project.name if row.key == "name" else project.notes, color=BLUE)
            ws.cell(r, 2).fill = YELLOW
            ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
        else:
            value = getattr(b, row.key)
            _input(
                ws.cell(r, 2), value, CUR_CENTS if row.key == "current_dues" else formats[row.kind]
            )
        _text(ws.cell(r, 3), b.sources.get(row.key, ""), size=9)
        ws.cell(r, 3).alignment = Alignment(wrap_text=True, vertical="top")


# ---------------------------------------------------------------- Expenses


@dataclass(frozen=True)
class _ExpenseRefs:
    year_col: dict[int, str]
    total_row: int
    ffb_col: dict[int, str]
    ffb_row: int


def _expenses(wb: Workbook, b: Baseline) -> _ExpenseRefs:
    ws = wb.create_sheet(EXPENSES)
    years = list(b.years)
    _widths(ws, [52, 14, 8, 12] + [12] * (len(years) + 1))
    _text(ws["A1"], "Projected reserve expenses by year ($)", bold=True, size=13)
    _text(
        ws["A2"],
        "One row per expense. Amounts are in the expense base year's dollars and grow at the "
        "reserve expense inflation rate to the year they fall in, unless marked as already in "
        "that year's dollars. To add an expense, copy a whole row and insert it inside the "
        "table, so its year formulas come with it.",
        italic=True,
        size=9,
    )
    year_col = {y: col_letter(EXPENSE_YEAR_COL + i) for i, y in enumerate(years)}
    for col, heading in enumerate(EXPENSE_COLUMNS, start=1):
        ws.cell(HEADER_ROW, col, heading)
    for y in years:
        ws[f"{year_col[y]}{HEADER_ROW}"] = y
        ws[f"{year_col[y]}{HEADER_ROW}"].number_format = YEAR
    _header(ws, HEADER_ROW, 1, EXPENSE_YEAR_COL + len(years) - 1)

    inflation, base = input_ref("expense_inflation"), input_ref("expense_base_year")
    r = FIRST_EXPENSE_ROW
    for line in b.expense_lines:  # the user's order, so a re-import is identical
        _text(ws.cell(r, 1), line.description)
        _comment(ws.cell(r, 1), line.source)
        _input(ws.cell(r, 2), line.amount, CUR)
        _input(ws.cell(r, 3), line.year, YEAR)
        ws.cell(r, 4).value = "yes" if line.nominal else "no"
        ws.cell(r, 4).font, ws.cell(r, 4).fill = _font(color=BLUE), YELLOW
        ws.cell(r, 4).alignment = Alignment(horizontal="center")
        for y in years:
            c = year_col[y]
            _formula(
                ws[f"{c}{r}"],
                f'=IF({c}${HEADER_ROW}=$C{r},$B{r}*IF($D{r}="yes",1,'
                f"(1+{inflation})^({c}${HEADER_ROW}-{base})),0)",
                CUR,
            )
        r += 1
    last_line = max(r - 1, FIRST_EXPENSE_ROW)  # an empty table still sums one blank row
    total_row = last_line + 2
    _text(ws.cell(total_row, 1), EXPENSE_TOTAL_LABEL, bold=True)
    for y in years:
        c = year_col[y]
        _formula(
            ws[f"{c}{total_row}"], f"=SUM({c}{FIRST_EXPENSE_ROW}:{c}{last_line})", CUR, bold=True
        )
        ws[f"{c}{total_row}"].fill = TOTAL_FILL

    ffb_head, ffb_row = total_row + 2, total_row + 3
    _text(ws.cell(ffb_head, 1), FFB_HEADER_LABEL, bold=True)
    _text(ws.cell(ffb_row, 1), FFB_LABEL)
    _comment(ws.cell(ffb_row, 1), b.sources.get("ffb", ""))
    ffb_col = {
        y: col_letter(EXPENSE_YEAR_COL + i)
        for i, y in enumerate(range(b.start_year, b.end_year + 2))
    }
    for y, c in ffb_col.items():
        ws[f"{c}{ffb_head}"] = y
        ws[f"{c}{ffb_head}"].number_format = YEAR
        _input(ws[f"{c}{ffb_row}"], b.ffb[y], CUR)
    _header(ws, ffb_head, 1, EXPENSE_YEAR_COL + len(ffb_col) - 1)
    ws.freeze_panes = ws.cell(FIRST_EXPENSE_ROW, EXPENSE_YEAR_COL)
    return _ExpenseRefs(year_col, total_row, ffb_col, ffb_row)


# ---------------------------------------------------------------- Plan sheets


def _plan(wb: Workbook, b: Baseline, plan: _Plan, ex: _ExpenseRefs) -> None:
    s, years = plan.scenario, list(b.years)
    ws = wb.create_sheet(plan.sheet)
    _widths(ws, [52, 3] + [12] * len(years))
    _text(ws["A1"], s.name, bold=True, size=13)
    _text(ws["A2"], s.description, italic=True)
    _text(
        ws["A3"],
        "Edit the blue cells – dues, special assessments and the dues settings below the table. "
        "Everything else is calculated.",
        italic=True,
        size=9,
    )
    pc = {y: col_letter(PLAN_FIRST_COL + i) for i, y in enumerate(years)}
    ws.cell(HEADER_ROW, 1, "Year")
    for y in years:
        ws[f"{pc[y]}{HEADER_ROW}"] = y
        ws[f"{pc[y]}{HEADER_ROW}"].number_format = YEAR
        ws[f"{pc[y]}{HEADER_ROW}"].alignment = Alignment(horizontal="center")
    _header(ws, HEADER_ROW, 1, PLAN_FIRST_COL + len(years) - 1)
    for key, (row, label) in PLAN_ROWS.items():
        _text(ws.cell(row, 1), label, bold=key in ("end", "pf"))

    ref = {
        k: input_ref(k)
        for k in (
            "starting_balance",
            "start_year",
            "units",
            "current_dues",
            "operating_start",
            "operating_inflation",
            "interest_rate",
            "cushion",
            "target",
            "max_dues_increase",
            "max_assessment_share",
        )
    }
    grown = s.dues.mode is DuesMode.RATE
    first_col = col_letter(PLAN_FIRST_COL)
    first, rate = f"${first_col}${ROW['first']}", f"${first_col}${ROW['rate']}"
    # The mode decides which cells hold formulas, so it is set in the app, not here.
    _text(ws.cell(ROW["mode"], PLAN_FIRST_COL), MODE_GROWN if grown else MODE_TYPED, italic=True)
    rounding_cell = ws.cell(ROW["rounding"], PLAN_FIRST_COL)
    rounding_text = ROUND_DOLLAR if s.rounding is Rounding.DOLLAR else ROUND_NONE
    _text(rounding_cell, rounding_text, color=BLUE)
    rounding_cell.fill = YELLOW
    choice = DataValidation(type="list", formula1=f'"{ROUND_DOLLAR},{ROUND_NONE}"')
    ws.add_data_validation(choice)
    choice.add(rounding_cell)
    rounding_ref = f"${first_col}${ROW['rounding']}"
    dues_fmt = CUR_CENTS
    if grown:
        _input(ws.cell(ROW["first"], PLAN_FIRST_COL), s.dues.first_value, CUR_CENTS)
        _input(ws.cell(ROW["rate"], PLAN_FIRST_COL), s.dues.annual_increase, PCT)

    _text(ws.cell(ASSESS_HEADING_ROW, 1), ASSESS_HEADING, bold=True)
    headings = (
        (ASSESS_NOTE_COL, "Note"),
        (ASSESS_YEAR_COL, "Year"),
        (ASSESS_AMOUNT_COL, "Per unit"),
    )
    for col, heading in headings:
        ws.cell(ASSESS_HEADING_ROW + 1, col, heading)
    _header(ws, ASSESS_HEADING_ROW + 1, 1, ASSESS_AMOUNT_COL)
    last_assess = assess_last_row(len(s.assessments))
    for k, r in enumerate(range(ASSESS_FIRST_ROW, last_assess + 1)):
        a = s.assessments[k] if k < len(s.assessments) else None
        _text(ws.cell(r, ASSESS_NOTE_COL), a.note if a else "", color=BLUE)
        ws.cell(r, ASSESS_NOTE_COL).fill = YELLOW
        _input(ws.cell(r, ASSESS_YEAR_COL), a.year if a else None, YEAR)
        _input(ws.cell(r, ASSESS_AMOUNT_COL), a.amount if a else None, CUR)
    year_col, amount_col = col_letter(ASSESS_YEAR_COL), col_letter(ASSESS_AMOUNT_COL)
    years_ref = f"${year_col}${ASSESS_FIRST_ROW}:${year_col}${last_assess}"
    amounts_ref = f"${amount_col}${ASSESS_FIRST_ROW}:${amount_col}${last_assess}"

    for i, y in enumerate(years):
        c, p = pc[y], pc.get(y - 1)
        D = {k: f"{c}{row}" for k, row in ROW.items()}
        P = {k: f"{p}{row}" for k, row in ROW.items()} if p else {}
        if grown:
            _input(ws[D["pinned"]], s.dues.overrides.get(y), CUR_CENTS)
            prior = first if i == 0 else f"{P['grown']}*(1+{rate})"
            _formula(ws[D["grown"]], f'=IF({D["pinned"]}<>"",{D["pinned"]},{prior})', CUR_CENTS)
            rounded = (
                f'=IF({D["pinned"]}<>"",{D["pinned"]},'
                f'IF({rounding_ref}="{ROUND_DOLLAR}",ROUND({D["grown"]},0),{D["grown"]}))'
                if i
                else f"={D['grown']}"
            )
            _formula(ws[D["dues"]], rounded, dues_fmt)
        else:
            _input(ws[D["dues"]], s.dues.explicit[y], dues_fmt)
        _formula(ws[D["sa"]], f"=SUMIF({years_ref},{c}${HEADER_ROW},{amounts_ref})", CUR)

        prior_dues = ref["current_dues"] if i == 0 else P["dues"]
        formulas: dict[str, tuple[str, str, str]] = {
            "total_dues": (f"={D['dues']}*{ref['units']}*12", CUR, BLACK),
            "operating": (
                f"={ref['operating_start']}*(1+{ref['operating_inflation']})"
                f"^({c}${HEADER_ROW}-{ref['start_year']})",
                CUR,
                BLACK,
            ),
            "contribution": (f"=MAX(0,{D['total_dues']}-{D['operating']})", CUR, BLACK),
            "sa_total": (f"={D['sa']}*{ref['units']}", CUR, BLACK),
            "owners": (f"={D['total_dues']}+{D['sa_total']}", CUR, BLACK),
            "interest": (f"={D['start']}*{ref['interest_rate']}", CUR, BLACK),
            "expenses": (f"={EXPENSES}!{ex.year_col[y]}${ex.total_row}", CUR, GREEN),
            "start": (f"={ref['starting_balance']}" if i == 0 else f"={P['end']}", CUR, BLACK),
            "end": (
                f"={D['start']}+{D['contribution']}+{D['sa_total']}+{D['interest']}"
                f"-{D['expenses']}",
                CUR,
                BLACK,
            ),
            "ffb": (f"={EXPENSES}!{ex.ffb_col[y + 1]}${ex.ffb_row}", CUR, GREEN),
            "pf": (f"=IF({D['ffb']}=0,0,{D['end']}/{D['ffb']})", PCT, BLACK),
            "low": (f'=IF({D["end"]}<{ref["cushion"]},"LOW","ok")', CUR, BLACK),
            "met": (f'=IF({D["pf"]}>={ref["target"]},"yes","no")', CUR, BLACK),
            "vote": (
                f'=IF(OR(AND({ref["max_dues_increase"]}<>"",'
                f"IF({prior_dues}>0,{D['dues']}/{prior_dues}-1>{ref['max_dues_increase']},FALSE)),"
                f'AND({ref["max_assessment_share"]}<>"",{D["sa_total"]}>'
                f"{ref['max_assessment_share']}*({D['operating']}+{D['contribution']}))),"
                '"yes","no")',
                CUR,
                BLACK,
            ),
            "short": (f'=IF({D["total_dues"]}<{D["operating"]},"yes","no")', CUR, BLACK),
            "own_dues": (f"={D['dues']}*12", CUR, BLACK),
            "own_cost": (f"={D['own_dues']}+{D['sa']}", CUR, BLACK),
            "increase": (f"=({D['dues']}-{ref['current_dues']})*12", CUR, BLACK),
            "cum_cost": (
                f"={D['own_cost']}" if i == 0 else f"={P['cum_cost']}+{D['own_cost']}",
                CUR,
                BLACK,
            ),
            "cum_extra": (
                f"={D['increase']}+{D['sa']}"
                if i == 0
                else f"={P['cum_extra']}+{D['increase']}+{D['sa']}",
                CUR,
                BLACK,
            ),
            "extra": (f"={D['increase']}+{D['sa']}", CUR, BLACK),
            "target": (f"={ref['target']}", PCT, GREEN),
        }
        for key, (formula, fmt, color) in formulas.items():
            _formula(ws[D[key]], formula, fmt, color=color, bold=key in ("end", "pf"))
        for key in ("low", "met", "vote", "short"):
            ws[D[key]].alignment = Alignment(horizontal="center")
            ws[D[key]].number_format = "General"

    last = pc[years[-1]]
    flags = [
        ("low", "LOW", LOW_FILL),
        ("met", "yes", YES_FILL),
        ("vote", "yes", WARN_FILL),
        ("short", "yes", LOW_FILL),
    ]
    for key, value, fill in flags:
        area = f"{first_col}{ROW[key]}:{last}{ROW[key]}"
        ws.conditional_formatting.add(
            area,
            CellIsRule(  # type: ignore[no-untyped-call]  # openpyxl ships it untyped
                operator="equal", formula=[f'"{value}"'], fill=fill
            ),
        )
    ws.freeze_panes = ws.cell(HEADER_ROW + 1, PLAN_FIRST_COL)
    for key, note in ROW_NOTES.items():
        _comment(ws.cell(ROW[key], 1), note)
    charts.add_plan_charts(ws, s.name, len(years), plan_chart_row(len(s.assessments)))


# ---------------------------------------------------------------- Compare


def _compare(wb: Workbook, b: Baseline, plans: list[_Plan]) -> None:
    ws = wb.create_sheet(COMPARE)
    years = list(b.years)
    start, end, n = b.start_year, b.end_year, len(years)
    _widths(ws, [58] + [18] * len(plans))
    _text(ws["A1"], "Scenario comparison", bold=True, size=13)
    _text(
        ws["A2"],
        "All figures are pulled from the Plan sheets. Change inputs there or on Inputs and "
        "Expenses and this updates.",
        italic=True,
        size=9,
    )
    first, last = col_letter(PLAN_FIRST_COL), col_letter(PLAN_FIRST_COL + n - 1)

    def span(sheet: str, key: str, a: int = 0, z: int | None = None) -> str:
        z = n - 1 if z is None else z
        return (
            f"{quote(sheet)}!{col_letter(PLAN_FIRST_COL + a)}{ROW[key]}"
            f":{col_letter(PLAN_FIRST_COL + z)}{ROW[key]}"
        )

    def at(sheet: str, key: str, offset: int) -> str:
        return f"={quote(sheet)}!{col_letter(PLAN_FIRST_COL + offset)}{ROW[key]}"

    Measure = tuple[str, Callable[[str], str], str]
    measures: list[Measure] = [
        (f"Dues per unit per month – {start}", lambda sh: at(sh, "dues", 0), CUR_CENTS),
        (f"Dues per unit per month – {start + 3}", lambda sh: at(sh, "dues", 3), CUR_CENTS),
    ]
    if n >= 9:
        measures.append(
            (f"Dues per unit per month – {start + 8}", lambda sh: at(sh, "dues", 8), CUR_CENTS)
        )
    measures += [
        (
            f"Special assessments per unit, total {start}–{end}",
            lambda sh: f"=SUM({span(sh, 'sa')})",
            CUR,
        ),
        (
            f"Lowest year-end reserve balance, {start}–{end}",
            lambda sh: f"=MIN({span(sh, 'end')})",
            CUR,
        ),
        (
            f"Year of lowest year-end balance, {start}–{end}",
            lambda sh: (
                f"=INDEX({quote(sh)}!{first}{HEADER_ROW}:{last}{HEADER_ROW},"
                f"MATCH(MIN({span(sh, 'end')}),{span(sh, 'end')},0))"
            ),
            YEAR,
        ),
        (
            f"Years below minimum cushion, {start}–{end}",
            lambda sh: f'=COUNTIF({span(sh, "low")},"LOW")',
            "0",
        ),
        (
            f"Years needing an owner vote, {start}–{end}",
            lambda sh: f'=COUNTIF({span(sh, "vote")},"yes")',
            "0",
        ),
        (
            f"Years with an operating shortfall, {start}–{end}",
            lambda sh: f'=COUNTIF({span(sh, "short")},"yes")',
            "0",
        ),
        (f"Reserve balance end of {start + 3}", lambda sh: at(sh, "end", 3), CUR),
        (f"Percent funded end of {start + 3}", lambda sh: at(sh, "pf", 3), PCT),
    ]
    if n >= 9:
        measures += [
            (f"Reserve balance end of {start + 8}", lambda sh: at(sh, "end", 8), CUR),
            (f"Percent funded end of {start + 8}", lambda sh: at(sh, "pf", 8), PCT),
        ]
    measures += [
        (f"Reserve balance end of {end}", lambda sh: at(sh, "end", n - 1), CUR),
        (f"Percent funded end of {end}", lambda sh: at(sh, "pf", n - 1), PCT),
        (
            "First year percent-funded target is met",
            lambda sh: (
                f"=IFERROR(INDEX({quote(sh)}!{first}{HEADER_ROW}:{last}{HEADER_ROW},"
                f'MATCH("yes",{span(sh, "met")},0)),"not by {end}")'
            ),
            YEAR,
        ),
        (
            f"Owner outlay per unit, first five years, {start}–{start + 4} (dues + assessments)",
            lambda sh: f"=SUM({span(sh, 'own_cost', 0, 4)})",
            CUR,
        ),
        (
            f"Owner outlay per unit, {start}–{end} (dues + assessments)",
            lambda sh: f"=SUM({span(sh, 'own_cost')})",
            CUR,
        ),
        (
            f"Extra cost vs current dues, {start}–{end}, per unit",
            lambda sh: f"=SUM({span(sh, 'extra')})",
            CUR,
        ),
        (
            f"Extra cost vs current dues, first four years, {start}–{start + 3}, per unit",
            lambda sh: f"=SUM({span(sh, 'extra', 0, 3)})",
            CUR,
        ),
        (
            f"Average owner cost per year, {start}–{end}, per unit",
            lambda sh: f"=AVERAGE({span(sh, 'own_cost')})",
            CUR,
        ),
        (
            f"Average extra cost per year vs current dues, {start}–{end}, per unit",
            lambda sh: f"=AVERAGE({span(sh, 'extra')})",
            CUR,
        ),
    ]
    head = 4
    ws.cell(head, 1, "Measure")
    for j, plan in enumerate(plans):
        _text(ws.cell(head, 2 + j), plan.scenario.name, bold=True)
    _header(ws, head, 1, 1 + len(plans))
    for i, (label, formula, fmt) in enumerate(measures, start=head + 1):
        _text(ws.cell(i, 1), label)
        for j, plan in enumerate(plans):
            _formula(ws.cell(i, 2 + j), formula(plan.sheet), fmt, color=GREEN)

    r = head + len(measures) + 2
    for title, key, fmt in (
        ("Year-end reserve balance by year", "end", CUR),
        ("Percent funded at year end, by year", "pf", PCT),
    ):
        _text(ws.cell(r, 1), title, bold=True)
        r += 1
        ws.cell(r, 1, "Year")
        for j, plan in enumerate(plans):
            _text(ws.cell(r, 2 + j), plan.scenario.name, bold=True)
        _header(ws, r, 1, 1 + len(plans))
        r += 1
        for i, y in enumerate(years):
            ws.cell(r, 1, y).number_format = YEAR
            ws.cell(r, 1).alignment = Alignment(horizontal="left")
            for j, plan in enumerate(plans):
                _formula(ws.cell(r, 2 + j), at(plan.sheet, key, i), fmt, color=GREEN)
            r += 1
        r += 1
    ws.freeze_panes = ws.cell(head + 1, 2)


# ---------------------------------------------------------------- Method


def _method(wb: Workbook, project: Project, plans: list[_Plan]) -> None:
    ws = wb.create_sheet(METHOD, 0)
    _widths(ws, [120])
    b = project.baseline
    vote_limits = []
    if b.max_dues_increase is not None:
        vote_limits.append(f"a dues increase above {b.max_dues_increase:.0%} in a year")
    if b.max_assessment_share is not None:
        vote_limits.append(
            f"a special assessment above {b.max_assessment_share:.0%} of the year's budget"
        )
    lines: list[tuple[str, bool, int]] = [
        (f"{project.name} – Reserve Funding Model", True, 13),
        (
            f"Projection {b.start_year}–{b.end_year}, exported from HOAForecaster. "
            "A planning tool, not a reserve study. All assumptions are editable and marked.",
            False,
            9,
        ),
        ("", False, 10),
        ("Purpose", True, 11),
        (
            "Answer one question each year – given where reserves are and what work is coming, "
            "what dues and assessments keep the reserve fund above a safe floor and moving toward "
            "a healthy percent funded?",
            False,
            10,
        ),
        ("", False, 10),
        ("How it works", True, 11),
        (
            "1. Inputs – starting balance, units, current dues, operating cost and its inflation, "
            "reserve expense inflation, interest, the minimum cushion, the percent-funded target "
            "and the owner-vote limits.",
            False,
            10,
        ),
        (
            "2. Expenses – one row per expected reserve expense with its amount and year. Amounts "
            "grow from the expense base year at the reserve expense inflation rate unless marked "
            "as already in that year's dollars. Below them is the reserve study's Fully Funded "
            "Balance for each year.",
            False,
            10,
        ),
        (
            "3. One sheet per scenario – the board sets dues per unit per month, either typed for "
            "each year or grown from a first-year figure, and any special assessment per unit. "
            "Dues above operating cost flow to reserves. The sheet projects the reserve balance "
            "each year, compares it to the Fully Funded Balance and flags years below the "
            "cushion, years that need an owner vote and years when dues do not cover operating "
            "cost.",
            False,
            10,
        ),
        (
            "4. Compare – the key results side by side, then year-end balance and percent funded "
            "by year for every scenario.",
            False,
            10,
        ),
        (
            "5. Charts – the first chart from each scenario sheet, stacked for comparison.",
            False,
            10,
        ),
        ("", False, 10),
        ("Scenarios", True, 11),
    ]
    for plan in plans:
        s = plan.scenario
        lines.append((f"{s.name} – {s.description}" if s.description else s.name, False, 10))
    lines += [
        ("", False, 10),
        ("Colour legend", True, 11),
        (
            "Blue text on yellow – inputs to edit.   Black – formulas.   Green – values pulled "
            "from another sheet.",
            False,
            10,
        ),
    ]
    sources = [(row.label, b.sources[row.key]) for row in INPUT_ROWS if b.sources.get(row.key)]
    if b.sources.get("ffb"):
        sources.append(("Fully Funded Balance", b.sources["ffb"]))
    if sources:
        lines += [("", False, 10), ("Sources", True, 11)]
        lines += [(f"{label} – {text}", False, 10) for label, text in sources]
    if project.notes:
        lines += [("", False, 10), ("Notes", True, 11), (project.notes, False, 10)]
    limits = (
        "The expense schedule is a forecast – real costs and timing will differ. Percent funded "
        "uses the reserve study's Fully Funded Balance, which a new study will change. "
        "Operating inflation is an assumption."
    )
    if vote_limits:
        limits += (
            " Under the limits on Inputs, "
            + " or ".join(vote_limits)
            + " needs an owner vote – the scenario sheets flag those years."
        )
    lines += [("", False, 10), ("Limits", True, 11), (limits, False, 10)]
    for i, (text, bold, size) in enumerate(lines, start=1):
        _text(ws.cell(i, 1), text, bold=bold, size=size)
        ws.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="top")
        if text and not bold and size == 10:
            ws.row_dimensions[i].height = 14 * (1 + len(text) // 125)


# ---------------------------------------------------------------- workbook


def build_workbook(
    project: Project,
    scenario_names: Sequence[str] | None = None,
    dollar_axis: tuple[Decimal, Decimal] | None = None,
) -> Workbook:
    """The workbook for a project.

    `scenario_names` picks and orders the scenarios to include (default all).
    `dollar_axis` fixes the Charts sheet's dollar scale as (min, max) so the
    stacked charts compare visually; the caller supplies it from the engine's
    results, since this module never runs the engine.
    """
    problems = validate_baseline(project.baseline)
    if problems:  # an impossible horizon would also make the sheets absurdly wide
        raise ValueError("; ".join(problems))
    names = [sc.name for sc in project.scenarios]
    if len(set(names)) != len(names):
        raise ValueError("scenario names must be unique")
    unknown = [n for n in scenario_names or [] if n not in names]
    if unknown:
        raise ValueError("no scenario named " + ", ".join(repr(n) for n in unknown))
    chosen = (
        list(project.scenarios)
        if scenario_names is None
        else [next(sc for sc in project.scenarios if sc.name == n) for n in scenario_names]
    )
    plans = [
        _Plan(s, sheet)
        for s, sheet in zip(chosen, sheet_names([s.name for s in chosen]), strict=True)
    ]
    wb = Workbook()
    wb.remove(wb.worksheets[0])
    _inputs(wb, project)
    refs = _expenses(wb, project.baseline)
    for plan in plans:
        _plan(wb, project.baseline, plan, refs)
    _compare(wb, project.baseline, plans)
    charts.add_charts_sheet(
        wb,
        CHARTS,
        [(p.sheet, p.scenario.name) for p in plans],
        len(project.baseline.years),
        dollar_axis,
    )
    _method(wb, project, plans)
    order = [*SHEET_ORDER, *(p.sheet for p in plans)]
    for index, name in enumerate(order):
        wb.move_sheet(name, index - wb.sheetnames.index(name))
    wb.active = 0
    wb.properties.creator = AUTHOR
    wb.properties.lastModifiedBy = AUTHOR
    return wb


def export_workbook(
    project: Project,
    path: Path | None = None,
    scenario_names: Sequence[str] | None = None,
    dollar_axis: tuple[Decimal, Decimal] | None = None,
) -> bytes:
    """Write the workbook to `path` if given, and return its bytes."""
    buffer = BytesIO()
    build_workbook(project, scenario_names, dollar_axis).save(buffer)
    data = buffer.getvalue()
    if path is not None:
        path.write_bytes(data)
    return data
