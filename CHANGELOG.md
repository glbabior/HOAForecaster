# Changelog

Newest first. Each entry describes what users can now do differently.

## Unreleased

Nothing has been released yet. The entries below follow the app as it was built, newest first, each dated and named for the version of the requirements it brought in.

### November 1, 2026 – Compare's extra cost

- **Extra cost says what it is measured against.** Compare shows each scenario's current dues in a row just above the extra-cost rows, and when every shown scenario has the same current dues the labels name them – "Extra cost per unit over today's $560 a month, 2027–2030" in the demo. A note under the summary explains that extra cost is what an owner pays above today's dues held flat, and that a negative figure is a saving.

### October 31, 2026 – a new look

- **Light screens, with a dark switch.** The screens are light, with colour, cards and clearer type. The **Dark screens** switch at the top right gives light text on a dark background, and the browser remembers the choice.
- **A bar of sections across the top.** Inside a project, its name and its sections – Scenarios, Compare, Charts and Export – sit in a bar at the top of every screen.
- **A scenario's screens as tabs.** Results, Facts and assumptions, Expenses, Fully Funded Balance, Dues and Special assessments are tabs under the scenario's name.
- **Project cards.** The Projects screen shows each project as a card, with a Sort choice – last saved, name or number of scenarios.
- **Start from a card.** The new-scenario screen shows "A blank scenario" and each scenario as a card to choose from, the adopted plan first.
- **Downloads as links.** Download CSV and Download PNG sit as links above their table or chart.

### October 31, 2026 – requirements v1.9

- **Already-inflated costs that repeat.** An every-few-years cost marked as already inflated is in its first year's dollars, and each repeat grows from there with reserve inflation – before, every repeat was charged the same amount. The Expenses screen asks for the year the amount is priced in.
- **No interest on a negative balance.** While the reserve balance is negative, no interest is earned or charged. The figures of the demo's scenarios that go negative change accordingly.

### October 28, 2026 – requirements v1.8

- **Dues increases by period.** Grown dues can rise by different amounts for stretches of years – for example +7% a year for 2028–2030, then +3.5%. The Dues screen has a Yearly increases table with From and To years, names any year left out or covered twice, and still lets you pin any year. The workbook carries the same list.
- **The board's order for scenarios.** Move up and Move down on Scenarios, and arrows in Compare's column headings, set the order every screen and the workbook follow. On Compare the first scenario is the one differences are measured from, so any scenario can be the yardstick.
- **Compare names its yardsticks.** When the scenarios share a cushion and target, Compare's labels name them, and adds the last year's dues. Negative balances and percent funded are shaded like a LOW year, and each difference sits on its own line under the figure.
- **Save Compare as a PDF.** Save as PDF… prints the comparison with the project's name and the date, its tables running across pages as needed.
- **Every-few-years costs in year order.** The every-few-years table numbers its lines and lists each repeat in the projection, read-only, with its cost in that year's dollars, all in year order.
- **Owner cost on two lines.** The owner cost chart, on screen and in the workbook, draws dues and the special assessment as separate lines, and the Results headline shows them separately too.
- **The Fully Funded Balance explained.** Its screen opens with a short explanation of what the figure means and why percent funded matters.
- **Saving survives a restart.** A page opened before the app was restarted keeps saving edits.

### October 27, 2026 – requirements v1.7

- **Work out the Fully Funded Balance.** A scenario can work its Fully Funded Balance out from its expenses – each reserve expense's cost times how far it is through its useful life – instead of typing the reserve study's figures. A one-time cost can carry a useful life; an every-few-years cost's interval is its life. The typed figures are kept for switching back, and the workbook works the figures out with its own formulas.
- **Results in two parts.** The Results table shows the headline figures first and the rest in a details table that opens beneath. Its labels name the scenario's own cushion and target.
- **Sort tables by their headings.** Click a heading to sort, again to reverse, a third time to put it back – on projects, scenarios, Compare's by-year tables, expenses, the Fully Funded Balance, dues and assessments. Sorting never changes the saved order.
- **Expenses by kind.** Monthly, yearly, every-few-years and one-time costs each have a table of their own with only the boxes they need.
- **Rename from any screen.** Rename… on a scenario changes its name and keeps its history.

