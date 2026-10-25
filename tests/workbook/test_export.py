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
    Changes,
    DuesMode,
    DuesPath,
    ExpenseLine,
    Frequency,
    Project,
    Rounding,
    Scenario,
    project_from_dict,
    project_to_dict,
    run,
)
from hoa_engine.model import frozen_baseline
from hoa_workbook import read as reader
from hoa_workbook.charts import shared_grid
from hoa_workbook.export import build_workbook, export_workbook
from hoa_workbook.layout import (
    ASSESS_FIRST_ROW,
    CHANGE_YEAR_COL,
    CHANGES_HEADING,
    EXPENSE_COL,
    EXPENSE_TOTAL_LABEL,
    EXPENSE_YEAR_COL,
    INPUT_ROWS,
    LEAVE_OUT_COL,
    MARK_COL,
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


def _short_project() -> Project:
    """Five years, no governance limits, no expenses, typed dues with cents, odd names."""
    b = replace(
        DEMO.baseline,
        end_year=DEMO.baseline.start_year + 4,
        expense_lines=(),
        max_dues_increase=None,
        max_assessment_share=None,
        ffb={y: v for y, v in DEMO.baseline.ffb.items() if y <= DEMO.baseline.start_year + 5},
    )
    years = range(b.start_year, b.end_year + 1)
    typed = Scenario(
        "Typed: dues / cents?",
        DuesPath(DuesMode.EXPLICIT, explicit={y: D("601.25") + i for i, y in enumerate(years)}),
        assessments=(Assessment(b.start_year + 1, D(1000), "=not a formula"),),
        description="+1 is text, not a formula",
    )
    grown = Scenario(
        "It's grown",
        DuesPath(DuesMode.RATE, first_value=D("700.40"), annual_increase=D("0.05")),
        rounding=Rounding.NONE,
    )
    return Project("=Short demo", b, (typed, grown), notes="@note stays text")


def _changed_project() -> Project:
    """The demo with two scenarios that change the baseline every way spec 5.1 allows – one
    on its own horizon, so Compare has to line up different years."""
    b = DEMO.baseline
    insurance = next(line for line in b.expense_lines if line.id == "insurance")
    grown = DuesPath(DuesMode.RATE, first_value=D(690), annual_increase=D("0.04"))
    own = Scenario(
        "Own assumptions",
        grown,
        changes=Changes(
            values={"interest_rate": D("0.03"), "cushion": D(90000), "max_dues_increase": None},
            sources={"cushion": "Board policy, fictional", "ffb": "Fictional study update"},
            expense_lines={
                "insurance": replace(insurance, inflation=D("0.08"), amount=D(44000)),
                "study-2029": None,
                "pool": ExpenseLine(
                    2030,
                    D(9000),
                    "Pool resurfacing",
                    frequency=Frequency.EVERY,
                    interval=6,
                    id="pool",
                ),
                "patrol": ExpenseLine(
                    2030,
                    D(900),
                    "Security patrol",
                    frequency=Frequency.MONTHLY,
                    end_year=2036,
                    id="patrol",
                ),
            },
            ffb={2030: D(700000)},
        ),
    )
    later = Scenario(
        "Later and longer",
        grown,
        assessments=(Assessment(2045, D(800), "Late"),),
        changes=Changes(
            values={"start_year": 2028, "end_year": 2045, "starting_balance": D(210000)},
            ffb={2044: D(1190000), 2045: D(1240000), 2046: D(1290000)},
        ),
    )
    short = Scenario(
        "Short run",
        grown,
        changes=Changes(
            values={
                "end_year": b.start_year + 5,
                "units": 26,
                "current_dues": D("580.50"),
                "operating_inflation": D("0.035"),
                "expense_inflation": D("0.04"),
                "expense_base_year": 2027,
                "target": D("0.65"),
                "max_assessment_share": D("0.1"),
            }
        ),
    )
    # adopted a year ago against a different baseline, and an earlier plan before that
    older = replace(
        b,
        starting_balance=D(160000),
        interest_rate=D("0.012"),
        expense_lines=b.expense_lines[:-1],
        ffb={y: v - 20000 for y, v in b.ffb.items()},
        sources={**b.sources, "ffb": "Fictional older study"},
    )
    adopted = replace(
        own,
        name="Adopted plan",
        adoption=Adoption(
            date(2026, 11, 3), "Fictional board vote", 2, frozen_baseline(older, own)
        ),
    )
    first = replace(
        later,
        name="Earlier plan",
        adoption=Adoption(date(2025, 6, 1), "", 1, frozen_baseline(older, later)),
    )
    return replace(DEMO, scenarios=(*DEMO.scenarios[:2], own, later, short, adopted, first))


def _projects() -> list[Any]:
    out = [
        pytest.param(DEMO, id="demo"),
        pytest.param(_short_project(), id="short"),
        pytest.param(_changed_project(), id="changes"),
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
        problems += [
            f"{s.name} {p}"
            for p in mismatches(run(project.baseline, s), expected["scenarios"][s.name])
        ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("project", _projects())
def test_export_then_import_gives_the_same_results(project: Project) -> None:
    again = read_workbook(export_workbook(project))
    assert [s.name for s in again.scenarios] == [s.name for s in project.scenarios]
    for before, after in zip(project.scenarios, again.scenarios, strict=True):
        a, b = run(project.baseline, before), run(again.baseline, after)
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


def test_scenario_changes_round_trip_identically() -> None:
    project = _changed_project()
    assert read_workbook(export_workbook(project)) == project


def _plan_cell(sheet: str, label: str, col: int = VALUE_COL) -> Any:
    """A cell in a Plan sheet's own inputs, by its row label."""

    def at(wb: openpyxl.Workbook) -> Any:
        ws = wb[sheet]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        return ws.cell(rows[label], col)

    return at


def _set(at: Any, value: Any) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        at(wb).value = value

    return edit


def _changes_after(edit: Any, sheet: str = "Dues only") -> Changes:
    project = read_workbook(_broken(edit, _changed_project()))
    return next(s for s in project.scenarios if s.name == sheet).changes


def test_typing_over_a_link_in_excel_makes_the_value_the_scenarios_own() -> None:
    changes = _changes_after(
        _set(_plan_cell("Dues only", "Interest earned on reserves per year"), 0.04)
    )
    assert changes.values == {"interest_rate": D("0.04")}
    blank = _set(_plan_cell("Dues only", "Largest dues increase without an owner vote"), None)
    assert _changes_after(blank).values == {"max_dues_increase": None}
    note = _set(_plan_cell("Dues only", "Minimum working cushion", SOURCE_COL), "Our policy")
    assert _changes_after(note).sources == {"cushion": "Our policy"}


def test_a_formula_other_than_the_link_is_refused() -> None:
    edit = _set(_plan_cell("Dues only", "Minimum working cushion"), "=Inputs!$B$15*2")
    with pytest.raises(WorkbookFormatError, match="'Minimum working cushion' holds a formula"):
        read_workbook(_broken(edit, _changed_project()))


def test_a_spare_change_row_filled_in_excel_adds_a_line_of_the_scenarios_own() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        r = rows[CHANGES_HEADING] + 2  # the first spare row – Dues only has no changes
        for key, value in (
            ("description", "Sign"),
            ("frequency", "once"),
            ("amount", 500),
            ("year", 2030),
        ):
            ws.cell(r, EXPENSE_COL[key], value)
        ws.cell(r + 1, EXPENSE_COL["id"], "insurance")
        ws.cell(r + 1, LEAVE_OUT_COL, "yes")

    changes = _changes_after(edit)
    assert changes.expense_lines == {
        "own-1": ExpenseLine(2030, D(500), "Sign", id="own-1"),
        "insurance": None,
    }


def test_leaving_out_a_line_needs_its_id() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        ws.cell(rows[CHANGES_HEADING] + 2, LEAVE_OUT_COL, "yes")

    with pytest.raises(WorkbookFormatError, match="leaves out a line but has no line id"):
        read_workbook(_broken(edit, _changed_project()))


def test_a_change_row_below_the_list_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        r = rows["TOTAL operating expenses – this scenario"] - 1
        ws.cell(r, EXPENSE_COL["frequency"], "once")
        ws.cell(r, EXPENSE_COL["amount"], 1)

    with pytest.raises(WorkbookFormatError, match="outside the rows the totals add up"):
        read_workbook(_broken(edit, _changed_project()))


def test_a_change_row_typed_without_year_formulas_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        r = rows[CHANGES_HEADING] + 2
        ws.cell(r, EXPENSE_COL["frequency"], "once")
        ws.cell(r, EXPENSE_COL["amount"], 1)
        ws.cell(r, CHANGE_YEAR_COL).value = None

    with pytest.raises(WorkbookFormatError, match="has no year formulas"):
        read_workbook(_broken(edit, _changed_project()))


@pytest.mark.parametrize(
    "label",
    [
        "Interest earned on reserves per year",
        CHANGES_HEADING,
        "TOTAL operating expenses – this scenario",
    ],
)
def test_a_scenario_sheet_without_its_own_inputs_is_refused(label: str) -> None:
    edit = _relabel("Dues only", label, "Something else")
    with pytest.raises(WorkbookFormatError, match=f"Dues only is missing the row '{label[:20]}"):
        read_workbook(_broken(edit))


def test_a_scenario_on_an_impossible_horizon_is_not_exported() -> None:
    wide = replace(DEMO.scenarios[0], changes=Changes(values={"end_year": 2100}))
    with pytest.raises(ValueError, match="Dues only – the horizon must be 5–30 full years"):
        export_workbook(replace(DEMO, scenarios=(wide,)))


def test_measures_a_short_scenario_cannot_have_are_dashes() -> None:
    wb = build_workbook(_changed_project())
    ws = wb["Compare"]
    labels = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
    columns = {ws.cell(4, c).value: c for c in range(2, ws.max_column + 1)}
    assert ws.cell(labels["Dues per unit per month – year 9"], columns["Short run"]).value == "–"
    assert ws.cell(labels["Dues per unit per month – year 9"], columns["Dues only"]).value


def test_text_worded_like_a_label_never_stands_in_for_it() -> None:
    """An expense, a left-out line or a note may read "Operating expenses" – the reader looks
    for each label only in its own part of the sheet."""
    project = _changed_project()
    b = project.baseline
    renamed = tuple(
        replace(line, description="Interest earned") if line.id == "boiler" else line
        for line in b.expense_lines
    )
    own, *rest = project.scenarios[2:]
    pool = own.changes.expense_lines["pool"]
    assert pool is not None
    worded = replace(
        own,
        name="Interest earned",  # a sheet's name and description sit above its rows
        description="Operating expenses",
        assessments=(Assessment(2030, D(10), "Start year"),),
        changes=replace(
            own.changes,
            expense_lines={
                **own.changes.expense_lines,
                "boiler": None,
                "pool": replace(pool, description="Operating expenses"),
            },
        ),
    )
    project = replace(
        project,
        baseline=replace(b, expense_lines=renamed),
        scenarios=(*project.scenarios[:2], worded, *rest),
    )
    assert read_workbook(export_workbook(project)) == project
    named = replace(project, scenarios=(replace(worded, name="How dues are set"),))
    assert read_workbook(export_workbook(named)) == named


def test_a_new_baseline_line_never_takes_an_id_a_scenario_uses() -> None:
    gate = ExpenseLine(2030, D(100), "Gate", id="line-1")  # the scenario's own, made earlier
    project = _changed_project()
    first = replace(project.scenarios[0], changes=Changes(expense_lines={"line-1": gate}))
    project = replace(project, scenarios=(first, *project.scenarios[1:]))
    again = read_workbook(_broken(_insert_expense(6, copy_formulas=True), project))
    new = again.baseline.expense_lines[1]
    assert (new.description, new.id) == ("New gate", "line-2")
    assert again.scenarios[0].changes.expense_lines == {"line-1": gate}


def test_a_link_copied_onto_the_wrong_row_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        interest = _plan_cell("Dues only", "Interest earned on reserves per year")(wb).value
        _plan_cell("Dues only", "Minimum working cushion")(wb).value = interest

    with pytest.raises(WorkbookFormatError, match="'Minimum working cushion' holds a formula"):
        read_workbook(_broken(edit, _changed_project()))


def test_putting_a_left_out_line_back_in_excel_follows_the_baseline() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Own assumptions"]
        for (cell,) in ws.iter_rows(min_col=LEAVE_OUT_COL, max_col=LEAVE_OUT_COL):
            if cell.value == "yes":
                cell.value = "no"

    changes = _changes_after(edit, "Own assumptions")
    assert "study-2029" not in changes.expense_lines and "pool" in changes.expense_lines


@pytest.mark.skipif(not _libreoffice(), reason="LibreOffice not installed")
def test_a_line_put_back_in_excel_is_back_in_the_workbooks_own_figures(tmp_path: Path) -> None:
    """What re-import reads must be what the edited workbook calculates (spec 7.6)."""

    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Own assumptions"]
        for (cell,) in ws.iter_rows(min_col=LEAVE_OUT_COL, max_col=LEAVE_OUT_COL):
            if cell.value == "yes":
                cell.value = "no"  # its id stays, with no inputs
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        spare = rows["TOTAL operating expenses – this scenario"] - 3
        ws.cell(spare, EXPENSE_COL["id"], "insurance")  # an id typed alone into a spare row

    workbook = tmp_path / "edited.xlsx"
    workbook.write_bytes(_broken(edit, _changed_project()))
    project = read_workbook(workbook)
    recalc.recalc(workbook)
    expected = extract_expected.extract(workbook, project_to_dict(project))
    s = next(s for s in project.scenarios if s.name == "Own assumptions")
    assert not mismatches(run(project.baseline, s), expected["scenarios"][s.name])


def test_a_scenarios_own_line_id_typed_on_expenses_is_refused() -> None:
    edit = _set(lambda wb: wb["Expenses"].cell(5, EXPENSE_COL["id"]), "own-1")
    with pytest.raises(WorkbookFormatError, match="'own-1' is kept for lines of a scenario's own"):
        read_workbook(_broken(edit))


def test_a_huge_horizon_of_a_scenario_is_refused_before_it_is_walked() -> None:
    edit = _set(_plan_cell("Dues only", "End year"), 10**12)
    with pytest.raises(WorkbookFormatError, match="Dues only – the horizon must be 5–30"):
        read_workbook(_broken(edit))
    inputs = _set(lambda wb: wb["Inputs"].cell(8, 2), 10**12)
    with pytest.raises(WorkbookFormatError, match="Inputs – the horizon must be 5–30"):
        read_workbook(_broken(inputs))


def test_an_adopted_plan_is_written_frozen_and_read_back_whole() -> None:
    wb = build_workbook(_changed_project())
    ws = wb["Adopted plan"]
    assert ws.protection.sheet  # a reminder that it is read-only
    assert str(ws["A3"].value).startswith("Adopted plan – adopted November 3, 2026")
    interest = _plan_cell("Adopted plan", "Interest earned on reserves per year")(wb)
    assert interest.value == 0.03  # typed, not linked to Inputs
    mark = _plan_cell("Adopted plan", "Interest earned on reserves per year", MARK_COL)(wb)
    assert mark.value == "value"


def test_an_adoption_date_excel_turned_into_a_date_is_read() -> None:
    edit = _set(_plan_cell("Adopted plan", "Adopted on"), datetime(2026, 11, 4))
    project = read_workbook(_broken(edit, _changed_project()))
    plan = next(s for s in project.scenarios if s.name == "Adopted plan")
    assert plan.adoption is not None and plan.adoption.adopted_on == date(2026, 11, 4)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_set(_plan_cell("Adopted plan", "Adopted on"), 5), "adoption date should be written"),
        (
            _set(_plan_cell("Adopted plan", "Minimum working cushion", MARK_COL), "no value"),
            "should be blank, value, note or value and note",
        ),
        (
            lambda wb: _relabel("Adopted plan", "Adoption note", "Note")(wb),
            "missing the row 'Adoption note'",
        ),
        (
            lambda wb: _relabel("Adopted plan", "This plan's own Fully Funded Balance?", "x")(wb),
            "missing the row 'This plan's own Fully Funded Balance?'",
        ),
        (
            lambda wb: _relabel("Dues only", "TOTAL reserve expenses – this scenario", "x")(wb),
            "missing the row 'TOTAL reserve expenses",
        ),
        (
            _set(_plan_cell("Adopted plan", "Minimum working cushion"), "=Inputs!$B$15"),
            "'Minimum working cushion' holds a formula",  # an adopted plan's figures are typed
        ),
    ],
)
def test_a_damaged_adopted_plan_sheet_is_refused(edit: Any, message: str) -> None:
    with pytest.raises(WorkbookFormatError, match=re.escape(message)):
        read_workbook(_broken(edit, _changed_project()))


