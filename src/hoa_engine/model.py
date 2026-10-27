"""Scenario inputs, and their JSON form.

Money and rates are `Decimal` in memory and decimal strings in JSON, never
binary floats. Rates and percentages are fractions (0.03 means 3%).
"""

from __future__ import annotations

import functools
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
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
    inflation: Decimal | None = None  # operating lines – their own rate; None, the scenario's
    id: str = ""  # stable, and kept when the scenario is copied
    useful_life: int | None = None  # once lines – years between replacements, for the FFB

    @property
    def life(self) -> int | None:
        """The years between this component's replacements (spec 4.1) – an every-few-years
        line's interval, a once line's own useful life; None for operating lines."""
        if self.frequency is Frequency.EVERY:
            return self.interval
        return self.useful_life if self.frequency is Frequency.ONCE else None


@dataclass(frozen=True)
class Facts:
    """A scenario's facts and assumptions (spec section 4)."""

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
    # True – the Fully Funded Balance is worked out from the expenses' useful lives (spec 4.2);
    # the typed figures in `ffb` are kept but not used
    ffb_from_lines: bool = False

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


LIMITS = ("max_dues_increase", "max_assessment_share")  # None is "no limit"


@dataclass(frozen=True)
class Adoption:
    """The board's adoption of a scenario (spec 5.2) – the plan is read-only from then on."""

    adopted_on: date  # as entered – the board's date, not the order of adoption
    note: str
    sequence: int  # adoption order; the highest is the current adopted plan


@dataclass(frozen=True)
class Scenario:
    name: str
    facts: Facts
    dues: DuesPath
    assessments: tuple[Assessment, ...] = ()
    rounding: Rounding = Rounding.DOLLAR
    description: str = ""
    adoption: Adoption | None = None


def current_adoption(scenarios: tuple[Scenario, ...]) -> Scenario | None:
    """The current adopted plan – the one adopted most recently (spec 5.2)."""
    adopted = [s for s in scenarios if s.adoption is not None]
    return max(adopted, key=lambda s: s.adoption.sequence if s.adoption else 0, default=None)


SCHEMA_VERSION = 3


@dataclass(frozen=True)
class Project:
    name: str
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


# lower case, starting with a letter – so a spreadsheet can never read one as a number or a
# pattern, and two ids never match by case
LINE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


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
        useful_life=_opt_int(e.get("useful_life")) if frequency is Frequency.ONCE else None,
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
    if e.frequency is Frequency.ONCE:
        out["useful_life"] = e.useful_life
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


@_reading("set of facts and assumptions")
def facts_from_dict(d: dict[str, Any]) -> Facts:
    return Facts(
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
        ffb_from_lines=_bool(d.get("ffb_from_lines", False)),
    )


def facts_to_dict(b: Facts) -> dict[str, Any]:
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
        "ffb_from_lines": b.ffb_from_lines,
    }


@_reading("scenario")
def scenario_from_dict(d: dict[str, Any]) -> Scenario:
    dues = d["dues"]
    return Scenario(
        name=_str(d["name"]),
        description=_str(d.get("description", "")),
        facts=facts_from_dict(d["facts"]),
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
        adoption=_adoption(d.get("adoption")),
    )


def _adoption(d: Any) -> Adoption | None:
    if d is None:
        return None
    if not isinstance(d, dict):
        raise TypeError("an adoption should be an object")
    sequence = _int(d["sequence"])
    if not 1 <= sequence <= MAX_ADOPTIONS:
        raise ValueError(f"an adoption's order must be 1 to {MAX_ADOPTIONS:,}")
    note = _str(d.get("note", ""))
    if len(note) > MAX_NOTE:
        raise ValueError(f"an adoption note may be at most {MAX_NOTE:,} characters")
    return Adoption(
        adopted_on=adoption_date(_str(d["date"])),
        note=note,
        sequence=sequence,
    )


MAX_NOTE = 2000  # characters in an adoption note
MAX_ADOPTIONS = 10_000
MAX_SCENARIOS = 200  # in a project – far beyond any board's choices
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def adoption_date(text: str) -> date:
    """A date written YYYY-MM-DD – the one form the app writes."""
    if not _ISO_DATE.fullmatch(text):
        raise ValueError(f"{text[:20]!r} is not a date written YYYY-MM-DD")
    return date.fromisoformat(text)


def adoption_to_dict(a: Adoption) -> dict[str, Any]:
    return {
        "date": a.adopted_on.isoformat(),
        "note": a.note,
        "sequence": a.sequence,
    }


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
        "facts": facts_to_dict(s.facts),
        "dues": dues,
        "assessments": [
            {"year": a.year, "amount": str(a.amount), "note": a.note} for a in s.assessments
        ],
        "rounding": s.rounding.value,
        "adoption": None if s.adoption is None else adoption_to_dict(s.adoption),
    }


@_reading("project")
def project_from_dict(d: dict[str, Any]) -> Project:
    from hoa_engine.upgrade import upgrade_v1_baseline, upgrade_v2_project

    version = _int(d.get("schema_version", SCHEMA_VERSION))
    raw_scenarios = d.get("scenarios", [])
    if isinstance(raw_scenarios, list) and len(raw_scenarios) > MAX_SCENARIOS:
        raise ValueError(f"a project may have at most {MAX_SCENARIOS} scenarios")
    if version == 1:
        d = {**d, "baseline": upgrade_v1_baseline(d["baseline"])}
    if version in (1, 2):
        d = upgrade_v2_project(d)
    elif version != SCHEMA_VERSION:
        raise ValueError(f"schema version {version} is not supported (expected {SCHEMA_VERSION})")
    scenarios = tuple(scenario_from_dict(s) for s in d.get("scenarios", []))
    names = [s.name for s in scenarios]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(
            "scenario names must be unique – " + ", ".join(repr(n) for n in duplicates)
        )
    orders = [s.adoption.sequence for s in scenarios if s.adoption is not None]
    if len(set(orders)) != len(orders):
        raise ValueError("two adopted plans have the same adoption order")
    return Project(name=_str(d["name"]), notes=_str(d.get("notes", "")), scenarios=scenarios)


def project_to_dict(p: Project) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": p.name,
        "notes": p.notes,
        "scenarios": [scenario_to_dict(s) for s in p.scenarios],
    }
