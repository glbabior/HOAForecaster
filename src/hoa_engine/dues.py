"""Resolve a scenario's dues path to a dues-per-unit-per-month figure for every year."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from hoa_engine.model import DuesMode, Rounding, Scenario


def resolve_dues(scenario: Scenario, years: range) -> dict[int, Decimal]:
    """Dues per unit per month for each year.

    EXPLICIT – the typed values. RATE – the first-year value grown by the annual
    increase; a pinned year takes its typed value and later years grow from it.
    Rounding applies only to grown values, never to typed ones, and each year is
    rounded from the unrounded growth (so rounding never compounds).
    """
    path = scenario.dues
    if path.mode is DuesMode.EXPLICIT:
        return {y: path.explicit[y] for y in years}
    anchor_year, anchor_value = years.start, path.first_value
    growth = 1 + path.annual_increase
    resolved = {}
    for y in years:
        if y in path.overrides:
            anchor_year, anchor_value = y, path.overrides[y]
            resolved[y] = anchor_value
        elif y == years.start:
            resolved[y] = anchor_value
        else:
            value = anchor_value * growth ** (y - anchor_year)
            if scenario.rounding is Rounding.DOLLAR:
                value = value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
            resolved[y] = value
    return resolved
