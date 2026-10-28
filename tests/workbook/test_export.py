"""Excel export and re-import (spec sections 7.6 and 9)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import zipfile
from dataclasses import fields, replace
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import extract_expected
import openpyxl
import pytest
import recalc
from openpyxl.comments import Comment
from openpyxl.formula.translate import Translator

from hoa_engine import (
    Adoption,
    Assessment,
    DuesMode,
    DuesPath,
    ExpenseLine,
    Facts,
    Frequency,
    Increase,
    Project,
    Rounding,
    Scenario,
    project_from_dict,
    project_to_dict,
    run,
)
from hoa_workbook import read as reader
from hoa_workbook.charts import shared_grid
from hoa_workbook.export import build_workbook, export_workbook
from hoa_workbook.layout import (
    ASSESS_FIRST_ROW,
    EXPENSE_COL,
    EXPENSE_YEAR_COL,
    EXPENSES_HEADING,
    FACTS_HEADING,
    PLAN_FIRST_COL,
    PLAN_OPERATING_LABEL,
    PLAN_RESERVE_LABEL,
    PROJECT_ROW,
    ROW,
    SOURCE_COL,
    VALUE_COL,
    quote,
    sheet_names,
)
from hoa_workbook.read import WorkbookFormatError, read_workbook
from tests.compare import mismatches

ROOT = Path(__file__).resolve().parents[2]
D = Decimal


def _load(path: Path) -> Project:
    return project_from_dict(json.loads(path.read_text(encoding="utf-8")))


DEMO = _load(ROOT / "demo" / "fixtures" / "project.json")
FACTS = DEMO.scenarios[0].facts  # the demo's shared starting point


def _short_project() -> Project:
    """Five years, no governance limits, no expenses, typed dues with cents, odd names."""
    f = replace(
        FACTS,
        end_year=FACTS.start_year + 4,
        expense_lines=(),
        max_dues_increase=None,
        max_assessment_share=None,
        ffb={y: v for y, v in FACTS.ffb.items() if y <= FACTS.start_year + 5},
    )
    years = range(f.start_year, f.end_year + 1)
    typed = Scenario(
        "Typed: dues / cents?",
        f,
        DuesPath(DuesMode.EXPLICIT, explicit={y: D("601.25") + i for i, y in enumerate(years)}),
        assessments=(Assessment(f.start_year + 1, D(1000), "=not a formula"),),
        description="+1 is text, not a formula",
    )
    grown = Scenario(
        "It's grown",
        f,
        DuesPath(DuesMode.RATE, first_value=D("700.40"), increases=(Increase(D("0.05")),)),
        rounding=Rounding.NONE,
    )
    return Project("=Short demo", (typed, grown), notes="@note stays text")


def _varied_project() -> Project:
    """The demo with scenarios whose facts differ every way a scenario's can – one on a
    horizon of its own, so Compare has to line up different years – and adopted plans."""
    f = FACTS
    insurance = next(line for line in f.expense_lines if line.id == "insurance")
    lines = tuple(
        replace(insurance, inflation=D("0.08"), amount=D(44000)) if line.id == "insurance" else line
        for line in f.expense_lines
        if line.id != "study-2029"
    )
    lines += (
        ExpenseLine(
            2030, D(9000), "Pool resurfacing", frequency=Frequency.EVERY, interval=6, id="pool"
        ),
        ExpenseLine(
            2030, D(900), "Security patrol", frequency=Frequency.MONTHLY, end_year=2036, id="patrol"
        ),
    )
    grown = DuesPath(DuesMode.RATE, first_value=D(690), increases=(Increase(D("0.04")),))
    own = Scenario(
        "Own assumptions",
        replace(
            f,
            interest_rate=D("0.03"),
            cushion=D(90000),
            max_dues_increase=None,
            expense_lines=lines,
            ffb={**f.ffb, 2030: D(700000)},
            sources={**f.sources, "cushion": "Board policy, fictional", "ffb": "Fictional update"},
        ),
        grown,
    )
    later = Scenario(
        "Later and longer",
        replace(
            f,
            start_year=2028,
            end_year=2045,
            starting_balance=D(210000),
            ffb={**f.ffb, 2044: D(1190000), 2045: D(1240000), 2046: D(1290000)},
        ),
        grown,
        assessments=(Assessment(2045, D(800), "Late"),),
    )
    short = Scenario(
        "Short run",
        replace(
            f,
            end_year=f.start_year + 5,
            units=26,
            current_dues=D("580.50"),
            operating_inflation=D("0.035"),
            expense_inflation=D("0.04"),
            expense_base_year=2027,
            target=D("0.65"),
            max_assessment_share=D("0.1"),
        ),
        grown,
    )
    adopted = replace(
        own,
        name="Adopted plan",
        facts=replace(own.facts, starting_balance=D(160000), interest_rate=D("0.012")),
        adoption=Adoption(date(2026, 11, 3), "Fictional board vote", 2),
    )
    first = replace(later, name="Earlier plan", adoption=Adoption(date(2025, 6, 1), "", 1))
    # worked out from useful lives, with no typed figures at all – a line coming into service
    # within the horizon, a nominal one already ageing, and one retired after its last year
    worked = Scenario(
        "Worked out from lives",
        replace(
            f,
            ffb={},
            ffb_from_lines=True,
            expense_lines=(
                ExpenseLine(2036, D(30000), "Lift", useful_life=5, id="lift"),
                ExpenseLine(2033, D(8000), "Doors", nominal=True, useful_life=12, id="doors"),
                ExpenseLine(
                    2028,
                    D(2500),
                    "Sealing",
                    frequency=Frequency.EVERY,
                    interval=4,
                    end_year=2036,
                    id="sealing",
                ),
                ExpenseLine(None, D(50000), "Running costs", frequency=Frequency.YEARLY, id="run"),
            ),
        ),
        grown,
    )
    return replace(DEMO, scenarios=(*DEMO.scenarios[:2], own, later, short, adopted, first, worked))


def _projects() -> list[Any]:
    out = [
        pytest.param(DEMO, id="demo"),
        pytest.param(_short_project(), id="short"),
        pytest.param(_varied_project(), id="varied"),
    ]
    data_dir = os.environ.get("HOA_PRIVATE_DIR")
    if data_dir:
        out.append(pytest.param(_load(Path(data_dir) / "fixtures" / "project.json"), id="private"))
    return out


def _libreoffice() -> bool:
    try:
        recalc.find_soffice()
    except SystemExit:
        return False
    return True


# ---------------------------------------------------------------- section 9


@pytest.mark.skipif(not _libreoffice(), reason="LibreOffice not installed")
@pytest.mark.parametrize("project", _projects())
def test_exported_workbook_recalculates_to_the_engines_figures(
    project: Project, tmp_path: Path
) -> None:
    workbook = tmp_path / "export.xlsx"
    export_workbook(project, workbook)
    recalc.recalc(workbook)
    assert recalc.formula_errors(workbook) == []
    expected = extract_expected.extract(workbook, project_to_dict(project))
    problems = []
    for s in project.scenarios:
        problems += [f"{s.name} {p}" for p in mismatches(run(s), expected["scenarios"][s.name])]
    assert not problems, "\n".join(problems)
    # a worked-out Fully Funded Balance, every year the screen shows – the start year too
    wb = openpyxl.load_workbook(workbook, data_only=True)
    for s in (x for x in project.scenarios if x.facts.ffb_from_lines):
        ws = next(w for w in wb.worksheets if w["A1"].value == s.name)
        row, header = _rows(ws)["Fully Funded Balance at start of year"], {}
        for c in range(VALUE_COL, ws.max_column + 1):
            if isinstance(ws.cell(row - 1, c).value, int):
                header[ws.cell(row - 1, c).value] = c
        worked = run(s).ffb
        assert sorted(worked) == sorted(header), s.name
        for y, v in worked.items():
            assert abs(Decimal(str(ws.cell(row, header[y]).value)) - v) < D("0.005"), (s.name, y)


@pytest.mark.parametrize("project", _projects())
def test_export_then_import_gives_the_same_results(project: Project) -> None:
    again = read_workbook(export_workbook(project))
    assert [s.name for s in again.scenarios] == [s.name for s in project.scenarios]
    for before, after in zip(project.scenarios, again.scenarios, strict=True):
        a, b = run(before), run(after)
        # Excel stores numbers as doubles, so allow a millionth of a cent of drift
        pairs = [(a.summary, b.summary), *zip(a.years, b.years, strict=True)]
        for x, y in pairs:
            for field in fields(x):
                vx, vy = getattr(x, field.name), getattr(y, field.name)
                if isinstance(vx, Decimal):
                    assert abs(vx - vy) < D("1e-8"), (before.name, field.name)
                elif field.name not in ("expense_lines", "operating_lines"):
                    assert vx == vy, (before.name, field.name)


def test_demo_round_trip_is_identical() -> None:
    assert read_workbook(export_workbook(DEMO)) == DEMO


def test_scenarios_with_their_own_facts_round_trip_identically() -> None:
    project = _varied_project()
    assert read_workbook(export_workbook(project)) == project


def test_fully_funded_balance_years_beyond_the_horizon_are_kept() -> None:
    s = DEMO.scenarios[0]
    wider = replace(s, facts=replace(s.facts, ffb={**s.facts.ffb, 2050: D(5)}))
    project = replace(DEMO, scenarios=(wider,))
    assert read_workbook(export_workbook(project)) == project


def _rows(ws: Any) -> dict[str, int]:
    """Each label's last row in column A."""
    return {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}


