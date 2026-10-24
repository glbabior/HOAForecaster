"""Read a workbook in the export layout back into a project (spec section 7.1 import).

Inputs are read from the blue cells – values, never formulas – and located by
their labels, so rows a board member inserts or moves are tolerated. Everything
read is passed through the same strict parser as a project file.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from hoa_engine.model import Project, ProjectFormatError, project_from_dict
from hoa_engine.validate import validate_baseline, validate_scenario
from hoa_workbook.layout import (
    ASSESS_AMOUNT_COL,
    ASSESS_NOTE_COL,
    ASSESS_YEAR_COL,
    CHARTS_LABEL,
    EXPENSE_COL,
    EXPENSE_TOTAL_LABEL,
    EXPENSE_YEAR_COL,
    EXPENSES,
    FFB_LABEL,
    FREQUENCY_TEXT,
    HEADER_ROW,
    INPUT_ROWS,
    INPUTS,
    MODE_GROWN,
    MODE_TYPED,
    OPERATING_TOTAL_LABEL,
    PLAN_FIRST_COL,
    PLAN_ROWS,
    RESERVED,
    ROUND_DOLLAR,
    ROUND_NONE,
    ROW,
)

if not openpyxl.DEFUSEDXML:  # pragma: no cover – guards the environment, not the code
    raise RuntimeError("defusedxml must be installed and enabled to read untrusted workbooks")

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024  # an export unpacks to well under 1 MB
MAX_ENTRIES = 2000
MAX_RATIO = 100  # compression ratio of any one part; larger means a crafted file
MAX_ROWS, MAX_COLUMNS = 2000, 200  # far beyond any real export


class WorkbookFormatError(ValueError):
    """A workbook this app cannot read, explained in plain language."""


def _check_package(data: bytes) -> None:
    if len(data) > MAX_FILE_BYTES:
        raise WorkbookFormatError("the file is larger than 20 MB – not an HOAForecaster workbook")
    try:
        entries = zipfile.ZipFile(BytesIO(data)).infolist()
    except zipfile.BadZipFile:
        raise WorkbookFormatError("the file is not an Excel workbook (.xlsx)") from None
    if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_UNPACKED_BYTES:
        raise WorkbookFormatError("the workbook unpacks to an unreasonable size – not read")
    if any(e.file_size > MAX_RATIO * max(e.compress_size, 1) for e in entries):
        raise WorkbookFormatError("the workbook is compressed suspiciously well – not read")


def _number(value: Any, where: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise WorkbookFormatError(f"{where} should be a number, found {value!r}")
    return repr(value) if isinstance(value, float) else str(value)


def _whole(value: Any, where: str, what: str = "a year") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkbookFormatError(f"{where} should be {what}, found {value!r}")
    return value


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _comment(cell: Any) -> str:
    return cell.comment.text.strip() if cell.comment else ""


def _label_rows(ws: Worksheet) -> dict[str, int]:
    rows = ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=1, values_only=True)
    return {_text(v): r for r, (v,) in enumerate(rows, start=1) if isinstance(v, str)}


def _check_size(wb: Workbook) -> None:
    for ws in wb.worksheets:
        if ws.max_row > MAX_ROWS or ws.max_column > MAX_COLUMNS:
            raise WorkbookFormatError(
                f"the {ws.title} sheet is far larger than an HOAForecaster export – not read"
            )


def _sheet(wb: Workbook, name: str) -> Worksheet:
    if name not in wb.sheetnames:
        raise WorkbookFormatError(f"the workbook has no {name} sheet – not an HOAForecaster export")
    return wb[name]


def _baseline(wb: Workbook) -> tuple[dict[str, str], dict[str, Any]]:
    ws = _sheet(wb, INPUTS)
    rows = _label_rows(ws)
    raw: dict[str, Any] = {"sources": {}}
    text: dict[str, str] = {}
    for spec in INPUT_ROWS:
        if spec.label not in rows:
            raise WorkbookFormatError(f"Inputs is missing the row '{spec.label}'")
        r = rows[spec.label]
        value = ws.cell(r, 2).value
        where = f"Inputs '{spec.label}'"
        if spec.kind == "text":
            text[spec.key] = "" if value is None else str(value)
        elif spec.kind == "year":
            raw[spec.key] = _whole(value, where)
        elif spec.kind == "count":
            raw[spec.key] = _whole(value, where, "a whole number")
        elif value is None and spec.key.startswith("max_"):
            raw[spec.key] = None  # a blank governance limit means no limit
        else:
            raw[spec.key] = _number(value, where)
        if _text(ws.cell(r, 3).value):
            raw["sources"][spec.key] = _text(ws.cell(r, 3).value)

    ex = _sheet(wb, EXPENSES)
    rows = _label_rows(ex)
    if not {EXPENSE_TOTAL_LABEL, OPERATING_TOTAL_LABEL, FFB_LABEL} <= rows.keys():
        raise WorkbookFormatError(
            "the Expenses sheet is missing its total or Fully Funded Balance row"
        )
    total_row = rows[EXPENSE_TOTAL_LABEL]
    summed = _summed_rows(ex.cell(total_row, EXPENSE_YEAR_COL).value, "Expenses total")
    operating = ex.cell(rows[OPERATING_TOTAL_LABEL], EXPENSE_YEAR_COL).value
    if _summed_rows(operating, "operating total") != summed:
        raise WorkbookFormatError(
            "the operating and reserve totals on Expenses add up different rows – "
            "export again from the app"
        )
    lines = []
    for r in range(HEADER_ROW + 1, rows[OPERATING_TOTAL_LABEL]):
        description = ex.cell(r, EXPENSE_COL["description"]).value
        amount = ex.cell(r, EXPENSE_COL["amount"]).value
        if description is None and amount is None:
            continue
        where = f"Expenses row {r}"
        if r not in summed:
            raise WorkbookFormatError(
                f"{where} is outside the rows the total adds up – insert new expenses between "
                "two existing expense rows"
            )
        if not _is_formula(ex.cell(r, EXPENSE_YEAR_COL).value):
            # the workbook's total would leave this row out; refuse rather than disagree with it
            raise WorkbookFormatError(
                f"{where} has no year formulas, so the workbook's totals leave it out – "
                "copy a whole existing row to add an expense"
            )
        lines.append((r, _expense_line(ex, r, where)))
    raw["expense_lines"] = _with_ids(lines, EXPENSES)

    ffb_row = rows[FFB_LABEL]
    if _comment(ex.cell(ffb_row, 1)):
        raw["sources"]["ffb"] = _comment(ex.cell(ffb_row, 1))
    ffb = {}
    for c in range(EXPENSE_YEAR_COL, ex.max_column + 1):
        year, value = ex.cell(ffb_row - 1, c).value, ex.cell(ffb_row, c).value
        if year is None:
            continue
        ffb[str(_whole(year, "Fully Funded Balance year"))] = _number(
            value, f"Fully Funded Balance {year}"
        )
    raw["ffb"] = ffb
    return text, raw


_FREQUENCY = {text: key for key, text in FREQUENCY_TEXT.items()}


def _optional_whole(value: Any, where: str) -> int | None:
    return None if value is None else _whole(value, where)


def _expense_line(ws: Worksheet, r: int, where: str) -> dict[str, Any]:
    """The inputs of one expense row, in the project file's form."""

    def cell(key: str) -> Any:
        return ws.cell(r, EXPENSE_COL[key]).value

    # exactly as written (SUMIF ignores case but not spaces), or the totals would leave it out
    text = cell("frequency")
    frequency = _FREQUENCY.get(text.lower()) if isinstance(text, str) else None
    if frequency is None:
        raise WorkbookFormatError(
            f"{where} – 'How often' should be one of {', '.join(FREQUENCY_TEXT.values())}"
        )
    inflation = cell("inflation")
    interval = cell("interval")
    return {
        "id": _text(cell("id")),
        "frequency": frequency,
        "description": _text(cell("description")),
        "source": _comment(ws.cell(r, EXPENSE_COL["description"])),
        "amount": _number(cell("amount"), where + " amount"),
        "year": _optional_whole(cell("year"), where + " year"),
        "end_year": _optional_whole(cell("end_year"), where + " last year"),
        "interval": None
        if interval is None
        else _whole(interval, where + " interval", "a number of years"),
        "inflation": None if inflation is None else _number(inflation, where + " inflation"),
        "nominal": _text(cell("nominal")).lower() == "yes",
    }


