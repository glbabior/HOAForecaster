"""Read a workbook in the export layout back into a project (spec section 7.1 import).

The project's facts are on the Project sheet and its Fully Funded Balance and expenses on the
Expenses sheet; an adopted plan's own are below its charts. A workbook exported before v2.0
has every scenario's below its charts, and is read as a schema 3 project and upgraded.

Inputs are read from the blue cells – values, never formulas – and located by
their labels, so rows a board member inserts or moves are tolerated. Each label
is looked for only in its own part of the sheet, so an expense or note worded
like a label cannot stand in for it. Everything read is passed through the same
strict parser as a project file.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import replace
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from hoa_engine.model import LIMITS, Project, ProjectFormatError, read_project
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
    EXPENSES,
    EXPENSES_HEADING,
    EXPENSES_TOP,
    FACT_ROWS,
    FACTS_HEADING,
    FFB_KEPT_LABEL,
    FFB_LABEL,
    FFB_MODE_LABEL,
    FFB_TYPED,
    FFB_WORKED_OUT,
    FREQUENCY_TEXT,
    HEADER_ROW,
    INCREASE_FROM_COL,
    INCREASE_RATE_COL,
    INCREASE_TO_COL,
    INCREASES_HEADING,
    MODE_GROWN,
    MODE_TYPED,
    NAME_LABEL,
    NOTES_LABEL,
    OLD_RATE_LABEL,
    OLD_SHEETS,
    PLAN_FFB_HEADING,
    PLAN_FFB_HEADING_BEFORE,
    PLAN_FIRST_COL,
    PLAN_OPERATING_LABEL,
    PLAN_RESERVE_LABEL,
    PLAN_ROWS,
    PROJECT,
    PROJECT_EXPENSES_HEADING,
    PROJECT_FACTS_HEADING,
    PROJECT_FFB_HEADING,
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
_LINE_INPUTS = (
    "frequency",
    "amount",
    "year",
    "end_year",
    "interval",
    "useful_life",
    "inflation",
    "nominal",
)


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
    life = cell("useful_life")
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
        "useful_life": None if life is None else _whole(life, where + " useful life", "years"),
    }


def _with_ids(facts: list[dict[str, Any]]) -> None:
    """Every line an identifier of its own – a row added in Excel with its id cleared, or copied
    with its id kept, gets a new `line-N` that no sheet of the workbook uses, so it can never be
    taken for another table's line."""
    all_lines = [f["expense_lines"] for f in facts]
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
    """Plan rows by label, so a row a board member inserts moves nothing out of reach. A sheet
    exported before yearly increases had periods has its one rate under the old label."""
    rows = _first_rows(ws, _TITLE_ROWS)
    if OLD_RATE_LABEL in rows and PLAN_ROWS["rate"][1] not in rows:
        rows[PLAN_ROWS["rate"][1]] = rows[OLD_RATE_LABEL]
    missing = [label for _, label in PLAN_ROWS.values() if label not in rows]
    if missing:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{missing[0]}'")
    return {key: rows[label] for key, (_, label) in PLAN_ROWS.items()}


def _is_plan(ws: Worksheet, shared: bool) -> bool:
    # before v2.0 a scenario named Expenses had a Plan sheet of that name; since, the name is the
    # project's Expenses sheet, whatever an expense on it is called
    known = ws.title not in RESERVED or (ws.title == EXPENSES and not shared)
    return known and PLAN_ROWS["mode"][1] in _first_rows(ws, _TITLE_ROWS)


def _typed_cell(value: Any, where: str) -> Any:
    """An input cell's value – a formula there is refused, since re-import could not say what
    it means."""
    if _is_formula(value):
        raise WorkbookFormatError(
            f"{where} holds a formula – type the figure instead, or export again from the app"
        )
    return value


