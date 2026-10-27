"""Read a workbook in the export layout back into a project (spec section 7.1 import).

Inputs are read from the blue cells – values, never formulas – and located by
their labels, so rows a board member inserts or moves are tolerated. Each label
is looked for only in its own part of the sheet, so an expense or note worded
like a label cannot stand in for it. Everything read is passed through the same
strict parser as a project file.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from hoa_engine.model import LIMITS, Project, ProjectFormatError, project_from_dict
from hoa_engine.validate import MAX_YEARS, MIN_YEARS, validate_run
from hoa_workbook.layout import (
    ADOPTED_ON_LABEL,
    ADOPTION_NOTE_LABEL,
    ADOPTION_ORDER_LABEL,
    ASSESS_AMOUNT_COL,
    ASSESS_NOTE_COL,
    ASSESS_YEAR_COL,
    CHARTS_LABEL,
    EXPENSE_COL,
    EXPENSE_YEAR_COL,
    EXPENSES_HEADING,
    FACT_ROWS,
    FACTS_HEADING,
    FFB_LABEL,
    FREQUENCY_TEXT,
    HEADER_ROW,
    MODE_GROWN,
    MODE_TYPED,
    NAME_LABEL,
    NOTES_LABEL,
    OLD_SHEETS,
    PLAN_FFB_HEADING,
    PLAN_FIRST_COL,
    PLAN_OPERATING_LABEL,
    PLAN_RESERVE_LABEL,
    PLAN_ROWS,
    PROJECT,
    RESERVED,
    ROUND_DOLLAR,
    ROUND_NONE,
    ROW,
    SOURCE_COL,
    VALUE_COL,
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


def _labels(ws: Worksheet) -> list[tuple[int, str]]:
    rows = ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=1, values_only=True)
    return [(r, _text(v)) for r, (v,) in enumerate(rows, start=1) if isinstance(v, str)]


def _last_rows(ws: Worksheet) -> dict[str, int]:
    """Each label's last row – a total sits below every line that might share its words."""
    return {label: r for r, label in _labels(ws)}


def _first_rows(ws: Worksheet, after: int = 0) -> dict[str, int]:
    """Each label's first row below `after` – a section's labels come before anything a
    board member typed further down."""
    out: dict[str, int] = {}
    for r, label in _labels(ws):
        if r > after:
            out.setdefault(label, r)
    return out


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


def _horizon(start: int, end: int, where: str) -> range:
    """The years from start to end – checked before anything walks them."""
    if not MIN_YEARS <= end - start + 1 <= MAX_YEARS:
        raise WorkbookFormatError(
            f"{where} – the horizon must be {MIN_YEARS}–{MAX_YEARS} full years"
        )
    return range(start, end + 1)


def _project(wb: Workbook) -> dict[str, str]:
    """The association's name and notes, from the Project sheet."""
    if PROJECT not in wb.sheetnames and all(name in wb.sheetnames for name in OLD_SHEETS):
        raise WorkbookFormatError(
            "this workbook was exported by an earlier version of HOAForecaster, before each "
            "scenario held its own facts – import the project file (Export project) instead"
        )
    ws = _sheet(wb, PROJECT)
    rows = _first_rows(ws)
    out = {}
    for key, label in (("name", NAME_LABEL), ("notes", NOTES_LABEL)):
        if label not in rows:
            raise WorkbookFormatError(f"{PROJECT} is missing the row '{label}'")
        value = ws.cell(rows[label], 2).value
        out[key] = "" if value is None else str(value)
    return out


_FREQUENCY = {text: key for key, text in FREQUENCY_TEXT.items()}
_LINE_INPUTS = ("frequency", "amount", "year", "end_year", "interval", "inflation", "nominal")


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


def _with_ids(scenarios: list[dict[str, Any]]) -> None:
    """Every line an identifier of its own – a row added in Excel with its id cleared, or copied
    with its id kept, gets a new `line-N` that no sheet of the workbook uses, so it can never be
    taken for another scenario's line (spec 7.2)."""
    all_lines = [s["facts"]["expense_lines"] for s in scenarios]
    used = {line["id"] for lines in all_lines for line in lines if line["id"]}
    n = 1
    for lines in all_lines:
        seen: set[str] = set()
        for line in lines:
            if line["id"] and line["id"] not in seen:
                seen.add(line["id"])
                continue
            while f"line-{n}" in used:
                n += 1
            line["id"] = f"line-{n}"
            used.add(line["id"])


