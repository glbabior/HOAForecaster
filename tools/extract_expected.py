"""Read expected results out of a recalculated workbook in the reference layout.

The workbook's cached values – computed by Excel or LibreOffice from its own
formulas, not by this app's engine – become the acceptance fixtures.

    python tools/extract_expected.py WORKBOOK.xlsx PROJECT.json OUT.json

Plan sheets are matched to the project's scenarios by name. Rows are matched by
label, so the extractor reads both the reference workbook and the demo
workbook. Years outside the project's horizon (a partial first year) are skipped.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import openpyxl

# label prefix → engine field
PLAN_ROWS = [
    ("Dues per unit per month", "dues"),
    ("Special assessment per unit", "assessment_per_unit"),
    ("Total dues collected", "total_dues"),
    ("Operating expenses", "operating"),
    ("Reserve contribution from dues", "contribution"),
    ("Special assessment to reserves", "assessment"),
    ("Total collected from owners", "total_from_owners"),
    ("Interest earned", "interest"),
    ("Reserve expenses", "expenses"),
    ("Starting reserve balance", "starting_balance"),
    ("Ending reserve balance", "ending_balance"),
    ("Fully Funded Balance", "ffb_next"),
    ("Percent funded at year end", "percent_funded"),
    ("Below minimum cushion?", "low_flag"),
    ("Meets percent-funded target?", "target_met"),
    ("Needs owner vote?", "needs_vote"),
    ("Operating shortfall?", "operating_shortfall"),
    ("Owner cost – dues per unit per year", "owner_dues_year"),
    ("Owner cost – dues + assessment", "owner_cost_year"),
    ("Increase vs", "dues_increase_vs_current"),
    ("Cumulative owner cost", "cumulative_owner_cost"),
    ("Cumulative extra cost", "cumulative_extra"),
    ("Extra vs current dues", "extra_vs_current"),
]
FLAG_TRUE = {
    "low_flag": "LOW",
    "target_met": "yes",
    "needs_vote": "yes",
    "operating_shortfall": "yes",
}


def _num(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"expected a number, got {value!r}")
    return repr(value)


def _plan(ws: Any, years: range) -> dict[str, dict[str, Any]]:
    header = {ws.cell(4, c).value: c for c in range(2, ws.max_column + 1)}
    out: dict[str, dict[str, Any]] = {str(y): {} for y in years}
    for r in range(5, ws.max_row + 1):
        label = ws.cell(r, 1).value
        if not isinstance(label, str):
            continue
        key = next((k for prefix, k in PLAN_ROWS if label.startswith(prefix)), None)
        if key is None:
            continue
        for y in years:
            v = ws.cell(r, header[y]).value
            out[str(y)][key] = (v == FLAG_TRUE[key]) if key in FLAG_TRUE else _num(v)
    return out


def _summary(ws: Any, plan_col: int, start: int, end: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    dues_points = iter(["dues_y1", "dues_y4", "dues_y9"])
    point = {start + 3: "y4", start + 8: "y9", end: "end"}
    for r in range(5, ws.max_row + 1):
        label = ws.cell(r, 1).value
        if not isinstance(label, str) or label.startswith("Year-end"):
            break
        v = ws.cell(r, plan_col).value
        # a "start–end" range, else a single trailing year – never a dollar figure in the label
        span = re.search(r"\b((?:19|20)\d\d)–((?:19|20)\d\d)\b", label)
        single = re.search(r"\b((?:19|20)\d\d)$", label)
        years = [int(y) for y in span.groups()] if span else [int(single[1])] if single else []
        if label.startswith("Dues per unit per month"):
            out[next(dues_points)] = _num(v)
        elif label.startswith("Special assessments per unit"):
            out["total_assessments"] = _num(v)
        elif label.startswith("Year of lowest"):
            out["lowest_balance_year"] = int(v)
        elif label.startswith("Lowest year-end"):
            out["lowest_balance"] = _num(v)
        elif label.startswith("Years below minimum cushion"):
            out["low_years"] = int(v)
        elif label.startswith("Years needing an owner vote"):
            out["vote_years"] = int(v)
        elif label.startswith("Years with an operating shortfall"):
            out["shortfall_years"] = int(v)
        elif label.startswith("Reserve balance end of"):
            out[f"balance_{point[years[0]]}"] = _num(v)
        elif label.startswith("Percent funded end of"):
            out[f"pf_{point[years[0]]}"] = _num(v)
        elif label.startswith("First year percent-funded target"):
            out["first_target_year"] = v if isinstance(v, int | float) else None
        elif label.startswith("Owner outlay per unit"):
            out["outlay_total" if years[1] == end else "outlay_first5"] = _num(v)
        elif label.startswith("Extra cost vs"):
            out["extra_total" if years[1] == end else "extra_first4"] = _num(v)
        elif label.startswith("Average owner cost"):
            out["avg_owner_cost"] = _num(v)
        elif label.startswith("Average extra cost"):
            out["avg_extra"] = _num(v)
    if isinstance(out.get("first_target_year"), float):
        out["first_target_year"] = int(out["first_target_year"])
    return out


def extract(workbook: Path, project: dict[str, Any]) -> dict[str, Any]:
    wb = openpyxl.load_workbook(workbook, data_only=True)
    start, end = project["baseline"]["start_year"], project["baseline"]["end_year"]
    compare = wb["Compare"]
    columns = {compare.cell(4, c).value: c for c in range(2, compare.max_column + 1)}
    scenarios = {}
    for s in project["scenarios"]:
        name = s["name"]
        scenarios[name] = {
            "years": _plan(wb[name], range(start, end + 1)),
            "summary": _summary(compare, columns[name], start, end),
        }
    return {"workbook": workbook.name, "scenarios": scenarios}


def main() -> None:
    workbook, project_path, out_path = (Path(a) for a in sys.argv[1:4])
    project = json.loads(project_path.read_text(encoding="utf-8"))
    result = extract(workbook, project)
    out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
