"""Baseline and scenario inputs, and their JSON form.

Money and rates are `Decimal` in memory and decimal strings in JSON, never
binary floats. Rates and percentages are fractions (0.03 means 3%).
"""

from __future__ import annotations

import functools
import re
from collections import Counter
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


class Frequency(StrEnum):
    """How often an expense falls (spec 4.1). Monthly and yearly lines are operating
    expenses, paid from dues; once and every-few-years lines are reserve expenses."""

    MONTHLY = "monthly"
    YEARLY = "yearly"
    EVERY = "every"  # every `interval` years from `year`
    ONCE = "once"

    @property
    def operating(self) -> bool:
        return self in (Frequency.MONTHLY, Frequency.YEARLY)


@dataclass(frozen=True)
class ExpenseLine:
    """One expense. `year` is the year of a once line, the first occurrence of an
    every-few-years line, or the first year of a monthly or yearly line (None – from the
    start year). `end_year` is the last year a repeating line applies (None – to the end)."""

    year: int | None
    amount: Decimal  # per month for monthly lines, per occurrence otherwise
    description: str = ""
    nominal: bool = False  # reserve lines – the amount is already in the year's dollars
    source: str = ""
    frequency: Frequency = Frequency.ONCE
    end_year: int | None = None
    interval: int | None = None  # every-few-years lines only
    inflation: Decimal | None = None  # operating lines – their own rate; None follows the baseline
    id: str = ""  # stable, so a scenario can change or leave out this line


@dataclass(frozen=True)
class Baseline:
    start_year: int
    end_year: int
    starting_balance: Decimal
    expense_lines: tuple[ExpenseLine, ...]
    expense_inflation: Decimal
    expense_base_year: int
    ffb: dict[int, Decimal]  # Fully Funded Balance at the start of each year, start..end+1
    operating_inflation: Decimal  # the rate of operating lines that do not set their own
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


SCHEMA_VERSION = 2


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


def _opt_int(value: Any) -> int | None:
    return None if value is None else _int(value)


def _year_map(raw: dict[str, Any]) -> dict[int, Decimal]:
    return {_int(year): _dec(value) for year, value in raw.items()}


def _year_map_out(values: dict[int, Decimal]) -> dict[str, str]:
    return {str(year): str(values[year]) for year in sorted(values)}


LINE_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _line_id(value: Any) -> str:
    text = _str(value)
    if not LINE_ID.fullmatch(text):
        raise ValueError(f"{text[:40]!r} is not a usable expense line identifier")
    return text


def expense_line_from_dict(e: dict[str, Any], line_id: Any) -> ExpenseLine:
    """A line, keeping only the fields its frequency uses."""
    frequency = Frequency(e.get("frequency", Frequency.ONCE))
    return ExpenseLine(
        id=_line_id(line_id),
        frequency=frequency,
        year=_opt_int(e.get("year")),
        amount=_dec(e["amount"]),
        description=_str(e.get("description", "")),
        source=_str(e.get("source", "")),
        nominal=not frequency.operating and _bool(e.get("nominal", False)),
        end_year=None if frequency is Frequency.ONCE else _opt_int(e.get("end_year")),
        interval=_opt_int(e.get("interval")) if frequency is Frequency.EVERY else None,
        inflation=_opt_dec(e.get("inflation")) if frequency.operating else None,
    )


def expense_line_to_dict(e: ExpenseLine) -> dict[str, Any]:
    """A line without its identifier – the fields its frequency uses."""
    out: dict[str, Any] = {
        "frequency": e.frequency.value,
        "year": e.year,
        "amount": str(e.amount),
        "description": e.description,
        "source": e.source,
    }
    if e.frequency is not Frequency.ONCE:
        out["end_year"] = e.end_year
    if e.frequency is Frequency.EVERY:
        out["interval"] = e.interval
    if e.frequency.operating:
        out["inflation"] = None if e.inflation is None else str(e.inflation)
    else:
        out["nominal"] = e.nominal
    return out


def _expense_lines(raw: Any) -> tuple[ExpenseLine, ...]:
    if not isinstance(raw, list):
        raise TypeError("expense lines should be a list")
    lines = tuple(expense_line_from_dict(e, e["id"]) for e in raw)
    ids = [line.id for line in lines]
    duplicates = sorted(i for i, n in Counter(ids).items() if n > 1)
    if duplicates:
        raise ValueError("expense line identifiers must be unique – " + ", ".join(duplicates))
    return lines


@_reading("baseline")
def baseline_from_dict(d: dict[str, Any]) -> Baseline:
    return Baseline(
        start_year=_int(d["start_year"]),
        end_year=_int(d["end_year"]),
        starting_balance=_dec(d["starting_balance"]),
        expense_lines=_expense_lines(d.get("expense_lines", [])),
        expense_inflation=_dec(d["expense_inflation"]),
        expense_base_year=_int(d["expense_base_year"]),
        ffb=_year_map(d["ffb"]),
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
        "expense_lines": [{"id": e.id, **expense_line_to_dict(e)} for e in b.expense_lines],
        "expense_inflation": str(b.expense_inflation),
        "expense_base_year": b.expense_base_year,
        "ffb": _year_map_out(b.ffb),
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


OPERATING_LINE_ID = "operating"


def upgrade_v1_baseline(d: Any) -> dict[str, Any]:
    """A schema 1 baseline in schema 2 form, with the same figures (spec 8.2) – its expense
    lines become once lines, and its start-year operating expenses one yearly line growing at
    the operating inflation rate from the start year."""
    if not isinstance(d, dict):
        raise TypeError("the baseline should be an object")
    lines = d.get("expense_lines", [])
    if not isinstance(lines, list) or not all(isinstance(e, dict) for e in lines):
        raise TypeError("expense lines should be a list of objects")
    sources = _sources(d.get("sources", {}))
    upgraded = [{**e, "id": f"line-{i}", "frequency": "once"} for i, e in enumerate(lines, 1)]
    if _dec(d["operating_start"]) != 0:
        operating = {
            "id": OPERATING_LINE_ID,
            "frequency": "yearly",
            "year": None,
            "amount": d["operating_start"],
            "description": "Operating expenses",
            "source": sources.pop("operating_start", ""),
        }
        upgraded.insert(0, operating)
    else:
        sources.pop("operating_start", None)
    rest = {k: v for k, v in d.items() if k != "operating_start"}
    return {**rest, "expense_lines": upgraded, "sources": sources}


@_reading("project")
def project_from_dict(d: dict[str, Any]) -> Project:
    version = _int(d.get("schema_version", SCHEMA_VERSION))
    if version == 1:
        d = {**d, "baseline": upgrade_v1_baseline(d["baseline"])}
    elif version != SCHEMA_VERSION:
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