def _plan_cell(sheet: str, label: str, col: int = VALUE_COL) -> Any:
    """A cell in a Plan sheet's own inputs, by its row label."""

    def at(wb: openpyxl.Workbook) -> Any:
        ws = wb[sheet]
        return ws.cell(_rows(ws)[label], col)

    return at


def _set(at: Any, value: Any) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        at(wb).value = value

    return edit


def _first_expense_row(ws: Any) -> int:
    return _rows(ws)[EXPENSES_HEADING] + 2


def _facts_after(edit: Any, sheet: str = "Dues only", project: Project = DEMO) -> Facts:
    again = read_workbook(_broken(edit, project))
    return next(s for s in again.scenarios if s.name == sheet).facts


def test_a_figure_typed_in_excel_is_read_as_the_scenarios_own() -> None:
    edit = _set(_plan_cell("Dues only", "Interest earned on reserves per year"), 0.04)
    assert _facts_after(edit).interest_rate == D("0.04")
    blank = _set(_plan_cell("Dues only", "Largest dues increase without an owner vote"), None)
    assert _facts_after(blank).max_dues_increase is None
    note = _set(_plan_cell("Dues only", "Minimum working cushion", SOURCE_COL), "Our policy")
    assert _facts_after(note).sources["cushion"] == "Our policy"
    # the other scenarios keep theirs – nothing is shared
    other = read_workbook(_broken(edit)).scenarios[1]
    assert other.facts.interest_rate == FACTS.interest_rate


def test_a_formula_in_a_fact_is_refused() -> None:
    edit = _set(_plan_cell("Dues only", "Minimum working cushion"), "=C80*2")
    with pytest.raises(WorkbookFormatError, match="'Minimum working cushion' holds a formula"):
        read_workbook(_broken(edit))


