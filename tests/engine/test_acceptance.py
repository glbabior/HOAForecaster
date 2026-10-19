"""Acceptance tests (spec section 9).

Each fixture set is a project.json plus an expected.json extracted from a
workbook that Excel or LibreOffice recalculated from its own formulas. The demo
set is always present; the private set runs when HOA_DATA_DIR points at the
private data repository.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hoa_engine import baseline_from_dict, run, scenario_from_dict

ROOT = Path(__file__).resolve().parents[2]
MONEY_TOLERANCE = Decimal("0.005")  # half a cent
RATIO_TOLERANCE = Decimal("1e-9")
RATIO_FIELDS = {"percent_funded", "pf_y4", "pf_y9", "pf_end"}


def _fixture_dirs() -> list[Any]:
    dirs = [pytest.param(ROOT / "demo" / "fixtures", id="demo")]
    data_dir = os.environ.get("HOA_DATA_DIR")
    if data_dir:
        dirs.append(pytest.param(Path(data_dir) / "fixtures", id="private"))
    else:
        dirs.append(
            pytest.param(None, id="private", marks=pytest.mark.skip(reason="HOA_DATA_DIR not set"))
        )
    return dirs


def _cases() -> list[Any]:
    cases = []
    for p in _fixture_dirs():
        (fixture_dir,) = p.values
        if fixture_dir is None:
            cases.append(pytest.param(None, None, None, id=p.id, marks=p.marks))
            continue
        if not (fixture_dir / "expected.json").exists():
            cases.append(pytest.param(None, None, None, id=f"{p.id}-missing"))
            continue
        project = json.loads((fixture_dir / "project.json").read_text(encoding="utf-8"))
        expected = json.loads((fixture_dir / "expected.json").read_text(encoding="utf-8"))
        for s in project["scenarios"]:
            cases.append(
                pytest.param(
                    project["baseline"],
                    s,
                    expected["scenarios"][s["name"]],
                    id=f"{p.id}-{s['name']}",
                )
            )
    return cases


def _close(field: str, actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or expected is None or isinstance(expected, int):
        return bool(actual == expected)
    tolerance = RATIO_TOLERANCE if field in RATIO_FIELDS else MONEY_TOLERANCE
    return abs(Decimal(str(actual)) - Decimal(expected)) <= tolerance


@pytest.mark.parametrize(("baseline", "scenario", "expected"), _cases())
def test_matches_reference_workbook(
    baseline: dict[str, Any], scenario: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert baseline is not None, "fixture set is missing project.json or expected.json"
    result = run(baseline_from_dict(baseline), scenario_from_dict(scenario))
    mismatches = []
    by_year = {y.year: y for y in result.years}
    assert sorted(by_year) == sorted(int(y) for y in expected["years"])
    for year, fields in expected["years"].items():
        for field, value in fields.items():
            actual = getattr(by_year[int(year)], field)
            if not _close(field, actual, value):
                mismatches.append(f"{year} {field}: engine {actual} vs workbook {value}")
    for field, value in expected["summary"].items():
        actual = getattr(result.summary, field)
        if not _close(field, actual, value):
            mismatches.append(f"summary {field}: engine {actual} vs workbook {value}")
    assert not mismatches, "\n".join(mismatches)
