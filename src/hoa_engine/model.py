"""Baseline and scenario inputs, and their JSON form.

Money and rates are `Decimal` in memory and decimal strings in JSON, never
binary floats. Rates and percentages are fractions (0.03 means 3%).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, TypeVar

T = TypeVar("T")


class DuesMode(StrEnum):
    EXPLICIT = "explicit"  # a value for every year
    RATE = "rate"  # first-year value, then a yearly increase, with optional pinned years


class Rounding(StrEnum):
    DOLLAR = "dollar"
    NONE = "none"


@dataclass(frozen=True)
class ExpenseLine:
    year: int
    amount: Decimal
    description: str = ""
    nominal: bool = False  # True – amount is already in the year's dollars, skip inflation
    source: str = ""


@dataclass(frozen=True)
class Baseline:
    start_year: int
    end_year: int
    starting_balance: Decimal
    expense_lines: tuple[ExpenseLine, ...]
    expense_inflation: Decimal
    expense_base_year: int
    ffb: dict[int, Decimal]  # Fully Funded Balance at the start of each year, start..end+1
    operating_start: Decimal  # operating expenses in the start year
    operating_inflation: Decimal
    interest_rate: Decimal
    units: int
    current_dues: Decimal  # per unit per month
    cushion: Decimal
    target: Decimal
    max_dues_increase: Decimal | None = Decimal("0.20")
    max_assessment_share: Decimal | None = Decimal("0.05")
    sources: dict[str, str] = field(default_factory=dict)  # input name → where it came from

    @property
    def years(self) -> range:
        return range(self.start_year, self.end_year + 1)


@dataclass(frozen=True)
class Assessment:
    year: int
    amount: Decimal  # per unit
    note: str = ""


@dataclass(frozen=True)
class DuesPath:
    mode: DuesMode
    explicit: dict[int, Decimal] = field(default_factory=dict)
    first_value: Decimal = Decimal(0)
    annual_increase: Decimal = Decimal(0)
    overrides: dict[int, Decimal] = field(default_factory=dict)  # pinned years, RATE mode only


@dataclass(frozen=True)
class Scenario:
    name: str
    dues: DuesPath
    assessments: tuple[Assessment, ...] = ()
    rounding: Rounding = Rounding.DOLLAR
    description: str = ""


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Project:
    name: str
    baseline: Baseline
    scenarios: tuple[Scenario, ...]
    notes: str = ""


# ---------------------------------------------------------------- JSON form


MAX_DIGITS = 15  # whole-number digits; far above any association's money, rejects absurd exponents


class ProjectFormatError(ValueError):
    """A project file that cannot be read – missing fields, wrong types, bad numbers."""


def _dec(value: Any) -> Decimal:
    if isinstance(value, float):
        raise TypeError(f"money and rates must be strings or integers, not float ({value!r})")
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise TypeError(f"expected a number written as a string, got {value!r}")
    try:
        d = Decimal(value.strip() if isinstance(value, str) else value)
    except InvalidOperation:
        raise ValueError(f"{value!r} is not a number") from None
    # check the exponent before any arithmetic – abs() of 1e999999999 overflows
    if not d.is_finite() or d.adjusted() >= MAX_DIGITS:
        raise ValueError(f"{value!r} is not a usable number")
    return d


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError(f"expected a whole number, got {value!r}")
    return int(value)


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # tab, newline, return are fine


def _str(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected text, got {value!r}")
    if _CONTROL.search(value):
        raise ValueError(f"text contains control characters – {value!r}")
    return value


def _sources(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise TypeError(f"sources should be a set of notes, got {value!r}")
    return {_str(k): _str(v) for k, v in value.items()}


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"expected true or false, got {value!r}")
    return value


def _reading(kind: str) -> Callable[[Callable[[dict[str, Any]], T]], Callable[[dict[str, Any]], T]]:
    """Turn any failure while reading a project file into one plain-language error."""

    def wrap(read: Callable[[dict[str, Any]], T]) -> Callable[[dict[str, Any]], T]:
        @functools.wraps(read)
        def reader(d: dict[str, Any]) -> T:
            try:
                return read(d)
            except KeyError as e:
                raise ProjectFormatError(f"the {kind} is missing {e.args[0]!r}") from None
            except (TypeError, ValueError, AttributeError) as e:
                raise ProjectFormatError(f"the {kind} has a bad value – {e}") from None

        return reader

    return wrap


def _opt_dec(value: Any) -> Decimal | None:
    return None if value is None else _dec(value)


def _year_map(raw: dict[str, Any]) -> dict[int, Decimal]:
    return {_int(year): _dec(value) for year, value in raw.items()}


def _year_map_out(values: dict[int, Decimal]) -> dict[str, str]:
    return {str(year): str(values[year]) for year in sorted(values)}


@_reading("baseline")
def baseline_from_dict(d: dict[str, Any]) -> Baseline:
    return Baseline(
        start_year=_int(d["start_year"]),
        end_year=_int(d["end_year"]),
        starting_balance=_dec(d["starting_balance"]),
        expense_lines=tuple(
            ExpenseLine(
                year=_int(e["year"]),
                amount=_dec(e["amount"]),
                description=_str(e.get("description", "")),
                nominal=_bool(e.get("nominal", False)),
                source=_str(e.get("source", "")),
            )
            for e in d.get("expense_lines", [])
        ),
        expense_inflation=_dec(d["expense_inflation"]),
        expense_base_year=_int(d["expense_base_year"]),
        ffb=_year_map(d["ffb"]),
        operating_start=_dec(d["operating_start"]),
        operating_inflation=_dec(d["operating_inflation"]),
        interest_rate=_dec(d["interest_rate"]),
        units=_int(d["units"]),
        current_dues=_dec(d["current_dues"]),
        cushion=_dec(d["cushion"]),
        target=_dec(d["target"]),
        max_dues_increase=_opt_dec(d.get("max_dues_increase")),
        max_assessment_share=_opt_dec(d.get("max_assessment_share")),
        sources=_sources(d.get("sources", {})),
    )


def baseline_to_dict(b: Baseline) -> dict[str, Any]:
    return {
        "start_year": b.start_year,
        "end_year": b.end_year,
        "starting_balance": str(b.starting_balance),
        "expense_lines": [
            {
                "year": e.year,
                "amount": str(e.amount),
                "description": e.description,
                "nominal": e.nominal,
                "source": e.source,
            }
            for e in b.expense_lines
        ],
        "expense_inflation": str(b.expense_inflation),
        "expense_base_year": b.expense_base_year,
        "ffb": _year_map_out(b.ffb),
        "operating_start": str(b.operating_start),
        "operating_inflation": str(b.operating_inflation),
        "interest_rate": str(b.interest_rate),
        "units": b.units,
        "current_dues": str(b.current_dues),
        "cushion": str(b.cushion),
        "target": str(b.target),
        "max_dues_increase": None if b.max_dues_increase is None else str(b.max_dues_increase),
        "max_assessment_share": (
            None if b.max_assessment_share is None else str(b.max_assessment_share)
        ),
        "sources": dict(b.sources),
    }


@_reading("scenario")
def scenario_from_dict(d: dict[str, Any]) -> Scenario:
    dues = d["dues"]
    return Scenario(
        name=_str(d["name"]),
        description=_str(d.get("description", "")),
        dues=DuesPath(
            mode=DuesMode(dues["mode"]),
            explicit=_year_map(dues.get("explicit", {})),
            first_value=_dec(dues.get("first_value", 0)),
            annual_increase=_dec(dues.get("annual_increase", 0)),
            overrides=_year_map(dues.get("overrides", {})),
        ),
        assessments=tuple(
            Assessment(year=_int(a["year"]), amount=_dec(a["amount"]), note=_str(a.get("note", "")))
            for a in d.get("assessments", [])
        ),
        rounding=Rounding(d.get("rounding", Rounding.DOLLAR)),
    )


def scenario_to_dict(s: Scenario) -> dict[str, Any]:
    dues: dict[str, Any] = {"mode": s.dues.mode.value}
    if s.dues.mode is DuesMode.EXPLICIT:
        dues["explicit"] = _year_map_out(s.dues.explicit)
    else:
        dues["first_value"] = str(s.dues.first_value)
        dues["annual_increase"] = str(s.dues.annual_increase)
        dues["overrides"] = _year_map_out(s.dues.overrides)
    return {
        "name": s.name,
        "description": s.description,
        "dues": dues,
        "assessments": [
            {"year": a.year, "amount": str(a.amount), "note": a.note} for a in s.assessments
        ],
        "rounding": s.rounding.value,
    }


@_reading("project")
def project_from_dict(d: dict[str, Any]) -> Project:
    version = _int(d.get("schema_version", SCHEMA_VERSION))
    if version != SCHEMA_VERSION:
        raise ValueError(f"schema version {version} is not supported (expected {SCHEMA_VERSION})")
    scenarios = tuple(scenario_from_dict(s) for s in d.get("scenarios", []))
    names = [s.name for s in scenarios]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(
            "scenario names must be unique – " + ", ".join(repr(n) for n in duplicates)
        )
    return Project(
        name=_str(d["name"]),
        notes=_str(d.get("notes", "")),
        baseline=baseline_from_dict(d["baseline"]),
        scenarios=scenarios,
    )


def project_to_dict(p: Project) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": p.name,
        "notes": p.notes,
        "baseline": baseline_to_dict(p.baseline),
        "scenarios": [scenario_to_dict(s) for s in p.scenarios],
    }