def test_a_spare_expense_row_filled_in_excel_adds_a_line() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        r = _first_expense_row(ws) + len(FACTS.expense_lines)  # the first spare row
        for key, value in (
            ("description", "Sign"),
            ("frequency", "once"),
            ("amount", 500),
            ("year", 2030),
        ):
            ws.cell(r, EXPENSE_COL[key], value)

    lines = _facts_after(edit).expense_lines
    assert lines[-1] == ExpenseLine(2030, D(500), "Sign", id="line-1")
    assert lines[:-1] == FACTS.expense_lines


def test_an_expense_row_cleared_in_excel_is_left_out() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        r = _first_expense_row(ws)
        for key in ("description", "frequency", "amount", "year", "end_year", "inflation", "id"):
            ws.cell(r, EXPENSE_COL[key]).value = None

    assert _facts_after(edit).expense_lines == FACTS.expense_lines[1:]


def test_an_expense_row_below_the_list_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        r = _rows(ws)[PLAN_OPERATING_LABEL] - 1  # the gap between the list and its total
        ws.cell(r, EXPENSE_COL["frequency"], "once")
        ws.cell(r, EXPENSE_COL["amount"], 1)

    with pytest.raises(WorkbookFormatError, match="outside the rows the totals add up"):
        read_workbook(_broken(edit))


def test_a_spare_row_without_its_year_formulas_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        r = _first_expense_row(ws) + len(FACTS.expense_lines)
        ws.cell(r, EXPENSE_COL["frequency"], "once")
        ws.cell(r, EXPENSE_COL["amount"], 1)
        ws.cell(r, EXPENSE_YEAR_COL).value = None

    with pytest.raises(WorkbookFormatError, match="has no year formulas"):
        read_workbook(_broken(edit))


@pytest.mark.parametrize(
    "label",
    [
        FACTS_HEADING,
        "Interest earned on reserves per year",
        EXPENSES_HEADING,
        PLAN_OPERATING_LABEL,
        PLAN_RESERVE_LABEL,
    ],
)
def test_a_scenario_sheet_without_its_own_inputs_is_refused(label: str) -> None:
    edit = _relabel("Dues only", label, "Something else")
    with pytest.raises(WorkbookFormatError, match=f"Dues only is missing the row '{label[:20]}"):
        read_workbook(_broken(edit))


def test_a_scenario_on_an_impossible_horizon_is_not_exported() -> None:
    s = DEMO.scenarios[0]
    wide = replace(s, facts=replace(s.facts, end_year=2100))
    with pytest.raises(ValueError, match="Dues only – the horizon must be 5–30 full years"):
        export_workbook(replace(DEMO, scenarios=(wide,)))


def test_a_scenario_with_problems_is_not_exported() -> None:
    s = DEMO.scenarios[2]  # typed dues
    gap = replace(s, dues=replace(s.dues, explicit={}))
    with pytest.raises(ValueError, match="Hold then catch up – dues are missing for 2027"):
        export_workbook(replace(DEMO, scenarios=(gap,)))


def test_measures_a_short_scenario_cannot_have_are_dashes() -> None:
    wb = build_workbook(_varied_project())
    ws = wb["Compare"]
    labels = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
    columns = {ws.cell(4, c).value: c for c in range(2, ws.max_column + 1)}
    assert ws.cell(labels["Dues per unit per month – year 9"], columns["Short run"]).value == "–"
    assert ws.cell(labels["Dues per unit per month – year 9"], columns["Dues only"]).value


def test_text_worded_like_a_label_never_stands_in_for_it() -> None:
    """An expense or a note may read "Operating expenses" – the reader looks for each label
    only in its own part of the sheet."""
    project = _varied_project()
    own, *rest = project.scenarios[2:]
    renamed = tuple(
        replace(line, description="Interest earned")
        if line.id == "boiler"
        else replace(line, description="Operating expenses")
        if line.id == "pool"
        else replace(line, description=PLAN_OPERATING_LABEL)
        if line.id == "gutters"
        else line
        for line in own.facts.expense_lines
    )
    worded = replace(
        own,
        name="Interest earned",  # a sheet's name and description sit above its rows
        description="Operating expenses",
        assessments=(Assessment(2030, D(10), "Start year"),),
        facts=replace(own.facts, expense_lines=renamed),
    )
    project = replace(project, scenarios=(*project.scenarios[:2], worded, *rest))
    assert read_workbook(export_workbook(project)) == project
    named = replace(project, scenarios=(replace(worded, name="How dues are set"),))
    assert read_workbook(export_workbook(named)) == named


def test_a_huge_horizon_of_a_scenario_is_refused_before_it_is_walked() -> None:
    edit = _set(_plan_cell("Dues only", "End year"), 10**12)
    with pytest.raises(WorkbookFormatError, match="Dues only – the horizon must be 5–30"):
        read_workbook(_broken(edit))


def test_an_adopted_plan_is_protected_and_read_back_whole() -> None:
    project = _varied_project()
    wb = build_workbook(project)
    ws = wb["Adopted plan"]
    assert ws.protection.sheet  # a reminder that it is read-only
    assert str(ws["A3"].value).startswith("Adopted plan – adopted November 3, 2026")
    assert _plan_cell("Adopted plan", "Interest earned on reserves per year")(wb).value == 0.012
    assert not wb["Own assumptions"].protection.sheet
    again = read_workbook(export_workbook(project))
    plans = [s for s in again.scenarios if s.adoption is not None]
    assert [(s.name, s.adoption) for s in plans] == [
        ("Adopted plan", Adoption(date(2026, 11, 3), "Fictional board vote", 2)),
        ("Earlier plan", Adoption(date(2025, 6, 1), "", 1)),
    ]


