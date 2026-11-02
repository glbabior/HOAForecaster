"""Scenario inputs, and their JSON form.

Money and rates are `Decimal` in memory and decimal strings in JSON, never
binary floats. Rates and percentages are fractions (0.03 means 3%).
"""

from __future__ import annotations

import functools
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
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
class Increase:
    """A yearly dues increase for a stretch of years (spec 5.1) – the years whose dues rise by
    `rate` over the year before; None is the scenario's start or end."""

    rate: Decimal
    first_year: int | None = None
    last_year: int | None = None

    def covers(self, year: int) -> bool:
        return (self.first_year is None or self.first_year <= year) and (
            self.last_year is None or year <= self.last_year
        )


@dataclass(frozen=True)
class DuesPath:
    mode: DuesMode
    explicit: dict[int, Decimal] = field(default_factory=dict)
    first_value: Decimal = Decimal(0)
    # RATE mode – one increase over every year, or several for stretches of years
    increases: tuple[Increase, ...] = (Increase(Decimal(0)),)
    overrides: dict[int, Decimal] = field(default_factory=dict)  # pinned years, RATE mode only

    def rate_in(self, year: int) -> Decimal | None:
        """The increase that raises `year`'s dues – None while no period, or several, cover it
        (a problem the scenario's checks name)."""
        rates = [i.rate for i in self.increases if i.covers(year)]
        return rates[0] if len(rates) == 1 else None


LIMITS = ("max_dues_increase", "max_assessment_share")  # None is "no limit"


@dataclass(frozen=True)
class Adoption:
    """The board's adoption of a scenario (spec 5.2) – the plan is read-only from then on."""

    adopted_on: date  # as entered – the board's date, not the order of adoption
    note: str
    sequence: int  # adoption order; the highest is the current adopted plan
    # the expense set the frozen expenses came from when it was adopted, and whether they had
    # been edited since it was loaded
    expenses_from: str | None = None
    expenses_edited: bool = False


@dataclass(frozen=True)
class Scenario:
    name: str
    # None – the project's facts (spec 3); an adopted plan's own, frozen when it was adopted
    facts: Facts | None
    dues: DuesPath
    assessments: tuple[Assessment, ...] = ()
    rounding: Rounding = Rounding.DOLLAR
    description: str = ""
    adoption: Adoption | None = None


def current_adoption(scenarios: tuple[Scenario, ...]) -> Scenario | None:
    """The current adopted plan – the one adopted most recently (spec 5.2)."""
    adopted = [s for s in scenarios if s.adoption is not None]
    return max(adopted, key=lambda s: s.adoption.sequence if s.adoption else 0, default=None)


SCHEMA_VERSION = 4

# the source notes that belong with the expenses, and so travel with an expense set
EXPENSE_SOURCES = ("ffb", "expense_base_year")


@dataclass(frozen=True)
class ExpenseSet:
    """A named, saved copy of the project's expenses (spec 4.3) – its lines, its Fully Funded
    Balance (typed or worked out) and the base year whose dollars the amounts are in."""

    name: str
    expense_lines: tuple[ExpenseLine, ...]
    expense_base_year: int
    ffb: dict[int, Decimal]
    ffb_from_lines: bool = False
    sources: dict[str, str] = field(default_factory=dict)  # the notes on the FFB and base year
    # the reserve inflation the set was saved with – for information, so loading it under
    # another rate can say so (a study states its dollars and its inflation together)
    saved_inflation: Decimal | None = None


def expenses_of(facts: Facts, name: str = "") -> ExpenseSet:
    """The expense parts of a set of facts, as a set named `name` – an operating line's blank
    first year (the start year) written as that year, so the set means the same figures
    whenever it is loaded (spec 4.3)."""
    return ExpenseSet(
        name=name,
        expense_lines=tuple(
            replace(line, year=facts.start_year)
            if line.frequency.operating and line.year is None
            else line
            for line in facts.expense_lines
        ),
        expense_base_year=facts.expense_base_year,
        ffb=dict(facts.ffb),
        ffb_from_lines=facts.ffb_from_lines,
        sources={k: v for k, v in facts.sources.items() if k in EXPENSE_SOURCES},
        saved_inflation=facts.expense_inflation,
    )


