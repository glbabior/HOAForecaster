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

from hoa_engine.model import (
    LIMITS,
    Baseline,
    Changes,
    DuesMode,
    ExpenseLine,
    Project,
    Rounding,
    Scenario,
    baseline_for,
)
from hoa_engine.validate import horizon_problem, validate_baseline
from hoa_workbook import charts
from hoa_workbook.layout import (
    ADOPTED_ON_LABEL,
    ADOPTION_NOTE_LABEL,
    ADOPTION_ORDER_LABEL,
    ASSESS_AMOUNT_COL,
    ASSESS_FIRST_ROW,
    ASSESS_HEADING,
    ASSESS_HEADING_ROW,
    ASSESS_NOTE_COL,
    ASSESS_YEAR_COL,
    ASSUMPTION_ROWS,
    ASSUMPTIONS_HEADING,
    CHANGE_SPARE_ROWS,
    CHANGE_YEAR_COL,
    CHANGES_HEADING,
    CHARTS,
    COMPARE,
    EXPENSE_COL,
    EXPENSE_COLUMNS,
    EXPENSE_TOTAL_LABEL,
    EXPENSE_YEAR_COL,
    EXPENSES,
    FFB_HEADER_LABEL,
    FFB_LABEL,
    FFB_NOTE_MARK_COL,
    FIRST_EXPENSE_ROW,
    FIRST_INPUT_ROW,
    FREQUENCY_TEXT,
    HEADER_ROW,
    INPUT_ROW,
    INPUT_ROWS,
    INPUTS,
    LEAVE_OUT_COL,
    LEAVE_OUT_HEADING,
    MARK_COL,
    METHOD,
    MODE_GROWN,
    MODE_TYPED,
    OPERATING_TOTAL_LABEL,
    OWN_COL,
    OWN_HEADING,
    PLAN_FFB_HEADING,
    PLAN_FFB_OWN_LABEL,
    PLAN_FFB_YEARS_LABEL,
    PLAN_FIRST_COL,
    PLAN_OPERATING_LABEL,
    PLAN_RESERVE_LABEL,
    PLAN_ROWS,
    ROUND_DOLLAR,
    ROUND_NONE,
    ROW,
    SHEET_ORDER,
    SOURCE_COL,
    VALUE_COL,
    assess_last_row,
    input_ref,
    plan_chart_row,
    plan_inputs_row,
    quote,
    sheet_names,
)

FONT = "Arial"
BLUE, GREEN, BLACK, GREY = "0000FF", "008000", "000000", "808080"
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
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)  # spelled out here, so no locale setting can change them
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


def _at(ws: Worksheet, row: int, col: int) -> Cell:
    cell = ws.cell(row, col)
    assert isinstance(cell, Cell)  # nothing in an export is merged
    return cell


ROW_NOTES = {
    "operating": "The monthly and yearly lines on the Expenses sheet, each grown at its own "
    "inflation rate or the operating rate on Inputs. Any dues above operating cost go to "
    "reserves.",
    "contribution": "Total dues less operating expenses, never below zero. A shortfall is flagged "
    "below, not taken from reserves.",
    "pf": "Year-end balance divided by the reserve study's Fully Funded Balance at the start of "
    "the following year. Under 30% is weak, 30–70% fair, over 70% strong.",
}


@dataclass(frozen=True)
class _Plan:
    scenario: Scenario
    sheet: str
    baseline: Baseline  # as the scenario sees it, its changes applied


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
    lines: tuple[int, int]  # the first and last row of the line table
    ffb_col: dict[int, str]
    ffb_row: int


@dataclass(frozen=True)
class _Rates:
    """The cells an expense line's year formula reads."""

    operating_inflation: str
    expense_inflation: str
    base_year: str
    start_year: str


def _expense_inputs(ws: Worksheet, r: int, line: ExpenseLine) -> None:
    """One line's input cells – blank where its frequency has no use for them."""

    def at(key: str) -> Cell:
        cell = ws.cell(r, EXPENSE_COL[key])
        assert isinstance(cell, Cell)  # nothing on these sheets is merged
        return cell

    _text(at("description"), line.description)
    _comment(at("description"), line.source)
    _text(at("frequency"), FREQUENCY_TEXT[line.frequency.value], color=BLUE)
    at("frequency").fill = YELLOW
    _input(at("amount"), line.amount, CUR)
    _input(at("year"), line.year, YEAR)
    _input(at("end_year"), line.end_year, YEAR)
    _input(at("interval"), line.interval, "0")
    _input(at("inflation"), line.inflation, PCT)
    nominal = at("nominal")
    nominal.value = None if line.frequency.operating else "yes" if line.nominal else "no"
    nominal.font, nominal.fill = _font(color=BLUE), YELLOW
    nominal.alignment = Alignment(horizontal="center")
    _text(at("id"), line.id, color=GREY, size=8)


