# HOAForecaster user guide

HOAForecaster helps a board see where its reserve fund is heading. You enter the building's facts once for the project – the reserve balance, the expenses and the reserve study's figures. Then you build scenarios, each a way of paying for it – a dues path and any special assessments. Every scenario runs on the same facts and expenses, so comparing them compares funding plans for the same building. For each one the app shows the reserve balance year by year, how well funded the reserves are, what each owner pays and any year that needs attention.

This guide walks through each screen and then the whole workflow, from a new project to the workbook you hand to the board. The examples use the fictional demo project, Maple Row Condominiums, which the app adds the first time it starts. Its figures are invented.

## Words used in this guide

- **Project** – one building or association. It holds the facts and assumptions, the expenses and the Fully Funded Balance that every scenario uses.
- **Scenario** – one funding plan – its dues each year and any special assessments.
- **Expense set** – a named, saved copy of the project's expenses, to load again later – a new reserve study, say, or a roof delayed.
- **Adopted plan** – a scenario the board has adopted. It is read-only and keeps the facts and expenses it was adopted with, so its figures never change.
- **Operating expenses** – costs paid from dues every month or year, such as insurance and utilities.
- **Reserve expenses** – one-time or occasional work paid from reserves, such as a roof or a repaint.
- **Fully Funded Balance** – what the fund should hold at the start of each year, from the reserve study or worked out by the app.
- **Percent funded** – the year-end balance divided by the next year's Fully Funded Balance.
- **Cushion** – the lowest year-end balance the board is comfortable with. A year below it is marked LOW.

## Starting the app

Someone with the app installed starts it with one command, or on Windows by double-clicking `HOAForecaster.bat` (see the [README](../README.md)). It opens in your web browser at http://127.0.0.1:8765/. It runs only on your own computer and sends nothing anywhere.

Your projects are saved as files in the app's data folder on your computer. Leave the app running while you work. To stop it, press Ctrl+C in the window where it was started, or close that window.

## Saving

There is no Save button. Every edit is saved by itself a moment after you stop typing, and the note beside the screen's title says "Saving…" and then "All changes saved". This is the same on the project's facts and expense screens as on a scenario's.

An entry that is not yet a usable number or year – "12,5x", say, or a year still being typed – is not saved. The screen lists it under "These entries are not usable numbers or years yet", and the note says "Not saved yet". It is saved as soon as you fix it. The same goes for a scenario name that is blank or already taken. If you try to leave the screen with such an entry, the app asks first, because the entry would be lost. If a save fails, the screen says so and offers "Try saving again".

Facts and expenses can have other problems – a missing Fully Funded Balance, say, or a negative expense. They are still saved. While the project's facts or expenses have a problem, no scenario can be worked out – the facts screens list the problem under "Fix these to see results", and each scenario says "Has problems". A scenario's own problems – an assessment outside the projection, say – are listed on it under "Fix these to see results".

## Around the screens

Across the top of every screen is the **HOAForecaster** name, which takes you back to your projects, and on the right two controls.

- **Dark screens** – a switch for light text on a dark background. Your browser remembers the choice.
- **Restart** – stops the app and starts it again, then reloads the page. You only need it after the app's code has been updated. Your edits are already saved.

Inside a project, a second bar shows the project's name and its sections – **Scenarios**, **Facts and assumptions**, **Expenses**, **Fully Funded Balance**, **Compare**, **Charts** and **Export**. A line of links above each screen's title (Projects › Maple Row Condominiums › Scenarios) takes you back up.

Many tables can be sorted by clicking a column heading – once for one direction, again for the other, a third time to put it back. Sorting changes only what you see, never the saved order. Long tables scroll inside their own box with the heading row held in place.

**Download CSV** above a table saves it as a spreadsheet file, and **Download PNG** above a chart saves it as a picture.

## The screens

### Projects

The first screen shows a card for each project, with the number of scenarios in it and when it was last saved. Click a project's name to open it. **Sort** orders the cards by when they were last saved (newest first), by name, or by number of scenarios.

