# The Excel workbook

HOAForecaster exports a project as an Excel workbook in the layout of the board's original reserve funding model. Every result is a live formula, so the workbook recalculates on its own when someone edits it. The same workbook can be read back into the app.

This page is for two readers. A board member who receives the workbook can read the first part to learn what each sheet shows and which cells to change. A developer will also want [Reading a workbook back](#reading-a-workbook-back) and [For developers](#for-developers).

The examples use the fictional demo project, Maple Row Condominiums, in `demo/fixtures/project.json`. Its exported workbook is `demo/fixtures/reference.xlsx`.

## The sheets, in order

| Sheet | What it holds |
|---|---|
| Method | What the model is for, how it works, the scenarios with their descriptions, the colour legend, the sources of the figures, the project notes and the model's limits. Text only. |
| Inputs | The building's reserve facts – one per row, with a source note beside each. |
| Compare | The summary measures side by side, one column per scenario, then year-end reserve balance and percent funded by year. |
| Charts | The first chart from each scenario sheet, stacked one above the other. |
| Expenses | One row per reserve expense, the yearly totals and the reserve study's Fully Funded Balance. |
| One sheet per scenario | The year-by-year plan (a "Plan sheet"), its dues settings, its special assessments and its two charts. |

The scenario sheets follow in the order the scenarios were chosen for export. Each is named after its scenario. A name that Excel cannot use as a sheet name is cleaned up – the characters `[ ] : * ? / \` become spaces, apostrophes and spaces at either end are dropped, the name is cut to Excel's limit of 31 characters, and a name already taken gets " (2)", " (3)" and so on. The scenario's full name is always in cell A1 of its sheet.

## Colours

The workbook keeps the original model's colour code.

- **Blue text on a yellow background** – an input. These are the cells to edit.
- **Black** – a formula on the same sheet.
- **Green** – a value pulled from another sheet.

On the Plan sheets, the yes/no flag rows are shaded when a flag is raised. LOW and "yes" for an operating shortfall are shaded red, "yes" for an owner vote orange, and "yes" for meeting the target green.

## Inputs

Column B holds the values and column C a note on where each one came from.

| Row | Input | Format |
|---|---|---|
| 5 | Association | text |
| 6 | Starting reserve balance (January 1 of the start year) | dollars |
| 7 | Start year | year |
| 8 | End year | year |
| 9 | Number of units | whole number |
| 10 | Current dues per unit per month | dollars and cents |
| 11 | Operating expenses in the start year | dollars |
| 12 | Operating cost inflation per year | percent |
| 13 | Reserve expense inflation per year | percent |
| 14 | Expense base year (dollars of the reserve study) | year |
| 15 | Interest earned on reserves per year | percent |
| 16 | Minimum working cushion | dollars |
| 17 | Percent-funded target | percent |
| 18 | Largest dues increase without an owner vote | percent |
| 19 | Largest assessment without a vote, share of budget | percent |
| 20 | Project notes | text |

Leaving either owner-vote limit (rows 18 and 19) blank turns that rule off – the sheet never flags a vote for it.

Do not change the start year or end year in Excel. The year columns on the Expenses and Plan sheets are fixed when the workbook is made, so a new end year changes nothing in the workbook, and a new start year shifts the operating-cost growth without moving the columns. Change the horizon in HOAForecaster and export again.

## Expenses

Each row from row 5 down is one reserve expense.

| Column | Holds |
|---|---|
| A – Item | A description of the expense. A cell comment on it, if any, records the expense's source. |
| B – Amount | The amount, in the expense base year's dollars (input). |
| C – Year | The year it falls in (input). |
| D – Already in that year's dollars? | "yes" or "no" (input). "yes" means the amount is used as it stands. |
| E onward | One column per year of the horizon. Each holds the expense's amount for that year – the amount grown at the reserve expense inflation rate from the base year to its year, or the amount as it stands when column D says "yes", and 0 in every other year. |

Below the expenses, the **TOTAL projected reserve expenses** row adds up each year's column. The Plan sheets take their reserve expenses from this row.

Below that are a row of years and the **Fully Funded Balance at start of year** row, from the start year through the year after the end year. Its values are inputs. A comment on its label records where the figures came from.

**To add an expense**, copy a whole existing expense row, then insert the copied cells between two existing expense rows and change the item, amount, year and yes/no. Copying the whole row brings its year formulas along. Inserting between two existing rows makes Excel widen the total's range to include the new row – a row inserted above the first expense or below the last one may be left out of the total.

**To remove an expense**, delete its whole row.

An expense typed into a blank row has no year formulas, so the workbook's total leaves it out. The app refuses such a workbook on re-import rather than read a figure the workbook itself ignores.

## Plan sheets

A1 holds the scenario's name and A2 its description. Years run across row 4, starting in column C.

### The table

| Row | Label | What it shows |
|---|---|---|
| 5 | Dues per unit per month ($) | Typed in for each year, or worked out from the dues settings below the table (see [Dues settings](#dues-settings)) |
| 6 | Special assessment per unit ($, this year) | The total of this year's entries in the special-assessment list |
| 8 | Total dues collected | Dues × units × 12 |
| 9 | Operating expenses | Start-year operating expenses grown at the operating inflation rate |
| 10 | Reserve contribution from dues | Total dues less operating expenses, never below zero |
| 11 | Special assessment to reserves | Assessment per unit × units |
| 12 | Total collected from owners (dues + assessment) | Row 8 + row 11 |
| 13 | Interest earned | Starting balance × the interest rate |
| 14 | Reserve expenses (Expenses sheet) | The year's total from the Expenses sheet |
| 16 | Starting reserve balance | The starting balance on Inputs in the first year, then the year before's ending balance |
| 17 | **Ending reserve balance** | Start + contribution + assessment + interest − reserve expenses |
| 18 | Fully Funded Balance (start of next year) | From the Expenses sheet |
| 19 | **Percent funded at year end** | Ending balance ÷ next year's Fully Funded Balance, or 0 when that balance is 0 |
| 20 | Below minimum cushion? | "LOW" when the ending balance is under the cushion, otherwise "ok" |
| 21 | Meets percent-funded target? | "yes" when percent funded is at or above the target |
| 22 | Needs owner vote? | "yes" when dues rise more than the dues limit over the year before (over current dues in the first year), or the assessment to reserves is more than the assessment limit × (operating expenses + reserve contribution) |
| 23 | Operating shortfall? | "yes" when total dues are less than operating expenses. A warning only – the gap is not taken from reserves |
| 25 | Owner cost – dues per unit per year | Dues × 12 |
| 26 | Owner cost – dues + assessment per unit | Row 25 + the assessment per unit |
| 27 | Increase vs current dues (per unit per year) | (Dues − current dues) × 12 |
| 28 | Cumulative owner cost per unit | Running total of row 26 |
| 29 | Cumulative extra cost vs current dues | Running total of row 30 |
| 30 | Extra vs current dues, with assessment (per unit per year) | Row 27 + the assessment per unit |
| 31 | Percent-funded target (Inputs) | The target, repeated each year for the charts |

The labels for operating expenses, reserve contribution and percent funded carry a cell comment explaining them. These are the same formulas the app's engine uses, described in [engine.md](engine.md).

### Dues settings

Below the table are the settings that decide row 5.

| Row | Label | Typed dues | Grown dues |
|---|---|---|---|
| 33 | How dues are set | "typed for each year" | "grown from the first year" |
| 34 | First-year dues (grown dues only) | blank | Input – the start year's dues |
| 35 | Annual dues increase (grown dues only) | blank | Input – the yearly increase |
| 36 | Pinned dues (blank = grow from the year before) | blank | Input, one cell per year |
| 37 | Dues before rounding | blank | The pinned value if there is one, otherwise the first-year dues in the start year and the year before's figure grown by the increase after that |
| 38 | Rounding of grown dues | Input – a dropdown | Input – a dropdown |

**Typed dues** – row 5 is an input in every year. Type each year's dues per unit per month.

**Grown dues** – row 5 is a formula. The start year takes the first-year dues as typed. Each later year takes row 37, rounded to whole dollars when row 38 says "whole dollars". A pinned year takes its pinned value as typed, and the years after it grow from that value. Rounding is applied to each year's unrounded figure, so it never builds up from year to year.

To change one year's grown dues, type it into row 36 (pin it) rather than over the formula in row 5.

**Rounding** – row 38 offers "whole dollars" or "none – cents kept". It affects grown dues only. Typed and pinned dues are always used as typed. The dropdown does not stop other text being typed in. The sheet then keeps cents, and the app refuses the workbook on re-import.

### Special assessments

From row 40, the sheet lists its special assessments, one row each, with a note, a year (column C) and an amount per unit (column D). Several assessments may fall in the same year – row 6 adds them up. Each list ends with five blank yellow rows to fill in.

To add an assessment, fill in a spare yellow row. To add more than the spare rows allow, insert new rows between two yellow rows, so the sum in row 6 stretches to include them. To remove one, clear its year and amount.

Installments stay separate rows and keep their notes when the workbook is read back.

### Charts

Below the assessment list, under the label "Charts – " and the scenario name, are two charts covering the whole horizon.

1. **Expenses, dues, reserve balance and percent funded** – reserve expenses, dues + assessments collected (all units) and year-end reserve balance on the left dollar axis. Percent funded and the target, dashed, on the right axis, which runs to 100%.
2. **Owner cost per unit and percent funded** – owner cost per unit per year (dues + assessment) on the left axis. Percent funded and the target on the right.

The charts draw from the Plan sheet's cells, so they redraw when the workbook recalculates. On a Plan sheet, Excel picks each chart's dollar scale.

## What you can change in Excel

Only the blue-on-yellow cells and the text cells listed below are read back into the app. Typing over a black or green formula changes the workbook's own figures but is lost on re-import.

| Change | Where | Effect |
|---|---|---|
| Any baseline fact | Inputs, column B | Every Plan sheet, Compare and the charts recalculate |
| A source note | Inputs, column C | Kept on re-import |
| An expense's amount, year or yes/no | Expenses, columns B–D | The year totals and every Plan sheet recalculate |
| Add or remove an expense | Expenses | See [Expenses](#expenses) |
| A Fully Funded Balance | Expenses, the FFB row | Percent funded recalculates |
| Typed dues | Plan sheet, row 5 | That scenario recalculates |
| First-year dues or the annual increase | Plan sheet, rows 34–35 | Every year's grown dues recalculate |
| Pin a year's dues | Plan sheet, row 36 | That year uses the pinned value, later years grow from it |
| Rounding | Plan sheet, row 38 | Grown dues are rounded to whole dollars or keep cents |
| A special assessment | Plan sheet, the assessment list | Row 6 and everything after it recalculate |
| A scenario's name or description | Plan sheet, A1 and A2 | Kept on re-import (the sheet tab can be renamed freely) |

### What cannot be changed in Excel

**How dues are set (row 33).** Typed and grown dues put formulas in different cells – typed dues make row 5 an input, grown dues make it a formula fed by rows 34–37. Changing the words in row 33 cannot move those formulas, so the sheet would not follow, and the app refuses the workbook on re-import. Change the dues mode in HOAForecaster and export again.

**The horizon.** See [Inputs](#inputs).

**The layout of a Plan sheet.** The app finds a Plan sheet's rows by position. Do not insert or delete rows above the special-assessment list. A sheet whose row 33 no longer says "How dues are set" is not recognised as a Plan sheet and its scenario is left out on re-import. Inserting rows inside the assessment list is fine.

On the Inputs and Expenses sheets, the app finds rows by their labels in column A, so rows can be moved or inserted there as long as the labels are left alone.

## Compare

The top table has one row per summary measure and one column per scenario.

- Dues per unit per month in years 1, 4 and 9
- Total special assessments per unit
- Lowest year-end reserve balance, and its year
- Years below the minimum cushion, years needing an owner vote and years with an operating shortfall
- Reserve balance and percent funded at the end of years 4 and 9 and of the end year
- The first year the percent-funded target is met, or "not by" the end year
- Owner outlay per unit over the first five years and over the whole horizon
- Extra cost vs current dues over the whole horizon and over the first four years
- Average owner cost per year and average extra cost per year

The year 9 measures are left out when the horizon is shorter than 9 years. Below the summary, two tables give year-end reserve balance and percent funded for every year and every scenario. Every figure is pulled from the Plan sheets.

## Charts sheet and the shared dollar scale

The Charts sheet stacks the first chart from each Plan sheet – expenses, dues, reserve balance and percent funded – in scenario order.

When the app exports, it can give all of these charts the same dollar scale so they compare at a glance. The scale is chosen so that its gridlines line up with the percent axis's 0%, 20%, 40%, 60%, 80% and 100%.

- The step is the smallest round figure – 1, 2, 2.5, 5 or 10 times a power of ten – that reaches the highest value in five steps.
- The top of the dollar axis is five steps.
- If any value is below zero, whole steps are added beneath zero on both axes, so the two zero lines stay level. The percent axis then starts below 0% by 20% for each step.

For the demo project, the values run from about −$45,222 (the lowest balance in Hold then catch up) to about $806,017 (the highest balance in Two-part assessment). The step is $200,000, so the dollar axis runs from −$200,000 to $1,000,000 and the percent axis from −20% to 100%.

The percent axis always stops at 100%, so a percent funded above 100% runs off the top of the chart.

Without a shared scale, each chart on the Charts sheet picks its own, and the note at the top of the sheet says so.

## Reading a workbook back

HOAForecaster reads a workbook only in its own export layout. It reads the inputs – values, never formulas – and builds a project from them.

| Sheet | What is read |
|---|---|
| Inputs | Column B of each labelled row, and the note in column C |
| Expenses | Each row between the column headings and the TOTAL row that has an item or an amount, with the comment on its item as its source. The Fully Funded Balance row and the years above it. The comment on the FFB label |
| Each Plan sheet | A1 and A2, rows 33 and 38, then row 5 for typed dues, or rows 34–36 for grown dues. The assessment list from row 42 down to the "Charts – " label |

A Plan sheet is any sheet other than the five fixed ones whose row 33 is labelled "How dues are set". Method, Compare and Charts are not read. A deleted Plan sheet means a scenario fewer.

A workbook read back without edits gives the exported project. The one difference is that numbers pass through Excel's floating-point storage, which keeps about 15 significant digits. The demo project comes back identical.

### What is refused

Every refusal is a plain-language message naming the sheet and, where it can, the row. The workbook is refused when

- the file is larger than 20 MB, is not an `.xlsx` workbook, or is damaged
- it unpacks to more than 20 MB or to more than 2,000 parts, or any part is compressed more than 100 to 1 – the signs of a crafted file
- any sheet runs past 2,000 rows or 200 columns
- the Inputs or Expenses sheet is missing, or one of their labelled rows
- a number cell holds text or a formula, or a year or the number of units is not a whole number
- an expense row has no year formulas
- row 33 or row 38 of a Plan sheet holds anything but the exported choices
- an assessment has an amount but no year, or a year but no amount
- two scenarios have the same name in A1
- a number is so large it cannot be a real amount (10<sup>15</sup> or more)

Once read, the project passes the same checks as one entered in the app (see [Input checks](engine.md#input-checks)). Every problem found is listed at once, separated by semicolons, with each scenario's problems prefixed by its name – for example a negative operating cost, a target above 100%, a missing Fully Funded Balance, or an assessment outside the horizon. A pinned value typed in a column past the last year has no year above it and is ignored.

The reader needs `defusedxml` installed and active, which guards against XML-based attacks. It refuses to load without it.

## Protection against formula injection

Text from a project – the association's name and notes, scenario names and descriptions, expense items, assessment notes and source notes – is always written as a text cell, never as a formula. Text that starts with `=`, `+`, `-`, `@`, a tab or a carriage return also gets Excel's quote prefix, so it stays text even after someone edits the cell or saves the sheet as CSV. A scenario named `=SUM(A1)` shows those characters and computes nothing.

Scenario names are also cleaned before they become sheet names (see [The sheets, in order](#the-sheets-in-order)), and quoted wherever a formula refers to the sheet.

When a project is read, a project name, project notes, scenario name or scenario description that holds a control character – anything below a space other than tab, newline and carriage return – is refused.

## For developers

The code is in `src/hoa_workbook/`.

| File | Role |
|---|---|
| `layout.py` | The single source for sheet names, row numbers, labels and the dropdown texts. The writer and the reader both use it. |
| `export.py` | Writes the workbook with `openpyxl`. |
| `charts.py` | The native Excel line charts and the shared dollar scale. |
| `read.py` | Reads an exported workbook back into a `Project`. |

The package imports only `hoa_engine.model` and `hoa_engine.validate` – the project's inputs and their checks – never the engine itself, so the workbook's formulas are a second, independent implementation of the arithmetic. `tests/workbook/test_independence.py` enforces this.

```python
import json
from pathlib import Path

from hoa_engine import project_from_dict, run
from hoa_workbook.export import export_workbook
from hoa_workbook.read import read_workbook

project = project_from_dict(
    json.loads(Path("demo/fixtures/project.json").read_text(encoding="utf-8"))
)
values = [
    v
    for s in project.scenarios
    for y in run(project.baseline, s).years
    for v in (y.expenses, y.total_from_owners, y.ending_balance)
]
data = export_workbook(project, Path("maple-row.xlsx"), dollar_axis=(min(values), max(values)))
assert read_workbook(Path("maple-row.xlsx")) == project
```

- `export_workbook(project, path=None, scenario_names=None, dollar_axis=None)` returns the workbook's bytes, and also writes them to `path` when one is given. `build_workbook` takes the same arguments without `path` and returns the `openpyxl` workbook.
- `scenario_names` picks and orders the scenarios to include. By default all are included, in the project's order.
- `dollar_axis` is the (lowest, highest) dollar value for the Charts sheet's shared scale. The exporter never runs the engine, so the caller works it out from the engine's results, as above.
- Export raises `ValueError` when the baseline fails its checks, when two scenarios share a name, or when `scenario_names` names a scenario the project does not have.
- `read_workbook(source)` takes a path or the file's bytes and returns a validated `Project`, or raises `WorkbookFormatError` with a plain-language message.

The tests in `tests/workbook/` recalculate exported workbooks in LibreOffice and compare every figure with the engine's, check that export then import gives the same results, open the workbook in Excel on Windows to check for repair prompts, and feed the reader damaged and edited files.
