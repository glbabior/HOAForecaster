# Changelog

Newest first. Each entry describes what users can now do differently.

## Unreleased

HOAForecaster is now a complete local app. A board member starts it with one command, enters a building's reserve facts in the browser, builds and compares funding plans, adopts the board's plan and exports the board's familiar Excel workbook. Nothing has been released yet, so everything below is new.

### The app

- **One command to start.** `uv run hoaforecaster` builds the screens the first time, opens the app in the browser and adds a fictional demo project, Maple Row Condominiums, to explore. It runs on your own computer only and answers no other computer or web page.
- **Projects saved for you.** Each project is a readable file in your application-data folder, or in a folder you choose with `HOA_DATA_DIR`. Create a project from a name and it starts with the usual assumptions – 3% inflation, 2% interest, a 70% target, owner-vote limits of 20% and 5%.
- **Nothing lost.** Unsaved edits are kept as a draft on every screen and offered back after a crash or a closed window, with a warning if the project was saved since. Leaving a screen with unsaved edits asks first. A save made in another window is never silently overwritten.
- **Snapshots and sharing.** Export project saves the whole project as a file, history included, and Import brings it back as a new project – on the same computer or another. Deleting a project moves it to a trash folder inside the data folder (restoring it from the app is still to come).

### The baseline

- **Edit the building's facts on one screen.** The horizon, balance, units, dues, rates, cushion, target and owner-vote limits, each with a note on where it came from, plus the expense table and the reserve study's Fully Funded Balance. Paste rows from a spreadsheet into either table.
- **Expenses by how often they fall.** Each expense is monthly, yearly, every few years or once. Monthly and yearly lines are the operating costs paid from dues, each with an optional first and last year and its own inflation rate if it needs one – so insurance can rise faster than utilities, and a contract can end and be renewed at a new price. They replace the single operating-cost figure. Every-few-years lines repeat on an interval, such as a repaint every 8 years.
- **See what a change does before saving.** As you type, the screen lists any problem in plain words and names the scenarios whose figures would change. Saving asks you to confirm, and names any scenario the edit would leave with problems. Adopted plans never change.
- **Older project files still open.** A file from before expense frequencies opens with the same figures – its expenses become one-off lines and its operating cost one yearly line – and is saved in the new form.

### Scenarios

- **Build a funding plan and see it live.** Set dues as a first-year figure with a yearly increase, pin any year to a figure, or type every year, and add special assessments in installments. The Plan table, the two charts and the warnings for LOW years, owner votes and operating shortfalls update as you type. Click a year's expenses to see the lines behind them.
- **Change any assumption for one scenario.** A scenario can set its own horizon, balance, units, dues, rates, base year, cushion, target or limits (including "no limit"), change or leave out any expense line, add lines of its own and set its own Fully Funded Balance for any year. Everything else keeps following the baseline, including expenses added to it later. Each change is highlighted and can be put back.
- **Adopt the board's plan.** Adopt a saved scenario with the date and a note on the meeting and vote. The adopted plan is shown first on the project page, is read-only, and keeps the baseline it was adopted against, so its figures never move when the baseline is edited. Adopting another keeps the earlier plan as a record. The current plan can be un-adopted to correct a mistake.
- **Start from any saved scenario.** A new scenario can start blank or from any other – the adopted plan, an earlier one or a working scenario – copying its dues, assessments, rounding, description and changes, and running on today's baseline. This is how to revise an adopted plan.
- **Save as copy and delete.** Save the scenario on screen as a new one, or delete a scenario (but never an adopted plan).

### Comparing

- **Compare side by side.** Choose any scenarios, adopted plans included, and see every summary measure in one table, then year-end balance and percent funded by year. Turn on differences to see each against the first, better in green and worse in red.
- **Scenarios over different years.** When scenarios cover different years, Compare counts years of each projection, runs its by-year tables over every year any of them covers and compares the same calendar year.
- **Charts on one scale.** The Charts screen stacks each scenario's main chart on a shared dollar scale and year axis. Hover for a year's values.
- **Print and download.** Print the scenario, Compare and Charts screens, download any table as CSV and any chart as a PNG.

### The Excel workbook

- **Export the board's workbook.** A project becomes a workbook in the layout of the board's original model – Method, Inputs, Compare, Charts, Expenses and one sheet per chosen scenario. Every result is a live formula, inputs are blue on yellow, flags are colour-coded, source notes are cell comments and each scenario sheet carries its two charts. It recalculates in Excel and LibreOffice to the app's figures and opens in Excel without a repair prompt.
- **Every expense and its frequency on one sheet.** The Expenses sheet lists every line with how often it falls, its years and its identifier, with an operating total and a reserve total for each year.
- **Each scenario's own assumptions.** Below its charts, each scenario sheet shows its assumptions, its Fully Funded Balance and its expense changes – linked to Inputs and Expenses unless the scenario sets its own, which a board member can also change in Excel.
- **Adopted plans in the workbook.** An adopted plan's sheet holds its frozen baseline as typed figures, marks which were the plan's own changes, shows its adoption date and note, and is protected as a reminder that it is read-only.
- **Edit in Excel and read it back.** Change any input in the workbook, add expenses and assessments in its spare rows, and import it as a new project – frequencies, scenario changes and adopted plans included. Edits the app could not read faithfully, such as a formula typed over or a row outside a total, are refused with a plain-language reason naming the sheet and row. Damaged, oversized or suspicious files are refused too.
- **Charts that compare.** The Charts sheet stacks each scenario's main chart on one dollar scale whose gridlines line up with percent funded at 0–100% in 20% steps.
- **Safe text.** Names, descriptions and notes are always written as text, so one starting with `=` can never run as a formula, even after the cell is edited or saved as CSV.

### The figures

- **Year-by-year reserve projection.** For each year the app works out dues collected, operating expenses, the reserve contribution, special assessments, interest, reserve expenses, the ending balance and percent funded. It flags years below the cushion, years that meet the target, years that need an owner vote and years where dues do not cover operating expenses.
- **Owner cost.** For each year it shows what one owner pays in dues and assessments, how much more that is than today's dues, and the running totals.
- **Summary measures for comparing plans.** Dues in years 1, 4 and 9, the lowest balance and when it happens, balance and percent funded at key years, the first year the target is met, owner outlay, extra cost and counts of LOW, vote and shortfall years.
- **Exact money.** Amounts are kept as exact decimals, never as binary floating-point numbers, and project files that contain them are refused.
- **Checked against a spreadsheet.** The demo project's six scenarios – every dues mode, every expense frequency, a scenario with its own changes and an adopted plan – are checked against a workbook that LibreOffice calculates on its own.

See [the user guide](docs/user-guide.md) for the screens, [docs/workbook.md](docs/workbook.md) for the workbook and [docs/engine.md](docs/engine.md) for the formulas and the demo project's figures.
