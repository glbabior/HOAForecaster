# HOAForecaster user guide

HOAForecaster helps a board see where its reserve fund is heading. You enter the building's facts – the reserve balance, the expenses and the reserve study's figures – into a scenario, a funding plan with its dues and any special assessments. Then you copy it into other scenarios that try something different. For each one the app shows the reserve balance year by year, how well funded the reserves are, what each owner pays and any year that needs attention.

This guide walks through each screen and then the whole workflow, from a new project to the workbook you hand to the board. The examples use the fictional demo project, Maple Row Condominiums, which the app adds the first time it starts. Its figures are invented.

## Words used in this guide

- **Project** – one building or association.
- **Scenario** – one funding plan, complete in itself. It holds its own facts and assumptions, its expenses, its Fully Funded Balance, its dues each year and any special assessments. Nothing is shared between scenarios, so each says exactly what it assumes.
- **Adopted plan** – a scenario the board has adopted. It is read-only, so its figures never change.
- **Operating expenses** – costs paid from dues every month or year, such as insurance and utilities.
- **Reserve expenses** – one-time or occasional work paid from reserves, such as a roof or a repaint.
- **Fully Funded Balance** – what the fund should hold at the start of each year, from the reserve study or worked out by the app.
- **Percent funded** – the year-end balance divided by the next year's Fully Funded Balance.
- **Cushion** – the lowest year-end balance the board is comfortable with. A year below it is marked LOW.

## Starting the app

Someone with the app installed starts it with one command, or on Windows by double-clicking `HOAForecaster.bat` (see the [README](../README.md)). It opens in your web browser at http://127.0.0.1:8765/. It runs only on your own computer and sends nothing anywhere.

Your projects are saved as files in the app's data folder on your computer. Leave the app running while you work. To stop it, press Ctrl+C in the window where it was started, or close that window.

## Saving

There is no Save button. Every edit is saved by itself a moment after you stop typing, and the note beside a scenario's name says "Saving…" and then "All changes saved".

An entry that is not yet a usable number or year – "12,5x", say, or a year still being typed – is not saved. The screen lists it under "These entries are not usable numbers or years yet", and the note says "Not saved yet". It is saved as soon as you fix it. The same goes for a scenario name that is blank or already taken. If you try to leave the screen with such an entry, the app asks first, because the entry would be lost. If a save fails, the screen says so and offers "Try saving again".

A scenario can have other problems – a missing Fully Funded Balance, say, or a negative expense. It is still saved, and lists its problems ("Fix these to see results") until they are fixed.

## Around the screens

Across the top of every screen is the **HOAForecaster** name, which takes you back to your projects, and on the right two controls.

- **Dark screens** – a switch for light text on a dark background. Your browser remembers the choice.
- **Restart** – stops the app and starts it again, then reloads the page. You only need it after the app's code has been updated. Your edits are already saved.

Inside a project, a second bar shows the project's name and its four sections – **Scenarios**, **Compare**, **Charts** and **Export**. A line of links above each screen's title (Projects › Maple Row Condominiums › Scenarios) takes you back up.

Many tables can be sorted by clicking a column heading – once for one direction, again for the other, a third time to put it back. Sorting changes only what you see, never the saved order. Long tables scroll inside their own box with the heading row held in place.

**Download CSV** above a table saves it as a spreadsheet file, and **Download PNG** above a chart saves it as a picture.

## The screens

### Projects

The first screen shows a card for each project, with the number of scenarios in it and when it was last saved. Click a project's name to open it. **Sort** orders the cards by when they were last saved (newest first), by name, or by number of scenarios.

- **New project** – type the building or association's name and choose Create. The project starts with one scenario, "First scenario", on January 1 of next year and running 14 years, with the usual assumptions – 3% inflation, 2% interest, a 70% percent-funded target and owner-vote limits of 20% and 5%. Amounts start at zero for you to fill in. The app takes you straight to its Facts and assumptions.
- **Import** – choose a project file (.json) saved from Export, or a workbook (.xlsx) exported from HOAForecaster. Either becomes a new project.

If a file in the data folder cannot be read as a project, the screen names it below the cards.

### Scenarios

This is the home of one project. It lists every scenario with its key results – the lowest year-end balance and its year, the years below the cushion, percent funded at the end, the first year the target is met and when it was last changed. A scenario's description is shown under its name. The adopted plan is marked "Adopted plan" with its adoption date, and earlier adopted plans "Earlier adopted plan". A scenario that cannot be worked out says "Has problems – open it to fix them". Click a name to open the scenario.

The list is in the board's order, which every other screen and the workbook follow. Use the ↑ and ↓ buttons in the Order column to move a scenario up or down. While a heading sorts the table, the buttons are off – click the sorted heading until the table is back in order. Moving a scenario does not change it, so even an adopted plan can be moved.