def test_an_adoption_date_excel_turned_into_a_date_is_read() -> None:
    edit = _set(_plan_cell("Adopted plan", "Adopted on"), datetime(2026, 11, 4))
    project = read_workbook(_broken(edit, _varied_project()))
    plan = next(s for s in project.scenarios if s.name == "Adopted plan")
    assert plan.adoption is not None and plan.adoption.adopted_on == date(2026, 11, 4)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_set(_plan_cell("Adopted plan", "Adopted on"), 5), "adoption date should be written"),
        (
            lambda wb: _relabel("Adopted plan", "Adoption note", "Note")(wb),
            "missing the row 'Adoption note'",
        ),
        (
            _set(_plan_cell("Adopted plan", "Minimum working cushion"), "=C80"),
            "'Minimum working cushion' holds a formula",
        ),
    ],
)
def test_a_damaged_adopted_plan_sheet_is_refused(edit: Any, message: str) -> None:
    with pytest.raises(WorkbookFormatError, match=re.escape(message)):
        read_workbook(_broken(edit, _varied_project()))


def test_a_scenarios_start_year_cannot_be_moved_in_excel() -> None:
    edit = _set(_plan_cell("Later and longer", "Start year"), 2029)
    with pytest.raises(WorkbookFormatError, match="horizon can only be changed in the app"):
        read_workbook(_broken(edit, _varied_project()))


def test_the_scenarios_fully_funded_balance_is_read_year_by_year() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        ws.cell(_rows(ws)["Fully Funded Balance at start of year"], VALUE_COL + 1, 650000)

    assert _facts_after(edit).ffb == {**FACTS.ffb, 2028: D(650000)}


def _excel_installed() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:  # Excel registers its COM class here whatever the install path or bitness
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"))
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _excel_installed(), reason="Microsoft Excel not installed")
@pytest.mark.parametrize(
    "project", [DEMO, _short_project(), _varied_project()], ids=["demo", "short", "varied"]
)
def test_excel_opens_the_export_without_repair(project: Project, tmp_path: Path) -> None:
    workbook = tmp_path / "export.xlsx"
    export_workbook(project, workbook, dollar_axis=(D(-45222), D(806568)))
    out = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "tools" / "excel_check.ps1"),
            "-Path",
            str(workbook),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    ).stdout
    assert "opened" in out and "no repair log" in out, out


# ---------------------------------------------------------------- layout and safety


def test_user_text_is_never_written_as_a_formula() -> None:
    wb = build_workbook(_short_project())
    plan = wb["Typed  dues   cents"]
    texts = {
        "project name": wb["Project"].cell(PROJECT_ROW["name"], 2),
        "notes": wb["Project"].cell(PROJECT_ROW["notes"], 2),
        "scenario name": plan["A1"],
        "description": plan["A2"],
        "assessment note": plan.cell(ASSESS_FIRST_ROW, 1),
    }
    for what, cell in texts.items():
        assert cell.data_type == "s", what
        # text that looks like a formula also stays text when edited in Excel
        assert cell.quotePrefix == (str(cell.value)[:1] in "=+-@"), what
    assert texts["project name"].value == "=Short demo"
    assert texts["assessment note"].value == "=not a formula"


def test_sheet_names_are_safe_unique_and_short() -> None:
    names = sheet_names(["Compare", "a/b", "a/b", "'quoted'", "", "x" * 40, "X" * 40])
    assert names == [
        "Compare (2)",
        "a b",
        "a b (2)",
        "quoted",
        "Scenario",
        "x" * 31,
        "X" * 27 + " (2)",
    ]
    assert quote("It's grown") == "'It''s grown'"
    # the old shared sheets' names are free for scenarios now
    assert sheet_names(["Inputs", "Expenses", "Project"]) == ["Inputs", "Expenses", "Project (2)"]


def test_choosing_and_ordering_scenarios() -> None:
    wb = build_workbook(DEMO, scenario_names=["Steady increase", "Dues only"])
    assert wb.sheetnames == [
        "Method",
        "Project",
        "Compare",
        "Charts",
        "Steady increase",
        "Dues only",
    ]


def test_short_horizon_leaves_out_year_nine_measures() -> None:
    labels = [c.value for c in build_workbook(_short_project())["Compare"]["A"] if c.value]
    assert not any(str(label).endswith(str(FACTS.start_year + 8)) for label in labels)


def test_every_chart_axis_states_whether_it_is_shown() -> None:
    package = zipfile.ZipFile(BytesIO(export_workbook(DEMO)))
    charts = [n for n in package.namelist() if n.startswith("xl/charts/chart")]
    n = len(DEMO.scenarios)
    assert len(charts) == 2 * n + n  # two per scenario sheet, one per scenario on Charts
    for name in charts:
        xml = package.read(name).decode()
        assert xml.count("<c:delete") == xml.count("<c:catAx>") + xml.count("<c:valAx>")


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (D(0), D(1040000), (D(0), D(1250000), D(250000), D(0))),
        (D(-45222), D(806568), (D(-200000), D(1000000), D(200000), D("-0.2"))),
        (D(-1), D(250000), (D(-50000), D(250000), D(50000), D("-0.2"))),
        (D(0), D(0), (D(0), D(5), D(1), D(0))),  # nothing to show – a minimal $0–$5 scale
    ],
)
def test_shared_dollar_grid_lines_up_with_percent(
    low: Decimal, high: Decimal, expected: tuple[Decimal, ...]
) -> None:
    g = shared_grid(low, high)
    assert (g.dollar_min, g.dollar_max, g.dollar_step, g.percent_min) == expected


