"""The exporter never computes results – its formulas are the independent check on the engine."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "hoa_workbook"
ALLOWED = {"hoa_engine.model", "hoa_engine.validate"}  # inputs and their checks only


def test_workbook_package_imports_only_the_engines_model() -> None:
    for path in PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("hoa_engine")
            ):
                assert node.module in ALLOWED, f"{path.name} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("hoa_engine") or alias.name in ALLOWED, (
                        path.name
                    )