def test_a_scenarios_own_start_year_cannot_be_moved_in_excel() -> None:
    edit = _set(_plan_cell("Later and longer", "Start year"), 2029)
    with pytest.raises(WorkbookFormatError, match="horizon can only be changed in the app"):
        read_workbook(_broken(edit, _changed_project()))


def test_the_scenarios_fully_funded_balance_is_read_year_by_year() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        ws.cell(rows["Fully Funded Balance at start of year"], VALUE_COL + 1, 650000)

    assert _changes_after(edit).ffb == {2028: D(650000)}


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
    "project", [DEMO, _short_project(), _changed_project()], ids=["demo", "short", "changes"]
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
        "project name": wb["Inputs"]["B5"],
        "notes": wb["Inputs"].cell(4 + len(INPUT_ROWS), 2),
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


def test_choosing_and_ordering_scenarios() -> None:
    wb = build_workbook(DEMO, scenario_names=["Steady increase", "Dues only"])
    assert wb.sheetnames == [
        "Method",
        "Inputs",
        "Compare",
        "Charts",
        "Expenses",
        "Steady increase",
        "Dues only",
    ]


def test_short_horizon_leaves_out_year_nine_measures() -> None:
    labels = [c.value for c in build_workbook(_short_project())["Compare"]["A"] if c.value]
    assert not any(str(label).endswith(str(DEMO.baseline.start_year + 8)) for label in labels)


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
    ws = wb["Expenses"]
    rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
    cell = ws.cell(rows["TOTAL operating expenses (monthly and yearly lines)"], EXPENSE_YEAR_COL)
    cell.value = re.sub(r"\$5:", "$6:", cell.value)


