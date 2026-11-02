"""Older project files in today's form (spec 8.2).

Schema 1 had a single operating-expense figure; schema 2 had one baseline per project, with
each scenario holding only its changes to it (and an adopted plan a frozen copy). Schema 3
gave every scenario all of its own inputs; schema 4 gives them back to the project, with each
scenario's own expenses saved as a set. The schema 1 and 2 upgrades work on the JSON form,
before it is read, with the model's own field readers and the same figures; the schema 3
upgrade works on the scenarios as read, and says which scenarios' figures change.
"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import date
from typing import Any

from hoa_engine.dues import rebase_dues
from hoa_engine.model import (
    EXPENSE_SOURCES,
    LIMITS,
    MAX_SET_NAME,
    ExpenseLine,
    ExpenseSet,
    Facts,
    Project,
    Scenario,
    _dec,
    _int,
    _line_id,
    _sources,
    _str,
    _year_map,
    blank_facts,
    check_project,
    expense_line_from_dict,
    expenses_of,
    facts_from_dict,
    facts_to_dict,
    same_expenses,
    same_set,
)

OPERATING_LINE_ID = "operating"
_YEAR_VALUES = ("start_year", "end_year", "expense_base_year", "units")
_CHANGEABLE = (
    "start_year",
    "end_year",
    "starting_balance",
    "units",
    "current_dues",
    "operating_inflation",
    "expense_inflation",
    "expense_base_year",
    "interest_rate",
    "cushion",
    "target",
    *LIMITS,
)
NO_SCENARIOS_NAME = "Current dues"  # the scenario a schema 2 project without any is given
MAX_LINES = 1000  # a schema 2 baseline's lines, or one scenario's line changes
# lines the upgrade may write in all – each scenario gets its own copy of the baseline's, so a
# small crafted file must not grow into one too large to hold
UPGRADE_BUDGET = 50_000


SET_PREFIX = "Expenses from "

# what each fact is called in the upgrade's report – the expense parts are told apart below
_FACT_WORDS = {
    "start_year": "its years",
    "end_year": "its years",
    "starting_balance": "its starting balance",
    "units": "its number of units",
    "current_dues": "its current dues",
    "expense_inflation": "its reserve inflation rate",
    "operating_inflation": "its operating inflation rate",
    "interest_rate": "its interest rate",
    "cushion": "its cushion",
    "target": "its percent-funded target",
    "max_dues_increase": "its owner-vote limits",
    "max_assessment_share": "its owner-vote limits",
}


def _short(name: str) -> str:
    """A name as a report sentence quotes it – a long one shortened, so a sentence stays short."""
    return name if len(name) <= MAX_SET_NAME else name[: MAX_SET_NAME - 1] + "…"


def _unique(base: str, taken: set[str]) -> str:
    base = base[:MAX_SET_NAME]
    name, n = base, 2
    while name in taken:
        tail = f" ({n})"
        name, n = base[: MAX_SET_NAME - len(tail)] + tail, n + 1
    return name


def _differences(own: Facts, project: Facts) -> list[str]:
    """What a scenario's own facts had that the project's do not, in words."""
    words = [w for k, w in _FACT_WORDS.items() if getattr(own, k) != getattr(project, k)]
    notes = {k: v for k, v in own.sources.items() if k not in EXPENSE_SOURCES}
    if notes != {k: v for k, v in project.sources.items() if k not in EXPENSE_SOURCES}:
        words.append("its source notes")
    mine = {line.id: line for line in own.expense_lines}
    theirs = {line.id: line for line in project.expense_lines}
    lines = sum(mine.get(i) != theirs.get(i) for i in mine.keys() | theirs.keys())
    if lines:
        words.append("1 expense line" if lines == 1 else f"{lines} expense lines")
    elif [line.id for line in own.expense_lines] != list(theirs):
        words.append("the order of its expense lines")
    if (own.ffb, own.ffb_from_lines, own.sources.get("ffb")) != (
        project.ffb,
        project.ffb_from_lines,
        project.sources.get("ffb"),
    ):
        words.append("its Fully Funded Balance")
    if (own.expense_base_year, own.sources.get("expense_base_year")) != (
        project.expense_base_year,
        project.sources.get("expense_base_year"),
    ):
        words.append("its expense base year")
    return list(dict.fromkeys(words))  # each once, in order


def _figures(s: Scenario) -> object:
    """A scenario's figures, or its problems when it has no figures – to tell whether the
    upgrade changes them. Only the numbers – a line's words or place in the list change none."""
    from hoa_engine.engine import InvalidInputs, run

    try:
        r = run(s)
    except InvalidInputs as e:
        return e.problems
    years = [
        tuple(getattr(y, f.name) for f in fields(y) if not f.name.endswith("_lines"))
        for y in r.years
    ]
    return r.summary, r.ffb, years


