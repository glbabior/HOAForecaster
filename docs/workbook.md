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
| Expenses | One row per expense with how often it falls, the operating and reserve totals by year, and the reserve study's Fully Funded Balance. |
| One sheet per scenario | The year-by-year plan (a "Plan sheet"), its dues settings, its special assessments, its two charts and, below them, the scenario's own assumptions, Fully Funded Balance and expense changes. |

The scenario sheets follow in the order the scenarios were chosen for export. Each is named after its scenario. A name that Excel cannot use as a sheet name is cleaned up – the characters `[ ] : * ? / \` become spaces, apostrophes and spaces at either end are dropped, the name is cut to Excel's limit of 31 characters, and a name already taken gets " (2)", " (3)" and so on. The scenario's full name is always in cell A1 of its sheet.

An adopted plan gets a Plan sheet too, laid out the same way but holding its frozen baseline – see [Adopted plans](#adopted-plans).

## Colours

The workbook keeps the original model's colour code.

- **Blue text on a yellow background** – an input. These are the cells to edit.
- **Black** – a formula on the same sheet.
- **Green** – a value pulled from another sheet.
- **Grey** – a line identifier or a mark, kept so the app can read the workbook back.

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
| 11 | Operating cost inflation per year (monthly and yearly lines without their own) | percent |
| 12 | Reserve expense inflation per year | percent |
| 13 | Expense base year (dollars of the reserve study) | year |
| 14 | Interest earned on reserves per year | percent |
| 15 | Minimum working cushion | dollars |
| 16 | Percent-funded target | percent |
| 17 | Largest dues increase without an owner vote | percent |
| 18 | Largest assessment without a vote, share of budget | percent |
| 19 | Project notes | text |

There is no operating-expenses row. Operating expenses are the monthly and yearly lines on the Expenses sheet.

Leaving either owner-vote limit (rows 17 and 18) blank turns that rule off – the sheet never flags a vote for it.

Do not change the start year or end year in Excel. The year columns on the Expenses and Plan sheets are fixed when the workbook is made, so a new end year changes nothing in the workbook, and a new start year shifts the growth of operating lines without moving the columns. Change the horizon in HOAForecaster and export again. If a Plan sheet's start or end year no longer matches its year columns, the app refuses the workbook on re-import and says so.

## Expenses

Each row from row 5 down is one expense. Columns A–I hold its inputs, and the year columns follow from column J.

| Column | Holds |
|---|---|
| A – Item | A description of the expense. A cell comment on it, if any, records the expense's source. |
| B – How often | "monthly", "yearly", "every few years" or "once" (a dropdown). Monthly and yearly lines are operating expenses, paid from dues. Once and every-few-years lines are reserve expenses. |
| C – Amount | A month for monthly lines, a year for yearly lines, each occurrence otherwise. |
| D – Year, or first year | The year of a once line, the first occurrence of an every-few-years line, or the first year of a monthly or yearly line (blank – from the start year). |
| E – Last year | The last year of a repeating line (blank – to the end). |
| F – Every … years | The years between occurrences of an every-few-years line. |
| G – Own inflation | A monthly or yearly line's own inflation rate (blank – the operating rate on Inputs). |
| H – Already in that year's dollars? | For once and every-few-years lines, "yes" or "no". "yes" means the amount is in the dollars of the line's first year: a once line uses it as it stands, and an every-few-years line's later occurrences grow from it at the reserve inflation rate. |
| I – Line id | The line's identifier, in grey. Scenarios use it to change or leave out the line. |
| J onward | One column per year of the horizon, each holding the line's amount that year. |

A line's amount in a year is worked out as the app does it (see [engine.md](engine.md#step-2--expense-lines-by-frequency)).

- A monthly or yearly line in a year from its first year to its last – the amount (× 12 for monthly) grown at its own rate, or the operating rate, from its first year (blank – the start year).
- A once line in its year, or an every-few-years line in its first year and every interval after it, up to its last year – the amount grown at the reserve expense inflation rate from the expense base year, or as it stands when column H says "yes".
- 0 in every other year.

Below the lines are two totals for each year.

- **TOTAL operating expenses (monthly and yearly lines)** – what the Plan sheets' operating expenses start from.
- **TOTAL projected reserve expenses (once and every few years)** – what their reserve expenses start from.

Each Plan sheet works out its own totals from these lines, at its own rates and with its own changes (see [The scenario's own inputs](#the-scenarios-own-inputs-below-the-charts)). For a scenario with no changes, its totals equal these.

Below the totals are a row of years and the **Fully Funded Balance at start of year** row, from the start year through the year after the end year. Its values are inputs. A comment on its label records where the figures came from.

**To add an expense**, copy a whole existing expense row, insert the copied cells between two existing expense rows, change its inputs and **clear its line id**. Copying the whole row brings its year formulas along. Inserting between two existing rows makes Excel widen the totals to include the new row – a row inserted above the first expense or below the last one may be left out. A cleared id gets a new one, `line-` and a number, on re-import.

**To remove an expense**, delete its whole row. A scenario that changed that line keeps its copy as a line of its own.

An expense typed into a blank row has no year formulas, so the workbook's totals leave it out. The app refuses such a workbook on re-import rather than read a figure the workbook itself ignores. The same goes for an expense on a row the totals do not add up, and for two rows with the same line id – clear the id of the row you added.

## Plan sheets

A1 holds the scenario's name, A2 its description and A3 a short guide. Years run across row 4, starting in column C – the scenario's own years, which differ from the baseline's when the scenario has its own start or end year.

### The table

| Row | Label | What it shows |
|---|---|---|
| 5 | Dues per unit per month ($) | Typed in for each year, or worked out from the dues settings below the table (see [Dues settings](#dues-settings)) |
| 6 | Special assessment per unit ($, this year) | The total of this year's entries in the special-assessment list |
| 8 | Total dues collected | Dues × units × 12 |
| 9 | Operating expenses | This scenario's operating total, from the block below the charts |
| 10 | Reserve contribution from dues | Total dues less operating expenses, never below zero |
| 11 | Special assessment to reserves | Assessment per unit × units |
| 12 | Total collected from owners (dues + assessment) | Row 8 + row 11 |
| 13 | Interest earned | Starting balance × the interest rate, or 0 when the starting balance is negative (`MAX(0, start) × rate`) |
| 14 | Reserve expenses (once and every few years) | This scenario's reserve total, from the block below the charts |
| 16 | Starting reserve balance | The scenario's starting balance in the first year, then the year before's ending balance |
| 17 | **Ending reserve balance** | Start + contribution + assessment + interest − reserve expenses |
| 18 | Fully Funded Balance (start of next year) | From the scenario's Fully Funded Balance block |
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
| 31 | Percent-funded target (this scenario) | The target, repeated each year for the charts |

Every rate, count and limit in these formulas is the scenario's own, from the assumptions block below the charts – which follows Inputs unless the scenario sets its own. The labels for operating expenses, reserve contribution and percent funded carry a cell comment explaining them. These are the same formulas the app's engine uses, described in [engine.md](engine.md).

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

From row 40, the sheet lists its special assessments, one row each, with a note (column A), a year (column C) and an amount per unit (column D). Several assessments may fall in the same year – row 6 adds them up. Each list ends with five blank yellow rows to fill in.

To add an assessment, fill in a spare yellow row. To add more than the spare rows allow, insert new rows between two yellow rows, so the sum in row 6 stretches to include them. To remove one, clear its year and amount.

Installments stay separate rows and keep their notes when the workbook is read back.

### Charts

Below the assessment list, under the label "Charts – " and the scenario name, are two charts covering the scenario's own years.

1. **Expenses, dues, reserve balance and percent funded** – reserve expenses, dues + assessments collected (all units) and year-end reserve balance on the left dollar axis. Percent funded and the target, dashed, on the right axis, which runs to 100%.
2. **Owner cost per unit and percent funded** – owner cost per unit per year (dues + assessment) on the left axis. Percent funded and the target on the right.

The charts draw from the Plan sheet's cells, so they redraw when the workbook recalculates. On a Plan sheet, Excel picks each chart's dollar scale.

### The scenario's own inputs, below the charts

Below the two charts are three blocks holding the scenario's changes to the baseline (spec 5.1). For a scenario with no changes, every cell in them follows the baseline.

**This scenario's assumptions.** One row for each input a scenario can change – every Inputs row except the association's name and the project notes. Column C holds the value and column D its source note.

- A green cell follows Inputs. Change the figure on Inputs and this scenario follows.
- A blue-on-yellow cell is the scenario's own. Type over a green cell to give the scenario its own figure, and over its note to give it its own note.
- For an owner-vote limit, a blank yellow cell is the scenario's own "no limit". In the demo, Insurance shock has no assessment limit of its own, while Inputs keeps 5%.

**This scenario's Fully Funded Balance.** A row of years (labelled "Start of year") and a Fully Funded Balance row, for the scenario's years and one more. A green cell follows the Expenses sheet. A blue-on-yellow cell is the scenario's own – in the demo, Insurance shock's $700,000 for 2031. A year the Expenses sheet does not show (when the scenario runs later than the baseline) is typed in yellow too.

**This scenario's expense changes.** A table with the same columns as the Expenses sheet (A–I), then "Leave out?" (column J), a column used only on adopted plans (K) and year columns from column L. Each row is one change, matched to the Expenses sheet by its line id.

| A row with | Means |
|---|---|
| A baseline line's id and all its inputs | The scenario's own copy of that line, replacing it. In the demo, Insurance shock's insurance at $47,000 growing at 8% |
| A baseline line's id and "Leave out?" = "yes" | The line is left out of this scenario. In the demo, Insurance shock's boiler |
| No id (or an id the baseline does not have) and its inputs | A line of the scenario's own, added to the baseline's. In the demo, Insurance shock's pool resurfacing |

Each list ends with three spare yellow rows. Below it are **TOTAL operating expenses – this scenario** and **TOTAL reserve expenses – this scenario** – the Expenses sheet's lines this scenario keeps, at this scenario's own rates, plus the rows of this table. Rows 9 and 14 of the table above take their figures from these totals. A line added to the Expenses sheet reaches every scenario that does not change it.

To put a left-out line back, set "Leave out?" to "no" and leave its other inputs blank, or clear the row. A row with only an id and nothing else does nothing.

### Adopted plans

An adopted plan's sheet is laid out like any Plan sheet, with these differences.

- A3 says the plan was adopted and on what date, and that it is read-only in the app.
- The assumptions block holds the frozen baseline's every value as typed figures – nothing links to Inputs. Column E, "This plan's own?", says which were the plan's own changes – "value", "note" or "value and note", or blank.
- The Fully Funded Balance block holds the frozen figures, typed, and a row below it, "This plan's own Fully Funded Balance?", marks the plan's own years with "yes" (and its own note with "note" in column B).
- The expense changes table holds every line of the frozen baseline, then the lines the plan left out (marked "Leave out?" = "yes"). Column K, "This plan's own?", says "yes" for the plan's own lines and "no" for the rest. Its totals are these rows alone, so nothing on the Expenses sheet reaches it.
- Below the totals are the **Adopted on** date (written as text, YYYY-MM-DD), the **Adoption note** and the **Adoption order** – the highest order is the current adopted plan.
- The sheet is protected, as a reminder that the plan is read-only. There is no password, so nothing is locked away.

In the demo, the sheet "Adopted – two-part assessment" shows the $172,000 starting balance it was adopted with, its own 2% interest marked "value and note", its own $650,000 for 2030 marked "yes", and the railings left out. The boiler is not listed, because the baseline did not yet have it when the plan was adopted.

## What you can change in Excel

Only the blue-on-yellow cells, the text cells and the marks listed below are read back into the app. Typing over a black formula changes the workbook's own figures, so the app refuses such a workbook on re-import and names the sheet, row and year – change the inputs the row is calculated from instead. For grown dues, set a year's dues by pinning it in row 36.

| Change | Where | Effect |
|---|---|---|
| Any baseline fact | Inputs, column B | Every scenario that follows it, Compare and the charts recalculate |
| A source note | Inputs, column C | Kept on re-import |
| An expense's inputs | Expenses, columns A–H | The year totals and every scenario that keeps the line recalculate |
| Add or remove an expense | Expenses | See [Expenses](#expenses) |
| A Fully Funded Balance | Expenses, the FFB row | Percent funded recalculates for every scenario that follows it |
| Typed dues | Plan sheet, row 5 | That scenario recalculates |
| First-year dues or the annual increase | Plan sheet, rows 34–35 | Every year's grown dues recalculate |
| Pin a year's dues | Plan sheet, row 36 | That year uses the pinned value, later years grow from it |
| Rounding | Plan sheet, row 38 | Grown dues are rounded to whole dollars or keep cents |
| A special assessment | Plan sheet, the assessment list | Row 6 and everything after it recalculate |
| A scenario's own assumption or note | Plan sheet, the assumptions block | That scenario recalculates on its own figure |
| A scenario's own Fully Funded Balance | Plan sheet, the Fully Funded Balance block | That scenario's percent funded recalculates |
| A scenario's expense changes | Plan sheet, the expense changes table | That scenario's operating and reserve totals recalculate |
| A scenario's name or description | Plan sheet, A1 and A2 | Kept on re-import (the sheet tab can be renamed freely) |

To make a scenario follow the baseline again in Excel, put back the formula the export wrote – for example `=Inputs!$B$14` for the interest rate. Any other formula in the assumptions or Fully Funded Balance blocks is refused on re-import. It is simpler to do this in the app.

### What cannot be changed in Excel

**How dues are set (row 33).** Typed and grown dues put formulas in different cells – typed dues make row 5 an input, grown dues make it a formula fed by rows 34–37. Changing the words in row 33 cannot move those formulas, so the sheet would not follow, and the app refuses the workbook on re-import. Change the dues mode in HOAForecaster and export again.

**The horizon.** See [Inputs](#inputs). This applies to a scenario's own start and end year too – its year columns are fixed when the workbook is made.

**Adopted plans.** Change them in the app – start a new scenario from the plan and adopt that.

**The layout of a Plan sheet.** The app finds a Plan sheet's rows by their labels in column A, so inserted rows do no harm. Renaming or deleting a labelled row makes the app refuse the workbook, naming the missing row. Only the rows that row 6's sum adds up are read as assessments – an amount typed below the list, which the sheet itself does not count, is refused rather than read. The same goes for expense change rows outside the rows the scenario's totals add up.

On the Inputs and Expenses sheets, the app finds rows by their labels in column A, so rows can be moved or inserted there as long as the labels are left alone.

## Compare

The top table has one row per summary measure and one column per scenario.

- Dues per unit per month in years 1, 4 and 9
- Total special assessments per unit
- Lowest year-end reserve balance, and its year
- Years below the minimum cushion, years needing an owner vote and years with an operating shortfall
- Reserve balance and percent funded at the end of years 4 and 9 and of the end year
- The first year the percent-funded target is met, or "not by" the scenario's end year
- Owner outlay per unit over the first five years and over the whole horizon
- Extra cost vs current dues over the whole horizon and over the first four years
- Average owner cost per year and average extra cost per year

Below the summary, two tables give year-end reserve balance and percent funded for every year and every scenario. Every figure is pulled from the Plan sheets.

**When the scenarios cover different years** – a scenario with its own horizon, or an adopted plan from an earlier year – the labels count years of each scenario's own projection ("year 1", "year 4", "whole projection") instead of naming calendar years, and a note at the top of the sheet says so. The by-year tables run over every year any of the scenarios covers, with a blank cell where a scenario has no figure for that year. The year 9 rows appear when any scenario runs 9 years or more, with "–" for a shorter one. When every scenario shares the horizon, as in the demo, the labels name the years – "2030", "2027–2042".

## Charts sheet and the shared dollar scale

The Charts sheet stacks the first chart from each Plan sheet – expenses, dues, reserve balance and percent funded – in scenario order. Each chart covers its own scenario's years.

When the app exports, it gives all of these charts the same dollar scale so they compare at a glance. The scale is chosen so that its gridlines line up with the percent axis's 0%, 20%, 40%, 60%, 80% and 100%.

- The step is the smallest round figure – 1, 2, 2.5, 5 or 10 times a power of ten – that reaches the highest value in five steps.
- The top of the dollar axis is five steps.
- If any value is below zero, whole steps are added beneath zero on both axes, so the two zero lines stay level. The percent axis then starts below 0% by 20% for each step.

For the demo project, the values run from about −$56,692 (the lowest balance in Hold then catch up) to about $808,669 (the 2042 balance of the adopted plan). The step is $200,000, so the dollar axis runs from −$200,000 to $1,000,000 and the percent axis from −20% to 100%.

The percent axis always stops at 100%, so a percent funded above 100% runs off the top of the chart.

Without a shared scale – when one of the chosen scenarios has problems in its inputs, or the workbook was made without one, as `reference.xlsx` is – each chart on the Charts sheet picks its own, and the note at the top of the sheet says so.

## Reading a workbook back

HOAForecaster reads a workbook only in its own export layout. It reads the inputs – values, never formulas – and builds a project from them.

| Sheet | What is read |
|---|---|
| Inputs | Column B of each labelled row, and the note in column C |
| Expenses | Each row between the column headings and the operating total that has an item or an amount – its inputs in columns A–I, with the comment on its item as its source. The Fully Funded Balance row and the years above it. The comment on the FFB label |
| Each Plan sheet | A1 and A2, rows 33 and 38, then row 5 for typed dues, or rows 34–36 for grown dues. The assessment list from row 42 down to the "Charts – " label. Below the charts, the assumptions, Fully Funded Balance and expense changes blocks, and on an adopted plan the adoption rows |

A Plan sheet is any sheet other than the five fixed ones whose row 33 is labelled "How dues are set". Method, Compare and Charts are not read. A deleted Plan sheet means a scenario fewer.

In the blocks below a Plan sheet's charts, a cell holding the export's link to the baseline follows the baseline, and a typed figure is the scenario's own. On an adopted plan's sheet the typed figures are its frozen baseline, and its marks say which of them are its own changes.

Re-import brings back everything the app holds for a project except its id, revision, drafts and timestamps – expense frequencies and line identifiers, every scenario's changes, and adoptions with their dates, notes, order and frozen baselines. An expense row whose id was cleared gets a new one (`line-1`, `line-2` and so on), and a scenario's own line without an id gets one too (`own-1` and so on). The imported project is a new project with times of its own.

A workbook read back without edits gives the exported project. The one difference is that numbers pass through Excel's floating-point storage, which keeps about 15 significant digits. The demo project comes back identical.

### What is refused

Every refusal is a plain-language message naming the sheet and, where it can, the row. The workbook is refused when

- the file is larger than 20 MB, is not an `.xlsx` workbook, or is damaged
- it unpacks to more than 20 MB or to more than 2,000 parts, or any part is compressed more than 100 to 1 – the signs of a crafted file
- any sheet runs past 2,000 rows or 200 columns
- the Inputs or Expenses sheet is missing, or one of their labelled rows, or the Expenses totals add up different rows from each other
- a number cell holds text or a formula, or a year, interval or the number of units is not a whole number
- an expense row has no year formulas, sits outside the rows the totals add up, or has a "How often" that is not one of the four
- two expense rows on one sheet share a line id, or an Expenses line id starts with `own-` (kept for scenarios' own lines)
- a labelled row of a Plan sheet is missing, including the headings and totals below the charts
- a Plan sheet's year columns no longer match its start and end year
- row 33 or row 38 of a Plan sheet holds anything but the exported choices
- a calculated row of a Plan sheet was typed over
- an assessment has an amount but no year, or a year but no amount, or lies below the list
- a cell in the assumptions or Fully Funded Balance blocks holds a formula other than the export's link to the baseline
- an expense change row leaves out a line but has no line id
- on an adopted plan, a frozen figure holds a formula, a mark is not one of the exported words, the adoption date is not a date written YYYY-MM-DD, or two adopted plans share an adoption order
- two scenarios have the same name in A1
- a number is so large it cannot be a real amount (10<sup>15</sup> or more)

Once read, the project passes the same checks as one entered in the app (see [Input checks](engine.md#input-checks)), each scenario on its own baseline. Every problem found is listed at once, separated by semicolons, with each scenario's problems prefixed by its name – for example a negative expense, a target above 100%, a missing Fully Funded Balance, or an assessment outside the horizon. A pinned value typed in a column past the last year has no year above it and is ignored.

The reader needs `defusedxml` installed and active, which guards against XML-based attacks. It refuses to load without it.

## Protection against formula injection

Text from a project – the association's name and notes, scenario names and descriptions, expense items, line ids, assessment notes, source notes and adoption notes – is always written as a text cell, never as a formula. Text that starts with `=`, `+`, `-`, `@`, a tab or a carriage return also gets Excel's quote prefix, so it stays text even after someone edits the cell or saves the sheet as CSV. A scenario named `=SUM(A1)` shows those characters and computes nothing.

Scenario names are also cleaned before they become sheet names (see [The sheets, in order](#the-sheets-in-order)), and quoted wherever a formula refers to the sheet.

When a project is read, any text field that holds a control character – anything below a space other than tab, newline and carriage return – is refused.

## For developers

The code is in `src/hoa_workbook/`.

| File | Role |
|---|---|
| `layout.py` | The single source for sheet names, row numbers, labels, column headings and the dropdown texts. The writer and the reader both use it. |
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
- Export raises `ValueError` when the baseline fails its checks, when two scenarios share a name, when `scenario_names` names a scenario the project does not have, or when a chosen scenario's own horizon is impossible.
- `read_workbook(source)` takes a path or the file's bytes and returns a validated `Project`, or raises `WorkbookFormatError` with a plain-language message.

The tests in `tests/workbook/` recalculate exported workbooks in LibreOffice and compare every figure with the engine's, check that export then import gives the same results, open the workbook in Excel on Windows to check for repair prompts, and feed the reader damaged and edited files.