# ---------------------------------------------------------------- bad files


def _retarget_operating_total(wb: openpyxl.Workbook) -> None:
    ws = wb["Dues only"]
    first = _first_expense_row(ws)
    cell = ws.cell(_rows(ws)[PLAN_OPERATING_LABEL], EXPENSE_YEAR_COL)
    cell.value = re.sub(rf"\${first}:", f"${first + 1}:", cell.value)


def _broken(edit: Any, project: Project = DEMO) -> bytes:
    wb = openpyxl.load_workbook(BytesIO(export_workbook(project)))
    edit(wb)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _fact(label: str, value: Any) -> Any:
    return lambda: _broken(_set(_plan_cell("Dues only", label), value))


def _expense(key: str, value: Any) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        ws.cell(_first_expense_row(ws), EXPENSE_COL[key], value)

    return lambda: _broken(edit)


def _old_layout(wb: openpyxl.Workbook) -> None:
    wb.remove(wb["Project"])
    wb.create_sheet("Inputs")
    wb.create_sheet("Expenses")


def _delete_fact_row(wb: openpyxl.Workbook) -> None:
    ws = wb["Dues only"]
    ws.delete_rows(_rows(ws)["Number of units"])


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not a zip", "not an Excel workbook"),
        (lambda: _broken(lambda wb: wb.remove(wb["Project"])), "no Project sheet"),
        (lambda: _broken(_old_layout), "exported by an earlier version of HOAForecaster"),
        (
            lambda: _broken(_relabel("Project", "Association", "Name")),
            "Project is missing the row 'Association'",
        ),
        (_fact("Minimum working cushion", "lots"), "should be a number"),
        (_fact("Start year", "soon"), "should be a whole number"),
        (lambda: _broken(_delete_fact_row), "missing the row 'Number of units'"),
        (
            lambda: _broken(lambda wb: wb["Dues only"].cell(ROW["mode"], 3, "guess")),
            "unrecognised dues",
        ),
        (_fact("Number of units", 2.5), "should be a whole number"),
        (_expense("amount", 1e20), "not a usable number"),
        (
            _expense("frequency", "often"),
            "'How often' should be one of monthly, yearly, every few years, once",
        ),
        (_expense("frequency", "yearly "), "'How often' should be one of"),
        (_expense("interval", 2.5), "interval should be a number of years"),
        (
            lambda: _broken(_retarget_operating_total),
            "operating and reserve totals on Dues only add up different rows",
        ),
        (
            lambda: _broken(lambda wb: [wb.remove(wb[s.name]) for s in DEMO.scenarios[:1]]),
            None,
        ),
    ],
)
def test_unreadable_workbooks_are_refused_in_plain_language(data: Any, message: str | None) -> None:
    if message is None:  # one sheet fewer is simply one scenario fewer
        assert len(read_workbook(data()).scenarios) == len(DEMO.scenarios) - 1
        return
    with pytest.raises(WorkbookFormatError, match=message):
        read_workbook(data() if callable(data) else data)


def test_a_workbook_without_scenario_sheets_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        for name in [
            n for n in wb.sheetnames if n not in ("Method", "Project", "Compare", "Charts")
        ]:
            wb.remove(wb[name])

    with pytest.raises(WorkbookFormatError, match="has no scenario sheets"):
        read_workbook(_broken(edit))


def test_oversized_files_are_refused_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_FILE_BYTES", 100)
    with pytest.raises(WorkbookFormatError, match="larger than 20 MB"):
        read_workbook(export_workbook(DEMO))


def test_unreasonable_unpacked_size_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(WorkbookFormatError, match="unreasonable size"):
        read_workbook(export_workbook(DEMO))


def _relabel(sheet: str, old: str, new: str) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        for (cell,) in wb[sheet].iter_rows(max_col=1):
            if cell.value == old:
                cell.value = new

    return edit


def _excel_insert(ws: Any, at: int) -> None:
    """Insert a row the way Excel does – shifting rows and rewriting every reference to the
    moved rows, on this sheet and from the others (openpyxl alone never rewrites formulas)."""
    ws.insert_rows(at)
    reference = re.compile(
        r"(?<![A-Za-z0-9_$.'])((?:'[^']+'|[A-Za-z]+)!)?"  # an optional sheet
        r"(\$?[A-Z]{1,3}\$?)(\d+)(?::(\$?[A-Z]{1,3}\$?)(\d+))?"  # a cell, or a range
    )

    def moved(n: str) -> int:
        return int(n) + (1 if int(n) >= at else 0)

    for sheet in ws.parent.worksheets:

        def rewrite(m: re.Match[str], on: Any = sheet) -> str:
            named = m[1][:-1].strip("'") if m[1] else None
            if (named or on.title) != ws.title:
                return m[0]  # a reference to another sheet's rows
            out = f"{m[1] or ''}{m[2]}{moved(m[3])}"
            return out + (f":{m[4]}{moved(m[5])}" if m[4] else "")

        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.value = reference.sub(rewrite, cell.value)


def _insert_expense(offset: int, copy_formulas: bool, line_id: str | None = None) -> Any:
    """An expense inserted into Dues only's list `offset` rows below its first line."""

    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        at = _first_expense_row(ws) + offset
        _excel_insert(ws, at)
        for key, value in (
            ("description", "New gate"),
            ("frequency", "once"),
            ("amount", 9000),
            ("year", 2030),
            ("nominal", "no"),
            ("id", line_id),
        ):
            ws.cell(at, EXPENSE_COL[key], value)
        if copy_formulas:  # what copying a whole row in Excel does
            for c in range(EXPENSE_YEAR_COL, EXPENSE_YEAR_COL + len(FACTS.years)):
                source = ws.cell(at + 1, c)
                ws.cell(at, c).value = Translator(
                    source.value, source.coordinate
                ).translate_formula(ws.cell(at, c).coordinate)

    return edit