def upgrade_v3_project(
    name: str, notes: str, scenarios: tuple[Scenario, ...], report: bool = True
) -> tuple[Project, list[str]]:
    """A schema 3 project in schema 4 form (spec 8.2) – the facts and expenses of its first
    scenario that is not an adopted plan become the project's, each different set of scenario
    expenses is saved as a set, and adopted plans keep theirs. Also, for each other scenario
    that had facts of its own, a sentence saying what they were and whether its figures
    change."""
    for s in scenarios:
        if s.facts is None:
            raise ValueError(f"{s.name!r} is missing its facts and assumptions")
    if not scenarios:
        return Project(name=name, notes=notes, facts=blank_facts(date.today().year + 1)), []
    own = [s.facts for s in scenarios if s.facts is not None]
    first = next((s for s in scenarios if s.adoption is None), scenarios[0]).facts
    assert first is not None  # every scenario has its facts, checked above
    sets: list[ExpenseSet] = []
    for s, f in zip(scenarios, own, strict=True):
        if not any(same_set(expenses_of(f), e) for e in sets):
            taken = {e.name for e in sets}
            sets.append(expenses_of(f, _unique(SET_PREFIX + s.name, taken)))

    def set_of(f: Facts) -> str:
        return next(e.name for e in sets if same_set(expenses_of(f), e))

    out = []
    for s, f in zip(scenarios, own, strict=True):
        if s.adoption is not None:  # keeps its own, frozen
            out.append(replace(s, adoption=replace(s.adoption, expenses_from=set_of(f))))
        else:  # the project's facts from now on, its dues carried on to their start year
            out.append(replace(rebase_dues(s, f, first.start_year), facts=None))
    project = Project(
        name=name,
        notes=notes,
        facts=first,
        scenarios=tuple(out),
        expense_sets=tuple(sets),
        expenses_from=set_of(first),
    )
    check_project(project)
    if not report:
        return project, []

    def funding(s: Scenario) -> tuple[object, ...]:
        return (s.dues, s.assessments, s.rounding)

    sentences = []
    plans = [s for s in project.scenarios if s.adoption is None]
    for before, after, f in zip(scenarios, project.scenarios, own, strict=True):
        differs = _differences(f, first) if after.adoption is None else []
        if not differs:
            continue
        changed = _figures(before) != _figures(project.runnable(after))
        parts = [
            ", ".join(differs),
            "its figures change" if changed else "its figures stay the same",
        ]
        twin = next(
            (p.name for p in plans if p is not after and funding(p) == funding(after)), None
        )
        if twin is not None:
            parts.append(f"it now matches {_short(twin)} exactly")
        sentence = f"{_short(before.name)} – " + " – ".join(parts)
        if not same_expenses(f, first):
            sentence += f" – its expenses are saved as the set '{set_of(f)}'"
            if any(w in _FACT_WORDS.values() or w == "its source notes" for w in differs):
                sentence += "; loading it does not bring back its other facts"
        sentences.append(sentence)
    return project, sentences


def upgrade_v1_baseline(d: Any) -> dict[str, Any]:
    """A schema 1 baseline in schema 2 form, with the same figures – its expense lines become
    once lines, and its start-year operating expenses one yearly line growing at the operating
    inflation rate from the start year."""
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


def _changed_value(key: str, value: Any) -> Any:
    if key not in _CHANGEABLE:
        raise ValueError(f"{key[:40]!r} is not a baseline input a scenario can change")
    if value is None:
        if key not in LIMITS:
            raise ValueError("only a governance limit can be changed to no limit")
        return None
    return _int(value) if key in _YEAR_VALUES else _dec(value)