def _with_ids(lines: list[tuple[int, dict[str, Any]]], sheet: str) -> list[dict[str, Any]]:
    """Every line with an identifier of its own. A row added in Excel with its id cleared gets
    a new one; a row copied with its id kept is refused, since which row is the original –
    the one scenarios refer to – cannot be told."""
    rows_of: dict[str, list[int]] = {}
    for r, line in lines:
        if line["id"]:
            rows_of.setdefault(line["id"], []).append(r)
    for line_id, rows in rows_of.items():
        if len(rows) > 1:
            raise WorkbookFormatError(
                f"rows {rows[0]} and {rows[1]} on {sheet} share the line id '{line_id[:40]}' – "
                "clear the id of the row you added"
            )
    n = 1
    for _, line in lines:
        if not line["id"]:
            while f"line-{n}" in rows_of:
                n += 1
            line["id"] = f"line-{n}"
            rows_of[line["id"]] = []
    return [line for _, line in lines]


_RANGE = re.compile(r"\$?[A-Z]{1,3}\$?(\d+):\$?[A-Z]{1,3}\$?(\d+)")
# rows whose year cells are always formulas; the dues rows are formulas only for grown dues
_INPUT_KEYS = {"dues", "grown", "mode", "first", "rate", "pinned", "rounding"}
_CALCULATED = [k for k in ROW if k not in _INPUT_KEYS]


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _summed_rows(formula: Any, what: str) -> range:
    """The rows a SUM or SUMIF in the export adds up – the reader takes exactly those."""
    match = _RANGE.search(formula) if isinstance(formula, str) else None
    if match is None:
        raise WorkbookFormatError(
            f"the {what} formula has been changed – export again from the app"
        )
    return range(int(match[1]), int(match[2]) + 1)