def _expense_formula(r: int, year: str, rates: _Rates) -> str:
    """A line's amount in the year whose number is in cell `year` (spec 4.1, section 6)."""
    c = {key: f"${col_letter(i)}{r}" for key, i in EXPENSE_COL.items()}
    f, amount, first, last = c["frequency"], c["amount"], c["year"], c["end_year"]
    t = FREQUENCY_TEXT
    in_range = f'AND({year}>={first},OR({last}="",{year}<={last}))'
    reserve = (
        f'{amount}*IF({c["nominal"]}="yes",1,'
        f"(1+{rates.expense_inflation})^({year}-{rates.base_year}))"
    )
    operating = (
        f'{amount}*IF({f}="{t["monthly"]}",12,1)'
        f'*(1+IF({c["inflation"]}="",{rates.operating_inflation},{c["inflation"]}))'
        f'^({year}-IF({first}="",{rates.start_year},{first}))'
    )
    return (
        f'=IF(OR({f}="{t["monthly"]}",{f}="{t["yearly"]}"),IF({in_range},{operating},0),'
        f'IF({f}="{t["once"]}",IF({year}={first},{reserve},0),'
        f"IF(AND({in_range},MOD({year}-{first},{c['interval']})=0),{reserve},0)))"
    )


def _frequency_choice(ws: Worksheet) -> DataValidation:
    choice = DataValidation(type="list", formula1='"' + ",".join(FREQUENCY_TEXT.values()) + '"')
    ws.add_data_validation(choice)
    return choice


def _totals(ws: Worksheet, rows: tuple[int, int], year_cols: Sequence[str], at: int) -> None:
    """The operating total at row `at` and the reserve total two rows below, for each year
    column – sums of the lines in `rows` by frequency."""
    first, last = rows
    freq = col_letter(EXPENSE_COL["frequency"])
    span = f"${freq}${first}:${freq}${last}"
    t = FREQUENCY_TEXT
    for row, kinds in ((at, ("monthly", "yearly")), (at + 2, ("once", "every"))):
        for c in year_cols:
            cells = f"{c}{first}:{c}{last}"
            parts = "+".join(f'SUMIF({span},"{t[k]}",{cells})' for k in kinds)
            _formula(ws[f"{c}{row}"], f"={parts}", CUR, bold=True)
            ws[f"{c}{row}"].fill = TOTAL_FILL