def _sections(ws: Worksheet, after: int, headings: tuple[tuple[str, ...], ...]) -> list[int]:
    """The rows of a sheet's blocks below `after`, each found below the one before – under any
    of its headings, the first on the sheet, so an expense worded like a newer heading never
    stands in for an older one – then the operating and reserve totals."""
    found = []
    for names in headings:
        rows = _first_rows(ws, after)
        r = min((rows[h] for h in names if h in rows), default=None)
        if r is None:
            raise WorkbookFormatError(f"{ws.title} is missing the row '{names[0]}'")
        found.append(r)
        after = r
    total = _last_rows(ws).get(PLAN_OPERATING_LABEL, 0)
    if total <= after:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{PLAN_OPERATING_LABEL}'")
    reserve = _first_rows(ws, total).get(PLAN_RESERVE_LABEL)
    if reserve is None:
        raise WorkbookFormatError(f"{ws.title} is missing the row '{PLAN_RESERVE_LABEL}'")
    return [*found, total, reserve]


def _charts_row(ws: Worksheet) -> int:
    return next((r for r, label in _labels(ws) if label.startswith(CHARTS_LABEL)), 0)


def _has_own_facts(ws: Worksheet) -> bool:
    """Whether a Plan sheet carries facts below its charts – an adopted plan's, or any
    scenario's in a workbook exported before v2.0."""
    return FACTS_HEADING in _first_rows(ws, _charts_row(ws))


def _typed(value: Any, kind: str, key: str, where: str) -> Any:
    """A scenario's value for one input, in the project file's form."""
    if value is None and key in LIMITS:
        return None  # no limit
    if kind in ("year", "count"):
        return _whole(value, where, "a whole number")
    return _number(value, where)


def _adoption(ws: Worksheet, reserve_row: int) -> dict[str, Any] | None:
    """An adopted plan's date, note and order – the rows below its reserve total."""
    rows = _first_rows(ws, reserve_row)
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


_OWN_FFB = (PLAN_FFB_HEADING, PLAN_FFB_HEADING_BEFORE)


def _own_inputs(ws: Worksheet) -> dict[str, Any]:
    """A scenario's own facts and assumptions, Fully Funded Balance and expenses, from the
    blocks below its charts, and its adoption if it is an adopted plan."""
    facts_row, ffb_heading, ffb_row, expenses, total, reserve = _sections(
        ws, _charts_row(ws), ((FACTS_HEADING,), _OWN_FFB, (FFB_LABEL,), (EXPENSES_HEADING,))
    )
    return {
        **_inputs(ws, facts_row, ffb_heading, ws, (ffb_row, expenses, total, reserve)),
        "adoption": _adoption(ws, reserve),
    }


def _project_inputs(wb: Workbook) -> dict[str, Any]:
    """The project's facts and assumptions from the Project sheet, and its Fully Funded Balance
    and expenses from the Expenses sheet."""
    project, expenses = _sheet(wb, PROJECT), _sheet(wb, EXPENSES)
    facts_row = _first_rows(project)[PROJECT_FACTS_HEADING]  # the layout is chosen by it
    _ffb_heading, ffb_row, heading, total, reserve = _sections(
        expenses,
        EXPENSES_TOP - 1,
        ((PROJECT_FFB_HEADING,), (FFB_LABEL,), (PROJECT_EXPENSES_HEADING,)),
    )
    return _inputs(
        project, facts_row, project.max_row + 1, expenses, (ffb_row, heading, total, reserve)
    )


