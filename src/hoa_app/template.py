"""A new, blank project or scenario with the spec's defaults (section 4) – nothing invented."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hoa_engine.model import (
    DuesMode,
    DuesPath,
    Increase,
    Project,
    Rounding,
    Scenario,
    blank_facts,
    project_from_dict,
    project_to_dict,
)

FIRST_SCENARIO = "First scenario"


def blank_scenario(name: str, current_dues: str = "0") -> Scenario:
    """A funding plan on the project's facts – dues from the current dues, rising 3% a year, no
    assessments, rounded to whole dollars."""
    return Scenario(
        name=name,
        facts=None,
        dues=DuesPath(
            DuesMode.RATE, first_value=Decimal(current_dues), increases=(Increase(Decimal("0.03")),)
        ),
        rounding=Rounding.DOLLAR,
    )


def blank_project(name: str, today: date) -> Project:
    """A project with the defaults – starting January 1 of next year (a mid-year start uses next
    year's opening balance), running 14 years, amounts zero – and one blank scenario."""
    project = Project(
        name=name,
        facts=blank_facts(today.year + 1),
        scenarios=(blank_scenario(FIRST_SCENARIO),),
    )
    # through the file form, so its name gets the same checks as any project's
    return project_from_dict(project_to_dict(project))
