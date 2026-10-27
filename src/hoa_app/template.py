"""A new, blank project or scenario with the spec's defaults (section 4) – nothing invented."""

from __future__ import annotations

from datetime import date
from typing import Any

from hoa_engine.model import Project, Scenario, project_from_dict, scenario_from_dict

FIRST_SCENARIO = "First scenario"


def _blank_scenario(name: str, today: date) -> dict[str, Any]:
    """Starts January 1 of next year (a mid-year start uses next year's opening balance) and
    runs 14 years (end = start + 13). Amounts are zero for the user to fill in."""
    start = today.year + 1
    end = start + 13
    return {
        "name": name,
        "description": "",
        "facts": {
            "start_year": start,
            "end_year": end,
            "starting_balance": "0",
            "expense_lines": [],
            "expense_inflation": "0.03",
            "expense_base_year": start - 1,
            "ffb": {str(y): "0" for y in range(start, end + 2)},
            "operating_inflation": "0.03",
            "interest_rate": "0.02",
            "units": 1,
            "current_dues": "0",
            "cushion": "0",
            "target": "0.7",
            "max_dues_increase": "0.2",
            "max_assessment_share": "0.05",
        },
        "dues": {"mode": "rate", "first_value": "0", "annual_increase": "0.03"},
        "assessments": [],
        "rounding": "dollar",
    }


def blank_scenario(name: str, today: date) -> Scenario:
    return scenario_from_dict(_blank_scenario(name, today))


def blank_project(name: str, today: date) -> Project:
    """A project with one blank scenario."""
    raw: dict[str, Any] = {
        "name": name,
        "notes": "",
        "schema_version": 3,
        "scenarios": [_blank_scenario(FIRST_SCENARIO, today)],
    }
    return project_from_dict(raw)
