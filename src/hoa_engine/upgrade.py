"""Older project files in today's form, with the same figures (spec 8.2).

Schema 1 had a single operating-expense figure; schema 2 had one baseline per project, with
each scenario holding only its changes to it (and an adopted plan a frozen copy). Schema 3
gives every scenario all of its own inputs. These work on the JSON form, before it is read,
with the model's own field readers – the same checks as a schema 3 file.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from hoa_engine.model import (
    LIMITS,
    ExpenseLine,
    Facts,
    _dec,
    _int,
    _line_id,
    _sources,
    _str,
    _year_map,
    expense_line_from_dict,
    facts_from_dict,
    facts_to_dict,
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
                    "annual_increase": "0",
                },
                "assessments": [],
                "rounding": "dollar",
            }
        )
    rest = {k: v for k, v in d.items() if k not in ("baseline", "scenarios")}
    return {**rest, "scenarios": scenarios}