- **New project** – type the building or association's name and choose Create. The project starts on January 1 of next year and runs 14 years, with the usual assumptions – 3% inflation, 2% interest, a 70% percent-funded target and owner-vote limits of 20% and 5%. Amounts start at zero for you to fill in. It has one scenario, "First scenario", whose dues start at the current dues and rise 3% a year. The new project opens on its Facts and assumptions.
- **Import** – choose a project file (.json) saved from Export, or a workbook (.xlsx) exported from HOAForecaster. Either becomes a new project.

If a file in the data folder cannot be read as a project, the screen names it below the cards.

### A project made by an earlier version

Before November 2026 each scenario held its own facts and expenses. The first time you open a project saved that way, the app moves it to the new form and saves it.

- The project's facts and expenses are those of its first scenario that is not an adopted plan.
- Each different set of scenario expenses is kept as an expense set, named after the first scenario that had it – "Expenses from Insurance shock", for example. Scenarios that had the same expenses share one set.
- Adopted plans keep the facts and expenses they were adopted with, so their figures do not change.
- Every other scenario now uses the project's facts and expenses, so a scenario that had figures of its own may show different results. Its dues carry on as they were – if the project starts in a later year, a grown path starts from what it would have charged in that year.

A panel at the top of the project, "This project now keeps its facts and expenses in one place", lists each scenario that had figures of its own, what differed, whether its figures change, whether it now matches another scenario exactly and which set its expenses are kept in. For example "Insurance shock – its interest rate, its owner-vote limits, its source notes, 3 expense lines, its Fully Funded Balance – its figures change – its expenses are saved as the set 'Expenses from Insurance shock'; loading it does not bring back its other facts". The panel stays until you choose **Dismiss**.

The project file as it was is kept in the `backups` folder inside the app's data folder. When the project is deleted, the backup goes to the trash folder with it.

### Scenarios

This is the home of one project. It lists every scenario with its key results – the lowest year-end balance and its year, the years below the cushion, percent funded at the end, the first year the target is met and when it was last changed. A scenario's description is shown under its name. The adopted plan is marked "Adopted plan" with its adoption date, and earlier adopted plans "Earlier adopted plan". A scenario that cannot be worked out says "Has problems – open it to fix them". Click a name to open the scenario.

The list is in the board's order, which every other screen and the workbook follow. Use the ↑ and ↓ buttons in the Order column to move a scenario up or down. While a heading sorts the table, the buttons are off – click the sorted heading until the table is back in order. Moving a scenario does not change it, so even an adopted plan can be moved.

**New scenario** opens the new-scenario screen.

Below the list, **Project** holds the project's name and notes. They save as you type.

At the bottom, **Delete this project…** asks first, then moves the project to the trash folder inside the app's data folder and returns to your projects. The app cannot yet bring a deleted project back, so export it first if you may want it again.

### Facts and assumptions

The project's figures, in groups. Every scenario uses them, except an adopted plan, which keeps the ones it was adopted with.

- **The years it covers** – the start year and end year, 5 to 30 full years. The projection starts on January 1 of the start year. If it is the middle of the year, start next year and enter the balance you expect on January 1.
- **The reserve fund** – the starting reserve balance, the interest it earns, the minimum working cushion and the percent-funded target.
- **Owners and dues** – the number of units and the current dues per unit per month (what each unit pays today).
- **Inflation** – operating cost inflation, reserve expense inflation and the expense base year – the year whose prices the reserve amounts are in, usually the reserve study's year.
- **When owners must vote** – the largest dues increase and the largest special assessment the board may make without a vote. Leave one blank for no limit.

Each figure has a box for its source note – where it came from and when. Notes are optional and travel into the exported workbook.

Changing the start or end year reshapes the project's tables once the horizon is 5 to 30 years. Nothing you have entered is thrown away when you shorten it, and any scenario's dues typed for each year are stretched to new years with the nearest figure.

Beside the figures is every scenario's key results – the lowest balance and its year, percent funded at the end and the years below the cushion – worked out again a moment after each edit, so you see what a change does to every funding plan at once. Adopted plans are named below the table, since the change does not reach them. The Expenses and Fully Funded Balance screens show the same table above their inputs.

### Expenses