def _expenses(wb: Workbook, b: Baseline) -> _ExpenseRefs:
    ws = wb.create_sheet(EXPENSES)
    years = list(b.years)
    _widths(ws, [44, 15, 14, 11, 11, 9, 11, 13, 9] + [12] * (len(years) + 1))
    _text(ws["A1"], "Expenses by year ($)", bold=True, size=13)
    _text(
        ws["A2"],
        "One row per expense. Monthly and yearly lines are operating costs paid from dues; they "
        "grow from their first year (blank – the start year) at their own inflation rate or "
        "the operating rate on Inputs. Once and every-few-years lines are reserve expenses in "
        "the expense base year's dollars, grown at the reserve expense inflation rate unless "
        "marked as already in that year's dollars. To add an expense, copy a whole row and "
        "insert it inside the table, so its year formulas come with it, and clear its line id.",
        italic=True,
        size=9,
    )
    ws.row_dimensions[2].height = 36
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    year_col = {y: col_letter(EXPENSE_YEAR_COL + i) for i, y in enumerate(years)}
    for col, column in enumerate(EXPENSE_COLUMNS, start=1):
        ws.cell(HEADER_ROW, col, column.heading).alignment = Alignment(wrap_text=True)
    for y in years:
        ws[f"{year_col[y]}{HEADER_ROW}"] = y
        ws[f"{year_col[y]}{HEADER_ROW}"].number_format = YEAR
    _header(ws, HEADER_ROW, 1, EXPENSE_YEAR_COL + len(years) - 1)

    rates = _Rates(
        input_ref("operating_inflation"),
        input_ref("expense_inflation"),
        input_ref("expense_base_year"),
        input_ref("start_year"),
    )
    if b.expense_lines:  # Excel repairs a dropdown that covers no cells
        _frequency_choice(ws).add(
            f"{col_letter(EXPENSE_COL['frequency'])}{FIRST_EXPENSE_ROW}:"
            f"{col_letter(EXPENSE_COL['frequency'])}{FIRST_EXPENSE_ROW + len(b.expense_lines) - 1}"
        )
    r = FIRST_EXPENSE_ROW
    for line in b.expense_lines:  # the user's order, so a re-import is identical
        _expense_inputs(ws, r, line)
        for y in years:
            c = year_col[y]
            _formula(ws[f"{c}{r}"], _expense_formula(r, f"{c}${HEADER_ROW}", rates), CUR)
        r += 1
    last_line = max(r - 1, FIRST_EXPENSE_ROW)  # an empty table still sums one blank row
    operating_row, total_row = last_line + 2, last_line + 4
    _text(ws.cell(operating_row, 1), OPERATING_TOTAL_LABEL, bold=True)
    _text(ws.cell(total_row, 1), EXPENSE_TOTAL_LABEL, bold=True)
    _totals(ws, (FIRST_EXPENSE_ROW, last_line), list(year_col.values()), operating_row)

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
    return _ExpenseRefs((FIRST_EXPENSE_ROW, last_line), ffb_col, ffb_row)


# ---------------------------------------------------------------- Plan sheets


_FORMATS = {"money": CUR, "rate": PCT, "year": YEAR, "count": "0"}


def _link(key: str) -> str:
    """A Plan cell that follows Inputs. A blank governance limit must stay blank (no limit) –
    a plain link would read it as 0."""
    cell = f"{INPUTS}!$B${INPUT_ROW[key]}"
    return f'=IF({cell}="","",{cell})' if key in LIMITS else f"={cell}"


def _plan_assumptions(
    ws: Worksheet, own: Baseline, changes: Changes, frozen: bool, top: int
) -> tuple[dict[str, str], int]:
    """The scenario's assumptions – a link to Inputs, or its own value (spec 5.1); for an
    adopted plan, its frozen baseline's every value, marked where it is the plan's own.
    Returns the cell of each, and the next free row."""
    _text(_at(ws, top, 1), ASSUMPTIONS_HEADING, bold=True)
    headings = [(1, "Assumption"), (VALUE_COL, "Value"), (SOURCE_COL, "Source / note")]
    for col, heading in headings + ([(MARK_COL, OWN_HEADING)] if frozen else []):
        ws.cell(top + 1, col, heading)
    _header(ws, top + 1, 1, MARK_COL if frozen else SOURCE_COL)
    refs = {}
    for r, row in enumerate(ASSUMPTION_ROWS, start=top + 2):
        _text(_at(ws, r, 1), row.label)
        value, fmt = _at(ws, r, VALUE_COL), _FORMATS[row.kind]
        fmt = CUR_CENTS if row.key == "current_dues" else fmt
        refs[row.key] = f"${col_letter(VALUE_COL)}${r}"
        source = _at(ws, r, SOURCE_COL)
        if frozen:
            _input(value, getattr(own, row.key), fmt)
            _text(source, own.sources.get(row.key, ""), size=9)
            mark = " and ".join(
                word
                for word, part in (("value", changes.values), ("note", changes.sources))
                if row.key in part
            )
            _text(_at(ws, r, MARK_COL), mark, color=GREY, size=9)
            continue
        if row.key in changes.values:
            _input(value, changes.values[row.key], fmt)
        else:
            _formula(value, _link(row.key), fmt, color=GREEN)
        if row.key in changes.sources:
            _text(source, changes.sources[row.key], size=9)
        else:
            note = f"{INPUTS}!$C${INPUT_ROW[row.key]}"
            _formula(source, f'=IF({note}="","",{note})', "General", color=GREEN)
            source.alignment = Alignment(horizontal="left")
    return refs, top + 2 + len(ASSUMPTION_ROWS) + 1