### October 27, 2026 – requirements v1.6

- **Each scenario complete in itself.** The shared baseline is gone. Every scenario holds its own facts and assumptions, expenses, Fully Funded Balance, dues and special assessments, so each says exactly what it assumes.
- **Copy to other scenarios.** A figure with its source note, an expense line or the whole Fully Funded Balance can be copied into chosen scenarios in one step – the way to bring a new reserve study or balance into several plans.
- **Every edit saves itself.** There is no Save button. An entry that is not yet a usable number is listed and saved once fixed, and leaving with one asks first.
- **A scenario's own screens.** Opening a scenario gives it six screens – Results, Facts and assumptions, Expenses, Fully Funded Balance, Dues and Special assessments – with key results beside the inputs.
- **Start blank or as a copy.** A new scenario starts from the usual assumptions or as a copy of any scenario, the adopted plan included.
- **Adopted plans are simply read-only.** An adopted plan keeps its own inputs, so nothing is frozen separately.
- **The workbook carries each scenario's inputs.** A Project sheet holds the name and notes, and each scenario's sheet holds its facts and assumptions, Fully Funded Balance and expenses below its charts. A workbook in the earlier layout is refused with a plain message – its project file still imports.
- **Older project files still open.** Files from earlier versions open with the same figures, each scenario given the facts it ran on, and are saved in the new form.
- **No more drafts.** With every edit saved as it is made, the draft and restore screens are gone. Deleting a project from the app is not offered in this version.

### October 19–25, 2026 – requirements v1.0 to v1.5

HOAForecaster became a complete local app. A board member starts it with one command, enters a building's reserve facts in the browser, builds and compares funding plans, adopts the board's plan and exports the board's familiar Excel workbook. This is how it worked at v1.5 – several parts were replaced from v1.6 on, as the entries above describe.

#### The app

- **One command to start.** `uv run hoaforecaster` builds the screens the first time, opens the app in the browser and adds a fictional demo project, Maple Row Condominiums, to explore. It runs on your own computer only and answers no other computer or web page.
- **Projects saved for you.** Each project is a readable file in your application-data folder, or in a folder you choose with `HOA_DATA_DIR`. Create a project from a name and it starts with the usual assumptions – 3% inflation, 2% interest, a 70% target, owner-vote limits of 20% and 5%.
- **Nothing lost.** Unsaved edits are kept as a draft on every screen and offered back after a crash or a closed window, with a warning if the project was saved since. Leaving a screen with unsaved edits asks first. A save made in another window is never silently overwritten.
- **Snapshots and sharing.** Export project saves the whole project as a file, history included, and Import brings it back as a new project – on the same computer or another. Deleting a project moves it to a trash folder inside the data folder (restoring it from the app is still to come).

#### The baseline

- **Edit the building's facts on one screen.** The horizon, balance, units, dues, rates, cushion, target and owner-vote limits, each with a note on where it came from, plus the expense table and the reserve study's Fully Funded Balance. Paste rows from a spreadsheet into either table.
- **Expenses by how often they fall.** Each expense is monthly, yearly, every few years or once. Monthly and yearly lines are the operating costs paid from dues, each with an optional first and last year and its own inflation rate if it needs one – so insurance can rise faster than utilities, and a contract can end and be renewed at a new price. They replace the single operating-cost figure. Every-few-years lines repeat on an interval, such as a repaint every 8 years.
- **See what a change does before saving.** As you type, the screen lists any problem in plain words and names the scenarios whose figures would change. Saving asks you to confirm, and names any scenario the edit would leave with problems. Adopted plans never change.
- **Older project files still open.** A file from before expense frequencies opens with the same figures – its expenses become one-off lines and its operating cost one yearly line – and is saved in the new form.

#### Scenarios