**New scenario** opens the new-scenario screen.

Below the list, **Project** holds the project's name and notes. They save as you type.

At the bottom, **Delete this project…** asks first, then moves the project to the trash folder inside the app's data folder and returns to your projects. The app cannot yet bring a deleted project back, so export it first if you may want it again.

### New scenario

**Start from** shows a card for each choice – "A blank scenario" and every scenario in the project, the adopted plan first. A copy takes all of that scenario's inputs – its facts and assumptions, expenses, Fully Funded Balance, dues and special assessments – but not its adoption. A blank scenario starts from the usual assumptions.

Give it a **Name** (a copy of Dues only is offered "Dues only – copy") and choose **Create**. A copy opens on its Results, ready to change and compare. A blank scenario opens on Facts and assumptions, ready for the building's figures.

### A scenario

A scenario's name is the title, with its six screens as tabs underneath – **Results**, **Facts and assumptions**, **Expenses**, **Fully Funded Balance**, **Dues** and **Special assessments**. Your edits carry across the tabs and save themselves.

The buttons beside the name are

- **Copy as a new scenario** – opens the new-scenario screen with this scenario chosen
- **Adopt…** – make it the board's adopted plan (see [Adopting the plan](#5-adopt-the-boards-plan))
- **Rename…** – give it a new name. Press Enter or choose Rename to confirm
- **Delete…** – remove it from the project, after asking
- **Print**

Every inputs screen shows key results beside the inputs – the lowest balance, percent funded at the end, the first year the target is met, the years below the cushion and the years needing a vote – so you see the effect of each edit. On Expenses they sit above the tables. **All results** goes to Results.

#### Results

The year-by-year Plan table, the same figures as a Plan sheet in the workbook, in two parts.

- **Headline figures** – dues per unit per month, the special assessment per unit, operating and reserve expenses, the ending reserve balance, percent funded, the owner's dues for the year and "Below cushion ($75,000)?" – named with the scenario's own cushion.
- **Details** (click to open) – total dues collected, the reserve contribution from dues, the assessment to reserves, the total from owners, interest, the starting balance, next year's Fully Funded Balance, "Meets target (60.0% funded)?", "Needs owner vote?", "Operating shortfall?", the owner's dues and assessment together, the increase over current dues, the running totals and the target.

Dues and assessments are shaded like the spreadsheet's blue-on-yellow inputs. LOW, a needed owner vote and an operating shortfall are shaded as warnings. "Meets target?" shows yes in green and no plainly – not yet reaching the target is normal for years. Hover over a year's operating or reserve expenses to see the lines behind it, or click the figure to list them with their sources. Download CSV saves every row of both tables.

Below the table are two charts – expenses, dues, the reserve balance and percent funded, and owner cost per unit (dues and any assessment as separate lines) with percent funded. The target is the dashed line. Hover for a year's values.

#### Facts and assumptions

The scenario's **Name** and **Description**, then its figures in groups.

- **The years it covers** – the start year and end year, 5 to 30 full years. The projection starts on January 1 of the start year. If it is the middle of the year, start next year and enter the balance you expect on January 1.
- **The reserve fund** – the starting reserve balance, the interest it earns, the minimum working cushion and the percent-funded target.
- **Owners and dues** – the number of units and the current dues per unit per month (what each unit pays today).
- **Inflation** – operating cost inflation, reserve expense inflation and the expense base year – the year whose prices the reserve amounts are in, usually the reserve study's year.
- **When owners must vote** – the largest dues increase and the largest special assessment the board may make without a vote. Leave one blank for no limit.

Each figure has a box for its source note – where it came from and when. Notes are optional and travel into the exported workbook.