def _plan_rows(ws: Worksheet) -> dict[str, int]:
    """Plan rows by label, so a row a board member inserts moves nothing out of reach."""
    rows = _label_rows(ws)
    missing = [label for _, label in PLAN_ROWS.values() if label not in rows]
    if missing:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{missing[0]}'")
    return {key: rows[label] for key, (_, label) in PLAN_ROWS.items()}


def _is_plan(ws: Worksheet) -> bool:
    return ws.title not in RESERVED and PLAN_ROWS["mode"][1] in _label_rows(ws)


def _scenario(ws: Worksheet, horizon: range) -> dict[str, Any]:
    row = _plan_rows(ws)
    years: dict[int, int] = {}
    for c in range(PLAN_FIRST_COL, ws.max_column + 1):
        v = ws.cell(HEADER_ROW, c).value
        if v is not None:
            years[_whole(v, f"{ws.title} year header")] = c
    if list(years) != list(horizon):
        raise WorkbookFormatError(
            f"{ws.title} has year columns that no longer match the start and end year on Inputs – "
            "the horizon can only be changed in the app"
        )
    mode = _text(ws.cell(row["mode"], PLAN_FIRST_COL).value)
    rounding = _text(ws.cell(row["rounding"], PLAN_FIRST_COL).value)
    if mode not in (MODE_TYPED, MODE_GROWN) or rounding not in (ROUND_DOLLAR, ROUND_NONE):
        raise WorkbookFormatError(f"{ws.title} – unrecognised dues settings below the table")

    def at(key: str, c: int) -> Any:
        return ws.cell(row[key], c).value

    calculated = _CALCULATED + (["dues", "grown"] if mode == MODE_GROWN else [])
    for key in calculated:
        for y, c in years.items():
            if not _is_formula(at(key, c)):
                advice = (
                    "pin that year's dues in the row below the table instead"
                    if key == "dues"
                    else "change the inputs it is calculated from instead"
                )
                raise WorkbookFormatError(
                    f"{ws.title} – '{PLAN_ROWS[key][1]}' for {y} was typed over, but that row is "
                    f"calculated; {advice}"
                )

    if mode == MODE_TYPED:
        dues: dict[str, Any] = {
            "mode": "explicit",
            "explicit": {
                str(y): _number(at("dues", c), f"{ws.title} dues {y}") for y, c in years.items()
            },
        }
    else:
        first = ws.cell(row["first"], PLAN_FIRST_COL).value
        rate = ws.cell(row["rate"], PLAN_FIRST_COL).value
        dues = {
            "mode": "rate",
            "first_value": _number(first, f"{ws.title} first-year dues"),
            "annual_increase": _number(rate, f"{ws.title} annual dues increase"),
            "overrides": {
                str(y): _number(at("pinned", c), f"{ws.title} pinned dues {y}")
                for y, c in years.items()
                if at("pinned", c) is not None
            },
        }

    listed = _summed_rows(at("sa", PLAN_FIRST_COL), f"{ws.title} special assessment")
    assessments = []
    r = listed.start
    while r <= ws.max_row and not _text(ws.cell(r, 1).value).startswith(CHARTS_LABEL):
        year, amount = ws.cell(r, ASSESS_YEAR_COL).value, ws.cell(r, ASSESS_AMOUNT_COL).value
        if year is not None or amount is not None:
            where = f"{ws.title} assessment row {r}"
            if r not in listed:
                raise WorkbookFormatError(
                    f"{where} is below the assessment list, so the sheet does not count it – "
                    "insert new assessments between two rows of the list"
                )
            note = ws.cell(r, ASSESS_NOTE_COL).value
            assessments.append(
                {
                    "year": _whole(year, where + " year"),
                    "amount": _number(amount, where + " amount"),
                    "note": "" if note is None else str(note),
                }
            )
        r += 1
    return {
        "name": ws.title if ws["A1"].value is None else str(ws["A1"].value),
        "description": "" if ws["A2"].value is None else str(ws["A2"].value),
        "dues": dues,
        "assessments": assessments,
        "rounding": "dollar" if rounding == ROUND_DOLLAR else "none",
    }


def read_workbook(source: Path | bytes) -> Project:
    """The project in an exported workbook. Raises WorkbookFormatError if it cannot be read."""
    data = source.read_bytes() if isinstance(source, Path) else source
    _check_package(data)
    try:
        wb = openpyxl.load_workbook(BytesIO(data), data_only=False)
    except Exception:  # openpyxl raises many types for damaged files
        raise WorkbookFormatError(
            "the workbook could not be opened – it may be damaged or not an Excel file"
        ) from None
    _check_size(wb)
    text, baseline = _baseline(wb)
    horizon = range(baseline["start_year"], baseline["end_year"] + 1)
    scenarios = [_scenario(ws, horizon) for ws in wb.worksheets if _is_plan(ws)]
    try:
        project = project_from_dict({**text, "baseline": baseline, "scenarios": scenarios})
    except ProjectFormatError as e:
        raise WorkbookFormatError(str(e)) from None
    problems = validate_baseline(project.baseline)
    for s in project.scenarios if not problems else ():
        problems += [f"{s.name} – {p}" for p in validate_scenario(s, project.baseline)]
    if problems:
        raise WorkbookFormatError("; ".join(problems))
    return project
