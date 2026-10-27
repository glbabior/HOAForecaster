"""Acceptance tests (spec section 9).

Each fixture set is a project.json plus an expected.json extracted from a
workbook that Excel or LibreOffice recalculated from its own formulas. The demo
set is always present; the private set runs when HOA_PRIVATE_DIR points at the
private data repository.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from hoa_engine import project_from_dict, run
from tests.compare import mismatches

ROOT = Path(__file__).resolve().parents[2]


def _fixture_dirs() -> list[Any]:
    dirs = [pytest.param(ROOT / "demo" / "fixtures", id="demo")]
    data_dir = os.environ.get("HOA_PRIVATE_DIR")
    if data_dir:
        dirs.append(pytest.param(Path(data_dir) / "fixtures", id="private"))
    else:
        dirs.append(
            pytest.param(
                None, id="private", marks=pytest.mark.skip(reason="HOA_PRIVATE_DIR not set")
            )
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
                    project,
                    s["name"],
                    expected["scenarios"][s["name"]],
                    id=f"{p.id}-{s['name']}",
                )
            )
    return cases


@pytest.mark.parametrize(("raw", "name", "expected"), _cases())
def test_matches_reference_workbook(
    raw: dict[str, Any], name: str, expected: dict[str, Any]
) -> None:
    assert raw is not None, "fixture set is missing project.json or expected.json"
    # the whole project file, so an older schema goes through its upgrade (spec 8.2)
    project = project_from_dict(raw)
    scenario = next(s for s in project.scenarios if s.name == name)
    result = run(scenario)
    problems = mismatches(result, expected)
    assert not problems, "\n".join(problems)