def test_an_expense_row_copied_between_rows_in_excel_is_read() -> None:
    lines = _facts_after(_insert_expense(1, copy_formulas=True)).expense_lines
    assert lines[1] == ExpenseLine(2030, D(9000), "New gate", id="line-1")
    assert len({line.id for line in lines}) == len(lines) == len(FACTS.expense_lines) + 1


def test_a_copied_row_that_keeps_its_line_id_gets_a_new_one() -> None:
    lines = _facts_after(_insert_expense(1, True, "insurance")).expense_lines
    # which row is the original cannot be told – the first keeps the id, the other gets a new one
    assert [line.id for line in lines[:4]] == ["management", "insurance", "utilities", "line-1"]


def test_an_expense_typed_into_a_bare_row_is_refused() -> None:
    # the sheet's own totals would leave it out, so reading it would disagree with them
    with pytest.raises(WorkbookFormatError, match="has no year formulas"):
        read_workbook(_broken(_insert_expense(1, copy_formulas=False)))


def test_an_expense_above_the_summed_rows_is_refused() -> None:
    # Excel does not stretch SUMIF(E5:E…) for a row inserted at its first row, so the totals skip it
    with pytest.raises(WorkbookFormatError, match="outside the rows the totals add up"):
        read_workbook(_broken(_insert_expense(0, copy_formulas=True)))


def test_a_row_inserted_on_a_scenario_sheet_keeps_the_scenario() -> None:
    project = read_workbook(_broken(lambda wb: _excel_insert(wb["Two-part assessment"], 39)))
    assert project == DEMO


def _row_of(ws: Any, start: str) -> int:
    return next(c.row for (c,) in ws.iter_rows(max_col=1) if str(c.value).startswith(start))


def test_an_assessment_below_the_list_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        # the blank row between the list's spare rows and the yearly increases
        below = _row_of(ws, "Yearly dues increases") - 1
        ws.cell(below, 3, 2030)
        ws.cell(below, 4, 500)

    with pytest.raises(WorkbookFormatError, match="below the assessment list"):
        read_workbook(_broken(edit))


# ---------------------------------------------------------------- yearly dues increases (5.1)

STEPPED = "Stepped increases"  # the demo's scenario with several periods


def test_the_yearly_increases_are_a_list_with_a_rate_formula_for_each_year() -> None:
    wb = openpyxl.load_workbook(BytesIO(export_workbook(DEMO)))
    ws = next(w for w in wb.worksheets if w["A1"].value == STEPPED)
    s = next(x for x in DEMO.scenarios if x.name == STEPPED)
    top = _row_of(ws, "Yearly dues increases")
    for k, inc in enumerate(s.dues.increases):
        r = top + 2 + k
        assert ws.cell(r, 3).value == inc.first_year and ws.cell(r, 4).value == inc.last_year
        assert Decimal(str(ws.cell(r, 5).value)) == inc.rate
    rate_row = _rows(ws)["Yearly dues increase (grown dues only)"]
    assert str(ws.cell(rate_row, PLAN_FIRST_COL + 1).value).startswith("=SUMPRODUCT(")


def test_several_yearly_increases_come_back_as_they_were() -> None:
    again = read_workbook(export_workbook(DEMO))
    before = next(x for x in DEMO.scenarios if x.name == STEPPED)
    after = next(x for x in again.scenarios if x.name == STEPPED)
    assert len(before.dues.increases) > 1
    assert after.dues == before.dues


def _stepped(edit: Any) -> Any:
    def apply(wb: openpyxl.Workbook) -> None:
        ws = next(w for w in wb.worksheets if w["A1"].value == STEPPED)
        edit(ws, _row_of(ws, "Yearly dues increases") + 2)

    return apply


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda ws, r: setattr(ws.cell(r, 5), "value", "lots"), "increase should be a number"),
        (lambda ws, r: setattr(ws.cell(r, 3), "value", 2030.5), "From should be a year"),
        (
            lambda ws, r: setattr(
                ws.cell(_rows(ws)["Yearly dues increase (grown dues only)"], PLAN_FIRST_COL + 2),
                "value",
                0.1,
            ),
            "was typed over",
        ),
        (
            lambda ws, r: setattr(
                ws.cell(_rows(ws)["Yearly dues increase (grown dues only)"], PLAN_FIRST_COL),
                "value",
                "=0.1",
            ),
            "has been changed",
        ),
        (lambda ws, r: ws.cell(_row_of(ws, "Charts") - 1, 5, 0.2), "outside the increases list"),
        (lambda ws, r: setattr(ws.cell(r + 1, 3), "value", 2029), "overlap"),
    ],
    ids=["rate", "year", "typed over", "formula changed", "below the list", "overlap"],
)
def test_damaged_yearly_increases_are_refused(edit: Any, message: str) -> None:
    with pytest.raises(WorkbookFormatError, match=message):
        read_workbook(_broken(_stepped(edit)))


