# The Excel workbook

HOAForecaster exports a project as an Excel workbook in the layout of the board's original reserve funding model. Every result is a live formula, so the workbook recalculates on its own when someone edits it. The same workbook can be read back into the app.

This page is for two readers. A board member who receives the workbook can read the first part to learn what each sheet shows and which cells to change. A developer will also want [Reading a workbook back](#reading-a-workbook-back) and [For developers](#for-developers).

The examples use the fictional demo project, Maple Row Condominiums, in `demo/fixtures/project.json`. Its exported workbook is `demo/fixtures/reference.xlsx`.

## The sheets, in order

| Sheet | What it holds |
|---|---|
| Method | What the model is for, how it works, the scenarios with their descriptions, the colour legend, the project notes and the model's limits. Text only. |
| Project | The association's name and the project notes. |
| Compare | The summary measures side by side, one column per scenario, then year-end reserve balance and percent funded by year. |
| Charts | The first chart from each scenario sheet, stacked one above the other. |
| One sheet per scenario | Everything about that scenario (a "Plan sheet") – the year-by-year plan, its dues settings, its special assessments, its yearly dues increases and its two charts, and below them its facts and assumptions, its Fully Funded Balance and its expenses. |

Each scenario is complete in itself, so there is no shared Inputs or Expenses sheet – every Plan sheet carries its own.

The scenario sheets follow in the order chosen for the project on the Scenarios screen. Each is named after its scenario. A name that Excel cannot use as a sheet name is cleaned up – the characters `[ ] : * ? / \` become spaces, apostrophes and spaces at either end are dropped, the name is cut to Excel's limit of 31 characters, and a name already taken gets " (2)", " (3)" and so on. The scenario's full name is always in cell A1 of its sheet.

A scenario with problems in its inputs cannot be exported. The app refuses the export and names it.

## Colours

The workbook keeps the original model's colour code.

- **Blue text on a yellow background** – an input. These are the cells to edit.
- **Black** – a formula on the same sheet.
- **Green** – a value pulled from another sheet (on Compare).
- **Grey** – a line identifier, or the reserve study's figures kept while the Fully Funded Balance is worked out.

On the Plan sheets, the yes/no flag rows are shaded when a flag is raised. LOW and "yes" for an operating shortfall are shaded red, "yes" for an owner vote orange, and "yes" for meeting the target green.

## Project

Column B of row 5 holds the association's name and row 6 the project notes. Both are kept on re-import.

## Plan sheets

A1 holds the scenario's name, A2 its description and A3 a short guide (on an adopted plan, its adoption date). Years run across row 4, starting in column C – the scenario's own years.

The rows below the table depend on how many special assessments and yearly increases the scenario has, so the row numbers from the assessment list down vary from sheet to sheet. The app finds every row by its label, not its number.

### The table

| Row | Label | What it shows |
|---|---|---|
| 5 | Dues per unit per month ($) | Typed in for each year, or worked out from the dues settings below the table (see [Dues settings](#dues-settings)) |
| 6 | Special assessment per unit ($, this year) | The total of this year's entries in the special-assessment list |
| 8 | Total dues collected | Dues × units × 12 |
| 9 | Operating expenses | The operating total of this sheet's expenses |
| 10 | Reserve contribution from dues | Total dues less operating expenses, never below zero |
| 11 | Special assessment to reserves | Assessment per unit × units |
| 12 | Total collected from owners (dues + assessment) | Row 8 + row 11 |
| 13 | Interest earned | Starting balance × the interest rate, or 0 when the starting balance is negative (`MAX(0, start) × rate`) |
| 14 | Reserve expenses (once and every few years) | The reserve total of this sheet's expenses |
| 16 | Starting reserve balance | The starting balance in the first year, then the year before's ending balance |
| 17 | **Ending reserve balance** | Start + contribution + assessment + interest − reserve expenses |
| 18 | Fully Funded Balance (start of next year) | From the sheet's Fully Funded Balance row |
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

Every rate, count and limit in these formulas comes from the sheet's own facts and assumptions, below the charts. The labels for operating expenses, reserve contribution and percent funded carry a cell comment explaining them. These are the same formulas the app's engine uses, described in [engine.md](engine.md). The vote formula uses nested `IF` rather than `AND`, because LibreOffice works out every argument of `AND`, and a blank limit ("no limit") must never reach the arithmetic.

### Dues settings

Below the table are the settings that decide row 5.

| Row | Label | Typed dues | Grown dues |
|---|---|---|---|
| 33 | How dues are set | "typed for each year" | "grown from the first year" |
| 34 | First-year dues (grown dues only) | blank | Input – the start year's dues |
| 35 | Yearly dues increase (grown dues only) | blank | Each year's rate, from the yearly increases list |
| 36 | Pinned dues (blank = grow from the year before) | blank | Input, one cell per year |
| 37 | Dues before rounding | blank | The pinned value if there is one, otherwise the first-year dues in the start year and the year before's figure × (1 + that year's rate) after it |
| 38 | Rounding of grown dues | Input – a dropdown | Input – a dropdown |

**Typed dues** – row 5 is an input in every year. Type each year's dues per unit per month.

**Grown dues** – row 5 is a formula. The start year takes the first-year dues as typed. Each later year takes row 37, rounded to whole dollars when row 38 says "whole dollars". A pinned year takes its pinned value as typed, and the years after it grow from that value at their own rates. Rounding is applied to each year's unrounded figure, so it never builds up from year to year.

To change one year's grown dues, type it into row 36 (pin it) rather than over the formula in row 5.

**Rounding** – row 38 offers "whole dollars" or "none – cents kept". It affects grown dues only. Typed and pinned dues are always used as typed. The dropdown does not stop other text being typed in. The sheet then keeps cents, and the app refuses the workbook on re-import.

### Special assessments

From row 40, the sheet lists its special assessments, one row each, with a note (column A), a year (column C) and an amount per unit (column D), starting in row 42. Several assessments may fall in the same year – row 6 adds them up. Each list ends with five blank yellow rows to fill in.

To add an assessment, fill in a spare yellow row. To add more than the spare rows allow, insert new rows between two yellow rows, so the sum in row 6 stretches to include them. To remove one, clear its year and amount.

Installments stay separate rows and keep their notes when the workbook is read back.

### Yearly dues increases

Below the assessments is the list of yearly increases (spec 5.1), one row each – From (column C), To (column D) and Increase (column E). A period's years are the years whose dues rise by its rate over the year before. A blank From is the start year and a blank To the end year. Each list ends with three blank yellow rows.

Each year's rate in row 35 is a `SUMPRODUCT` over the rows whose years include it. The app makes sure every year after the start falls in exactly one period, so the sum is that period's rate. In the demo, Stepped increases has 7% from 2028 to 2030 and 3.5% from 2031 with a blank To.

For typed dues the list is left blank, since no increase is used.

### Charts

Below the increases, under the label "Charts – " and the scenario name, are two charts covering the scenario's years.

1. **Expenses, dues, reserve balance and percent funded** – reserve expenses, dues + assessments collected (all units) and year-end reserve balance on the left dollar axis. Percent funded and the target, dashed, on the right axis, which runs to 100%.
2. **Owner cost per unit and percent funded** – dues per unit per year and the special assessment per unit, as separate lines, on the left axis. Percent funded and the target on the right.

The charts draw from the Plan sheet's cells, so they redraw when the workbook recalculates. On a Plan sheet, Excel picks each chart's dollar scale.

### Facts and assumptions, below the charts

**This scenario's facts and assumptions.** One row per input – starting reserve balance, start year, end year, number of units, current dues, operating cost inflation, reserve expense inflation, the expense base year, interest, the minimum cushion, the percent-funded target and the two owner-vote limits. Column C holds the value and column D its source note.

For an owner-vote limit, a blank yellow cell means no limit. In the demo, Insurance shock has no assessment limit.

### Fully Funded Balance

**This scenario's Fully Funded Balance.** A row of years ("Start of year") and the **Fully Funded Balance at start of year** row, from column C – the scenario's years and the year after, and any other year the scenario holds (kept so it survives a re-import). A comment on the label records where the figures came from.

The row below, **Fully Funded Balance from**, says which figures are used. It is set in the app, because it decides which cells hold formulas.

- **"the reserve study's figures"** – the Fully Funded Balance row holds the study's figures as inputs.
- **"this sheet's expenses' useful lives"** – each year's figure is a formula over the expense rows below (spec 4.2), and a grey row beneath, "Reserve study's figures (kept, not used while worked out)", holds the typed figures for switching back. In the demo, the sheet "Worked-out Fully Funded Balance" works this way.

Each worked-out figure is one `SUMPRODUCT` over the sheet's expense rows. For each once or every-few-years row with a useful life (the interval for every few years, the Useful life column for once), it adds the row's cost in that year's dollars × its age ÷ its life, where the remaining life is the life when the row is not yet in service, and otherwise the years until it falls due `MOD` the life. An every-few-years row counts only up to its last year. This is the engine's formula worked a second way (see [engine.md](engine.md#step-1--the-fully-funded-balance)).

### Expenses

**This scenario's expenses.** One row per expense, with three spare yellow rows at the end. Columns A–J hold its inputs and the year columns follow from column K.

| Column | Holds |
|---|---|
| A – Item | A description of the expense. A cell comment on it, if any, records the expense's source. |
| B – How often | "monthly", "yearly", "every few years" or "once" (a dropdown). Monthly and yearly lines are operating expenses, paid from dues. Once and every-few-years lines are reserve expenses. |
| C – Amount | A month for monthly lines, a year for yearly lines, each occurrence otherwise. |
| D – Year, or first year | The year of a once line, the first occurrence of an every-few-years line, or the first year of a monthly or yearly line (blank – from the start year). |
| E – Last year | The last year of a repeating line (blank – to the end). |
| F – Every … years | The years between occurrences of an every-few-years line – also its useful life. |
| G – Useful life | A once line's useful life in years, for a worked-out Fully Funded Balance (blank – it counts 0 there). |
| H – Own inflation | A monthly or yearly line's own inflation rate (blank – the operating rate). |
| I – Already in that year's dollars? | For once and every-few-years lines, "yes" or "no". "yes" means the amount is in the dollars of the line's own (first) year – a once line uses it as it stands, and an every-few-years line's later occurrences grow from it at the reserve inflation rate. |
| J – Line id | The line's identifier, in grey. It names the same line in every scenario of the project, so the app can copy a line from one scenario into others. |
| K onward | One column per year of the horizon, each holding the line's amount that year. |

A line's amount in a year is worked out as the app does it (see [engine.md](engine.md#step-3--expense-lines-by-frequency)).

- A monthly or yearly line in a year from its first year to its last – the amount (× 12 for monthly) grown at its own rate, or the operating rate, from its first year (blank – the start year).
- A once line in its year, or an every-few-years line in its first year and every interval after it, up to its last year – the amount grown at the reserve expense inflation rate from the expense base year, or from the line's own (first) year when column I says "yes".
- 0 in every other year, and in every year of a row with a blank How often.

Below the lines are two totals for each year, each a `SUMIF` over the rows by How often.

- **TOTAL operating expenses (monthly and yearly lines)** – which row 9 takes.
- **TOTAL reserve expenses (once and every few years)** – which row 14 takes.

**To add an expense**, fill in a spare row, or – for more – insert rows inside the list and copy a whole existing row into them, so its year formulas come with it, then change its inputs. Rows inserted between two rows of the list are added up by the totals. A copied row may keep its id or have it cleared – either way the app gives it a new one on re-import.

**To remove an expense**, delete its whole row, or clear its inputs.

An expense typed into a row with no year formulas, or below the rows the totals add up, is left out of the workbook's own totals. The app refuses such a workbook on re-import rather than read a figure the workbook itself ignores.

### Adopted plans

An adopted plan's sheet is laid out like any Plan sheet, with these differences.

- A3 says the plan was adopted and on what date, and that it is read-only in the app.
- Below the reserve total are the **Adopted on** date (written as text, YYYY-MM-DD), the **Adoption note** and the **Adoption order (the highest is the current plan)**.
- The sheet is protected, as a reminder that the plan is read-only. There is no password, so nothing is locked away.

In the demo, the sheet "Adopted – two-part assessment" holds the facts it was adopted with – a $172,000 starting balance and 2% interest – no railings or boiler rows, and the date 2026-10-14.

## What you can change in Excel

Only the blue-on-yellow cells and the text cells are read back into the app. Typing over a black formula changes the workbook's own figures, so the app refuses such a workbook on re-import and names the sheet, row and year – change the inputs the row is calculated from instead.

| Change | Where | Effect |
|---|---|---|
| The association's name or notes | Project, column B | Kept on re-import |
| A fact or assumption, or its source note | Plan sheet, the facts block, columns C and D | That scenario recalculates |
| An expense's inputs | Plan sheet, the expenses block, columns A–I | That scenario's totals and everything after them recalculate |
| Add or remove an expense | Plan sheet, the expenses block | See [Expenses](#expenses) |
| A typed Fully Funded Balance | Plan sheet, the Fully Funded Balance row (or the kept row while worked out) | Percent funded recalculates |
| Typed dues | Plan sheet, row 5 | That scenario recalculates |
| First-year dues | Plan sheet, row 34 | Every year's grown dues recalculate |
| A yearly increase | Plan sheet, the increases list | The years it covers, and the years after, recalculate |
| Pin a year's dues | Plan sheet, row 36 | That year uses the pinned value, later years grow from it |
| Rounding | Plan sheet, row 38 | Grown dues are rounded to whole dollars or keep cents |
| A special assessment | Plan sheet, the assessment list | Row 6 and everything after it recalculate |
| A scenario's name or description | Plan sheet, A1 and A2 | Kept on re-import (the sheet tab can be renamed freely) |

A change made on one sheet affects that scenario only. To change a fact in several scenarios, change it on each sheet – or in the app, where "Copy to…" does it in one step.

### What cannot be changed in Excel

**How dues are set (row 33) and where the Fully Funded Balance comes from.** Each decides which cells hold formulas – typed dues make row 5 an input, grown dues make it a formula fed by rows 34–37, and a worked-out Fully Funded Balance is a row of formulas. Changing the words cannot move those formulas, so the sheet would not follow, and the app refuses the workbook on re-import. Change them in HOAForecaster and export again.

**The horizon.** The year columns are fixed when the workbook is made, so a new start or end year in the facts block changes nothing in the table. Change the horizon in HOAForecaster and export again. If a Plan sheet's start or end year no longer matches its year columns, the app refuses the workbook on re-import and says so.

**Adopted plans.** Change them in the app – copy the plan as a new scenario and adopt that.

**The layout of a Plan sheet.** The app finds every row by its label in column A, so inserted rows do no harm. Renaming or deleting a labelled row or a block heading makes the app refuse the workbook, naming the missing row.

## Compare

The top table has one row per summary measure and one column per scenario.

- Dues per unit per month in years 1, 4 and 9 and the last year
- Total special assessments per unit
- Lowest year-end reserve balance, and its year
- Years below the minimum cushion, years needing an owner vote and years with an operating shortfall
- Reserve balance and percent funded at the end of years 4 and 9 and of the last year
- The first year the percent-funded target is met, or "not by" the scenario's end year
- Owner outlay per unit over the first five years and over the whole horizon
- Extra cost vs current dues over the whole horizon and over the first four years
- Average owner cost per year and average extra cost per year

Below the summary, two tables give year-end reserve balance and percent funded for every year and every scenario. Every figure is pulled from the Plan sheets.

**When the scenarios cover different years** – an adopted plan from an earlier year, say – the labels count years of each scenario's own projection ("year 1", "year 4", "whole projection") instead of naming calendar years, and a note at the top of the sheet says so. The by-year tables run over every year any of the scenarios covers, with a blank cell where a scenario has no figure for that year. The year 9 rows appear when any scenario runs 9 years or more, with "–" for a shorter one. When every scenario shares the horizon, as in the demo, the labels name the years – "2030", "2027–2042".

## Charts sheet and the shared dollar scale

The Charts sheet stacks the first chart from each Plan sheet – expenses, dues, reserve balance and percent funded – in scenario order. Each chart covers its own scenario's years.

When the app exports, it gives all of these charts the same dollar scale so they compare at a glance. The scale is chosen so that its gridlines line up with the percent axis's 0%, 20%, 40%, 60%, 80% and 100%.

- The step is the smallest round figure – 1, 2, 2.5, 5 or 10 times a power of ten – that reaches the highest value in five steps.
- The top of the dollar axis is five steps.
- If any value is below zero, whole steps are added beneath zero on both axes, so the two zero lines stay level. The percent axis then starts below 0% by 20% for each step.

For the demo project, the values run from about −$55,201 (the lowest balance in Hold then catch up) to about $808,669 (the 2042 balance of the adopted plan). The step is $200,000, so the dollar axis runs from −$200,000 to $1,000,000 and the percent axis from −20% to 100%.

The percent axis always stops at 100%, so a percent funded above 100% runs off the top of the chart.

Without a shared scale – a workbook made without one, as `reference.xlsx` is – each chart on the Charts sheet picks its own, and the note at the top of the sheet says so.

## Reading a workbook back

HOAForecaster reads a workbook only in its own export layout. It reads the inputs – values, never formulas – and builds a new project from them.

| Sheet | What is read |
|---|---|
| Project | The name and notes in column B, by their labels |
| Each Plan sheet | A1 and A2. Rows 33 and 38, then row 5 for typed dues, or row 34, the yearly increases list and row 36 for grown dues. The assessment list. Below the charts, the facts block (values and notes), the Fully Funded Balance and its mode row, the expense rows the totals add up (with the comment on each item as its source), and on an adopted plan the adoption rows |

A Plan sheet is any sheet other than Method, Project, Compare and Charts with a row labelled "How dues are set". Method, Compare and Charts are not read. A deleted Plan sheet means a scenario fewer.

Each label is looked for only in its own part of the sheet – the table's rows from the top, each block below the charts after the one before, the totals as the last row with their label – so an expense or note worded like a label never stands in for it.

Re-import brings back everything the app holds for a project except its id, revision and timestamps – every scenario's facts and assumptions, Fully Funded Balance and its mode, expenses with their frequencies, useful lives and line ids, dues, increases and assessments, and adoptions with their dates, notes and order. A line copied in Excel with its id kept, or with the id cleared, gets a new one – the first `line-N` no sheet of the workbook uses. The imported project is a new project with times of its own.

A workbook read back without edits gives the exported project. The one difference is that numbers pass through Excel's floating-point storage, which keeps about 15 significant digits. The demo project comes back identical.

A workbook exported before yearly increases had periods, with one "Annual dues increase", reads as one increase over every year. One exported before the Fully Funded Balance could be worked out, with no mode row, reads as the study's figures.

### What is refused

Every refusal is a plain-language message naming the sheet and, where it can, the row. The workbook is refused when

- the file is larger than 20 MB, is not an `.xlsx` workbook, or is damaged
- it unpacks to more than 20 MB or to more than 2,000 parts, or any part is compressed more than 100 to 1 – the signs of a crafted file
- any sheet runs past 2,000 rows or 200 columns
- it was exported before each scenario held its own facts (an Inputs and an Expenses sheet, no Project sheet) – import that version's project file instead
- the Project sheet or one of its rows is missing, or there are no scenario sheets
- a labelled row or block heading of a Plan sheet is missing
- a Plan sheet's horizon is not 5–30 years, or its year columns no longer match its start and end year
- row 33, row 38 or the Fully Funded Balance mode row holds anything but the exported choices
- a calculated row of a Plan sheet was typed over, including grown dues and their yearly rate
- a worked-out Fully Funded Balance was typed over
- a fact, a source note or a typed Fully Funded Balance holds a formula
- a number cell holds text, or a year, interval, useful life or the number of units is not a whole number
- the yearly increases list or its formula was changed, or an increase sits outside the rows the formula adds up
- an assessment has an amount but no year, or a year but no amount, or lies below the list
- an expense row has no year formulas, sits outside the rows the totals add up, or has a How often that is not one of the four
- the operating and reserve totals add up different rows
- on an adopted plan, an adoption row is missing, the date is not text written YYYY-MM-DD, the order is not a whole number from 1 to 10,000, or the note runs past 2,000 characters
- two scenarios have the same name in A1, or two adopted plans share an adoption order
- a number is so large it cannot be a real amount (10<sup>15</sup> or more)

Once read, the project passes the same checks as one entered in the app (see [Input checks](engine.md#input-checks)). Every problem found is listed at once, separated by semicolons, with each scenario's problems prefixed by its name – for example a negative expense, a target above 100%, a missing Fully Funded Balance, a gap between yearly increases, or an assessment outside the horizon. A pinned value typed in a column past the last year has no year above it and is ignored.

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
    for y in run(s).years
    for v in (y.expenses, y.total_from_owners, y.ending_balance)
]
data = export_workbook(project, Path("maple-row.xlsx"), dollar_axis=(min(values), max(values)))
assert read_workbook(Path("maple-row.xlsx")) == project
```

- `export_workbook(project, path=None, scenario_names=None, dollar_axis=None)` returns the workbook's bytes, and also writes them to `path` when one is given. `build_workbook` takes the same arguments without `path` and returns the `openpyxl` workbook.
- `scenario_names` picks and orders the scenarios to include. By default all are included, in the project's order.
- `dollar_axis` is the (lowest, highest) dollar value for the Charts sheet's shared scale. The exporter never runs the engine, so the caller works it out from the engine's results, as above.
- Export raises `ValueError` when two scenarios share a name, when `scenario_names` names a scenario the project does not have or none at all, or when a chosen scenario fails its checks (the message names it).
- `read_workbook(source)` takes a path or the file's bytes and returns a validated `Project`, or raises `WorkbookFormatError` with a plain-language message.

The tests in `tests/workbook/` recalculate exported workbooks in LibreOffice and compare every figure with the engine's, check that export then import gives the same project, open the workbook in Excel on Windows to check for repair prompts, and feed the reader damaged and edited files.