def _with_changes(b: Facts, d: Any) -> Facts:
    """A schema 2 baseline as one scenario saw it – its changed lines in their baseline line's
    place, its own lines after them, lines it left out gone; its own values, notes and Fully
    Funded Balance years over the baseline's."""
    if not isinstance(d, dict):
        raise TypeError("a scenario's changes should be an object")
    raw_lines = d.get("expense_lines", {})
    if not isinstance(raw_lines, dict):
        raise TypeError("a scenario's expense line changes should be an object")
    if len(raw_lines) > MAX_LINES:
        raise ValueError(f"a scenario changes more than {MAX_LINES:,} expense lines")
    changed = {
        _line_id(i): None if e is None else expense_line_from_dict(e, i)
        for i, e in raw_lines.items()
    }
    values = {_str(k): _changed_value(k, v) for k, v in d.get("values", {}).items()}
    sources = {k: v for k, v in _sources(d.get("sources", {})).items() if v}
    known = {line.id for line in b.expense_lines}
    lines = [changed.get(line.id, line) for line in b.expense_lines]
    lines += [line for i, line in changed.items() if i not in known and line is not None]
    return replace(
        b,
        **values,
        expense_lines=tuple(line for line in lines if line is not None),
        ffb={**b.ffb, **_year_map(d.get("ffb", {}))},
        sources={**b.sources, **sources},
    )


def _own_ids(facts: Facts, known: set[str], own: dict[str, ExpenseLine]) -> Facts:
    """A scenario's own lines (not the baseline's) with ids no other scenario uses for a different
    line – schema 2 numbered each scenario's own lines from own-1, and ids now say which line is
    the same in two scenarios (spec 7.2). The same line copied between them keeps its id."""
    lines = []
    for line in facts.expense_lines:
        if line.id not in known:
            if line.id in own and own[line.id] != line:
                n = 1
                while f"line-{n}" in known or f"line-{n}" in own:
                    n += 1
                line = replace(line, id=f"line-{n}")
            own.setdefault(line.id, line)
        lines.append(line)
    return replace(facts, expense_lines=tuple(lines))


def upgrade_v2_project(d: dict[str, Any]) -> dict[str, Any]:
    """A schema 2 project in schema 3 form – each scenario given the baseline as it saw it (an
    adopted plan, its frozen copy), so every figure is the same."""
    raw = d.get("scenarios", [])
    if not isinstance(raw, list) or not all(isinstance(s, dict) for s in raw):
        raise TypeError("scenarios should be a list of objects")
    raw_lines = (d.get("baseline") or {}).get("expense_lines", [])
    if isinstance(raw_lines, list) and len(raw_lines) > MAX_LINES:
        raise ValueError(f"the baseline has more than {MAX_LINES:,} expense lines")
    if isinstance(raw_lines, list) and len(raw_lines) * max(len(raw), 1) > UPGRADE_BUDGET:
        raise ValueError("the project is too large to upgrade – too many scenarios and lines")
    baseline = facts_from_dict(d["baseline"])
    scenarios = []
    known = {line.id for line in baseline.expense_lines}
    own: dict[str, ExpenseLine] = {}  # a scenario's own line, by id – the first to use it
    for s in raw:
        adoption = s.get("adoption")
        if adoption is not None and not isinstance(adoption, dict):
            raise TypeError("an adoption should be an object")
        seen = baseline if adoption is None else facts_from_dict(adoption["baseline"])
        facts = _own_ids(_with_changes(seen, s.get("changes", {})), known, own)
        rest = {k: v for k, v in s.items() if k != "changes"}
        if adoption is not None:
            rest["adoption"] = {k: v for k, v in adoption.items() if k != "baseline"}
        scenarios.append({**rest, "facts": facts_to_dict(facts)})
    if not scenarios:
        scenarios.append(
            {
                "name": NO_SCENARIOS_NAME,
                "description": "",
                "facts": facts_to_dict(baseline),
                "dues": {
                    "mode": "rate",
                    "first_value": str(baseline.current_dues),
                    "increases": [{"first_year": None, "last_year": None, "rate": "0"}],
                },
                "assessments": [],
                "rounding": "dollar",
            }
        )
    rest = {k: v for k, v in d.items() if k not in ("baseline", "scenarios")}
    return {**rest, "scenarios": scenarios}