def with_expenses(facts: Facts, expenses: ExpenseSet) -> Facts:
    """`facts` with a set's expenses loaded in place of their own – every other fact as it was,
    and the Fully Funded Balance years the set lacks kept (spec 4.3)."""
    kept = {k: v for k, v in facts.sources.items() if k not in EXPENSE_SOURCES}
    return replace(
        facts,
        expense_lines=expenses.expense_lines,
        expense_base_year=expenses.expense_base_year,
        ffb={**facts.ffb, **expenses.ffb},
        ffb_from_lines=expenses.ffb_from_lines,
        sources={**kept, **expenses.sources},
    )


def same_set(a: ExpenseSet, b: ExpenseSet) -> bool:
    """The same expenses, whatever the sets are called, the order of their lines or the
    inflation they were saved with (spec 4.3)."""

    def key(s: ExpenseSet) -> ExpenseSet:
        lines = tuple(sorted(s.expense_lines, key=lambda line: line.id))
        return replace(s, name="", expense_lines=lines, saved_inflation=None)

    return key(a) == key(b)


def same_expenses(a: Facts, b: Facts) -> bool:
    return same_set(expenses_of(a), expenses_of(b))


def blank_facts(start_year: int) -> Facts:
    """A project's facts before any are entered – the spec's defaults (section 4) – 14 years from
    `start_year`, 3% inflation, 2% interest, a 70% target and the vote limits; amounts zero."""
    end = start_year + 13
    return Facts(
        start_year=start_year,
        end_year=end,
        starting_balance=Decimal(0),
        expense_lines=(),
        expense_inflation=Decimal("0.03"),
        expense_base_year=start_year - 1,
        ffb={y: Decimal(0) for y in range(start_year, end + 2)},
        operating_inflation=Decimal("0.03"),
        interest_rate=Decimal("0.02"),
        units=1,
        current_dues=Decimal(0),
        cushion=Decimal(0),
        target=Decimal("0.7"),
    )


@dataclass(frozen=True)
class Project:
    """One building – its facts and expenses, shared by every scenario that is not an adopted
    plan, its saved expense sets and its funding scenarios (spec 3)."""

    name: str
    facts: Facts
    scenarios: tuple[Scenario, ...] = ()
    notes: str = ""
    expense_sets: tuple[ExpenseSet, ...] = ()
    expenses_from: str | None = None  # the set the expenses were loaded from, if any
    expenses_edited: bool = False  # and whether they have been edited since

    def runnable(self, s: Scenario) -> Scenario:
        """The scenario with the facts it runs on – the project's, or an adopted plan's own."""
        return s if s.facts is not None else replace(s, facts=self.facts)

    def runnable_scenarios(self) -> tuple[Scenario, ...]:
        return tuple(self.runnable(s) for s in self.scenarios)


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