- **Build a funding plan and see it live.** Set dues as a first-year figure with a yearly increase, pin any year to a figure, or type every year, and add special assessments in installments. The Plan table, the two charts and the warnings for LOW years, owner votes and operating shortfalls update as you type. Click a year's expenses to see the lines behind them.
- **Change any assumption for one scenario.** A scenario can set its own horizon, balance, units, dues, rates, base year, cushion, target or limits (including "no limit"), change or leave out any expense line, add lines of its own and set its own Fully Funded Balance for any year. Everything else keeps following the baseline, including expenses added to it later. Each change is highlighted and can be put back.
- **Adopt the board's plan.** Adopt a saved scenario with the date and a note on the meeting and vote. The adopted plan is shown first on the project page, is read-only, and keeps the baseline it was adopted against, so its figures never move when the baseline is edited. Adopting another keeps the earlier plan as a record. The current plan can be un-adopted to correct a mistake.
- **Start from any saved scenario.** A new scenario can start blank or from any other – the adopted plan, an earlier one or a working scenario – copying its dues, assessments, rounding, description and changes, and running on today's baseline. This is how to revise an adopted plan.
- **Save as copy and delete.** Save the scenario on screen as a new one, or delete a scenario (but never an adopted plan).

#### Comparing

- **Compare side by side.** Choose any scenarios, adopted plans included, and see every summary measure in one table, then year-end balance and percent funded by year. Turn on differences to see each against the first, better in green and worse in red.
- **Scenarios over different years.** When scenarios cover different years, Compare counts years of each projection, runs its by-year tables over every year any of them covers and compares the same calendar year.
- **Charts on one scale.** The Charts screen stacks each scenario's main chart on a shared dollar scale and year axis. Hover for a year's values.
- **Print and download.** Print the scenario, Compare and Charts screens, download any table as CSV and any chart as a PNG.

#### The Excel workbook

- **Export the board's workbook.** A project becomes a workbook in the layout of the board's original model – Method, Inputs, Compare, Charts, Expenses and one sheet per chosen scenario. Every result is a live formula, inputs are blue on yellow, flags are colour-coded, source notes are cell comments and each scenario sheet carries its two charts. It recalculates in Excel and LibreOffice to the app's figures and opens in Excel without a repair prompt.
- **Every expense and its frequency on one sheet.** The Expenses sheet lists every line with how often it falls, its years and its identifier, with an operating total and a reserve total for each year.
- **Each scenario's own assumptions.** Below its charts, each scenario sheet shows its assumptions, its Fully Funded Balance and its expense changes – linked to Inputs and Expenses unless the scenario sets its own, which a board member can also change in Excel.
- **Adopted plans in the workbook.** An adopted plan's sheet holds its frozen baseline as typed figures, marks which were the plan's own changes, shows its adoption date and note, and is protected as a reminder that it is read-only.
- **Edit in Excel and read it back.** Change any input in the workbook, add expenses and assessments in its spare rows, and import it as a new project – frequencies, scenario changes and adopted plans included. Edits the app could not read faithfully, such as a formula typed over or a row outside a total, are refused with a plain-language reason naming the sheet and row. Damaged, oversized or suspicious files are refused too.
- **Charts that compare.** The Charts sheet stacks each scenario's main chart on one dollar scale whose gridlines line up with percent funded at 0–100% in 20% steps.
- **Safe text.** Names, descriptions and notes are always written as text, so one starting with `=` can never run as a formula, even after the cell is edited or saved as CSV.

#### The figures

- **Year-by-year reserve projection.** For each year the app works out dues collected, operating expenses, the reserve contribution, special assessments, interest, reserve expenses, the ending balance and percent funded. It flags years below the cushion, years that meet the target, years that need an owner vote and years where dues do not cover operating expenses.
- **Owner cost.** For each year it shows what one owner pays in dues and assessments, how much more that is than today's dues, and the running totals.
- **Summary measures for comparing plans.** Dues in years 1, 4 and 9, the lowest balance and when it happens, balance and percent funded at key years, the first year the target is met, owner outlay, extra cost and counts of LOW, vote and shortfall years.
- **Exact money.** Amounts are kept as exact decimals, never as binary floating-point numbers, and project files that contain them are refused.
- **Checked against a spreadsheet.** The demo project's scenarios – every dues mode, every expense frequency, a scenario with its own changes and an adopted plan – are checked against a workbook that LibreOffice calculates on its own.

See [the user guide](docs/user-guide.md) for the screens, [docs/workbook.md](docs/workbook.md) for the workbook and [docs/engine.md](docs/engine.md) for the formulas and the demo project's figures.