def _broken(edit: Any, project: Project = DEMO) -> bytes:
    wb = openpyxl.load_workbook(BytesIO(export_workbook(project)))
    edit(wb)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not a zip", "not an Excel workbook"),
        (lambda: _broken(lambda wb: wb.remove(wb["Inputs"])), "no Inputs sheet"),
        (lambda: _broken(lambda wb: wb["Inputs"].cell(6, 2, "lots")), "should be a number"),
        (lambda: _broken(lambda wb: wb["Inputs"].cell(7, 2, "soon")), "should be a year"),
        (lambda: _broken(lambda wb: wb["Inputs"].delete_rows(9)), "missing the row"),
        (
            lambda: _broken(lambda wb: wb["Dues only"].cell(ROW["mode"], 3, "guess")),
            "unrecognised dues",
        ),
        (lambda: _broken(lambda wb: wb["Inputs"].cell(9, 2, 2.5)), "should be a whole number"),
        (
            lambda: _broken(lambda wb: wb["Expenses"].cell(5, EXPENSE_COL["amount"], 1e20)),
            "not a usable number",
        ),
        (
            lambda: _broken(lambda wb: wb["Expenses"].cell(5, EXPENSE_COL["frequency"], "often")),
            "'How often' should be one of monthly, yearly, every few years, once",
        ),
        (
            lambda: _broken(lambda wb: wb["Expenses"].cell(5, EXPENSE_COL["frequency"], "yearly ")),
            "'How often' should be one of",  # the workbook's SUMIF totals would skip it
        ),
        (
            lambda: _broken(lambda wb: wb["Expenses"].cell(5, EXPENSE_COL["interval"], 2.5)),
            "row 5 interval should be a number of years",
        ),
        (
            lambda: _broken(_retarget_operating_total),
            "operating and reserve totals on Expenses add up different rows",
        ),
    ],
)
def test_unreadable_workbooks_are_refused_in_plain_language(data: Any, message: str) -> None:
    with pytest.raises(WorkbookFormatError, match=message):
        read_workbook(data() if callable(data) else data)


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