def _plan_ffb(
    ws: Worksheet, own: Baseline, changes: Changes, frozen: bool, ex: _ExpenseRefs, top: int
) -> tuple[dict[int, str], int]:
    """The scenario's Fully Funded Balance for its own years and one more – a link to the
    Expenses sheet, or its own figure; an adopted plan's frozen figures, with a row marking its
    own. Returns the cell of each year, and the next free row."""
    _text(_at(ws, top, 1), PLAN_FFB_HEADING, bold=True)
    _text(_at(ws, top + 1, 1), PLAN_FFB_YEARS_LABEL)
    _text(_at(ws, top + 2, 1), FFB_LABEL)
    _comment(_at(ws, top + 2, 1), (own.sources if frozen else changes.sources).get("ffb", ""))
    if frozen:
        _text(_at(ws, top + 3, 1), PLAN_FFB_OWN_LABEL, color=GREY, size=9)
        _text(
            _at(ws, top + 3, FFB_NOTE_MARK_COL),
            "note" if "ffb" in changes.sources else "",
            color=GREY,
            size=9,
        )
    cells = {}
    years = range(own.start_year, own.end_year + 2)
    for i, y in enumerate(years):
        c = col_letter(VALUE_COL + i)
        ws[f"{c}{top + 1}"] = y
        ws[f"{c}{top + 1}"].number_format = YEAR
        value = ws[f"{c}{top + 2}"]
        if frozen:
            _input(value, own.ffb.get(y), CUR)
            _text(ws[f"{c}{top + 3}"], "yes" if y in changes.ffb else "", color=GREY, size=9)
        elif y not in changes.ffb and y in ex.ffb_col:
            _formula(value, f"={EXPENSES}!{ex.ffb_col[y]}${ex.ffb_row}", CUR, color=GREEN)
        else:  # its own figure – or the baseline's for a year the Expenses sheet does not show
            _input(value, own.ffb.get(y), CUR)
        cells[y] = f"{c}${top + 2}"
    _header(ws, top + 1, 1, VALUE_COL + len(years) - 1)
    return cells, top + (5 if frozen else 4)


@dataclass(frozen=True)
class _ChangeTable:
    """The columns of a Plan sheet's expense changes table that say which lines it replaces."""

    ids: str
    frequency: str
    leave_out: str


def _baseline_lines(
    kind: str, ex: _ExpenseRefs, year: str, rates: _Rates, table: _ChangeTable
) -> str:
    """The Expenses sheet's operating or reserve lines in one year, at the scenario's own rates –
    leaving out every line the scenario changes (a row with its id and a frequency) or leaves
    out (its id and "yes"); a row with only an id does neither, as on import. One array
    formula, so a line added on Expenses reaches every scenario."""
    first, last = ex.lines

    def column(key: str) -> str:
        c = col_letter(EXPENSE_COL[key])
        return f"{EXPENSES}!${c}${first}:${c}${last}"

    f, amount, start, end = (
        column("frequency"),
        column("amount"),
        column("year"),
        column("end_year"),
    )
    line_id, t = column("id"), FREQUENCY_TEXT
    replaced = (
        f'COUNTIFS({table.ids},{line_id},{table.leave_out},"yes")'
        f'+COUNTIFS({table.ids},{line_id},{table.frequency},"<>")'
    )
    kept = f'((({line_id}="")+(({replaced})=0))>0)'
    until = f'((({end}="")+({year}<={end}))>0)'
    if kind == "operating":
        own_rate = column("inflation")
        weight = f'(({f}="{t["monthly"]}")*12+({f}="{t["yearly"]}"))*({year}>={start})*{until}'
        growth = (
            f'(1+{own_rate}+({own_rate}="")*{rates.operating_inflation})'
            f'^({year}-({start}+({start}="")*{rates.start_year}))'
        )
    else:
        interval, nominal = column("interval"), column("nominal")
        weight = (
            f'(({f}="{t["once"]}")*({year}={start})+({f}="{t["every"]}")*({year}>={start})'
            f'*(MOD({year}-{start},{interval}+({interval}=""))=0)*{until})'
        )
        growth = (
            f'(({nominal}="yes")+({nominal}<>"yes")'
            f"*(1+{rates.expense_inflation})^({year}-{rates.base_year}))"
        )
    return f"SUMPRODUCT({weight}*{kept}*{amount}*{growth})"


@dataclass(frozen=True)
class _Totals:
    operating: dict[int, str]  # the cell of each year's total
    reserve: dict[int, str]
    last_row: int


