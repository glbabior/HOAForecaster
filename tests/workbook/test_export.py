"""Excel export and re-import (spec sections 7.6 and 9)."""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from dataclasses import fields, replace
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
    Assessment,
    DuesMode,
    DuesPath,
    ExpenseLine,
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
from hoa_workbook.layout import ASSESS_FIRST_ROW, INPUT_ROWS, ROW, quote, sheet_names
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


def _projects() -> list[Any]:
    out = [pytest.param(DEMO, id="demo"), pytest.param(_short_project(), id="short")]
    data_dir = os.environ.get("HOA_DATA_DIR")
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
                elif field.name != "expense_lines":
                    assert vx == vy, (before.name, field.name)


def test_demo_round_trip_is_identical() -> None:
    assert read_workbook(export_workbook(DEMO)) == DEMO


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
@pytest.mark.parametrize("project", [DEMO, _short_project()], ids=["demo", "short"])
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
    assert len(charts) == 2 * 4 + 4  # two per scenario sheet, one per scenario on Charts
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


def _broken(edit: Any) -> bytes:
    wb = openpyxl.load_workbook(BytesIO(export_workbook(DEMO)))
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
        (lambda: _broken(lambda wb: wb["Expenses"].cell(5, 2, 1e20)), "not a usable number"),
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


def _insert_expense(copy_formulas: bool) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        ws = wb["Expenses"]
        ws.insert_rows(5)
        ws["A5"], ws["B5"], ws["C5"], ws["D5"] = "New gate", 9000, 2030, "no"
        if copy_formulas:  # what copying a whole row in Excel does
            for c in range(5, ws.max_column + 1):
                source = ws.cell(6, c)
                ws.cell(5, c).value = Translator(source.value, source.coordinate).translate_formula(
                    ws.cell(5, c).coordinate
                )

    return edit


def test_an_expense_row_copied_in_excel_is_read() -> None:
    project = read_workbook(_broken(_insert_expense(copy_formulas=True)))
    assert project.baseline.expense_lines[0] == ExpenseLine(2030, D(9000), "New gate")


def test_an_expense_typed_into_a_bare_row_is_refused() -> None:
    # the workbook's own totals would leave it out, so reading it would disagree with them
    with pytest.raises(WorkbookFormatError, match="row 5 has no year formulas"):
        read_workbook(_broken(_insert_expense(copy_formulas=False)))


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
    with pytest.raises(WorkbookFormatError, match="far larger than a planner export"):
        read_workbook(export_workbook(DEMO))


def test_a_damaged_package_gets_a_plain_message() -> None:
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<not a workbook")
    with pytest.raises(WorkbookFormatError, match="may be damaged or not an Excel file"):
        read_workbook(out.getvalue())


def _relabel(sheet: str, old: str, new: str) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        for (cell,) in wb[sheet].iter_rows(max_col=1):
            if cell.value == old:
                cell.value = new

    return edit


def _assessment_in(year: int) -> Any:
    def edit(wb: openpyxl.Workbook) -> None:
        wb["Dues only"].cell(ASSESS_FIRST_ROW, 3, year)
        wb["Dues only"].cell(ASSESS_FIRST_ROW, 4, 100)

    return edit


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_relabel("Expenses", "TOTAL projected reserve expenses", "Total"), "missing its total"),
        (lambda wb: wb["Inputs"].cell(11, 2, -5), "operating expenses cannot be negative"),
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