def _insert_expense(at: int, copy_formulas: bool) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Expenses"]
        _excel_insert(ws, at)
        for key, value in (
            ("description", "New gate"),
            ("frequency", "once"),
            ("amount", 9000),
            ("year", 2030),
            ("nominal", "no"),
        ):
            ws.cell(at, EXPENSE_COL[key], value)
        if copy_formulas:  # what copying a whole row in Excel does
            for c in range(EXPENSE_YEAR_COL, ws.max_column + 1):
                source = ws.cell(at + 1, c)
                ws.cell(at, c).value = Translator(
                    source.value, source.coordinate
                ).translate_formula(ws.cell(at, c).coordinate)

    return edit


def test_an_expense_row_copied_between_rows_in_excel_is_read() -> None:
    project = read_workbook(_broken(_insert_expense(6, copy_formulas=True)))
    lines = project.baseline.expense_lines
    assert ExpenseLine(2030, D(9000), "New gate", id="line-1") in lines
    assert len({line.id for line in lines}) == len(lines) == len(DEMO.baseline.expense_lines) + 1


def test_a_new_row_gets_an_id_no_other_line_has() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        _insert_expense(6, copy_formulas=True)(wb)
        wb["Expenses"].cell(5, EXPENSE_COL["id"], "line-1")

    lines = read_workbook(_broken(edit)).baseline.expense_lines
    assert [line.id for line in lines[:2]] == ["line-1", "line-2"]


