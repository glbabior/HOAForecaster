# Changelog

Newest first. Each entry describes what users can now do differently.

## Unreleased

The calculation engine – the part that does the arithmetic – and the Excel export are complete. There are no screens yet, so a workbook is made from a project file by a developer, but a board member can already open, read and edit the result.

- **Renamed to HOAForecaster.** The app was previously called HOA Reserve Planner. Exported workbooks name HOAForecaster as their author, and the private data folder is expected at `../HOAForecaster-data`.
- **Excel workbook export.** A project becomes a workbook in the layout of the board's original model – Method, Inputs, Compare, Charts, Expenses and one sheet per scenario, with the scenarios chosen and ordered at export. Every result is a live formula, inputs are blue on yellow, flags are colour-coded and each scenario sheet carries its two charts. The workbook recalculates in LibreOffice to the same figures as the engine and opens in Excel without a repair prompt.
- **Edit the plan in Excel.** Change any baseline fact, expense or Fully Funded Balance, a scenario's typed dues, first-year dues, yearly increase, pinned years or rounding (a dropdown), and add special assessments in the spare rows of each scenario's list. To add an expense, copy a whole expense row. How dues are set stays fixed in Excel, because it decides which cells hold formulas – change it in the app.
- **Charts that compare.** The Charts sheet stacks each scenario's main chart. Given the projection's range, it puts them all on one dollar scale whose gridlines line up with percent funded at 0–100% in 20% steps.
- **Read a workbook back.** An exported workbook, edited or not, reads back into a project – installments and their notes included. Damaged, oversized or suspicious files are refused, and everything read passes the same checks as a project file, with every problem reported in plain language.
- **Safe text.** Names, descriptions and notes are always written as text, so one starting with `=` can never run as a formula, even after the cell is edited or saved as CSV.
- **Stricter project files.** A project file now carries the association's name and notes along with its scenarios. Files with duplicate scenario names, an unknown schema version or control characters in names, descriptions or notes are refused.
- **Year-by-year reserve projection.** Given a building's reserve facts and a funding plan, the engine works out each year's dues collected, operating expenses, reserve contribution, special assessments, interest, reserve expenses, ending balance and percent funded. It flags years below the minimum cushion, years that meet the percent-funded target, years that need an owner vote and years where dues do not cover operating expenses.
- **Owner cost.** For each year it shows what one owner pays in dues and assessments, how much more that is than today's dues, and the running totals.
- **Summary for comparing plans.** Each plan gets the measures the Compare view will show – dues in years 1, 4 and 9, the lowest balance and when it happens, balance and percent funded at key years, the first year the target is met, owner outlay, extra cost and counts of LOW, vote and shortfall years.
- **Three ways to set dues.** Type a figure for every year, give a first-year figure and a yearly increase, or do that and pin any year to a set figure. Grown dues are rounded to whole dollars by default, or cents can be kept.
- **Checks in plain language.** Missing or impossible inputs – a horizon outside 5–30 years, a missing Fully Funded Balance, a negative amount, a rate above 50% – are reported together, each as a sentence.
- **Project files.** A project is a readable JSON file with amounts written as exact decimal strings. Files with binary floating-point numbers are refused, so no amount is ever stored inexactly.
- **A fictional demo project.** Maple Row Condominiums, an invented 24-unit association with four funding plans, ships in `demo/`. Its figures are checked against a spreadsheet that LibreOffice calculates on its own, so the engine is tested against the same formulas as the board's existing workbook.

See [docs/workbook.md](docs/workbook.md) for the workbook and [docs/engine.md](docs/engine.md) for the formulas and the demo project's figures.