# the range a SUMIF or SUM adds up – the first argument, on the formula's own sheet
_SUMMED = re.compile(r"\bSUM(?:IF)?\(\$?[A-Z]{1,3}\$?(\d+):\$?[A-Z]{1,3}\$?(\d+)")
# rows whose year cells are always formulas; the dues rows are formulas only for grown dues
_INPUT_KEYS = {"dues", "grown", "mode", "first", "rate", "pinned", "rounding"}
_CALCULATED = [k for k in ROW if k not in _INPUT_KEYS]


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _summed_rows(formula: Any, what: str) -> range:
    """The rows a SUM or SUMIF in the export adds up – the reader takes exactly those."""
    match = _SUMMED.search(formula) if isinstance(formula, str) else None
    if match is None:
        raise WorkbookFormatError(
            f"the {what} formula has been changed – export again from the app"
        )
    return range(int(match[1]), int(match[2]) + 1)


# a Plan sheet's name, description and note above its rows, never read as labels
_TITLE_ROWS = 3


def _plan_rows(ws: Worksheet) -> dict[str, int]:
    """Plan rows by label, so a row a board member inserts moves nothing out of reach."""
    rows = _first_rows(ws, _TITLE_ROWS)
    missing = [label for _, label in PLAN_ROWS.values() if label not in rows]
    if missing:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{missing[0]}'")
    return {key: rows[label] for key, (_, label) in PLAN_ROWS.items()}


def _is_plan(ws: Worksheet) -> bool:
    return ws.title not in RESERVED and PLAN_ROWS["mode"][1] in _first_rows(ws, _TITLE_ROWS)


def _typed_cell(value: Any, where: str) -> Any:
    """An input cell's value – a formula there is refused, since re-import could not say what
    it means."""
    if _is_formula(value):
        raise WorkbookFormatError(
            f"{where} holds a formula – type the figure instead, or export again from the app"
        )
    return value


def _sections(ws: Worksheet) -> dict[str, int]:
    """The rows of the blocks below a Plan sheet's charts, each found below the one before."""
    found: dict[str, int] = {}
    after = next((r for r, label in _labels(ws) if label.startswith(CHARTS_LABEL)), 0)
    for heading in (FACTS_HEADING, PLAN_FFB_HEADING, FFB_LABEL, EXPENSES_HEADING):
        r = _first_rows(ws, after).get(heading)
        if r is None:
            raise WorkbookFormatError(f"{ws.title} is missing the row '{heading}'")
        found[heading] = after = r
    total = _last_rows(ws).get(PLAN_OPERATING_LABEL, 0)
    if total <= after:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{PLAN_OPERATING_LABEL}'")
    found[PLAN_OPERATING_LABEL] = total
    reserve = _first_rows(ws, total).get(PLAN_RESERVE_LABEL)
    if reserve is None:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{PLAN_RESERVE_LABEL}'")
    found[PLAN_RESERVE_LABEL] = reserve
    return found


def _typed(value: Any, kind: str, key: str, where: str) -> Any:
    """A scenario's value for one input, in the project file's form."""
    if value is None and key in LIMITS:
        return None  # no limit
    if kind in ("year", "count"):
        return _whole(value, where, "a whole number")
    return _number(value, where)


def _adoption(ws: Worksheet, sections: dict[str, int]) -> dict[str, Any] | None:
    """An adopted plan's date, note and order – the rows below its reserve total."""
    rows = _first_rows(ws, sections[PLAN_RESERVE_LABEL])
    if ADOPTED_ON_LABEL not in rows:
        return None
    labels = (ADOPTED_ON_LABEL, ADOPTION_NOTE_LABEL, ADOPTION_ORDER_LABEL)
    missing = [label for label in labels if label not in rows]
    if missing:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{missing[0]}'")
    when, note, order = (ws.cell(rows[label], VALUE_COL).value for label in labels)
    if isinstance(when, datetime):  # Excel turns a date typed over the text into one
        when = when.date().isoformat()
    if not isinstance(when, str):
        raise WorkbookFormatError(f"{ws.title} – the adoption date should be written as text")
    return {
        "date": when,
        "note": "" if note is None else str(note),
        "sequence": _whole(order, f"{ws.title} adoption order", "a whole number"),
    }