def test_a_copied_row_that_keeps_its_line_id_is_refused() -> None:
    # scenarios refer to lines by id, and which row is the original cannot be told
    def edit(wb: openpyxl.Workbook) -> None:
        _insert_expense(6, copy_formulas=True)(wb)
        wb["Expenses"].cell(6, EXPENSE_COL["id"], "insurance")

    with pytest.raises(WorkbookFormatError, match="rows 6 and 8 on Expenses share the line id"):
        read_workbook(_broken(edit))


def test_an_expense_typed_into_a_bare_row_is_refused() -> None:
    # the workbook's own totals would leave it out, so reading it would disagree with them
    with pytest.raises(WorkbookFormatError, match="row 6 has no year formulas"):
        read_workbook(_broken(_insert_expense(6, copy_formulas=False)))


def test_an_expense_above_the_summed_rows_is_refused() -> None:
    # Excel does not stretch SUM(E5:E…) for a row inserted at row 5, so the total skips it
    with pytest.raises(WorkbookFormatError, match="row 5 is outside the rows the total adds up"):
        read_workbook(_broken(_insert_expense(5, copy_formulas=True)))


def test_an_expense_typed_in_the_gap_above_the_total_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Expenses"]
        rows = {c.value: c.row for (c,) in ws.iter_rows(max_col=1) if c.value}
        gap = rows["TOTAL operating expenses (monthly and yearly lines)"] - 1
        ws.cell(gap, EXPENSE_COL["description"], "Forgotten")
        ws.cell(gap, EXPENSE_COL["amount"], 100)

    with pytest.raises(WorkbookFormatError, match="outside the rows the total adds up"):
        read_workbook(_broken(edit))