def _plan_changes(
    ws: Worksheet,
    b: Baseline,
    own: Baseline,
    changes: Changes,
    frozen: bool,
    ex: _ExpenseRefs,
    rates: _Rates,
    top: int,
) -> _Totals:
    """The scenario's expense changes, one row each with its year formulas, and its operating
    and reserve totals – the Expenses lines it keeps plus its own rows. An adopted plan's table
    holds every line of its frozen baseline instead, marked where it is the plan's own, and its
    totals are those rows alone."""
    years = list(own.years)
    _text(_at(ws, top, 1), CHANGES_HEADING, bold=True)
    head = top + 1
    for col, column in enumerate(EXPENSE_COLUMNS, start=1):
        ws.cell(head, col, column.heading).alignment = Alignment(wrap_text=True)
    ws.cell(head, LEAVE_OUT_COL, LEAVE_OUT_HEADING)
    if frozen:
        ws.cell(head, OWN_COL, OWN_HEADING)
    year_col = {y: col_letter(CHANGE_YEAR_COL + i) for i, y in enumerate(years)}
    for y, c in year_col.items():
        ws[f"{c}{head}"] = y
        ws[f"{c}{head}"].number_format = YEAR
    _header(ws, head, 1, CHANGE_YEAR_COL + len(years) - 1)

    described = {line.id: line.description for line in b.expense_lines}
    if frozen:  # every line it runs on, then the lines it leaves out
        entries: list[tuple[str, ExpenseLine | None]] = [(x.id, x) for x in own.expense_lines]
        entries += [(i, None) for i, line in changes.expense_lines.items() if line is None]
        spare = 0
    else:
        entries = list(changes.expense_lines.items())
        spare = CHANGE_SPARE_ROWS
    first = head + 1
    last = max(first, first + len(entries) + spare - 1)  # an empty table still sums a row
    leave_out = col_letter(LEAVE_OUT_COL)
    frequency = col_letter(EXPENSE_COL["frequency"])
    for k, r in enumerate(range(first, last + 1)):
        line_id, line = entries[k] if k < len(entries) else ("", None)
        if frozen and line_id:
            mark = "yes" if line_id in changes.expense_lines else "no"
            _text(_at(ws, r, OWN_COL), mark, color=GREY, size=9)
        if line is not None:
            _expense_inputs(ws, r, line)
        else:  # a line left out, or a spare row – inputs to fill in
            _text(_at(ws, r, EXPENSE_COL["description"]), described.get(line_id, ""))
            for key in ("frequency", "amount", "year", "end_year", "interval", "inflation"):
                ws.cell(r, EXPENSE_COL[key]).fill = YELLOW
                ws.cell(r, EXPENSE_COL[key]).font = _font(color=BLUE)
            _text(_at(ws, r, EXPENSE_COL["id"]), line_id, color=GREY, size=8)
        out = ws.cell(r, LEAVE_OUT_COL)
        out.value = "yes" if line_id and line is None else "no" if line_id else None
        out.font, out.fill = _font(color=BLUE), YELLOW
        out.alignment = Alignment(horizontal="center")
        for c in year_col.values():
            inner = _expense_formula(r, f"{c}${head}", rates)[1:]
            formula = f'=IF(OR(${leave_out}{r}="yes",${frequency}{r}=""),0,{inner})'
            _formula(ws[f"{c}{r}"], formula, CUR)
    _frequency_choice(ws).add(f"{frequency}{first}:{frequency}{last}")

    id_col = col_letter(EXPENSE_COL["id"])
    ids = f"${id_col}${first}:${id_col}${last}"
    table = _ChangeTable(
        ids,
        f"${frequency}${first}:${frequency}${last}",
        f"${leave_out}${first}:${leave_out}${last}",
    )
    span = f"${frequency}${first}:${frequency}${last}"
    t = FREQUENCY_TEXT
    operating_row, reserve_row = last + 2, last + 4
    _text(_at(ws, operating_row, 1), PLAN_OPERATING_LABEL, bold=True)
    _text(_at(ws, reserve_row, 1), PLAN_RESERVE_LABEL, bold=True)
    totals: tuple[dict[int, str], dict[int, str]] = ({}, {})
    for (row, kind, kinds), out_cells in zip(
        (
            (operating_row, "operating", ("monthly", "yearly")),
            (reserve_row, "reserve", ("once", "every")),
        ),
        totals,
        strict=True,
    ):
        for y, c in year_col.items():
            year = f"{c}${head}"
            rows = "+".join(f'SUMIF({span},"{t[k]}",{c}{first}:{c}{last})' for k in kinds)
            shared = "" if frozen else f"{_baseline_lines(kind, ex, year, rates, table)}+"
            _formula(ws[f"{c}{row}"], f"={shared}{rows}", CUR, bold=True)
            ws[f"{c}{row}"].fill = TOTAL_FILL
            out_cells[y] = f"{c}${row}"
    return _Totals(*totals, reserve_row)