At the top is the **Expense set** panel (see [Expense sets](#expense-sets)). Below it, the expenses are in four tables, one for each way an expense falls. Each table opens and closes, and shows only the boxes its kind needs.

| Table | Amount | Years | Grows with |
|---|---|---|---|
| Monthly costs | a month | an optional first and last year – blank means the whole projection | its own inflation rate, or operating inflation when blank |
| Yearly costs | a year | as monthly | as monthly |
| Every few years | each time | a first year, the years between (also its useful life) and an optional last year | reserve inflation from the base year |
| One-time costs | the one time | its year, and an optional useful life | reserve inflation from the base year |

Monthly and yearly amounts are in the dollars of their first year (blank – the start year). Every-few-years and one-time amounts are in the base year's dollars. Tick **Already inflated?** when an amount is already a future cost, as a reserve study's yearly totals usually are. A one-time cost is then used as it stands. An every-few-years cost is in its first year's dollars, and each repeat grows from there with reserve inflation – so enter as its first year the year the amount is priced in.

In the demo, management is a yearly $58,000, utilities a monthly $3,100 at their own 3.5%, the landscaping contract runs 2027–2033, the exterior repaint falls every 8 years from 2031 and the boiler once, in 2035.

The every-few-years table numbers its lines and, with **Show each one's repeats in 2027–2042, in year order** ticked, lists every later occurrence in the projection in year order, read-only, with its cost in that year's dollars ("Repeat of #1 – Exterior repaint").

Each row has a **How often** choice – choosing another moves the line to that table – and **Remove**. Each table has an Add button, and **Sort by year** puts its lines in year order. You can paste rows copied from a spreadsheet into One-time costs – year, amount, description, yes/no for already inflated, and source – and each becomes a one-time cost.

#### Expense sets

An expense set keeps a version of the expenses to come back to – the expense lines with their notes, the Fully Funded Balance (typed or worked out, with its note) and the expense base year. Every other fact, the reserve inflation rate included, stays as it is when a set is loaded.

The panel says where the expenses on screen came from – "From the set “Expenses from Dues only”", with "– edited since it was loaded" once you change them, or "These expenses are not saved as a set". Below it is the list of saved sets, each with its base year and number of lines.

- **Save as a set…** – saves the expenses on screen under a new name, unique in the project and at most 100 characters. They now come from that set.
- **Save changes to “…”** – shown once the expenses have been edited since their set was loaded. It writes them back into that set.
- **Load…** – replaces the project's expenses, Fully Funded Balance and base year with a copy of the set, for every scenario but an adopted plan. Before it does, the app asks what to do with the expenses on screen. If they came from no set, it offers to save them as one first. If they came from a set and have been edited since, it offers three choices – save the changes to that set, save them as a new set, or discard them. If the set was saved with a different reserve inflation rate, it says so ("This set was saved with … reserve inflation – the project uses 3.5%") and offers to switch the project's rate to the set's – a reserve study states its dollars and its inflation together. The box is ticked to begin with. The demo's sets were all saved at 3.5%, so loading one never asks.
- **Rename…** and **Delete** – Delete asks first. Deleting the set the expenses came from leaves the expenses as they are, from no set.

Loading copies the set. Editing the expenses afterwards never changes the set until you save the changes to it, and a set never changes the project until it is loaded.

A set keeps a monthly or yearly cost with a blank first year as starting in the project's start year at the time. Loading it after the start year has moved gives the figures it was saved with. Loading keeps the project's typed Fully Funded Balance for any year the set does not have. Years still missing for the projection are listed as problems, as usual.

The demo has five sets. "Expenses from Dues only" is loaded. "Expenses from Insurance shock" has insurance at $47,000 a year growing 8%, a pool resurfacing every 6 years from 2030, no boiler and a Fully Funded Balance of $700,000 for 2031. Load it and Dues only's balance falls below zero, to -$219,839.98 by the end of 2042. "Expenses from Adopted – two-part assessment" has no railings or boiler and a lower Fully Funded Balance. "Worked out from useful lives" gives the reserve costs useful lives and works the Fully Funded Balance out from them – under it, Dues only is 96.8% funded at the end of 2042 instead of 23.2%. "Older study, in 2024 dollars" has the same expenses with 2024 as the base year, so the reserve costs grow two more years – under it, Dues only's lowest balance is $47,948 in 2031 instead of $57,739. Load "Expenses from Dues only" again to go back.

### Fully Funded Balance

The screen starts with a short explanation of what the Fully Funded Balance means. Then choose where it comes from.

- **The reserve study's figures, typed below** – one figure for every year of the projection and the year after. Paste a column of amounts to fill down from the box you are in, or paste year and amount pairs.
- **Worked out from the expenses and their useful lives** – the app works it out the way reserve studies do. For each reserve expense, its cost in that year's dollars times how far it is through its useful life. The useful life is an every-few-years expense's interval, or a one-time cost's own useful life, entered on Expenses. Monthly and yearly costs do not count, and the screen says how many one-time costs have no useful life yet. The figures for each year are shown, and the typed ones are kept for switching back.

There is a box for the source note. Which way the figure comes, the typed figures and the note all travel with an expense set.

### New scenario

**Start from** shows a card for each choice – "A blank scenario" and every scenario in the project, the adopted plan first. A copy takes that scenario's dues, special assessments, rounding and description – not its name or its adoption. A blank scenario's dues start at the project's current dues and rise 3% a year, with no special assessments. Every new scenario uses the project's facts and expenses, even one started from an adopted plan. When that plan was adopted with an earlier start year, its grown dues carry on – the copy's first-year dues are what the plan charged in the project's start year.

Give it a **Name** (a copy of Dues only is offered "Dues only – copy") and choose **Create**. A copy opens on its Results, ready to change and compare. A blank scenario opens on Dues.

### A scenario

A scenario's name is the title, with its three screens as tabs underneath – **Results**, **Dues** and **Special assessments**. Your edits carry across the tabs and save themselves.

The buttons beside the name are

- **Copy as a new scenario** – opens the new-scenario screen with this scenario chosen
- **Adopt…** – make it the board's adopted plan (see [Adopt the board's plan](#6-adopt-the-boards-plan))
- **Rename…** – give it a new name. Press Enter or choose Rename to confirm
- **Delete…** – remove it from the project, after asking
- **Print**

Dues and Special assessments show key results beside the inputs – the lowest balance, percent funded at the end, the first year the target is met, the years below the cushion and the years needing a vote – so you see the effect of each edit. **All results** goes to Results.

#### Results

The year-by-year Plan table, the same figures as a scenario's sheet in the workbook, in two parts.

- **Headline figures** – dues per unit per month, the special assessment per unit, operating and reserve expenses, the ending reserve balance, percent funded, the owner's dues for the year and "Below cushion ($75,000)?" – named with the project's cushion.
- **Details** (click to open) – total dues collected, the reserve contribution from dues, the assessment to reserves, the total from owners, interest, the starting balance, next year's Fully Funded Balance, "Meets target (60.0% funded)?", "Needs owner vote?", "Operating shortfall?", the owner's dues and assessment together, the increase over current dues, the running totals and the target.

Dues and assessments are shaded like the spreadsheet's blue-on-yellow inputs. LOW, a needed owner vote and an operating shortfall are shaded as warnings. "Meets target?" shows yes in green and no plainly – not yet reaching the target is normal for years. Hover over a year's operating or reserve expenses to see the lines behind it, or click the figure to list them with their sources. Download CSV saves every row of both tables.

Below the table are two charts – expenses, dues, the reserve balance and percent funded, and owner cost per unit (dues and any assessment as separate lines) with percent funded. The target is the dashed line. Hover for a year's values.

#### Dues

At the top, **This scenario** holds its **Name** and **Description**.

Dues per unit per month can be set three ways.

- **A first-year figure, then a yearly increase** – for example $650 in 2027, then +4.5% a year.
- **The same, with some years pinned to a figure** – type a figure for any year in the Pinned column. Later years grow from it.
- **Typed for each year** – a figure in every year.

For the first two, the **Yearly increases** table can hold different increases for stretches of years. Each row has a From year, a To year and an increase – a blank From is the start and a blank To the end. Each year's dues rise by the increase whose years include it, and every year after the first must be in exactly one row – the screen names any years with none or two. **Add yearly % increase** adds a row starting the year after the last one ends. The demo's Stepped increases has +7% for 2028–2030, then +3.5% from 2031, and is pinned at $900 in 2034.

The **Resolved** column shows the dues each year actually comes to. Grown dues are rounded to whole dollars unless you choose "None – keep cents". Typed and pinned figures are always used exactly as typed.

#### Special assessments

A year, an amount per unit and a note for each assessment. Installments are separate rows, such as the demo's $5,000 in 2028 and again in 2029. **Add assessment** adds a row and **Remove** deletes one.

### An adopted plan

An adopted plan opens read-only. A panel under the tabs says whether it is the adopted plan or an earlier one, with its adoption date and note. It cannot be renamed or deleted.

It has three more tabs than an ordinary scenario – **Facts and assumptions**, **Expenses** and **Fully Funded Balance** – showing, read-only, the facts and expenses it was adopted with. Changes to the project's own facts and expenses, and loading an expense set, never reach it. In the demo, "Adopted – two-part assessment" was adopted with a $172,000 starting balance, 2% interest, no railings or boiler and a lower Fully Funded Balance.

- **Save these expenses as a set…** – on its Expenses tab. It saves the plan's expenses, Fully Funded Balance and base year as an expense set, to load as the project's on the Expenses screen. The plan itself does not change.
- **Copy as a new scenario** – the way to revise the plan. The copy takes its dues and assessments and uses the project's facts and expenses. Edit it, compare it with the plan and adopt it when the board decides.
- **Un-adopt…** – on the current adopted plan only, to correct a mistake. It becomes an ordinary, editable scenario again, and the plan adopted before it, if any, becomes the adopted plan again. It drops the facts and expenses it was adopted with and uses the project's, so its figures change if the project's have changed since – save its expenses as a set first to keep them. If the project now starts in a later year, its grown dues carry on from what it charged in that year.

### Compare

Compare puts the scenarios side by side, in the board's order. Choose which to show from the scenario list (all, by default, adopted plans included).

Above the summary, a line says which expense set the project's expenses came from, and whether they have been edited since – "Expenses from the set “Expenses from Dues only”." – and names any adopted plan shown, since it keeps the facts and expenses it was adopted with.

- **Summary** – one row per measure, one column per scenario. Dues per unit per month in years 1, 4 and 9 and the last year, total special assessments, the lowest balance and its year, the years below the cushion, the balance and percent funded at years 4 and 9 and at the end, the first year the target is met, owner outlay over the first five years and the whole projection, the average owner cost per year, extra cost, years needing a vote and years with an operating shortfall.
- **Year-end reserve balance by year** and **Percent funded by year** – one column per scenario. LOW years and figures below zero are shaded.

When every shown scenario has the same cushion and target, the labels name them – "Years below the cushion ($75,000)", "First year the target (60.0% funded) is met". When they differ – an adopted plan with a target of its own, say – a row shows each scenario's own.

Extra cost is what an owner pays above today's dues held flat – each year's dues increase over the current dues, plus any special assessment. A negative figure is a saving. A row "Current dues per unit per month – what extra cost is measured against" sits just above the extra-cost rows. When every shown scenario has the same current dues, the labels name them – in the demo, "Extra cost per unit over today's $560 a month, 2027–2030", "Extra cost per unit over today's $560 a month, 2027–2042" and "Average extra cost per unit per year over today's $560 a month". When they differ, the labels say "over each scenario's current dues". A note under the summary says what extra cost is.

Tick **Show differences** to see each scenario's difference from the first one shown, on its own line under the figure, in green where it is better and red where it is worse. To measure from another scenario, move it first with the ← and → arrows in its column heading. This changes the board's order everywhere, as Move up and Move down do on Scenarios.

The by-year tables can be sorted by the year or by any scenario. Each table has Download CSV. **Save as PDF…** prints the page – choose "Save as PDF" (or "Microsoft Print to PDF") as the printer, or a real printer.

When the scenarios cover different years – an adopted plan from an earlier year, say – the summary counts years of each scenario's own projection ("year 1", "year 4") instead of naming calendar years. The by-year tables then run over every year any of them covers, blank where a scenario has no figure, and differences compare the same calendar year.

A scenario with problems in its inputs is left out, and the page names it.

### Charts

Charts stacks the first chart of each chosen scenario – reserve expenses, dues and assessments collected, the year-end balance and percent funded with the dashed target line. Every chart uses the same dollar scale, so the scenarios compare at a glance. When the scenarios cover different years, they share one year axis and each is drawn over its own years.

Hover for a year's values. Each chart has Download PNG, and Print prints the page.

### Export

- **Excel workbook** – choose the scenarios (all, by default) and **Download the workbook**. It is the board's familiar spreadsheet – the project's facts, its expenses and Fully Funded Balance, and one sheet per scenario, all with live formulas (see [The Excel workbook](workbook.md)). A scenario with problems cannot be exported, and the app names it. Neither can a project whose facts or expenses have problems. Saved expense sets are not in the workbook.
- **Project file** – **Download the project file** saves a copy of the whole project, its expense sets included, which Import on the Projects screen brings back. Make one before a big change, as a snapshot.

## The workflow

### 1. Create or open a project

Open the demo project to explore, or create a new one on the Projects screen. To bring in a project from someone else, use Import with their exported project file or HOAForecaster workbook.

### 2. Enter the building's facts and expenses

A new project opens on **Facts and assumptions**, and the project's bar across the top leads to the rest. On Facts and assumptions, fill in the years, the balance, units, current dues, rates, cushion, target and vote limits, each with its source. On **Expenses**, enter operating costs as monthly or yearly lines and reserve work as one-time or every-few-years lines. On **Fully Funded Balance**, type the reserve study's figures or have the app work them out. Fix any problems the screens list.

When the expenses are as the reserve study gives them, save them as a set – "2027 reserve study", say – so you can always come back to them.

### 3. Build the scenarios

Open the first scenario from Scenarios, give it a name that says what it is, such as "Dues only", and set its dues and any special assessments. Then choose New scenario and start from it, and change what the new plan does differently – a steeper increase, an assessment in installments. Watch the key results beside the inputs. Look for LOW years, owner votes and operating shortfalls in the Results table, and at when percent funded reaches the target.

Put the scenarios in the order the board should see them with Move up and Move down.

### 4. Try other expenses

When a fact changes – a new reserve study, a contractor's estimate, an updated balance – change it once on the project's screens and every scenario follows. Watch the table of every scenario's key results as you type.

To see the plans under a different view of the expenses – a roof delayed, a pool added – save the current expenses as a set, edit them, and save the edited ones as a set of their own. Load either to see every scenario under it, and load the first back to return.

### 5. Compare

Open Compare to see the summary measures side by side, and Charts to see the balances on one scale. Turn on Show differences to see how each plan compares with the first, and move the plan you want to measure from to the front. The line above the summary says which expenses the comparison is on.

### 6. Adopt the board's plan

When the board decides, open the chosen scenario and choose Adopt…. Enter the date it was adopted (today, unless you change it) and a note, such as the meeting and the vote. Any edit still waiting is saved first. The scenario becomes the adopted plan, read-only, with a frozen copy of the project's facts and expenses as they are at that moment, so its figures never change.

Adopting another scenario later makes that one the adopted plan. The earlier one stays, read-only, as a record of the past decision.

### 7. Revise the plan

To revise the adopted plan, open it and choose Copy as a new scenario. The copy has the plan's dues and assessments and the project's current facts and expenses. Edit it, compare it with the adopted plan, and adopt it when the board agrees. To bring the plan's own expenses back as the project's, save them as a set from its Expenses tab and load the set on the project's Expenses screen.

### 8. Export

On Export, choose the scenarios for the workbook and download it. It opens in Excel with every figure a live formula and recalculates when someone edits it. A change to a fact or an expense on the Project or Expenses sheet changes every scenario, as in the app. Adopted plans get a protected sheet with their own facts and expenses.

A board member can change inputs in the workbook and send it back. Import reads it as a new project, and the app explains in plain words anything in it that it cannot accept. See [The Excel workbook](workbook.md) for what can be changed in Excel.

To keep a copy of the whole project, expense sets included, or move it to another computer, download the project file and import it there.

To print, use Print on a scenario or Charts, or Save as PDF… on Compare, or download any table as CSV and any chart as a PNG picture.
