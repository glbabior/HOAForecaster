"""Resolve a scenario's dues path to a dues-per-unit-per-month figure for every year."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from hoa_engine.model import DuesMode, Rounding, Scenario


def resolve_dues(scenario: Scenario, years: range) -> dict[int, Decimal]:
    """Dues per unit per month for each year.

    EXPLICIT – the typed values. RATE – the first-year value grown each year by the
    increase of that year's period (spec 5.1); a pinned year takes its typed value and
    later years grow from it. Rounding applies only to grown values, never to typed ones,
    and each year is rounded from the unrounded growth (so rounding never compounds).
    """
    path = scenario.dues
    if path.mode is DuesMode.EXPLICIT:
        return {y: path.explicit[y] for y in years}
    anchor_value = path.first_value
    # the growth since the anchor, a power per run of equal rates – exactly what one rate
    # over the whole run gives
    done = Decimal(1)  # the runs finished since the anchor
    rate, run = None, 0  # the run in progress
    resolved = {}
    for y in years:
        if y in path.overrides:
            anchor_value, done, rate, run = path.overrides[y], Decimal(1), None, 0
            resolved[y] = anchor_value
        elif y == years.start:
            resolved[y] = anchor_value
        else:
            this = path.rate_in(y)
            assert this is not None  # validate_scenario guarantees one period a year
            if this != rate:
                done *= (1 + rate) ** run if rate is not None else Decimal(1)
                rate, run = this, 0
            run += 1
            value = anchor_value * done * (1 + this) ** run
            if scenario.rounding is Rounding.DOLLAR:
                value = value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
            resolved[y] = value
    return resolved
