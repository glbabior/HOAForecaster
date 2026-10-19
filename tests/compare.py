"""Compare engine results with figures read from a recalculated workbook."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from hoa_engine import ScenarioResult

MONEY_TOLERANCE = Decimal("0.005")  # half a cent
RATIO_TOLERANCE = Decimal("1e-9")
RATIO_FIELDS = {"percent_funded", "pf_y4", "pf_y9", "pf_end"}


def _close(field: str, actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or expected is None or isinstance(expected, int):
        return bool(actual == expected)
    tolerance = RATIO_TOLERANCE if field in RATIO_FIELDS else MONEY_TOLERANCE
    return abs(Decimal(str(actual)) - Decimal(expected)) <= tolerance


def mismatches(result: ScenarioResult, expected: dict[str, Any]) -> list[str]:
    """Every field where the engine and the workbook disagree, as readable lines."""
    by_year = {y.year: y for y in result.years}
    out = []
    if sorted(by_year) != sorted(int(y) for y in expected["years"]):
        return [f"years differ: engine {sorted(by_year)} vs workbook {sorted(expected['years'])}"]
    for year, fields in expected["years"].items():
        for field, value in fields.items():
            actual = getattr(by_year[int(year)], field)
            if not _close(field, actual, value):
                out.append(f"{year} {field}: engine {actual} vs workbook {value}")
    for field, value in expected["summary"].items():
        actual = getattr(result.summary, field)
        if not _close(field, actual, value):
            out.append(f"summary {field}: engine {actual} vs workbook {value}")
    return out
