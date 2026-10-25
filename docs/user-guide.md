# HOAForecaster user guide

HOAForecaster helps a board see where its reserve fund is heading. You enter the building's facts once – the reserve balance, the expenses and the reserve study's figures – and then try out funding plans. For each plan the app shows the reserve balance year by year, how well funded the reserves are, what each owner pays and any year that needs attention.

This guide walks through each screen and then the whole workflow, from a new project to the workbook you hand to the board. The examples use the fictional demo project, Maple Row Condominiums, which the app adds the first time it starts. Its figures are invented.

## Words used in this guide

- **Baseline** – the building's facts and assumptions. There is one per project, and you edit it in place when a fact changes.
- **Scenario** – one funding plan – a path for dues, any special assessments, and anything it assumes differently from the baseline.
- **Adopted plan** – a scenario the board has adopted. It is read-only and keeps the baseline it was adopted against, so its figures never move.
- **Operating expenses** – costs paid from dues every month or year, such as insurance and utilities.
- **Reserve expenses** – one-off or occasional work paid from reserves, such as a roof or a repaint.
- **Fully Funded Balance** – the reserve study's figure for what the fund should hold at the start of each year.
- **Percent funded** – the year-end balance divided by the next year's Fully Funded Balance.
- **Cushion** – the lowest year-end balance the board is comfortable with. A year below it is marked LOW.

## Starting the app

Someone with the app installed starts it with one command (see the [README](../README.md)). It opens in your web browser at http://127.0.0.1:8765/. It runs only on your own computer and sends nothing anywhere.

Your projects are saved as files in the app's data folder on your computer. Leave the app running while you work. To stop it, press Ctrl+C in the window where it was started.

## The screens

### Projects

The first screen lists your projects, with the number of scenarios in each and when it was last saved. Click a project's name to open it.

- **New project** – type the building or association's name and choose Create. The project starts on January 1 of next year and runs 14 years, with the usual assumptions – 3% inflation, 2% interest, a 70% percent-funded target and owner-vote limits of 20% and 5%. Amounts start at zero for you to fill in, and there is one blank scenario. The app takes you straight to the baseline.
- **Import** – choose a project file (.json) saved with Export project, or a workbook (.xlsx) exported from HOAForecaster. Either becomes a new project.

If a file in the data folder cannot be read as a project, the screen names it below the list.

### The project page

This is the home of one project.

**Baseline** – a one-line summary (the years, units, starting balance, current dues and number of expense lines), when it was last changed and the reserve study's source, if you entered one. Choose Edit baseline to change it.

**Scenarios** – a table of every scenario with its key results – the lowest year-end balance and its year, the years below the cushion, percent funded at the end and the first year the target is met. The current adopted plan comes first, marked "Adopted plan" with its adoption date. Then come the working scenarios, then earlier adopted plans, newest first. A scenario that cannot be worked out says "Has problems – open it to fix them". Click a name to open the scenario. Download CSV saves the table.

Below the table are New scenario, Compare scenarios and Charts.

**Export** – choose which scenarios to include (all, by default) and then

- **Excel workbook** – the board's familiar spreadsheet, with live formulas (see [The Excel workbook](workbook.md))
- **Export project** – a copy of the whole project as a file, which Import brings back. Make one before a big change, as a snapshot

**Delete project** – moves the project to the trash folder inside the app's data folder. The app cannot restore it yet, so export it first if you may want it back.

### The baseline

The baseline screen is one long form. Each part follows.

**Project** – the name and free-text notes.

**Horizon** – the start year and end year, 5 to 30 full years. The projection starts on January 1 of the start year. If it is the middle of the year, start next year and enter the balance you expect on January 1. The tables below change shape only once the horizon is 5 to 30 years, and nothing you have entered is thrown away when you shorten it.

