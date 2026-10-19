# Changelog

Newest first. Each entry describes what users can now do differently.

## Unreleased

The calculation engine – the part that does the arithmetic – is complete. There are no screens or Excel export yet, so there is nothing for a board member to open. What exists now is the foundation they will sit on.

- **Year-by-year reserve projection.** Given a building's reserve facts and a funding plan, the engine works out each year's dues collected, operating expenses, reserve contribution, special assessments, interest, reserve expenses, ending balance and percent funded. It flags years below the minimum cushion, years that meet the percent-funded target, years that need an owner vote and years where dues do not cover operating expenses.
- **Owner cost.** For each year it shows what one owner pays in dues and assessments, how much more that is than today's dues, and the running totals.
- **Summary for comparing plans.** Each plan gets the measures the Compare view will show – dues in years 1, 4 and 9, the lowest balance and when it happens, balance and percent funded at key years, the first year the target is met, owner outlay, extra cost and counts of LOW, vote and shortfall years.
- **Three ways to set dues.** Type a figure for every year, give a first-year figure and a yearly increase, or do that and pin any year to a set figure. Grown dues are rounded to whole dollars by default, or cents can be kept.
- **Checks in plain language.** Missing or impossible inputs – a horizon outside 5–30 years, a missing Fully Funded Balance, a negative amount, a rate above 50% – are reported together, each as a sentence.
- **Project files.** A project is a readable JSON file with amounts written as exact decimal strings. Files with binary floating-point numbers are refused, so no amount is ever stored inexactly.
- **A fictional demo project.** Maple Row Condominiums, an invented 24-unit association with four funding plans, ships in `demo/`. Its figures are checked against a spreadsheet that LibreOffice calculates on its own, so the engine is tested against the same formulas as the board's existing workbook.

See [docs/engine.md](docs/engine.md) for the formulas and the demo project's figures.