def _inputs(
    facts_ws: Worksheet,
    facts_row: int,
    facts_end: int,
    ws: Worksheet,
    blocks: tuple[int, int, int, int],
) -> dict[str, Any]:
    """Facts and assumptions from the block at `facts_row` on one sheet (up to `facts_end`),
    and the Fully Funded Balance and expenses from `blocks` on another – the Fully Funded
    Balance row, the expenses heading and the two totals."""
    ffb_row, expenses_heading, operating_total, reserve_total = blocks
    rows = _first_rows(facts_ws, facts_row)
    facts: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for spec in FACT_ROWS:
        r = rows.get(spec.label)
        if r is None or r > facts_end:
            raise WorkbookFormatError(f"{facts_ws.title} is missing the row '{spec.label}'")
        where = f"{facts_ws.title} '{spec.label}'"
        value = _typed_cell(facts_ws.cell(r, VALUE_COL).value, where)
        note = _typed_cell(facts_ws.cell(r, SOURCE_COL).value, f"{where} source")
        facts[spec.key] = _typed(value, spec.kind, spec.key, where)
        if _text(note):
            sources[spec.key] = _text(note)
    horizon = _horizon(facts["start_year"], facts["end_year"], facts_ws.title)

    if _comment(ws.cell(ffb_row, 1)):
        sources["ffb"] = _comment(ws.cell(ffb_row, 1))
    worked_out = _ffb_mode(ws, ffb_row + 1)
    typed_row = ffb_row
    if worked_out:
        typed_row = ffb_row + 2
        if _text(ws.cell(typed_row, 1).value) != FFB_KEPT_LABEL:
            raise WorkbookFormatError(f"{ws.title} is missing the row '{FFB_KEPT_LABEL}'")
    ffb = {}
    for c in range(VALUE_COL, ws.max_column + 1):
        year = ws.cell(ffb_row - 1, c).value
        if year is None:
            continue
        y = _whole(year, f"{ws.title} Fully Funded Balance year")
        where = f"{ws.title} Fully Funded Balance {y}"
        due = horizon.start <= y <= horizon.stop  # its years and one more
        if worked_out and due and not _is_formula(ws.cell(ffb_row, c).value):
            raise WorkbookFormatError(
                f"{where} was typed over, but it is worked out from the expenses – type the "
                "study's figure in the row below instead, or choose the study's figures in the app"
            )
        value = ws.cell(typed_row, c).value
        if value is not None:
            ffb[str(y)] = _number(_typed_cell(value, where), where)

    head = expenses_heading + 1
    total = ws.cell(operating_total, EXPENSE_YEAR_COL).value
    listed = _summed_rows(total, f"{ws.title} operating total")
    reserve = ws.cell(reserve_total, EXPENSE_YEAR_COL).value
    if _summed_rows(reserve, f"{ws.title} reserve total") != listed:
        raise WorkbookFormatError(
            f"the operating and reserve totals on {ws.title} add up different rows – export "
            "again from the app"
        )
    lines = []
    for r in range(head + 1, operating_total):
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
            "ffb_from_lines": worked_out,
        },
        "horizon": horizon,
    }


def _ffb_mode(ws: Worksheet, r: int) -> bool:
    """Whether the sheet's Fully Funded Balance is worked out from its expenses (spec 4.2) – the
    mode row below the figures."""
    label, value = _text(ws.cell(r, 1).value), _text(ws.cell(r, VALUE_COL).value)
    if not label and not value:
        return False  # exported before v1.7, which had no mode row – the study's figures
    if label != FFB_MODE_LABEL or value not in (FFB_TYPED, FFB_WORKED_OUT):
        raise WorkbookFormatError(
            f"{ws.title} – unrecognised '{FFB_MODE_LABEL}' below the Fully Funded Balance"
        )
    return value == FFB_WORKED_OUT


def _ends_assessments(label: str) -> bool:
    return label == INCREASES_HEADING or label.startswith(CHARTS_LABEL)


# the rows of the increases list a year's rate adds up – the From column's range
_COVERED = re.compile(r"SUMPRODUCT\(\(\(\(\$?[A-Z]{1,3}\$?(\d+):\$?[A-Z]{1,3}\$?(\d+)")


def _increases(ws: Worksheet, rate_formula: Any) -> list[dict[str, Any]]:
    """The yearly dues increases (spec 5.1) – the rows of the list below the assessments that
    the yearly rate formula adds up; blank rows are spare."""
    heading = _first_rows(ws, _TITLE_ROWS).get(INCREASES_HEADING)
    match = _COVERED.match(rate_formula[1:]) if _is_formula(rate_formula) else None
    if heading is None or match is None:
        raise WorkbookFormatError(
            f"{ws.title} – the yearly dues increases list or its formula has been changed – "
            "export again from the app"
        )
    listed = range(int(match[1]), int(match[2]) + 1)
    out = []
    r = heading + 2
    while r <= ws.max_row and not _text(ws.cell(r, 1).value).startswith(CHARTS_LABEL):
        cells = [
            ws.cell(r, c).value for c in (INCREASE_FROM_COL, INCREASE_TO_COL, INCREASE_RATE_COL)
        ]
        if any(v is not None for v in cells):
            where = f"{ws.title} yearly dues increase row {r}"
            if r not in listed:
                raise WorkbookFormatError(
                    f"{where} is outside the increases list, so the sheet does not count it – "
                    "insert new increases between two rows of the list"
                )
            first, last, rate = cells
            out.append(
                {
                    "first_year": _optional_whole(first, where + " From"),
                    "last_year": _optional_whole(last, where + " To"),
                    "rate": _number(rate, where + " increase"),
                }
            )
        r += 1
    return out