def _plan(wb: Workbook, b: Baseline, plan: _Plan, ex: _ExpenseRefs) -> None:
    s, own = plan.scenario, plan.baseline
    years = list(own.years)
    ws = wb.create_sheet(plan.sheet)
    _widths(ws, [52, 15] + [12] * (CHANGE_YEAR_COL + len(years)))
    _text(ws["A1"], s.name, bold=True, size=13)
    _text(ws["A2"], s.description, italic=True)
    frozen = s.adoption is not None
    on = s.adoption.adopted_on if s.adoption else None
    guide = (
        f"Adopted plan – adopted {MONTHS[on.month - 1]} {on.day}, {on.year}. Its figures are "
        "frozen with the baseline it was adopted against, typed below the charts. Read-only in "
        "the app – start a new scenario from it there to revise it."
        if on
        else "Edit the blue cells – dues, special assessments and the dues settings below the "
        "table, and below the charts this scenario's own assumptions, Fully Funded Balance and "
        "expense changes. Everything else is calculated."
    )
    _text(ws["A3"], guide, italic=True, size=9)
    pc = {y: col_letter(PLAN_FIRST_COL + i) for i, y in enumerate(years)}
    ws.cell(HEADER_ROW, 1, "Year")
    for y in years:
        ws[f"{pc[y]}{HEADER_ROW}"] = y
        ws[f"{pc[y]}{HEADER_ROW}"].number_format = YEAR
        ws[f"{pc[y]}{HEADER_ROW}"].alignment = Alignment(horizontal="center")
    _header(ws, HEADER_ROW, 1, PLAN_FIRST_COL + len(years) - 1)
    for key, (row, label) in PLAN_ROWS.items():
        _text(ws.cell(row, 1), label, bold=key in ("end", "pf"))

    ref, row = _plan_assumptions(ws, own, s.changes, frozen, plan_inputs_row(len(s.assessments)))
    ffb, row = _plan_ffb(ws, own, s.changes, frozen, ex, row)
    rates = _Rates(
        ref["operating_inflation"],
        ref["expense_inflation"],
        ref["expense_base_year"],
        ref["start_year"],
    )
    totals = _plan_changes(ws, b, own, s.changes, frozen, ex, rates, row)
    operating, reserve = totals.operating, totals.reserve
    if s.adoption:
        r = totals.last_row + 2
        for i, label in enumerate((ADOPTED_ON_LABEL, ADOPTION_NOTE_LABEL, ADOPTION_ORDER_LABEL)):
            _text(_at(ws, r + i, 1), label, bold=True)
        _text(_at(ws, r, VALUE_COL), s.adoption.adopted_on.isoformat())
        _text(_at(ws, r + 1, VALUE_COL), s.adoption.note)
        _at(ws, r + 2, VALUE_COL).value = s.adoption.sequence
        # a reminder that it is read-only – no password, so nothing is locked away
        ws.protection.sheet = True

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
            "operating": (f"={operating[y]}", CUR, BLACK),
            "contribution": (f"=MAX(0,{D['total_dues']}-{D['operating']})", CUR, BLACK),
            "sa_total": (f"={D['sa']}*{ref['units']}", CUR, BLACK),
            "owners": (f"={D['total_dues']}+{D['sa_total']}", CUR, BLACK),
            "interest": (f"={D['start']}*{ref['interest_rate']}", CUR, BLACK),
            "expenses": (f"={reserve[y]}", CUR, BLACK),
            "start": (f"={ref['starting_balance']}" if i == 0 else f"={P['end']}", CUR, BLACK),
            "end": (
                f"={D['start']}+{D['contribution']}+{D['sa_total']}+{D['interest']}"
                f"-{D['expenses']}",
                CUR,
                BLACK,
            ),
            "ffb": (f"={ffb[y + 1]}", CUR, BLACK),
            "pf": (f"=IF({D['ffb']}=0,0,{D['end']}/{D['ffb']})", PCT, BLACK),
            "low": (f'=IF({D["end"]}<{ref["cushion"]},"LOW","ok")', CUR, BLACK),
            "met": (f'=IF({D["pf"]}>={ref["target"]},"yes","no")', CUR, BLACK),
            "vote": (
                # IF, not AND – a blank limit ("no limit") must never reach the arithmetic
                f'=IF(OR(IF({ref["max_dues_increase"]}="",FALSE,'
                f"IF({prior_dues}>0,{D['dues']}/{prior_dues}-1>{ref['max_dues_increase']},FALSE)),"
                f'IF({ref["max_assessment_share"]}="",FALSE,{D["sa_total"]}>'
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
            "target": (f"={ref['target']}", PCT, BLACK),
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


def _compare(wb: Workbook, plans: list[_Plan]) -> None:
    ws = wb.create_sheet(COMPARE)
    spans = {(p.baseline.start_year, p.baseline.end_year) for p in plans}
    shared = len(spans) == 1  # calendar years in the labels only when every plan has them
    start, end = next(iter(spans)) if shared else (0, 0)
    _widths(ws, [58] + [18] * len(plans))
    _text(ws["A1"], "Scenario comparison", bold=True, size=13)
    _text(
        ws["A2"],
        "All figures are pulled from the Plan sheets. Change inputs there or on Inputs and "
        "Expenses and this updates."
        + (
            ""
            if shared
            else " The scenarios cover different years, so measures are by year of "
            "each scenario's own projection."
        ),
        italic=True,
        size=9,
    )

    def span(p: _Plan, key: str, a: int = 0, z: int | None = None) -> str:
        z = len(p.baseline.years) - 1 if z is None else z
        return (
            f"{quote(p.sheet)}!{col_letter(PLAN_FIRST_COL + a)}{ROW[key]}"
            f":{col_letter(PLAN_FIRST_COL + z)}{ROW[key]}"
        )

    def at(p: _Plan, key: str, offset: int) -> str:
        if offset >= len(p.baseline.years):
            return ""  # the plan is shorter than this measure
        return f"={quote(p.sheet)}!{col_letter(PLAN_FIRST_COL + offset)}{ROW[key]}"

    def header(p: _Plan) -> str:
        n = len(p.baseline.years)
        return (
            f"{quote(p.sheet)}!{col_letter(PLAN_FIRST_COL)}{HEADER_ROW}"
            f":{col_letter(PLAN_FIRST_COL + n - 1)}{HEADER_ROW}"
        )

    def year(offset: int) -> str:
        return str(start + offset) if shared else f"year {offset + 1}"

    whole = f"{start}–{end}" if shared else "whole projection"
    final = str(end) if shared else "the projection"
    longest = max(len(p.baseline.years) for p in plans)
    Measure = tuple[str, Callable[[_Plan], str], str]
    measures: list[Measure] = [
        (f"Dues per unit per month – {year(0)}", lambda p: at(p, "dues", 0), CUR_CENTS),
        (f"Dues per unit per month – {year(3)}", lambda p: at(p, "dues", 3), CUR_CENTS),
    ]
    if longest >= 9:
        measures.append(
            (f"Dues per unit per month – {year(8)}", lambda p: at(p, "dues", 8), CUR_CENTS)
        )
    measures += [
        (
            f"Special assessments per unit, total {whole}",
            lambda p: f"=SUM({span(p, 'sa')})",
            CUR,
        ),
        (f"Lowest year-end reserve balance, {whole}", lambda p: f"=MIN({span(p, 'end')})", CUR),
        (
            f"Year of lowest year-end balance, {whole}",
            lambda p: f"=INDEX({header(p)},MATCH(MIN({span(p, 'end')}),{span(p, 'end')},0))",
            YEAR,
        ),
        (
            f"Years below minimum cushion, {whole}",
            lambda p: f'=COUNTIF({span(p, "low")},"LOW")',
            "0",
        ),
        (
            f"Years needing an owner vote, {whole}",
            lambda p: f'=COUNTIF({span(p, "vote")},"yes")',
            "0",
        ),
        (
            f"Years with an operating shortfall, {whole}",
            lambda p: f'=COUNTIF({span(p, "short")},"yes")',
            "0",
        ),
        (f"Reserve balance end of {year(3)}", lambda p: at(p, "end", 3), CUR),
        (f"Percent funded end of {year(3)}", lambda p: at(p, "pf", 3), PCT),
    ]
    if longest >= 9:
        measures += [
            (f"Reserve balance end of {year(8)}", lambda p: at(p, "end", 8), CUR),
            (f"Percent funded end of {year(8)}", lambda p: at(p, "pf", 8), PCT),
        ]
    measures += [
        (
            f"Reserve balance end of {final}",
            lambda p: at(p, "end", len(p.baseline.years) - 1),
            CUR,
        ),
        (
            f"Percent funded end of {final}",
            lambda p: at(p, "pf", len(p.baseline.years) - 1),
            PCT,
        ),
        (
            "First year percent-funded target is met",
            lambda p: (
                f"=IFERROR(INDEX({header(p)},"
                f'MATCH("yes",{span(p, "met")},0)),"not by {p.baseline.end_year}")'
            ),
            YEAR,
        ),
        (
            "Owner outlay per unit, first five years"
            + (f", {start}–{start + 4}" if shared else "")
            + " (dues + assessments)",
            lambda p: f"=SUM({span(p, 'own_cost', 0, 4)})",
            CUR,
        ),
        (
            f"Owner outlay per unit, {whole} (dues + assessments)",
            lambda p: f"=SUM({span(p, 'own_cost')})",
            CUR,
        ),
        (
            f"Extra cost vs current dues, {whole}, per unit",
            lambda p: f"=SUM({span(p, 'extra')})",
            CUR,
        ),
        (
            "Extra cost vs current dues, first four years"
            + (f", {start}–{start + 3}" if shared else "")
            + ", per unit",
            lambda p: f"=SUM({span(p, 'extra', 0, 3)})",
            CUR,
        ),
        (
            f"Average owner cost per year, {whole}, per unit",
            lambda p: f"=AVERAGE({span(p, 'own_cost')})",
            CUR,
        ),
        (
            f"Average extra cost per year vs current dues, {whole}, per unit",
            lambda p: f"=AVERAGE({span(p, 'extra')})",
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
            text = formula(plan)
            if text:
                _formula(ws.cell(i, 2 + j), text, fmt, color=GREEN)
            else:
                _text(ws.cell(i, 2 + j), "–")
                ws.cell(i, 2 + j).alignment = Alignment(horizontal="right")

    r = head + len(measures) + 2
    every_year = sorted({y for p in plans for y in p.baseline.years})
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
        for y in every_year:
            ws.cell(r, 1, y).number_format = YEAR
            ws.cell(r, 1).alignment = Alignment(horizontal="left")
            for j, plan in enumerate(plans):
                if y in plan.baseline.years:
                    offset = y - plan.baseline.start_year
                    _formula(ws.cell(r, 2 + j), at(plan, key, offset), fmt, color=GREEN)
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
            "1. Inputs – starting balance, units, current dues, operating cost inflation, reserve "
            "expense inflation, interest, the minimum cushion, the percent-funded target and the "
            "owner-vote limits.",
            False,
            10,
        ),
        (
            "2. Expenses – one row per expense and how often it falls. Monthly and yearly lines "
            "are operating costs paid from dues, each grown at its own inflation rate or the "
            "operating rate. Once and every-few-years lines are reserve expenses, grown from the "
            "expense base year at the reserve expense inflation rate unless marked as already in "
            "that year's dollars. Below them is the reserve study's Fully Funded Balance for each "
            "year.",
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
        _Plan(s, sheet, baseline_for(project.baseline, s))
        for s, sheet in zip(chosen, sheet_names([s.name for s in chosen]), strict=True)
    ]
    for plan in plans:
        horizon = horizon_problem(plan.baseline)
        if horizon:  # its sheet could not be laid out
            raise ValueError(f"{plan.scenario.name} – {horizon}")
    wb = Workbook()
    wb.remove(wb.worksheets[0])
    _inputs(wb, project)
    refs = _expenses(wb, project.baseline)
    for plan in plans:
        _plan(wb, project.baseline, plan, refs)
    _compare(wb, plans)
    charts.add_charts_sheet(
        wb,
        CHARTS,
        [(p.sheet, p.scenario.name, len(p.baseline.years)) for p in plans],
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