def _reading(kind: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Turn any failure while reading a project file into one plain-language error."""

    def wrap(read: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(read)
        def reader(d: dict[str, Any], *args: Any) -> T:
            try:
                return read(d, *args)
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
        facts=None if d.get("facts") is None else facts_from_dict(d["facts"]),
        dues=DuesPath(
            mode=DuesMode(dues["mode"]),
            explicit=_year_map(dues.get("explicit", {})),
            first_value=_dec(dues.get("first_value", 0)),
            increases=_increases(dues),
            overrides=_year_map(dues.get("overrides", {})),
        ),
        assessments=tuple(
            Assessment(year=_int(a["year"]), amount=_dec(a["amount"]), note=_str(a.get("note", "")))
            for a in d.get("assessments", [])
        ),
        rounding=Rounding(d.get("rounding", Rounding.DOLLAR)),
        adoption=_adoption(d.get("adoption")),
    )


MAX_INCREASES = 100  # yearly dues increases in a scenario – one a year over the longest horizon


def _increases(dues: dict[str, Any]) -> tuple[Increase, ...]:
    """A grown path's yearly increases – or, in a file written before they had periods, its one
    `annual_increase` over every year."""
    if "increases" not in dues:
        return (Increase(_dec(dues.get("annual_increase", 0))),)
    raw = dues["increases"]
    if not isinstance(raw, list) or not all(isinstance(i, dict) for i in raw):
        raise TypeError("the yearly dues increases should be a list")
    if len(raw) > MAX_INCREASES:
        raise ValueError(f"a scenario may have at most {MAX_INCREASES} yearly dues increases")
    return tuple(
        Increase(
            rate=_dec(i["rate"]),
            first_year=_opt_int(i.get("first_year")),
            last_year=_opt_int(i.get("last_year")),
        )
        for i in raw
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
    expenses_from = d.get("expenses_from")
    return Adoption(
        adopted_on=adoption_date(_str(d["date"])),
        note=note,
        sequence=sequence,
        expenses_from=None if expenses_from is None else _set_name(expenses_from),
        expenses_edited=expenses_from is not None and _bool(d.get("expenses_edited", False)),
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
        "expenses_from": a.expenses_from,
        "expenses_edited": a.expenses_edited,
    }


MAX_SETS = 200  # expense sets in a project
MAX_SET_NAME = 100  # characters


def _set_name(value: Any) -> str:
    name = _str(value)
    if not name.strip():
        raise ValueError("an expense set needs a name")
    if len(name) > MAX_SET_NAME:
        raise ValueError(f"an expense set's name may be at most {MAX_SET_NAME} characters")
    return name


@_reading("expense set")
def expense_set_from_dict(d: dict[str, Any]) -> ExpenseSet:
    sources = _sources(d.get("sources", {}))
    return ExpenseSet(
        name=_set_name(d["name"]),
        expense_lines=_expense_lines(d.get("expense_lines", [])),
        expense_base_year=_int(d["expense_base_year"]),
        ffb=_year_map(d["ffb"]),
        ffb_from_lines=_bool(d.get("ffb_from_lines", False)),
        sources={k: v for k, v in sources.items() if k in EXPENSE_SOURCES},
        saved_inflation=_opt_dec(d.get("saved_inflation")),
    )


def expense_set_to_dict(s: ExpenseSet) -> dict[str, Any]:
    return {
        "name": s.name,
        "expense_lines": [{"id": e.id, **expense_line_to_dict(e)} for e in s.expense_lines],
        "expense_base_year": s.expense_base_year,
        "ffb": _year_map_out(s.ffb),
        "ffb_from_lines": s.ffb_from_lines,
        "sources": dict(s.sources),
        "saved_inflation": None if s.saved_inflation is None else str(s.saved_inflation),
    }


def scenario_to_dict(s: Scenario) -> dict[str, Any]:
    dues: dict[str, Any] = {"mode": s.dues.mode.value}
    if s.dues.mode is DuesMode.EXPLICIT:
        dues["explicit"] = _year_map_out(s.dues.explicit)
    else:
        dues["first_value"] = str(s.dues.first_value)
        dues["increases"] = [
            {"first_year": i.first_year, "last_year": i.last_year, "rate": str(i.rate)}
            for i in s.dues.increases
        ]
        dues["overrides"] = _year_map_out(s.dues.overrides)
    return {
        "name": s.name,
        "description": s.description,
        "facts": None if s.facts is None else facts_to_dict(s.facts),
        "dues": dues,
        "assessments": [
            {"year": a.year, "amount": str(a.amount), "note": a.note} for a in s.assessments
        ],
        "rounding": s.rounding.value,
        "adoption": None if s.adoption is None else adoption_to_dict(s.adoption),
    }


def _scenarios(d: dict[str, Any]) -> tuple[Scenario, ...]:
    raw = d.get("scenarios", [])
    if not isinstance(raw, list):
        raise TypeError("scenarios should be a list")
    scenarios = tuple(scenario_from_dict(s) for s in raw)
    names = [s.name for s in scenarios]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(
            "scenario names must be unique – " + ", ".join(repr(n) for n in duplicates)
        )
    orders = [s.adoption.sequence for s in scenarios if s.adoption is not None]
    if len(set(orders)) != len(orders):
        raise ValueError("two adopted plans have the same adoption order")
    return scenarios


def _expense_sets(raw: Any) -> tuple[ExpenseSet, ...]:
    if not isinstance(raw, list):
        raise TypeError("expense sets should be a list")
    if len(raw) > MAX_SETS:
        raise ValueError(f"a project may have at most {MAX_SETS} expense sets")
    sets = tuple(expense_set_from_dict(s) for s in raw)
    names = [s.name for s in sets]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(
            "expense set names must be unique – " + ", ".join(repr(n) for n in duplicates)
        )
    return sets


def check_project(p: Project) -> None:
    """What a project must be, however it was made – raises ValueError."""
    for s in p.scenarios:
        if s.adoption is not None and s.facts is None:
            raise ValueError(
                f"the adopted plan {s.name!r} is missing the facts it was adopted with"
            )
        if s.adoption is None and s.facts is not None:
            raise ValueError(
                f"{s.name!r} has facts of its own – only an adopted plan keeps its own"
            )
    if p.expenses_from is not None and p.expenses_from not in {e.name for e in p.expense_sets}:
        raise ValueError(f"the expenses came from {p.expenses_from!r}, which is not a saved set")
    if p.expenses_edited and p.expenses_from is None:
        raise ValueError("expenses from no set cannot have been edited since it was loaded")


def read_project(d: dict[str, Any], report: bool = True) -> tuple[Project, list[str]]:
    """A project file of any schema, in today's form – with, for an older file, what the upgrade
    changed (spec 8.2), in plain sentences (none when `report` is false – working out whether
    figures change runs the engine)."""
    return _read_project(d, report)


@_reading("project")
def _read_project(d: dict[str, Any], report: bool) -> tuple[Project, list[str]]:
    from hoa_engine.upgrade import upgrade_v1_baseline, upgrade_v2_project, upgrade_v3_project

    version = _int(d.get("schema_version", SCHEMA_VERSION))
    raw_scenarios = d.get("scenarios", [])
    if isinstance(raw_scenarios, list) and len(raw_scenarios) > MAX_SCENARIOS:
        raise ValueError(f"a project may have at most {MAX_SCENARIOS} scenarios")
    if version == 1:
        d = {**d, "baseline": upgrade_v1_baseline(d["baseline"])}
    if version in (1, 2):
        d = upgrade_v2_project(d)
    if version in (1, 2, 3):
        return upgrade_v3_project(
            _str(d["name"]), _str(d.get("notes", "")), _scenarios(d), report=report
        )
    if version != SCHEMA_VERSION:
        raise ValueError(f"schema version {version} is not supported (expected {SCHEMA_VERSION})")
    expenses_from = d.get("expenses_from")
    project = Project(
        name=_str(d["name"]),
        notes=_str(d.get("notes", "")),
        facts=facts_from_dict(d["facts"]),
        scenarios=_scenarios(d),
        expense_sets=_expense_sets(d.get("expense_sets", [])),
        expenses_from=None if expenses_from is None else _set_name(expenses_from),
        expenses_edited=_bool(d.get("expenses_edited", False)),
    )
    check_project(project)
    return project, []


def project_from_dict(d: dict[str, Any]) -> Project:
    """The project alone – an older file's upgrade report is not wanted, so not worked out."""
    return read_project(d, report=False)[0]


def project_to_dict(p: Project) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": p.name,
        "notes": p.notes,
        "facts": facts_to_dict(p.facts),
        "expense_sets": [expense_set_to_dict(e) for e in p.expense_sets],
        "expenses_from": p.expenses_from,
        "expenses_edited": p.expenses_edited,
        "scenarios": [scenario_to_dict(s) for s in p.scenarios],
    }