def _inputs(ws: Worksheet) -> dict[str, Any]:
    """The scenario's facts and assumptions, Fully Funded Balance and expenses, from the blocks
    below its charts, and its adoption if it is an adopted plan."""
    sections = _sections(ws)
    rows = _first_rows(ws, sections[FACTS_HEADING])
    facts: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for spec in FACT_ROWS:
        r = rows.get(spec.label)
        if r is None or r > sections[PLAN_FFB_HEADING]:
            raise WorkbookFormatError(f"{ws.title} is missing the row '{spec.label}'")
        where = f"{ws.title} '{spec.label}'"
        value = _typed_cell(ws.cell(r, VALUE_COL).value, where)
        note = _typed_cell(ws.cell(r, SOURCE_COL).value, f"{where} source")
        facts[spec.key] = _typed(value, spec.kind, spec.key, where)
        if _text(note):
            sources[spec.key] = _text(note)
    horizon = _horizon(facts["start_year"], facts["end_year"], ws.title)

    ffb_row = sections[FFB_LABEL]
    if _comment(ws.cell(ffb_row, 1)):
        sources["ffb"] = _comment(ws.cell(ffb_row, 1))
    ffb = {}
    for c in range(VALUE_COL, ws.max_column + 1):
        year, value = ws.cell(ffb_row - 1, c).value, ws.cell(ffb_row, c).value
        if year is None or value is None:
            continue
        y = _whole(year, f"{ws.title} Fully Funded Balance year")
        where = f"{ws.title} Fully Funded Balance {y}"
        ffb[str(y)] = _number(_typed_cell(value, where), where)

    head = sections[EXPENSES_HEADING] + 1
    total = ws.cell(sections[PLAN_OPERATING_LABEL], EXPENSE_YEAR_COL).value
    listed = _summed_rows(total, f"{ws.title} operating total")
    reserve = ws.cell(sections[PLAN_RESERVE_LABEL], EXPENSE_YEAR_COL).value
    if _summed_rows(reserve, f"{ws.title} reserve total") != listed:
        raise WorkbookFormatError(
            f"the operating and reserve totals on {ws.title} add up different rows – export "
            "again from the app"
        )
    lines = []
    for r in range(head + 1, sections[PLAN_OPERATING_LABEL]):
        inputs = [ws.cell(r, EXPENSE_COL[key]).value for key in _LINE_INPUTS]
        if all(v is None or v == "" for v in inputs):
            continue  # a spare row
        where = f"{ws.title} expense row {r}"
        if r not in listed:
            raise WorkbookFormatError(
                f"{where} is outside the rows the totals add up – use the spare rows, or insert "
                "new rows between two rows of the list"
            )
        if not _is_formula(ws.cell(r, EXPENSE_YEAR_COL).value):
            raise WorkbookFormatError(
                f"{where} has no year formulas, so the sheet's totals leave it out – copy a whole "
                "row of the list to add one"
            )
        lines.append(_expense_line(ws, r, where))
    return {
        "facts": {
            **facts,
            "expense_lines": lines,
            "ffb": ffb,
            "sources": sources,
        },
        "horizon": horizon,
        "adoption": _adoption(ws, sections),
    }


def _scenario(ws: Worksheet) -> dict[str, Any]:
    read = _inputs(ws)
    horizon = read["horizon"]
    row = _plan_rows(ws)
    years: dict[int, int] = {}
    for c in range(PLAN_FIRST_COL, ws.max_column + 1):
        v = ws.cell(HEADER_ROW, c).value
        if v is not None:
            years[_whole(v, f"{ws.title} year header")] = c
    if list(years) != list(horizon):
        raise WorkbookFormatError(
            f"{ws.title} has year columns that no longer match its start and end year – "
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
        "facts": read["facts"],
        "adoption": read["adoption"],
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
    text = _project(wb)
    scenarios = [_scenario(ws) for ws in wb.worksheets if _is_plan(ws)]
    _with_ids(scenarios)
    if not scenarios:
        raise WorkbookFormatError("the workbook has no scenario sheets")
    try:
        project = project_from_dict({**text, "schema_version": 3, "scenarios": scenarios})
    except ProjectFormatError as e:
        raise WorkbookFormatError(str(e)) from None
    problems = [f"{s.name} – {p}" for s in project.scenarios for p in validate_run(s)]
    if problems:
        raise WorkbookFormatError("; ".join(problems))
    return project