**Facts and assumptions** – the starting reserve balance, number of units, current dues per unit per month, operating and reserve inflation, the expense base year (whose dollars the reserve amounts are in – usually the reserve study's year), interest, the cushion, the percent-funded target and the two owner-vote limits. Leave a limit blank for no limit. Each figure has a box for its source – where it came from and when. The source travels into the workbook as a cell comment.

**Expenses** – one row per expense. Choose how often it falls, and the row shows only the boxes that frequency needs.

| How often | Amount | Years | Grows with |
|---|---|---|---|
| Monthly | a month | an optional first and last year – blank means the whole horizon | its own inflation rate, or the operating rate when blank |
| Yearly | a year | as monthly | as monthly |
| Every few years | each time | a first year, the years between, and an optional last year | reserve inflation from the base year |
| Once | the one time | its year | reserve inflation from the base year |

Monthly and yearly amounts are in the dollars of their first year. Once and every-few-years amounts are in the base year's dollars – tick "Already in that year's dollars" when the figure is already a future cost, as a reserve study's yearly totals usually are.

In the demo, management is a yearly $58,000, utilities a monthly $3,100 at their own 3.5%, the landscaping contract runs 2027–2033, the exterior repaint falls every 8 years from 2031 and the boiler once, in 2035.

Use Add expense for a new row, Remove to delete one and Sort by year to order them (lines without a year come first). You can paste rows copied from a spreadsheet – year, amount, description, yes/no for already in that year's dollars, and source – and each becomes a one-off expense.

**Fully Funded Balance by year** – from the reserve study, for every year of the horizon and the year after. Paste a column of amounts to fill down from the box you are in, or paste year and amount pairs.

**Saving** – as you type, the app checks the baseline and lists any problem in plain words, such as "the 2031 expense 'Gate' cannot be negative". It also says which saved scenarios' figures the change would move. Save baseline asks you to confirm, naming those scenarios and any that the edit would leave with problems – they keep their inputs, and you can open them afterwards to fix them. Adopted plans never change. When you change the horizon, scenarios with dues typed for each year are stretched to the new years with their nearest figure.

### A scenario

The scenario screen has the inputs on the left, the live results on the right, and the scenario's changes to the baseline across the bottom. Results update a moment after you stop typing.

**Start from** (new scenarios only) – begin blank, or from any saved scenario, including the adopted plan or an earlier one. Starting from one copies its dues, assessments, rounding, description and changes to the baseline. It does not copy the adoption, and the new scenario runs on today's baseline. Choosing a different starting point replaces what you have typed, after asking.

**Name and description.** Every scenario needs a name of its own.

**Dues per unit per month** – three ways to set them.

- **A first-year figure, then a yearly increase** – for example $650 in 2027, then +4.5% a year.
- **The same, with some years pinned to a figure** – type a figure for any year in the Pinned column. Later years grow from it. The demo's Two-part assessment pins 2032 at $860.
- **Typed for each year** – a figure in every year.

The Resolved column shows the dues each year actually comes to. Grown dues are rounded to whole dollars unless you choose to keep cents. Typed and pinned figures are always used exactly as typed.

**Special assessments** – a year, an amount per unit and a note. Installments are separate rows, such as the demo's $5,000 in 2028 and again in 2029.

**Buttons** – Save, Save as copy (a new scenario from what is on screen, leaving the saved one as it was), Delete, Adopt, Print and Cancel. Adopt works on a saved scenario with no unsaved edits, so save first.

**Results** – the year-by-year Plan table, the same rows as a Plan sheet in the workbook. Inputs are shaded like the spreadsheet's blue-on-yellow cells. "LOW", a needed owner vote and an operating shortfall are shaded as warnings. "Meets target?" shows yes in green and no plainly – not yet reaching the target is normal for years. Hover over a year's operating or reserve expenses to see the lines behind it, or click the figure to list them with their sources. Download CSV saves the table.

Below the table are two charts – expenses, dues, the reserve balance and percent funded, and owner cost per unit with percent funded. Hover for a year's values. Download PNG saves a chart as a picture.

**Changes to the baseline** – anything this scenario assumes differently. Everything here follows the baseline until you set the scenario's own value, so a later baseline edit still reaches the scenario everywhere except those values. Changed values are highlighted, and the heading counts them.

- **Assumptions** – choose Set its own beside any input (the horizon, starting balance, units, current dues, the rates, the base year, cushion, target or a limit), type the scenario's figure and, if you like, its own source. Use baseline puts it back. A limit left blank is this scenario's "no limit".
- **Expenses** – each baseline line can be changed (the scenario then keeps its own full copy, which no longer follows edits to the baseline line), left out, or put back. Add a line of this scenario's own for an expense only it has. Lines added to the baseline later reach the scenario automatically.
- **Fully Funded Balance** – type a figure for any year to replace the baseline's. Blank follows the baseline.

The demo's Insurance shock does all of these – its own 2.5% interest with a source note, no assessment limit, insurance changed to $47,000 a year growing at 8%, the boiler left out, a pool resurfacing of its own every 6 years from 2030, and its own Fully Funded Balance for 2031.

A scenario with its own start or end year runs over its own years – it needs a Fully Funded Balance through its end year and the year after, and its dues and assessments must fall in its years.

**Unsaved edits** – the app keeps your unsaved edits as a draft while you type ("Unsaved edits are kept as a draft"). If you leave the screen, it asks first. If the app or the computer stops, the next time you open the screen it offers to restore the edits or discard them. If the project has been saved since the draft was made, it warns you that restoring replaces those later changes on that screen.

### An adopted plan

An adopted plan opens like a scenario but read-only. A panel at the top says whether it is the adopted plan or an earlier one, with its adoption date and note.

Its figures are worked out on the baseline as it stood when it was adopted, with its own changes applied. The Changes to the baseline section shows that frozen baseline ("As adopted") and highlights the plan's own changes.

- **Start a new scenario from it** – the way to revise the plan. Edit the new scenario and adopt it when the board decides.
- **Un-adopt** – on the current adopted plan only, to correct a mistake. It becomes an ordinary, editable scenario again, with its inputs and changes as they were, running on today's baseline. The plan adopted before it, if any, becomes the adopted plan again.

An adopted plan cannot be renamed or deleted.

### Compare

Compare puts the scenarios side by side. Choose which to show from the scenario list (all, by default, adopted plans included).

- **Summary** – one row per measure, one column per scenario – dues in years 1, 4 and 9, total assessments, the lowest balance and its year, years below the cushion, balance and percent funded at years 4 and 9 and at the end, the first year the target is met, owner outlay over the first five years and the whole horizon, extra cost over current dues, averages, years needing a vote and years with an operating shortfall.
- **Year-end reserve balance by year** and **Percent funded by year** – one column per scenario. LOW years are shaded.

Tick "Show differences" to see each scenario's difference from the first one shown, in green where it is better and red where it is worse. Each table has Download CSV, and Print gives a clean page.

When the scenarios cover different years – one with its own horizon, or an adopted plan from an earlier year – the summary counts years of each scenario's own projection ("year 1", "year 4") instead of naming calendar years. The by-year tables then run over every year any of them covers, blank where a scenario has no figure, and differences compare the same calendar year.

A scenario with problems in its inputs is left out, and the page names it.

### Charts

Charts stacks the first chart of each chosen scenario – reserve expenses, dues and assessments collected, the year-end balance and percent funded with the dashed target line. Every chart uses the same dollar scale, so the scenarios compare at a glance. When the scenarios cover different years, they share one year axis and each is drawn over its own years.

Hover for a year's values. Each chart has Download PNG, and Print prints the page.

## The workflow

### 1. Create or open a project

Open the demo project to explore, or create a new one from the Projects screen. To bring in a project from someone else, use Import with their exported project file or HOAForecaster workbook.

### 2. Enter the baseline

Fill in the horizon, the facts and assumptions, each with its source, then the expenses and the Fully Funded Balance from the reserve study. Enter operating costs as monthly or yearly lines and reserve work as once or every-few-years lines. Fix any problems the screen lists, and save.

Come back whenever a fact changes – a new reserve study, a contractor's estimate, an updated balance. The save confirmation tells you which scenarios will change. Export the project first if you want a snapshot of the old figures.

### 3. Build scenarios

From the project page choose New scenario. Set the dues and any special assessments and watch the results update. Look for LOW years, owner votes and operating shortfalls in the Plan table, and at when percent funded reaches the target.

When a plan depends on a different assumption – a higher insurance quote, a better interest rate, a project the board might defer – put it in Changes to the baseline rather than editing the baseline itself. Only that scenario changes. Save, then use Save as copy or Start from to try variations.

### 4. Compare

Open Compare scenarios to see the summary measures side by side, and Charts to see the balances on one scale. Turn on differences to see how each plan compares with the first.

### 5. Adopt the board's plan

When the board decides, open the chosen scenario, save any edits and choose Adopt. Enter the date it was adopted (today, unless you change it) and a note, such as the meeting and the vote. The scenario becomes the adopted plan, shown first on the project page. Its figures are frozen with today's baseline and do not move when the baseline changes later.

Adopting another scenario later makes that one the adopted plan. The earlier one stays, read-only, as a record of the past decision.

### 6. Revise the plan

To revise the adopted plan, open it and choose Start a new scenario from it. The new scenario has the plan's dues, assessments and changes, running on today's baseline. Edit it, compare it with the adopted plan, and adopt it when the board agrees.

### 7. Export

On the project page, choose the scenarios for the workbook and select Excel workbook. The workbook has the Method, Inputs, Compare, Charts and Expenses sheets and one sheet per scenario, every figure a live formula. It opens in Excel and recalculates when someone edits it. Adopted plans get a protected sheet with their frozen figures.

A board member can change inputs in the workbook and send it back. Import reads it as a new project, and the app explains in plain words anything in it that it cannot accept. See [The Excel workbook](workbook.md) for what can be changed in Excel.

To keep a copy of the whole project, or move it to another computer, use Export project and Import.

To print, use Print on a scenario, Compare or Charts, or download any table as CSV and any chart as a PNG picture.