def test_a_sheet_from_before_periods_reads_its_one_rate() -> None:
    def older(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        r = _rows(ws)["Yearly dues increase (grown dues only)"]
        ws.cell(r, 1).value = "Annual dues increase (grown dues only)"
        ws.cell(r, PLAN_FIRST_COL).value = 0.045
        for c in range(PLAN_FIRST_COL + 1, ws.max_column + 1):
            ws.cell(r, c).value = None  # the old sheet had one cell, no formulas

    again = read_workbook(_broken(older))
    dues = next(s for s in again.scenarios if s.name == "Dues only").dues
    assert dues.increases == (Increase(Decimal("0.045")),)


@pytest.mark.parametrize(
    ("sheet", "key", "advice"),
    [
        ("Dues only", "dues", "pin that year's dues"),
        ("Dues only", "end", "change the inputs it is calculated from"),
        ("Hold then catch up", "sa", "change the inputs"),
    ],
)
def test_a_value_typed_over_a_formula_is_refused(sheet: str, key: str, advice: str) -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        wb[sheet].cell(ROW[key], 5, 123)

    with pytest.raises(WorkbookFormatError, match=f"typed over.*{advice}"):
        read_workbook(_broken(edit))


def test_typed_dues_may_be_edited() -> None:
    project = read_workbook(_broken(lambda wb: wb["Hold then catch up"].cell(ROW["dues"], 5, 700)))
    hold = next(s for s in project.scenarios if s.name == "Hold then catch up")
    assert hold.dues.explicit[FACTS.start_year + 2] == 700


def test_changing_the_horizon_in_excel_is_refused() -> None:
    edit = _set(_plan_cell("Dues only", "End year"), FACTS.end_year - 1)
    with pytest.raises(WorkbookFormatError, match="horizon can only be changed in the app"):
        read_workbook(_broken(edit))


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (
            lambda wb: wb["Dues only"].cell(ROW["sa"], 3, "=0"),
            "special assessment formula has been changed",
        ),
        (_relabel("Dues only", "Interest earned", "Interest"), "missing the row 'Interest earned'"),
    ],
)
def test_a_reshaped_scenario_sheet_is_refused(edit: Any, message: str) -> None:
    with pytest.raises(WorkbookFormatError, match=message):
        read_workbook(_broken(edit))


def test_assessments_round_trip_one_row_each() -> None:
    f = FACTS
    two = Scenario(
        "Two in one year",
        f,
        DuesPath(DuesMode.RATE, first_value=D(600), increases=(Increase(D("0.03")),)),
        assessments=(
            Assessment(f.start_year + 1, D(1500), "First half"),
            Assessment(f.start_year + 1, D(1500), "Second half"),
            Assessment(f.start_year + 2, D(0), "Placeholder"),
        ),
    )
    project = Project("Installments", (two,))
    assert read_workbook(export_workbook(project)) == project


def test_scenario_names_keep_their_spaces() -> None:
    padded = replace(DEMO.scenarios[0], name="  Padded  ", description=" lead")
    project = Project("Spaces", (padded,))
    assert read_workbook(export_workbook(project)).scenarios[0] == padded


def test_a_scenario_named_notes_does_not_become_the_project_notes() -> None:
    project = Project("N", (replace(DEMO.scenarios[0], name="Project notes"),))
    assert read_workbook(export_workbook(project)).notes == ""


# ---------------------------------------------------------------- review follow-ups


def test_sheet_names_never_end_in_an_apostrophe_and_fit_excels_utf16_limit() -> None:
    cut, emoji = sheet_names(["a" * 30 + "'b", "😀" * 20])
    assert cut == "a" * 30
    assert len(emoji.encode("utf-16-le")) // 2 <= 31


def test_method_sheet_lists_the_scenarios_and_notes() -> None:
    lines = [c.value for c in build_workbook(DEMO)["Method"]["A"] if c.value]
    assert all(any(str(line).startswith(s.name) for line in lines) for s in DEMO.scenarios)
    assert DEMO.notes in lines


def test_a_facts_source_note_sits_beside_it() -> None:
    wb = build_workbook(DEMO)
    note = _plan_cell("Dues only", "Current dues per unit per month", SOURCE_COL)(wb)
    assert note.value == FACTS.sources["current_dues"]


@pytest.mark.parametrize(
    ("project", "names", "message"),
    [
        (DEMO, ["Nope"], "no scenario named 'Nope'"),
        (replace(DEMO, scenarios=(DEMO.scenarios[0], DEMO.scenarios[0])), None, "must be unique"),
        (
            replace(
                DEMO, scenarios=(replace(DEMO.scenarios[0], facts=replace(FACTS, end_year=10**9)),)
            ),
            None,
            "horizon",
        ),
        (replace(DEMO, scenarios=()), None, "no scenarios to export"),
    ],
)
def test_export_refuses_what_it_cannot_write(
    project: Project, names: list[str] | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_workbook(project, scenario_names=names)


def test_suspiciously_compressed_files_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_RATIO", 1)
    with pytest.raises(WorkbookFormatError, match="compressed suspiciously well"):
        read_workbook(export_workbook(DEMO))


def test_oversized_sheets_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_ROWS", 10)
    with pytest.raises(WorkbookFormatError, match="far larger than an HOAForecaster export"):
        read_workbook(export_workbook(DEMO))


def test_a_damaged_package_gets_a_plain_message() -> None:
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<not a workbook")
    with pytest.raises(WorkbookFormatError, match="may be damaged or not an Excel file"):
        read_workbook(out.getvalue())


def _assessment_in(year: int) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        wb["Dues only"].cell(ASSESS_FIRST_ROW, 3, year)
        wb["Dues only"].cell(ASSESS_FIRST_ROW, 4, 100)

    return edit


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (
            lambda wb: wb["Dues only"].cell(_first_expense_row(wb["Dues only"]), 3, -5),
            "the yearly expense 'Management, accounting and administration' cannot be negative",
        ),
        (lambda wb: wb["Dues only"].cell(ROW["pinned"], 3 + 20, 700), None),
        (_assessment_in(1999), "the 1999 assessment is outside"),
    ],
)
def test_imported_values_are_validated(edit: Any, message: str | None) -> None:
    data = _broken(edit)
    if message is None:  # a pin past the horizon's last column is outside the year header
        assert read_workbook(data).scenarios[0].dues.overrides == {}
        return
    with pytest.raises(WorkbookFormatError, match=message):
        read_workbook(data)


