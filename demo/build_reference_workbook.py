"""Build the demo reference workbook and its expected results.

    uv run python demo/build_reference_workbook.py

1. Writes demo/fixtures/reference.xlsx from demo/fixtures/project.json – the
   reference layout (Inputs, Expenses, one Plan sheet per scenario, Compare),
   every result a live formula. This script never imports the engine, so the
   expected figures are an independent check on it.
2. Recalculates the workbook in LibreOffice headless (tools/recalc.py).
3. Extracts the cached values to demo/fixtures/expected.json
   (tools/extract_expected.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as col_letter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_expected  # noqa: E402
import recalc  # noqa: E402

FIXTURES = ROOT / "demo" / "fixtures"
CUR = "$#,##0;($#,##0);-"
PCT = "0.0%"
INPUT_FONT = Font(name="Arial", color="0000FF")
INPUT_FILL = PatternFill("solid", fgColor="FFFF00")
FIRST = 3  # Plan sheets – column C is the start year


def _input(cell: Any, value: Any, fmt: str | None = None) -> None:
    cell.value = value
    cell.font, cell.fill = INPUT_FONT, INPUT_FILL
    if fmt:
        cell.number_format = fmt


def _text(cell: Any, value: str) -> None:
    """Write user text as text – a leading = + - @ must never start a formula."""
    cell.value = value
    cell.data_type = "s"


def _num(value: str) -> float | int:
    # openpyxl writes numbers; inputs are exact decimal strings in the project file
    return int(value) if value.lstrip("-").isdigit() else float(value)


def build(project: dict[str, Any], out: Path) -> None:
    b = project["baseline"]
    start, end = b["start_year"], b["end_year"]
    years = list(range(start, end + 1))
    wb = Workbook()

    # ---------------- Inputs
    inp = wb.active
    inp.title = "Inputs"
    _text(inp["A1"], f"{project['name']} – Inputs")
    rows = [
        ("Starting reserve balance (January 1 of the start year)", b["starting_balance"], CUR),
        ("Start year", b["start_year"], "0"),
        ("End year", b["end_year"], "0"),
        ("Number of units", b["units"], "0"),
        ("Current dues per unit per month", b["current_dues"], CUR),
        ("Operating expenses in the start year", b["operating_start"], CUR),
        ("Operating cost inflation per year", b["operating_inflation"], PCT),
        ("Reserve expense inflation per year", b["expense_inflation"], PCT),
        ("Expense base year", b["expense_base_year"], "0"),
        ("Interest earned on reserves per year", b["interest_rate"], PCT),
        ("Minimum working cushion", b["cushion"], CUR),
        ("Percent-funded target", b["target"], PCT),
        ("Largest dues increase without an owner vote", b["max_dues_increase"], PCT),
        ("Largest assessment without a vote, share of budget", b["max_assessment_share"], PCT),
    ]
    ref = {}
    for i, (label, value, fmt) in enumerate(rows, start=4):
        inp.cell(i, 1, label)
        if value is not None:  # a blank governance limit means no limit
            _input(inp.cell(i, 2), _num(str(value)), fmt)
        ref[label] = f"Inputs!$B${i}"
    BAL, START, _, UNITS, DUES0, OPEX, OPINF, EXINF, BASE, INT, FLOOR, TARGET, MAXINC, MAXSA = (
        ref[r[0]] for r in rows
    )

    # ---------------- Expenses
    ex = wb.create_sheet("Expenses")
    ex["A1"] = "Projected reserve expenses by year ($)"
    for c, h in enumerate(["Item", "Amount", "Year", "Already nominal?"], start=1):
        ex.cell(4, c, h)
    ycol = {y: col_letter(5 + i) for i, y in enumerate(years)}
    for y in years:
        ex[f"{ycol[y]}4"] = y
    r = 5
    for line in b["expense_lines"]:
        _text(ex.cell(r, 1), line["description"])
        if line.get("source"):
            ex.cell(r, 1).comment = Comment(line["source"], "Model")
        _input(ex.cell(r, 2), _num(line["amount"]), CUR)
        _input(ex.cell(r, 3), line["year"], "0")
        _input(ex.cell(r, 4), "yes" if line["nominal"] else "no")
        for y in years:
            c = ycol[y]
            ex[f"{c}{r}"] = f'=IF({c}$4=$C{r},$B{r}*IF($D{r}="yes",1,(1+{EXINF})^({c}$4-{BASE})),0)'
            ex[f"{c}{r}"].number_format = CUR
        r += 1
    total_row = r + 1
    ex.cell(total_row, 1, "TOTAL projected reserve expenses")
    for y in years:
        c = ycol[y]
        ex[f"{c}{total_row}"] = f"=SUM({c}5:{c}{r - 1})"
        ex[f"{c}{total_row}"].number_format = CUR
    ffb_head, ffb_row = total_row + 2, total_row + 3
    ex.cell(ffb_head, 1, "Year")
    ex.cell(ffb_row, 1, "Fully Funded Balance at start of year")
    fcol = {y: col_letter(5 + i) for i, y in enumerate(range(start, end + 2))}
    for y in range(start, end + 2):
        ex[f"{fcol[y]}{ffb_head}"] = y
        _input(ex[f"{fcol[y]}{ffb_row}"], _num(b["ffb"][str(y)]), CUR)

    # ---------------- Plan sheets
    compare_rows: dict[str, dict[str, int]] = {}
    for s in project["scenarios"]:
        ws = wb.create_sheet(s["name"])
        _text(ws["A1"], f"{s['name']} – {s['description']}")
        ws.cell(4, 1, "Year")
        pc = {y: col_letter(FIRST + i) for i, y in enumerate(years)}
        for y in years:
            ws[f"{pc[y]}4"] = y
        R = {
            "dues": 5,
            "sa": 6,
            "total_dues": 8,
            "operating": 9,
            "contribution": 10,
            "sa_total": 11,
            "owners": 12,
            "interest": 13,
            "expenses": 14,
            "start": 16,
            "end": 17,
            "ffb": 18,
            "pf": 19,
            "low": 20,
            "met": 21,
            "vote": 22,
            "short": 23,
            "own_dues": 25,
            "own_cost": 26,
            "increase": 27,
            "cum_cost": 28,
            "cum_extra": 29,
            "extra": 30,
            "target": 31,
            "first": 34,
            "rate": 35,
            "pinned": 36,
            "grown": 37,
        }
        labels = {
            "dues": "Dues per unit per month ($)",
            "sa": "Special assessment per unit ($, this year)",
            "total_dues": "Total dues collected",
            "operating": "Operating expenses",
            "contribution": "Reserve contribution from dues",
            "sa_total": "Special assessment to reserves",
            "owners": "Total collected from owners (dues + assessment)",
            "interest": "Interest earned",
            "expenses": "Reserve expenses (Expenses sheet)",
            "start": "Starting reserve balance",
            "end": "Ending reserve balance",
            "ffb": "Fully Funded Balance (start of next year)",
            "pf": "Percent funded at year end",
            "low": "Below minimum cushion?",
            "met": "Meets percent-funded target?",
            "vote": "Needs owner vote?",
            "short": "Operating shortfall?",
            "own_dues": "Owner cost – dues per unit per year",
            "own_cost": "Owner cost – dues + assessment per unit",
            "increase": "Increase vs current dues (per unit per year)",
            "cum_cost": "Cumulative owner cost per unit",
            "cum_extra": "Cumulative extra cost vs current dues",
            "extra": "Extra vs current dues, with assessment (per unit per year)",
            "target": "Percent-funded target (Inputs)",
            "first": "First-year dues (grown dues only)",
            "rate": "Annual dues increase (grown dues only)",
            "pinned": "Pinned dues (blank = grow from the year before)",
            "grown": "Dues before rounding",
        }
        for key, label in labels.items():
            ws.cell(R[key], 1, label)
        compare_rows[s["name"]] = R

        dues = s["dues"]
        grown = dues["mode"] == "rate"
        if grown:
            _input(ws.cell(R["first"], FIRST), _num(dues["first_value"]), CUR)
            _input(ws.cell(R["rate"], FIRST), _num(dues["annual_increase"]), PCT)
        per_unit: dict[int, float] = {}
        for a in s["assessments"]:
            per_unit[a["year"]] = per_unit.get(a["year"], 0) + _num(a["amount"])

        for i, y in enumerate(years):
            c, p = pc[y], (pc[y - 1] if i else None)
            D = {k: f"{c}{row}" for k, row in R.items()}
            P = {k: f"{p}{row}" for k, row in R.items()} if p else {}
            if grown:
                pinned = dues["overrides"].get(str(y))
                if pinned is not None:
                    _input(ws[D["pinned"]], _num(pinned), CUR)
                first = f"${col_letter(FIRST)}${R['first']}"
                rate = f"${col_letter(FIRST)}${R['rate']}"
                prior = first if i == 0 else f"{P['grown']}*(1+{rate})"
                ws[D["grown"]] = f'=IF({D["pinned"]}<>"",{D["pinned"]},{prior})'
                if i == 0 or s["rounding"] == "none":
                    ws[D["dues"]] = f"={D['grown']}"
                else:
                    ws[D["dues"]] = f'=IF({D["pinned"]}<>"",{D["pinned"]},ROUND({D["grown"]},0))'
            else:
                _input(ws[D["dues"]], _num(dues["explicit"][str(y)]), CUR)
            _input(ws[D["sa"]], per_unit.get(y, 0), CUR)
            prior_dues = DUES0 if i == 0 else P["dues"]
            formulas = {
                "total_dues": f"={D['dues']}*{UNITS}*12",
                "operating": f"={OPEX}*(1+{OPINF})^({c}$4-{START})",
                "contribution": f"=MAX(0,{D['total_dues']}-{D['operating']})",
                "sa_total": f"={D['sa']}*{UNITS}",
                "owners": f"={D['total_dues']}+{D['sa_total']}",
                "interest": f"={D['start']}*{INT}",
                "expenses": f"=Expenses!{ycol[y]}${total_row}",
                "start": f"={BAL}" if i == 0 else f"={P['end']}",
                "end": (
                    f"={D['start']}+{D['contribution']}+{D['sa_total']}"
                    f"+{D['interest']}-{D['expenses']}"
                ),
                "ffb": f"=Expenses!{fcol[y + 1]}${ffb_row}",
                "pf": f"=IF({D['ffb']}=0,0,{D['end']}/{D['ffb']})",
                "low": f'=IF({D["end"]}<{FLOOR},"LOW","ok")',
                "met": f'=IF({D["pf"]}>={TARGET},"yes","no")',
                "vote": (
                    f"=IF(OR(AND({prior_dues}>0,{D['dues']}/{prior_dues}-1>{MAXINC}),"
                    f'{D["sa_total"]}>{MAXSA}*({D["operating"]}+{D["contribution"]})),"yes","no")'
                ),
                "short": f'=IF({D["total_dues"]}<{D["operating"]},"yes","no")',
                "own_dues": f"={D['dues']}*12",
                "own_cost": f"={D['own_dues']}+{D['sa']}",
                "increase": f"=({D['dues']}-{DUES0})*12",
                "cum_cost": f"={D['own_cost']}" if i == 0 else f"={P['cum_cost']}+{D['own_cost']}",
                "cum_extra": (
                    f"={D['increase']}+{D['sa']}"
                    if i == 0
                    else f"={P['cum_extra']}+{D['increase']}+{D['sa']}"
                ),
                "extra": f"={D['increase']}+{D['sa']}",
                "target": f"={TARGET}",
            }
            for key, formula in formulas.items():
                ws[D[key]] = formula
                ws[D[key]].number_format = PCT if key in ("pf", "target") else CUR

    # ---------------- Compare
    cp = wb.create_sheet("Compare", 1)
    cp["A1"] = "Scenario comparison"
    cp.cell(4, 1, "Measure")
    names = [s["name"] for s in project["scenarios"]]
    for j, n in enumerate(names):
        _text(cp.cell(4, 2 + j), n)
    first, last = col_letter(FIRST), col_letter(FIRST + len(years) - 1)

    def span(n: str, row: int, a: int = 0, z: int | None = None) -> str:
        z = len(years) - 1 if z is None else z
        return f"'{n}'!{col_letter(FIRST + a)}{row}:{col_letter(FIRST + z)}{row}"

    def at(n: str, row: int, offset: int) -> str:
        return f"='{n}'!{col_letter(FIRST + offset)}{row}"

    n_years = len(years)
    measures = [
        (f"Dues per unit per month – {start}", lambda n, R: at(n, R["dues"], 0), CUR),
        (f"Dues per unit per month – {start + 3}", lambda n, R: at(n, R["dues"], 3), CUR),
        (f"Dues per unit per month – {start + 8}", lambda n, R: at(n, R["dues"], 8), CUR),
        (
            f"Special assessments per unit, total {start}–{end}",
            lambda n, R: f"=SUM({span(n, R['sa'])})",
            CUR,
        ),
        (
            f"Lowest year-end reserve balance, {start}–{end}",
            lambda n, R: f"=MIN({span(n, R['end'])})",
            CUR,
        ),
        (
            f"Year of lowest year-end balance, {start}–{end}",
            lambda n, R: (
                f"=INDEX('{n}'!{first}4:{last}4,"
                f"MATCH(MIN({span(n, R['end'])}),{span(n, R['end'])},0))"
            ),
            "0",
        ),
        (
            f"Years below minimum cushion, {start}–{end}",
            lambda n, R: f'=COUNTIF({span(n, R["low"])},"LOW")',
            "0",
        ),
        (
            f"Years needing an owner vote, {start}–{end}",
            lambda n, R: f'=COUNTIF({span(n, R["vote"])},"yes")',
            "0",
        ),
        (
            f"Years with an operating shortfall, {start}–{end}",
            lambda n, R: f'=COUNTIF({span(n, R["short"])},"yes")',
            "0",
        ),
        (f"Reserve balance end of {start + 3}", lambda n, R: at(n, R["end"], 3), CUR),
        (f"Percent funded end of {start + 3}", lambda n, R: at(n, R["pf"], 3), PCT),
        (f"Reserve balance end of {start + 8}", lambda n, R: at(n, R["end"], 8), CUR),
        (f"Percent funded end of {start + 8}", lambda n, R: at(n, R["pf"], 8), PCT),
        (f"Reserve balance end of {end}", lambda n, R: at(n, R["end"], n_years - 1), CUR),
        (f"Percent funded end of {end}", lambda n, R: at(n, R["pf"], n_years - 1), PCT),
        (
            "First year percent-funded target is met",
            lambda n, R: (
                f"=IFERROR(INDEX('{n}'!{first}4:{last}4,MATCH(\"yes\",{span(n, R['met'])},0)),"
                f'"not by {end}")'
            ),
            "0",
        ),
        (
            f"Owner outlay per unit, {start}–{start + 4} (dues + assessments)",
            lambda n, R: f"=SUM({span(n, R['own_cost'], 0, 4)})",
            CUR,
        ),
        (
            f"Owner outlay per unit, {start}–{end} (dues + assessments)",
            lambda n, R: f"=SUM({span(n, R['own_cost'])})",
            CUR,
        ),
        (
            f"Extra cost vs current dues, {start}–{end}, per unit",
            lambda n, R: f"=SUM({span(n, R['increase'])})+SUM({span(n, R['sa'])})",
            CUR,
        ),
        (
            f"Extra cost vs current dues, {start}–{start + 3}, per unit",
            lambda n, R: f"=SUM({span(n, R['increase'], 0, 3)})+SUM({span(n, R['sa'], 0, 3)})",
            CUR,
        ),
        (
            f"Average owner cost per year, {start}–{end}, per unit",
            lambda n, R: f"=AVERAGE({span(n, R['own_cost'])})",
            CUR,
        ),
        (
            f"Average extra cost per year vs current dues, {start}–{end}, per unit",
            lambda n, R: f"=(SUM({span(n, R['increase'])})+SUM({span(n, R['sa'])}))/{n_years}",
            CUR,
        ),
    ]
    for i, (label, formula, fmt) in enumerate(measures, start=5):
        cp.cell(i, 1, label)
        for j, n in enumerate(names):
            cell = cp.cell(i, 2 + j, formula(n, compare_rows[n]))
            cell.number_format = fmt
    cp.cell(len(measures) + 6, 1, "Year-end reserve balance by year")
    wb.save(out)


def main() -> None:
    project_path = FIXTURES / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    workbook = FIXTURES / "reference.xlsx"
    build(project, workbook)
    recalc.recalc(workbook)
    errors = recalc.formula_errors(workbook)
    if errors:
        sys.exit("formula errors\n" + "\n".join(errors))
    expected = extract_expected.extract(workbook, project)
    out = FIXTURES / "expected.json"
    out.write_text(json.dumps(expected, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {workbook.name} and {out.name} – zero formula errors")


if __name__ == "__main__":
    main()