def test_a_row_inserted_on_a_scenario_sheet_keeps_the_scenario() -> None:
    project = read_workbook(_broken(lambda wb: _excel_insert(wb["Two-part assessment"], 39)))
    assert project == DEMO


def test_an_assessment_below_the_list_is_refused() -> None:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Dues only"]
        charts = next(
            c.row for (c,) in ws.iter_rows(max_col=1) if str(c.value).startswith("Charts")
        )
        below = charts - 1  # the blank row between the list's spare rows and the charts
        ws.cell(below, 3, 2030)
        ws.cell(below, 4, 500)

    with pytest.raises(WorkbookFormatError, match="below the assessment list"):
        read_workbook(_broken(edit))


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
    assert hold.dues.explicit[DEMO.baseline.start_year + 2] == 700


def test_changing_the_horizon_in_excel_is_refused() -> None:
    with pytest.raises(WorkbookFormatError, match="horizon can only be changed in the app"):
        read_workbook(_broken(lambda wb: wb["Inputs"].cell(8, 2, DEMO.baseline.end_year - 1)))


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
    b = DEMO.baseline
    two = Scenario(
        "Two in one year",
        DuesPath(DuesMode.RATE, first_value=D(600), annual_increase=D("0.03")),
        assessments=(
            Assessment(b.start_year + 1, D(1500), "First half"),
            Assessment(b.start_year + 1, D(1500), "Second half"),
            Assessment(b.start_year + 2, D(0), "Placeholder"),
        ),
    )
    project = Project("Installments", b, (two,))
    assert read_workbook(export_workbook(project)) == project