**Copy to…** beside a figure puts that figure and its note into other scenarios – a new balance or a revised interest rate, for example (see [Copying into other scenarios](#copying-into-other-scenarios)).

Changing the start or end year reshapes the scenario's tables once the horizon is 5 to 30 years. Nothing you have entered is thrown away when you shorten it, and dues typed for each year are stretched to new years with the nearest figure.

#### Expenses

Expenses are in four tables, one for each way an expense falls. Each table opens and closes, and shows only the boxes its kind needs.

| Table | Amount | Years | Grows with |
|---|---|---|---|
| Monthly costs | a month | an optional first and last year – blank means the whole projection | its own inflation rate, or operating inflation when blank |
| Yearly costs | a year | as monthly | as monthly |
| Every few years | each time | a first year, the years between (also its useful life) and an optional last year | reserve inflation from the base year |
| One-time costs | the one time | its year, and an optional useful life | reserve inflation from the base year |

Monthly and yearly amounts are in the dollars of their first year (blank – the start year). Every-few-years and one-time amounts are in the base year's dollars. Tick **Already inflated?** when an amount is already a future cost, as a reserve study's yearly totals usually are. A one-time cost is then used as it stands. An every-few-years cost is in its first year's dollars, and each repeat grows from there with reserve inflation – so enter as its first year the year the amount is priced in.

In the demo, management is a yearly $58,000, utilities a monthly $3,100 at their own 3.5%, the landscaping contract runs 2027–2033, the exterior repaint falls every 8 years from 2031 and the boiler once, in 2035.

The every-few-years table numbers its lines and, with **Show each one's repeats** ticked, lists every later occurrence in the projection in year order, read-only, with its cost in that year's dollars ("Repeat of #1 – Exterior repaint").

Each row has a **How often** choice – choosing another moves the line to that table – then **Copy to…** and **Remove**. Each table has an Add button, and **Sort by year** puts its lines in year order. You can paste rows copied from a spreadsheet into One-time costs – year, amount, description, yes/no for already inflated, and source – and each becomes a one-time cost.

#### Fully Funded Balance

The screen starts with a short explanation of what the Fully Funded Balance means. Then choose where it comes from.

- **The reserve study's figures, typed below** – one figure for every year of the projection and the year after. Paste a column of amounts to fill down from the box you are in, or paste year and amount pairs.
- **Worked out from this scenario's expenses and their useful lives** – the app works it out the way reserve studies do. For each reserve expense, its cost in that year's dollars times how far it is through its useful life. The useful life is an every-few-years expense's interval, or a one-time cost's own useful life, entered on Expenses. Monthly and yearly costs do not count, and the screen says how many one-time costs have no useful life yet. The figures for each year are shown, and the typed ones are kept for switching back.

The demo's "Worked-out Fully Funded Balance" scenario uses the second way. It has the same dues and balances as "Dues only", but a much lower Fully Funded Balance, so its percent funded is much higher.

There is a box for the source note, and **Copy to…** copies the whole Fully Funded Balance – and which way it comes – into other scenarios.

#### Dues

Dues per unit per month can be set three ways.

- **A first-year figure, then a yearly increase** – for example $650 in 2027, then +4.5% a year.
- **The same, with some years pinned to a figure** – type a figure for any year in the Pinned column. Later years grow from it.
- **Typed for each year** – a figure in every year.

For the first two, the **Yearly increases** table can hold different increases for stretches of years. Each row has a From year, a To year and an increase – a blank From is the start and a blank To the end. Each year's dues rise by the increase whose years include it, and every year after the first must be in exactly one row – the screen names any years with none or two. **Add yearly % increase** adds a row starting the year after the last one ends. The demo's Stepped increases has +7% for 2028–2030, then +3.5% from 2031, and is pinned at $900 in 2034.

The **Resolved** column shows the dues each year actually comes to. Grown dues are rounded to whole dollars unless you choose "None – keep cents". Typed and pinned figures are always used exactly as typed.

#### Special assessments

A year, an amount per unit and a note for each assessment. Installments are separate rows, such as the demo's $5,000 in 2028 and again in 2029. **Add assessment** adds a row and **Remove** deletes one.

#### Copying into other scenarios

Because each scenario holds its own facts, a fact that changes later – a new reserve study, a contractor's estimate, an updated balance – is edited in one scenario and copied into the others that should use it. **Copy to…** works on

- any figure on Facts and assumptions, with its source note
- any expense line – it replaces the same line in the other scenario, or is added there
- the whole Fully Funded Balance

The dialog lists every other scenario with a box each, and **All scenarios**. Adopted plans are listed but cannot be chosen. **Copy** replaces what the chosen scenarios have now, and the screen confirms where it went.

### An adopted plan

An adopted plan opens like any scenario, but read-only. A panel under the tabs says whether it is the adopted plan or an earlier one, with its adoption date and note. It cannot be renamed, deleted or copied into.

- **Copy as a new scenario** – the way to revise the plan. Edit the copy, compare it with the plan and adopt it when the board decides.
- **Un-adopt…** – on the current adopted plan only, to correct a mistake. It becomes an ordinary, editable scenario again, and the plan adopted before it, if any, becomes the adopted plan again.

### Compare

Compare puts the scenarios side by side, in the board's order. Choose which to show from the scenario list (all, by default, adopted plans included).

- **Summary** – one row per measure, one column per scenario. Dues per unit per month in years 1, 4 and 9 and the last year, total special assessments, the lowest balance and its year, the years below the cushion, the balance and percent funded at years 4 and 9 and at the end, the first year the target is met, owner outlay over the first five years and the whole projection, the average owner cost per year, extra cost, years needing a vote and years with an operating shortfall.
- **Year-end reserve balance by year** and **Percent funded by year** – one column per scenario. LOW years and figures below zero are shaded.

When every shown scenario has the same cushion and target, the labels name them – "Years below the cushion ($75,000)", "First year the target (60.0% funded) is met". When they differ, a row shows each scenario's own.

Extra cost is what an owner pays above today's dues held flat – each year's dues increase over the current dues, plus any special assessment. A negative figure is a saving. A row "Current dues per unit per month – what extra cost is measured against" sits just above the extra-cost rows. When every shown scenario has the same current dues, the labels name them – in the demo, "Extra cost per unit over today's $560 a month, 2027–2030", "Extra cost per unit over today's $560 a month, 2027–2042" and "Average extra cost per unit per year over today's $560 a month". When they differ, the labels say "over each scenario's current dues". A note under the summary says what extra cost is.

Tick **Show differences** to see each scenario's difference from the first one shown, on its own line under the figure, in green where it is better and red where it is worse. To measure from another scenario, move it first with the ← and → arrows in its column heading. This changes the board's order everywhere, as Move up and Move down do on Scenarios.

The by-year tables can be sorted by the year or by any scenario. Each table has Download CSV. **Save as PDF…** prints the page – choose "Save as PDF" (or "Microsoft Print to PDF") as the printer, or a real printer.

When the scenarios cover different years – an adopted plan from an earlier year, say – the summary counts years of each scenario's own projection ("year 1", "year 4") instead of naming calendar years. The by-year tables then run over every year any of them covers, blank where a scenario has no figure, and differences compare the same calendar year.

A scenario with problems in its inputs is left out, and the page names it.

### Charts

Charts stacks the first chart of each chosen scenario – reserve expenses, dues and assessments collected, the year-end balance and percent funded with the dashed target line. Every chart uses the same dollar scale, so the scenarios compare at a glance. When the scenarios cover different years, they share one year axis and each is drawn over its own years.

Hover for a year's values. Each chart has Download PNG, and Print prints the page.

### Export

- **Excel workbook** – choose the scenarios (all, by default) and **Download the workbook**. It is the board's familiar spreadsheet, with one sheet per scenario and live formulas (see [The Excel workbook](workbook.md)). A scenario with problems cannot be exported, and the app names it.
- **Project file** – **Download the project file** saves a copy of the whole project, which Import on the Projects screen brings back. Make one before a big change, as a snapshot.

## The workflow

### 1. Create or open a project

Open the demo project to explore, or create a new one on the Projects screen. To bring in a project from someone else, use Import with their exported project file or HOAForecaster workbook.

### 2. Enter the facts in the first scenario

A new project opens on its first scenario's Facts and assumptions. Fill in the years, the balance, units, dues, rates, cushion, target and vote limits, each with its source. On Expenses, enter operating costs as monthly or yearly lines and reserve work as one-time or every-few-years lines. On Fully Funded Balance, type the reserve study's figures or have the app work them out. Then set the dues and any special assessments. Fix any problems the screens list.

Give the scenario a name that says what it is, such as "Dues only".

### 3. Build more scenarios

On Scenarios, choose New scenario and start from the one you have, so every fact carries over. Change what this plan does differently – the dues, an assessment, a higher insurance quote, a project the board might defer – and watch the key results beside the inputs. Look for LOW years, owner votes and operating shortfalls in the Results table, and at when percent funded reaches the target.

When a fact changes for several scenarios – a new reserve study, a contractor's estimate, an updated balance – edit it in one and use Copy to… to put it into the others. Download the project file first if you want a snapshot of the old figures.

Put the scenarios in the order the board should see them with Move up and Move down.

### 4. Compare

Open Compare to see the summary measures side by side, and Charts to see the balances on one scale. Turn on Show differences to see how each plan compares with the first, and move the plan you want to measure from to the front.

### 5. Adopt the board's plan

When the board decides, open the chosen scenario and choose Adopt…. Enter the date it was adopted (today, unless you change it) and a note, such as the meeting and the vote. Any edit still waiting is saved first. The scenario becomes the adopted plan, read-only, so its figures never change.

Adopting another scenario later makes that one the adopted plan. The earlier one stays, read-only, as a record of the past decision.

### 6. Revise the plan

To revise the adopted plan, open it and choose Copy as a new scenario. The copy has all of the plan's inputs. Edit it, compare it with the adopted plan, and adopt it when the board agrees.

### 7. Export

On Export, choose the scenarios for the workbook and download it. It has the Method, Project, Compare and Charts sheets and one sheet per scenario, every figure a live formula. It opens in Excel and recalculates when someone edits it. Adopted plans get a protected sheet.

A board member can change inputs in the workbook and send it back. Import reads it as a new project, and the app explains in plain words anything in it that it cannot accept. See [The Excel workbook](workbook.md) for what can be changed in Excel.

To keep a copy of the whole project, or move it to another computer, download the project file and import it there.

To print, use Print on a scenario or Charts, or Save as PDF… on Compare, or download any table as CSV and any chart as a PNG picture.