def test_stray_cells_are_tolerated() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        plan = wb["Dues only"]
        ffb = _rows(plan)["Fully Funded Balance at start of year"]
        plan.cell(ffb, plan.max_column + 2, 5)  # no year above it – ignored
        plan.cell(ffb, 1).comment = Comment("Reserve study, 2026", "x")
        plan.cell(4, plan.max_column + 2, None)
        plan.cell(5, plan.max_column + 2, "stray")

    assert _facts_after(edit).sources["ffb"] == "Reserve study, 2026"


def test_a_new_row_gets_an_id_no_other_line_has() -> None:
    s = DEMO.scenarios[0]
    first = replace(s.facts.expense_lines[0], id="line-1")
    taken = replace(s, facts=replace(s.facts, expense_lines=(first, *s.facts.expense_lines[1:])))
    project = replace(DEMO, scenarios=(taken,))
    lines = _facts_after(_insert_expense(1, copy_formulas=True), project=project).expense_lines
    assert [line.id for line in lines[:2]] == ["line-1", "line-2"]


# ---------------------------------------------------------------- the worked-out FFB (4.2)

WORKED = "Worked-out Fully Funded Balance"  # the demo's scenario


def test_a_worked_out_fully_funded_balance_is_formulas_with_the_typed_figures_kept() -> None:
    wb = openpyxl.load_workbook(BytesIO(export_workbook(DEMO)))
    ws = wb[WORKED]  # 31 characters – the name fits a sheet as it is
    rows = _rows(ws)
    ffb = rows["Fully Funded Balance at start of year"]
    assert ws.cell(ffb + 1, VALUE_COL).value == "this sheet's expenses' useful lives"
    assert str(ws.cell(ffb, VALUE_COL).value).startswith("=SUMPRODUCT(")
    assert ws.cell(ffb + 2, 1).value == "Reserve study's figures (kept, not used while worked out)"
    facts = next(s for s in DEMO.scenarios if s.name == WORKED).facts
    assert ws.cell(ffb + 2, VALUE_COL).value == int(facts.ffb[facts.start_year])
    typed = wb["Dues only"]
    assert typed.cell(
        _rows(typed)["Fully Funded Balance at start of year"] + 1, VALUE_COL
    ).value == ("the reserve study's figures")


def _worked_ffb(edit: Any) -> Any:
    def apply(wb: openpyxl.Workbook) -> None:
        ws = next(w for w in wb.worksheets if w["A1"].value == WORKED)
        edit(ws, _rows(ws)["Fully Funded Balance at start of year"])

    return apply


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda ws, r: setattr(ws.cell(r + 1, VALUE_COL), "value", "guesswork"), "unrecognised"),
        (lambda ws, r: setattr(ws.cell(r + 1, 1), "value", None), "unrecognised"),
        (lambda ws, r: setattr(ws.cell(r + 2, 1), "value", None), "Reserve study's figures"),
        (lambda ws, r: setattr(ws.cell(r, VALUE_COL), "value", 5), "worked out from the expenses"),
    ],
    ids=["bad mode", "no mode", "no kept row", "typed over"],
)
def test_a_damaged_worked_out_fully_funded_balance_is_refused(edit: Any, message: str) -> None:
    with pytest.raises(WorkbookFormatError, match=message):
        read_workbook(_broken(_worked_ffb(edit)))


def test_a_workbook_from_before_the_mode_row_reads_as_the_studys_figures() -> None:
    def older(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        r = _rows(ws)["Fully Funded Balance at start of year"] + 1
        ws.cell(r, 1).value = ws.cell(r, VALUE_COL).value = None  # v1.6 left this row blank

    again = read_workbook(_broken(older))
    facts = next(s for s in again.scenarios if s.name == "Dues only").facts
    assert not facts.ffb_from_lines
    assert facts.ffb == next(s for s in DEMO.scenarios if s.name == "Dues only").facts.ffb


def test_switching_the_mode_in_excel_is_read() -> None:
    def to_typed(ws: Any, r: int) -> None:
        ws.cell(r + 1, VALUE_COL).value = "the reserve study's figures"
        for c in range(VALUE_COL, ws.max_column + 1):
            ws.cell(r, c).value = ws.cell(r + 2, c).value  # the kept figures, typed back
        ws.cell(r + 2, 1).value = None

    again = read_workbook(_broken(_worked_ffb(to_typed)))
    facts = next(s for s in again.scenarios if s.name == WORKED).facts
    before = next(s for s in DEMO.scenarios if s.name == WORKED).facts
    assert not facts.ffb_from_lines and facts.ffb == before.ffb


def test_a_one_time_costs_useful_life_is_read_and_must_be_whole() -> None:
    def life(value: Any) -> Any:
        def edit(wb: openpyxl.Workbook) -> None:
            ws = wb["Dues only"]
            first = _first_expense_row(ws)
            row = next(
                r
                for r in range(first, ws.max_row)
                if ws.cell(r, EXPENSE_COL["id"]).value == "boiler"
            )
            ws.cell(row, EXPENSE_COL["useful_life"]).value = value

        return edit

    facts = _facts_after(life(18))
    assert next(x for x in facts.expense_lines if x.id == "boiler").useful_life == 18
    with pytest.raises(WorkbookFormatError, match="useful life should be years"):
        read_workbook(_broken(life(2.5)))