def _scenario(ws: Worksheet, project: dict[str, Any] | None) -> dict[str, Any]:
    """A Plan sheet's scenario – on its own facts if it has them below its charts, else on
    `project`'s (the project's facts and expenses, from the shared sheets)."""
    if project is None or _has_own_facts(ws):
        read = _own_inputs(ws)
    elif ADOPTED_ON_LABEL in _first_rows(ws, _charts_row(ws)):
        # an adopted plan keeps the facts it was adopted with – never the project's instead
        raise WorkbookFormatError(f"{ws.title} is missing the row '{FACTS_HEADING}'")
    else:
        read = project
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

    old_rate = OLD_RATE_LABEL in _first_rows(ws, _TITLE_ROWS)
    grown = ["dues", "grown"] + ([] if old_rate else ["rate"])
    calculated = _CALCULATED + (grown if mode == MODE_GROWN else [])
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
        if old_rate:  # one rate over every year, as exported before increases had periods
            rate = _number(ws.cell(row["rate"], PLAN_FIRST_COL).value, f"{ws.title} dues increase")
            increases = [{"first_year": None, "last_year": None, "rate": rate}]
        else:
            increases = _increases(ws, at("rate", PLAN_FIRST_COL))
        dues = {
            "mode": "rate",
            "first_value": _number(first, f"{ws.title} first-year dues"),
            "increases": increases,
            "overrides": {
                str(y): _number(at("pinned", c), f"{ws.title} pinned dues {y}")
                for y, c in years.items()
                if at("pinned", c) is not None
            },
        }

    listed = _summed_rows(at("sa", PLAN_FIRST_COL), f"{ws.title} special assessment")
    assessments = []
    r = listed.start
    while r <= ws.max_row and not _ends_assessments(_text(ws.cell(r, 1).value)):
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
        "facts": None if read is project else read["facts"],
        "adoption": read.get("adoption"),
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
    # the v2.0 layout – the project's facts on its Project sheet, beside an Expenses sheet
    shared = PROJECT_FACTS_HEADING in _first_rows(_sheet(wb, PROJECT))
    inputs = _project_inputs(wb) if shared else None
    scenarios = [_scenario(ws, inputs) for ws in wb.worksheets if _is_plan(ws, shared)]
    own = [s["facts"] for s in scenarios if s["facts"] is not None]
    _with_ids(([inputs["facts"]] if inputs else []) + own)
    if not scenarios:
        raise WorkbookFormatError("the workbook has no scenario sheets")
    try:
        if inputs is not None:
            raw = {**text, "schema_version": 4, "facts": inputs["facts"], "scenarios": scenarios}
            project, _ = read_project(raw)
        else:
            # exported before v2.0 – each sheet carries the facts its scenario runs on, read as a
            # schema 3 project whose upgrade gives them to the project (spec 8.2)
            raw = {**text, "schema_version": 3, "scenarios": scenarios}
            project, _ = read_project(raw, report=False)
    except ProjectFormatError as e:
        raise WorkbookFormatError(str(e)) from None
    if inputs is not None:
        # a workbook holds no saved expense sets, so the expenses come back from none (spec 7.6)
        plain = tuple(
            s
            if s.adoption is None
            else replace(s, adoption=replace(s.adoption, expenses_from=None))
            for s in project.scenarios
        )
        project = replace(project, scenarios=plain, expense_sets=(), expenses_from=None)
    # before v2.0, each scenario's own expenses are kept as the upgrade's sets (spec 8.2)
    runnable = project.runnable_scenarios()
    problems = [f"{s.name} – {p}" for s in runnable for p in validate_run(s)]
    if problems:
        raise WorkbookFormatError("; ".join(problems))
    return project
