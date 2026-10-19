"""The two scenario charts (spec section 7.5) as native Excel line charts.

Dollar series sit on the left axis; percent funded and the dashed target line
on a right axis fixed at 0–100%. Charts reference the Plan sheet cells, so
they redraw when the workbook recalculates.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference, Series
from openpyxl.chart.axis import TextAxis
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.marker import Marker
from openpyxl.chart.series import Series as ChartSeries
from openpyxl.chart.series import SeriesLabel
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

from hoa_workbook.layout import (
    CHART_HEIGHT_ROWS,
    CHARTS_LABEL,
    HEADER_ROW,
    PLAN_FIRST_COL,
    ROW,
)

BLUE, RED, GREEN, PURPLE, GREY = "4A7EBB", "BE4B48", "98B855", "7D60A0", "7F7F7F"
WIDTH_CM, HEIGHT_CM = 26, 10.5
PERCENT_AXIS_ID, HIDDEN_CATEGORY_AXIS_ID = 200, 500


PERCENT_STEP = Decimal("0.2")
ROUND_STEPS = tuple(Decimal(m) for m in ("1", "2", "2.5", "5", "10"))
STEPS_TO_TOP = 5  # 0% to 100% in 20% steps


@dataclass(frozen=True)
class Grid:
    dollar_min: Decimal
    dollar_max: Decimal
    dollar_step: Decimal
    percent_min: Decimal


def shared_grid(low: Decimal, high: Decimal) -> Grid:
    """A dollar scale whose gridlines coincide with 0–100% in 20% steps.

    The dollar step is the smallest round figure (1, 2, 2.5 or 5 × a power of ten)
    that fits the highest value in five steps; values below zero add whole steps
    beneath both axes, so the two zero lines stay level.
    """
    need = max(high, Decimal(1)) / STEPS_TO_TOP
    magnitude = Decimal(10) ** (len(str(int(need))) - 1)
    step = next(m * magnitude for m in ROUND_STEPS if m * magnitude >= need)
    below = max(Decimal(0), (-low / step).to_integral_value(rounding=ROUND_CEILING))
    return Grid(-below * step, STEPS_TO_TOP * step, step, -below * PERCENT_STEP)


def _series(
    ws: Worksheet, key: str, n_years: int, title: str, color: str, dashed: bool = False
) -> ChartSeries:
    ref = Reference(
        ws,
        min_col=PLAN_FIRST_COL,
        max_col=PLAN_FIRST_COL + n_years - 1,
        min_row=ROW[key],
        max_row=ROW[key],
    )
    series: ChartSeries = Series(ref, title=None)
    series.tx = SeriesLabel(v=title)
    series.smooth = False
    series.marker = Marker(symbol="none")
    line = series.graphicalProperties.line
    line.solidFill = color
    line.width = 28575  # 2.25 pt
    if dashed:
        line.dashStyle = "dash"
    return series


def _chart(
    ws: Worksheet,
    title: str,
    dollar_title: str,
    dollar_series: list[tuple[str, str, str]],
    n_years: int,
    dollar_axis: tuple[Decimal, Decimal] | None = None,
) -> LineChart:
    chart = LineChart()
    chart.title = title
    chart.width, chart.height = WIDTH_CM, HEIGHT_CM
    assert chart.legend is not None
    chart.legend.position = "b"
    for key, label, color in dollar_series:
        chart.series.append(_series(ws, key, n_years, label, color))
    years = Reference(
        ws,
        min_col=PLAN_FIRST_COL,
        max_col=PLAN_FIRST_COL + n_years - 1,
        min_row=HEADER_ROW,
        max_row=HEADER_ROW,
    )
    chart.set_categories(years)
    chart.x_axis.title = "Year"
    chart.x_axis.number_format = "0"
    chart.x_axis.delete = False
    chart.x_axis.tickLblPos = "low"  # years along the bottom even when balances go negative
    chart.y_axis.title = dollar_title
    chart.y_axis.number_format = "$#,##0"
    chart.y_axis.delete = False
    chart.y_axis.majorGridlines = None
    grid = shared_grid(*dollar_axis) if dollar_axis is not None else None
    if grid is not None:
        chart.y_axis.scaling.min = float(grid.dollar_min)
        chart.y_axis.scaling.max = float(grid.dollar_max)
        chart.y_axis.majorUnit = float(grid.dollar_step)

    percent = LineChart()
    percent.series.append(_series(ws, "pf", n_years, "Percent funded", PURPLE))
    percent.series.append(
        _series(ws, "target", n_years, "Percent-funded target", GREY, dashed=True)
    )
    percent.y_axis.axId = PERCENT_AXIS_ID
    percent.y_axis.title = "Percent funded"
    percent.y_axis.number_format = "0%"
    percent.y_axis.scaling.min = float(grid.percent_min) if grid else 0
    percent.y_axis.majorUnit = float(PERCENT_STEP) if grid else None
    percent.y_axis.scaling.max = 1
    percent.y_axis.crosses = "max"
    percent.y_axis.delete = False
    percent.y_axis.majorGridlines = None
    # The secondary series need a category axis of their own; it is never shown.
    percent.x_axis = TextAxis(axId=HIDDEN_CATEGORY_AXIS_ID, crossAx=PERCENT_AXIS_ID, delete=True)
    percent.y_axis.crossAx = HIDDEN_CATEGORY_AXIS_ID
    chart += percent
    # Fixed room for titles, tick labels and the legend, so nothing overlaps.
    chart.plot_area.layout = Layout(
        ManualLayout(xMode="edge", yMode="edge", x=0.09, y=0.11, w=0.80, h=0.62)
    )
    chart.legend.overlay = False
    for t in (chart.title, chart.x_axis.title, chart.y_axis.title, percent.y_axis.title):
        assert t is not None  # every title is set above
        t.overlay = False
    return chart


def _expenses_chart(
    ws: Worksheet, name: str, n_years: int, dollar_axis: tuple[Decimal, Decimal] | None = None
) -> LineChart:
    return _chart(
        ws,
        f"{name} – expenses, dues, reserve balance and percent funded",
        "Dollars ($)",
        [
            ("expenses", "Reserve expenses (year)", BLUE),
            ("owners", "Dues + assessments collected (year, all units)", RED),
            ("end", "Year-end reserve balance", GREEN),
        ],
        n_years,
        dollar_axis,
    )


def add_plan_charts(ws: Worksheet, name: str, n_years: int, top_row: int) -> None:
    label = ws.cell(top_row - 1, 1)
    label.value, label.data_type = f"{CHARTS_LABEL}{name}", "s"  # user text, never a formula
    label.font = Font(name="Arial", bold=True, size=11)
    ws.add_chart(_expenses_chart(ws, name, n_years), f"A{top_row}")
    owner = _chart(
        ws,
        f"{name} – owner cost per unit and percent funded",
        "Owner cost ($ per unit)",
        [("own_cost", "Owner cost – dues + assessment per unit", RED)],
        n_years,
    )
    ws.add_chart(owner, f"A{top_row + CHART_HEIGHT_ROWS}")


def add_charts_sheet(
    wb: Workbook,
    title: str,
    plans: list[tuple[str, str]],
    n_years: int,
    dollar_axis: tuple[Decimal, Decimal] | None,
) -> None:
    ws = wb.create_sheet(title)
    ws.column_dimensions["A"].width = 120
    ws["A1"] = "Scenario comparison – expenses, dues, reserve balance and percent funded"
    ws["A1"].font = Font(name="Arial", bold=True, size=13)
    scale = "the same dollar scale" if dollar_axis else "each its own dollar scale"
    ws["A2"] = (
        "The first chart from each scenario sheet, stacked for comparison with "
        f"{scale}. Dollar lines on the left axis, percent funded and the target on the right. "
        "Charts update with the inputs."
    )
    ws["A2"].font = Font(name="Arial", italic=True, size=9)
    ws["A2"].alignment = Alignment(wrap_text=True)
    for i, (sheet, name) in enumerate(plans):
        chart = _expenses_chart(wb[sheet], name, n_years, dollar_axis)
        ws.add_chart(chart, f"A{4 + i * CHART_HEIGHT_ROWS}")