def test_scenario_names_keep_their_spaces() -> None:
    padded = replace(DEMO.scenarios[0], name="  Padded  ", description=" lead")
    project = Project("Spaces", DEMO.baseline, (padded,))
    assert read_workbook(export_workbook(project)).scenarios[0] == padded


def test_a_scenario_named_notes_does_not_become_the_project_notes() -> None:
    project = Project("N", DEMO.baseline, (replace(DEMO.scenarios[0], name="Notes"),))
    assert read_workbook(export_workbook(project)).notes == ""


# ---------------------------------------------------------------- review follow-ups


def test_sheet_names_never_end_in_an_apostrophe_and_fit_excels_utf16_limit() -> None:
    cut, emoji = sheet_names(["a" * 30 + "'b", "😀" * 20])
    assert cut == "a" * 30
    assert len(emoji.encode("utf-16-le")) // 2 <= 31


def test_method_sheet_lists_sources() -> None:
    sources = {"starting_balance": "Balance sheet, Dec 2026", "ffb": "Reserve study, 2026"}
    project = replace(DEMO, baseline=replace(DEMO.baseline, sources=sources))
    lines = [c.value for c in build_workbook(project)["Method"]["A"] if c.value]
    assert "Sources" in lines
    assert any(str(line).endswith("Reserve study, 2026") for line in lines)
    bare = replace(DEMO, baseline=replace(DEMO.baseline, sources={}))
    assert "Sources" not in [c.value for c in build_workbook(bare)["Method"]["A"]]


@pytest.mark.parametrize(
    ("project", "names", "message"),
    [
        (DEMO, ["Nope"], "no scenario named 'Nope'"),
        (replace(DEMO, scenarios=(DEMO.scenarios[0], DEMO.scenarios[0])), None, "must be unique"),
        (replace(DEMO, baseline=replace(DEMO.baseline, end_year=10**9)), None, "horizon"),
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
        (_relabel("Expenses", EXPENSE_TOTAL_LABEL, "Total"), "missing its total"),
        (
            lambda wb: wb["Expenses"].cell(5, EXPENSE_COL["amount"], -5),
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
        ex = wb["Expenses"]
        rows = {c.value: c.row for (c,) in ex.iter_rows(max_col=1) if c.value}
        ffb = rows["Fully Funded Balance at start of year"]
        ex.cell(ffb, ex.max_column + 2, 5)  # no year above it – ignored
        ex.cell(ffb, 1).comment = Comment("Reserve study, 2026", "x")
        plan = wb["Dues only"]
        plan.cell(4, plan.max_column + 2, None)
        plan.cell(5, plan.max_column + 2, "stray")

    project = read_workbook(_broken(edit))
    assert project.baseline.sources["ffb"] == "Reserve study, 2026"
