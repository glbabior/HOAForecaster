"""Build the demo reference workbook and its expected results.

    uv run python demo/build_reference_workbook.py

1. Exports demo/fixtures/project.json to demo/fixtures/reference.xlsx with the
   app's exporter – every result a live formula. Neither this script nor the
   exporter runs the engine, so the expected figures are an independent check
   on it: spreadsheet formulas on one side, the Python engine on the other.
2. Recalculates the workbook in LibreOffice headless (tools/recalc.py).
3. Extracts the cached values to demo/fixtures/expected.json
   (tools/extract_expected.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hoa_engine.model import project_from_dict
from hoa_workbook.export import export_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_expected  # noqa: E402
import recalc  # noqa: E402

FIXTURES = ROOT / "demo" / "fixtures"


def main() -> None:
    raw = json.loads((FIXTURES / "project.json").read_text(encoding="utf-8"))
    workbook = FIXTURES / "reference.xlsx"
    export_workbook(project_from_dict(raw), workbook)
    recalc.recalc(workbook)
    errors = recalc.formula_errors(workbook)
    if errors:
        sys.exit("formula errors\n" + "\n".join(errors))
    expected = extract_expected.extract(workbook, raw)
    out = FIXTURES / "expected.json"
    out.write_text(json.dumps(expected, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {workbook.name} and {out.name} – zero formula errors")


if __name__ == "__main__":
    main()
