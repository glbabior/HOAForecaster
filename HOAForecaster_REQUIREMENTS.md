# HOAForecaster – Application Requirements

Version 1.8 – October 28, 2026 (v1.7 and v1.6 October 27, v1.5 October 24, v1.4 October 20, v1.0–v1.3 October 19, 2026) – the brief for a Claude Code build.

Changes in v1.8 – a grown dues path can have different yearly increases for stretches of years (section 5.1).

Changes in v1.7 – a one-time expense can carry its useful life, and a scenario's Fully Funded Balance can be worked out from its expenses instead of typed from the reserve study (sections 4, 4.1 and 6).

Changes in v1.6 – the shared baseline is gone – every scenario holds all of its own inputs (its facts and assumptions, its expenses and its Fully Funded Balance as well as its dues and assessments), so a scenario's changes to the baseline (v1.5 section 5.1) are gone too; a new scenario copies everything from the scenario it starts from, and a fact, an expense line or the Fully Funded Balance can be copied into chosen scenarios later (section 7.2); an adopted plan is a scenario made read-only (section 5.2); the project's screens are organised by scenario (section 7); every edit is saved as it is made, with no Save button (sections 7.2 and 8.2); the workbook carries each scenario's inputs on its own sheet (section 7.6); project files move to schema version 3 (section 8.2).

Changes in v1.5 – expenses are categorised by how often they occur (monthly, yearly, every few years, once), and monthly and yearly expenses replace the single operating-expense figure (sections 4 and 6); a scenario can change any baseline assumption, line by line for the tables (section 5.1); a scenario can be adopted as the board's decision – the adopted plan – which is read-only and keeps the baseline it was adopted against (sections 3 and 5.2); a new scenario can start from any other (section 7.2); Compare, Charts and the workbook handle scenarios over different years (sections 7.4–7.6); project files move to schema version 2 (section 8.2); acceptance tests cover the new inputs and the version 1 upgrade (section 9).

Changes in v1.4 – the application is named HOAForecaster; the repositories are HOAForecaster (public) and HOAForecaster-data (private).

Changes in v1.3 – code and data separated for a public repository (section 8.1); real-association figures moved to a private appendix in the private data repository; public acceptance tests use a fictional demo project (section 9); security review checks that no real data enters the public repo.

Changes in v1.2 – stack fixed as FastAPI + React (section 11); the supplied script is v1.0, so the v1.3 workbook is the layout and formula reference (sections 1 and 13); operating-shortfall warning added (sections 6 and 7.3); leftover baseline-versioning wording removed (sections 7.1 and 8); generated text names no individual.

Changes in v1.1 – full-year start (no partial start year); one editable baseline per project instead of versioned baselines; single-user local app confirmed; development process with code-review, security and documentation agents added (section 10).

## 1. Purpose

A small application that replaces a hand-built Excel reserve funding model ("the reference workbook") with an editable, persistent tool. A board member enters a building's reserve facts – balance, expenses, the reserve study's Fully Funded Balance – into a scenario with its dues path and special assessments, copies it into any number of other funding scenarios that differ in any input, compares them, adopts one as the board's decision, and sees, for each, the year-by-year reserve balance, percent funded, owner cost and warning flags, as tables and charts. The app also exports the same Excel workbook the board already knows.

The calculation logic is defined by the reference workbook's formulas and described in the handoff notes that accompany it. Both belong to a real association and live in the private data repository (section 8.1), with a private appendix that names them and records their figures. The app must reproduce the reference workbook's numbers exactly (section 9).

## 2. Users and context

- Single-user local application – one person (a board member or prospective owner) on their own computer. No login, no server, no multi-user editing. A shared or hosted version is a possible later phase; nothing in the data model should prevent it, but nothing in v1 should be built for it.
- Secondary use – printing or exporting results to share with a board.
- Data is small (tens of scenarios, 15–30 year horizons). Nothing here needs a server-side database beyond a local file store.

## 3. Domain model

```
Project            – one building / association
  └─ Scenarios     – any number of funding plans, each complete in itself – its facts and assumptions (section 4), its expenses and Fully Funded Balance, its dues path and special assessments (section 5)
       └─ Adopted plans – scenarios the board has adopted, each read-only; the most recently adopted is the current adopted plan
```

- Every scenario holds all of its own inputs; nothing is shared between scenarios. A new scenario starts from a copy of another (section 7.2), so facts entered once carry into every scenario made from it. A fact that changes later (a new reserve study, a contractor estimate, an updated balance) is edited in one scenario and copied into the others that should use it (section 7.2) – scenarios are alternatives, and each says exactly what it assumes. "Export project" (section 8) is the way to keep a snapshot before a large change.
- Everything has a name, free-text notes, created and modified timestamps.

## 4. Facts and assumptions (in every scenario)

Every numeric input carries an optional `source` text field (where the number came from and when) – this mirrors the cell comments in the spreadsheet and matters for a board audience.

| # | Input | Type | Notes |
|---|---|---|---|
| 1 | Starting reserve balance | currency | As of January 1 of the start year |
| 2 | Start year, end year | integer | Horizon of 5–30 full years. Default end = start + 13. If today is mid-year, the user enters the expected January 1 balance of the next year and starts there |
| 3 | Expenses | table – frequency, amount, description, years | One line per expense, each with a frequency (section 4.1). Free text per line records the nature of the expense; many lines per year allowed |
| 4 | Reserve expense inflation rate and base year | percent, integer | Default 3%, base year = the reserve study's year. Applies to once and every-few-years expenses |
| 5 | Fully Funded Balance by year | table – year, amount, or worked out | From the reserve study, start year through end year + 1 – or worked out from the expenses' useful lives (section 4.2). Required for percent funded |
| 6 | (removed in v1.5 – operating expenses are the monthly and yearly lines of input 3) | | |
| 7 | Operating expense inflation rate | percent | Default 3%. The growth rate of any monthly or yearly expense that does not set its own |
| 8 | Interest rate earned on reserves | percent | Default 2% |
| 9 | Number of units | integer | Assessments and dues are per unit, equal shares (v1) |
| 10 | Current dues per unit per month | currency | The "no change" reference for extra-cost measures |
| 11 | Minimum working cushion | currency | Year-end balance below this is flagged LOW |
| 12 | Percent-funded target | percent | Default 70%. Drawn as the target line on charts |
| 13 | Governance limits (optional) | percent, percent | Max dues increase per year without an owner vote (default 20%); max special assessment as a share of the annual budget without a vote (default 5%). Used only for warnings |

Validation – FFB present for every year from the start year to end year + 1 (unless it is worked out), a useful life of at least 1 year, rates between 0 and 50% (each expense line's own rate too), currency non-negative, units ≥ 1.

### 4.1 Expense frequencies

| Frequency | Example | Paid from | Amount | Years |
|---|---|---|---|---|
| Monthly | utilities | dues (operating) | per month, in the dollars of its first year | every year from an optional first year to an optional last year (blank = the whole horizon) |
| Yearly | insurance | dues (operating) | per year, in the dollars of its first year | as monthly |
| Every few years | repaint every 7 years | reserves | per occurrence, in base-year dollars (input 4) unless marked as already in that year's dollars | a first year, an interval in whole years and an optional last year |
| Once | roof replacement | reserves | in base-year dollars unless marked as already in that year's dollars | one year |

- Monthly and yearly lines are the operating expenses. Each grows from its first year (or the start year, when it has none) at its own inflation rate, or at input 7 when it has none.
- Once and every-few-years lines are the reserve expenses, inflated from the base year at input 4.
- Every line has a stable identifier, kept when a scenario is copied, so a line copied into other scenarios (section 7.2) replaces the same line there.
- Lines and occurrences outside the horizon are kept and ignored. An every-few-years line needs an interval of at least 1; a last year may not come before the first year.
- A reserve expense's useful life is how many years the component lasts between replacements – for an every-few-years line its interval; a once line can carry one (optional). It is used only to work out the Fully Funded Balance (section 4.2).

### 4.2 Fully Funded Balance worked out from the expenses

A scenario's Fully Funded Balance is either typed from the reserve study (input 5) or worked out from its reserve expenses – the scenario chooses; typed figures are kept while it is worked out. Worked out, for the start of each year Y from the start year to end year + 1, it is the sum over the reserve lines that have a useful life L (every-few-years lines, and once lines with one) of

```
cost_Y × age_Y / L
  cost_Y = the line's amount in year-Y dollars – inflated from the base year at input 4, or for a line marked as already in its year's dollars deflated at input 4 from the year it falls (a once line's year; an every-few-years line's next occurrence, Y + rem, since the same amount falls each time)
  next   = the line's year, or for an every-few-years line its first occurrence
  rem    = L when next − Y ≥ L (not yet in service), else (next − Y) mod L   (mod taking the sign of L, so a line already replaced keeps ageing on the same cycle)
  age_Y  = L − rem
```

An every-few-years line with a last year counts only for years up to it. Monthly and yearly lines never count. This is the reserve-study standard's "effective age ÷ useful life × current cost", with each line's remaining life taken from its schedule.

## 5. Scenario inputs

Besides its facts and assumptions (section 4), each scenario has –

| # | Input | Type | Notes |
|---|---|---|---|
| 1 | Name, description | text | |
| 2 | Dues path | one of three modes | (a) **explicit** – dues per unit per month for each year; (b) **first-year value + yearly increase %** – e.g. $900 in year 1 then +4%, or different increases for stretches of years, e.g. +8% a year for 2028–2030 then +3% (section 5.1); (c) **mode b with per-year overrides** – any year can be pinned to a value, later years continue the rate from the pinned value |
| 3 | Special assessments | table – year, amount per unit, note | Zero or more. Multiple installments are separate rows |
| 4 | Dues rounding | choice | Round to whole dollars (default) or no rounding |

The dues path must be shown resolved (the actual number for every year) next to the inputs so the user sees what mode b produced.

### 5.1 Yearly increases by period

A grown dues path (modes b and c) has one or more yearly increases, each a rate with a first and a last year – blank meaning the scenario's start and end. A period's years are the years whose dues rise by its rate over the year before; the start year is the first-year value and is never raised. Every year after the start year must be in exactly one period – overlapping periods, and years no period covers, are problems naming the years – and a period may not end before it starts, nor name a year outside the scenario. A pinned year takes its value, and later years grow from it at their own periods' rates.

### 5.2 The adopted plan

The board's decision is the **adopted plan** – a scenario that has been adopted.

- Any scenario can be adopted, with an adoption date (default today) and a note (for example the meeting and vote).
- An adopted plan keeps all of its inputs as they were when it was adopted, so its figures never change. Nothing is copied into it (section 7.2).
- An adopted plan is read-only and cannot be renamed or deleted. To revise it, start a new scenario from it (section 7.2), edit that and adopt it.
- Adopting another scenario makes it the current adopted plan – the current plan is always the one adopted most recently, whatever adoption date was entered. Earlier adopted plans stay, read-only, as a record of past decisions, each with its adoption date.
- The current adopted plan can be un-adopted to correct a mistake – it becomes an ordinary, editable scenario again, with its inputs as they were, and the plan adopted before it becomes current. Earlier adopted plans cannot be un-adopted.

## 6. Calculation engine

Implement as a pure function `run(scenario) -> results` with no UI or storage dependencies, so it can be unit-tested and reused by the exporter. Per year, in this order –

```
total_dues          = dues_per_unit_per_month × units × 12
operating           = Σ monthly and yearly lines active in the year, each amount × (12 if monthly, else 1) × (1 + line rate)^(year − line's first year)
                        (line rate = the line's own rate, else op_inflation; line's first year = its own, else start_year)
contribution        = max(0, total_dues − operating)
assessment          = assessment_per_unit × units
total_from_owners   = total_dues + assessment
interest            = starting_balance × interest_rate
expenses            = Σ once lines in the year and every-few-years lines falling in the year, each × (1 + exp_inflation)^(year − base_year) unless flagged nominal
ending_balance      = starting_balance + contribution + assessment + interest − expenses
ffb_next            = FFB for year + 1 (typed, or worked out – section 4.2)
percent_funded      = ending_balance / ffb_next
low_flag            = ending_balance < cushion
target_met          = percent_funded ≥ target
owner_dues_year     = dues_per_unit_per_month × 12
owner_cost_year     = owner_dues_year + assessment_per_unit
extra_vs_current    = (dues_per_unit_per_month − current_dues) × 12 + assessment_per_unit
cumulative_owner_cost, cumulative_extra   – running sums from the start year
needs_vote          = dues increase over prior year > governance limit, or assessment > limit × (operating + contribution)
operating_shortfall = total_dues < operating   (warning only – the shortfall is not drawn from reserves, matching the workbook)
```

The starting balance of the first year is input 1; of each later year, the prior year's ending balance.

Every input in these formulas is the scenario's own (sections 4 and 5).

Scenario summary measures (used by the Compare view) –

- Dues per unit per month at year 1, year 4, year 9 (offsets 0, 3 and 8 from the start year).
- Total special assessments per unit over the horizon.
- Lowest year-end balance and the year it occurs; count of LOW years.
- Balance and percent funded at year 4, year 9 and the end year.
- First year the target is met, or "not by {end year}".
- Owner outlay per unit over the first five years and over the whole horizon.
- Extra cost vs current dues over the first four years and over the whole horizon.
- Average owner cost per year over the horizon; average extra cost per year.
- Count of years needing an owner vote.

All percentages are stored as fractions; money as decimal or integer cents, never binary floats in storage. Display rounding only at the UI layer.

## 7. Screens

### 7.1 Project

- Project list → a project's screens, with an index on the left – **Scenarios**, **Compare**, **Charts** and **Export**.
- Scenarios – the current adopted plan first, marked as such, then the working scenarios, then earlier adopted plans with their adoption dates; and New scenario.
- **Import** – (a) CSV for a scenario's expense table and Fully Funded Balance table, its columns to be fixed when this is built – a row without a frequency is a once line; (b) a workbook in the reference layout – read Inputs, Expenses (baseline row, item rows, FFB row) and each Plan sheet's input rows into one scenario per Plan sheet, each with the Inputs and Expenses facts, dropping a partial first-year column if present and using that year's ending balance as the next January 1 starting balance. Its item rows become once lines and its operating-expense input one yearly line, as in the version 1 upgrade (section 8.2).

### 7.2 A scenario's screens

- Opening a scenario shows its own index of screens – **Results** (the Plan table of section 7.3 and the two charts of section 7.5), **Facts and assumptions** (the scalar inputs of section 4), **Expenses** (the expense table, with each line's frequency), **Fully Funded Balance** (by year), **Dues** (section 5 inputs 2 and 4, with the dues path shown resolved) and **Special assessments**. The inputs screens show key results alongside, recalculating as inputs change (debounced).
- Table editing supports add/delete rows, paste from clipboard (tab-separated), and sorting by year (lines without a year first).
- Every edit is saved as it is made – there is no Save button. An entry that is not yet a usable value (text that is not a number, a name another scenario has) is shown as a problem and saved once it is fixed. A scenario with other problems (section 4's validation) is saved and shows its problems until they are fixed.
- **Copy to scenarios** – any fact or assumption (with its source note), any expense line, or the whole Fully Funded Balance table can be copied into other scenarios, chosen in a dialog with a checkbox for each and one for all. An expense line replaces the line with the same identifier there, or is added. Adopted plans are listed but cannot be chosen.
- Copy (a new scenario starting from this one), Delete, Adopt.
- A new scenario starts blank (the defaults of section 4) or from any scenario – the adopted plan, an earlier adopted plan or any other. Starting from one copies all of its inputs – facts and assumptions, expenses, Fully Funded Balance, dues, assessments, rounding and description – but not its name, its adoption or its timestamps.
- An adopted plan opens read-only, with its adoption date and note, a way to start a new scenario from it and – for the current adopted plan – Un-adopt.

### 7.3 Plan view (per scenario) – the equivalent of a Plan tab

A year-by-year table, years as columns, with these rows in this order – on screen the headline rows (dues per unit per month, special assessment per unit, operating expenses, reserve expenses, ending reserve balance, percent funded, owner cost – dues per year, below cushion?) come first – an owner's dues and any assessment so on separate lines – in a table of their own and the rest follow in a details table, each collapsible; a CSV of the table keeps this order –

dues per unit per month · special assessment per unit · total dues collected · operating expenses · reserve contribution from dues · special assessment to reserves · total collected from owners · interest earned · reserve expenses · starting reserve balance · **ending reserve balance** · fully funded balance (start of next year) · **percent funded** · below cushion? · meets target? · needs owner vote? · operating shortfall? · owner cost – dues per year · owner cost – dues + assessment · increase vs current dues · cumulative owner cost · cumulative extra cost · percent-funded target.

Input rows visually distinct (the spreadsheet uses blue on yellow). LOW and "no"/"yes" flags colour-coded. The two charts (7.5) below the table. Expense lines for a year visible on hover or expand (the free-text descriptions) – the operating lines under operating expenses, the reserve lines under reserve expenses.

### 7.4 Compare view

- A multi-select of the project's scenarios (dropdown with checkboxes; default = all, adopted plans included).
- Table 1 – the summary measures in section 6, one column per selected scenario.
- Table 2 – year-end reserve balance by year, one column per scenario.
- Table 3 – percent funded by year, one column per scenario.
- Differences highlighted against the first selected scenario (optional toggle).
- Scenarios may cover different years (a scenario's own horizon, or an adopted plan from an earlier year). The by-year tables then run over every year any selected scenario covers, blank where a scenario does not; the summary measures are by year of each scenario's own horizon (year 1, 4, 9 and the end), labelled with calendar years only when every selected scenario shares the horizon. By-year differences compare the same calendar year.

### 7.5 Charts

Two charts per scenario, over the whole horizon –

1. **Expenses, dues and reserve balance** – lines for reserve expenses (year), dues + assessments collected (year, all units) and year-end reserve balance on the left dollar axis; percent funded as a line and the target as a dashed horizontal line on the right 0–100% axis.
2. **Owner cost** – owner cost per unit per year (dues + assessment) on the left axis; percent funded and the target line on the right.

Charts view (the equivalent of the Charts tab) – chart 1 for each selected scenario, stacked with a shared year axis and the same dollar scale across scenarios so they compare visually (when scenarios cover different years, the shared axis runs over every year any of them covers, each drawn over its own years); the same scenario multi-select as Compare. Hover shows the year's values. Each chart downloadable as PNG.

### 7.6 Export

- **Excel workbook** following the v1.3 layout – Method, Project (the association's name and notes), Compare, Charts, then one sheet per selected scenario (named by scenario), each carrying the scenario's Plan table, its facts and assumptions, its Fully Funded Balance and its expense table, with live formulas (not pasted values), the same colour conventions, number formats and cell comments carrying the source notes, and the same charts. Generated server-side or in-browser; must open in Excel without repair prompts and recalculate to the same numbers the app shows.
- Each scenario's expense table lists every line with its frequency and identifier, operating and reserve lines in one table with a total of each.
- An adopted plan's sheet shows its adoption date and note and is protected as a reminder that it is read-only.
- When the chosen scenarios cover different years, the Compare sheet runs its by-year tables over every year any of them covers and labels its summary measures by year of each horizon; each chart covers its own scenario's years.
- Re-import brings back everything the app holds for the project except ids, revisions and timestamps – every scenario's inputs, expense frequencies and line identifiers, and adoptions.
- CSV of any table.
- PDF/print stylesheet for the Plan, Compare and Charts views.

## 8. Persistence

### 8.1 Code and data separation

- The code is public; real association data is not. Two repositories –
  - **HOAForecaster** (public) – code, this spec, the fictional demo project and its fixtures. It must never contain a real association's name, figures, documents or workbook.
  - **HOAForecaster-data** (private, cloned beside the code) – real projects, the reference workbook and handoff notes, the private appendix and the private acceptance fixtures.
- `HOA_PRIVATE_DIR` names the private repository for the private acceptance tests and the commit guard; it is never the app's data folder.
- The app reads and writes projects in a data folder set by the `HOA_DATA_DIR` environment variable or a setting, defaulting to the bundled demo folder. No path into the private repo is hard-coded.
- No plugin system in v1 – the data folder is the seam. Importers for other reserve-study formats are a possible later use for one.

### 8.2 Storage


- Local file store – one JSON file per project in a user-chosen folder (or app data directory), human-readable, with a schema version field. SQLite is acceptable instead if simpler for the chosen stack.
- Schema version 3 (v1.6) moves the baseline into every scenario. A version 2 file still opens – each scenario receives the baseline with its own changes applied (an adopted plan, its frozen baseline), so every figure is the same; a project with no scenarios gets one holding the baseline, with dues starting at its current dues. A version 1 file also opens – first its expense lines become once lines and its operating-expense figure one yearly line with no first year and no rate of its own, so it grows at input 7 from the start year and the figures are the same. Either is saved as version 3.
- Every edit is saved as it is made (section 7.2). No version history – "Export project" is the snapshot.
- Backup – "Export project" bundles the project JSON; "Import project" restores it.

## 9. Acceptance tests (must pass)

Two fixture sets, one engine.

- **Public – demo project** (`demo/` in the public repo, tests always run). A fictional association – invented name, unit count, balance, expense schedule and FFB – with scenarios that between them exercise every dues mode (explicit, first-year value + rate, rate with per-year overrides), a special assessment, nominal and inflated expense lines, every expense frequency (with a line's own rate and a first and last year), scenarios whose facts differ (a rate, an expense line changed, one left out, one added, a Fully Funded Balance year), an adopted plan, a LOW year, an operating shortfall year, a needs-vote year, a target met and a target never met. Expected figures come from a demo workbook built with the reference formulas – extended with formulas of the same kind for expense frequencies and each scenario's own inputs – and recalculated in LibreOffice headless, never from the engine itself. The demo workbook and the script that builds it are committed with the fixtures.
- **Private – real project** (private appendix, section A3). Runs when `HOA_PRIVATE_DIR` points at the private repo; skipped otherwise. Must pass before every release. Its project file is version 1, so it also checks that the version 1 and version 2 upgrades (section 8.2) keep the reference workbook's figures.

Also – a round-trip export → re-import reproduces the same results for both projects; the exported workbook recalculates in LibreOffice headless with zero formula errors.

## 10. Non-functional and development process

### 10.1 Non-functional

- Runs locally on Windows and macOS from a single command (`npm start` or equivalent); no cloud dependency.
- Results recalculate in under 100 ms for a 30-year horizon so the editor feels live.
- Accessible tables (real `<table>` markup) and charts with text alternatives.
- US number formatting; en-dashes in generated text; no colons in generated prose (match the spreadsheet's Method tab style).
- Code – TypeScript throughout if a web stack is chosen; calculation engine in its own package with 100% unit-test coverage of section 6; lint and format on commit.

### 10.2 Agents

Define three Claude Code subagents in `.claude/agents/` and use them as gates –

- **code-reviewer** – runs on every pull request or before each commit to main. Checks the change against this document (section by section), the engine formulas in section 6, test coverage, type safety, naming and dead code. Output is a findings list ranked by severity with file and line; blocking findings must be resolved before merge.
- **security-reviewer** – runs before each release and on any change touching file I/O, import/export, dependencies or the local server. Checks file-path handling on import and export (no path traversal, no writing outside the chosen folder), parsing of untrusted CSV and XLSX input (size limits, no formula injection into exported cells from user text, safe handling of malformed files), dependency audit (`npm audit` or equivalent, no known critical vulnerabilities), no network calls, no secrets in the repo, that the local server binds to localhost only, and that nothing from a real association (names, figures, documents, workbooks) is committed to the public repo – checked on every change, not only releases.
- **documentation-writer** – runs when a feature is complete and before each release. Maintains `README.md` (install, run, test), `docs/user-guide.md` (each screen, with the workflow from seeding a project through comparing scenarios and exporting), `docs/engine.md` (the formulas as implemented, with the acceptance figures), and `CHANGELOG.md`. Documentation is a deliverable – a release is not done until it passes.

### 10.3 Working method for the build

- Build the engine first, with the section 9 fixtures as failing tests, then the exporter, then the UI.
- Keep a `CLAUDE.md` in the repo that points at this document, names the three agents and when to invoke them, and records stack decisions as they are made.
- Commit after each green test run; do not batch unrelated changes.

## 11. Stack

Decided in v1.2 – **Python FastAPI backend + React/TypeScript front end**, running locally. The engine and the Excel exporter are both Python, so the math has one source of truth and the exporter reuses the openpyxl chart technique from the reference script. The UI calls the engine over a localhost API (bound to 127.0.0.1); recalculation must still meet the 100 ms target round trip. Section 10.1's "TypeScript throughout" applies to the front end; the engine package is Python with 100% test coverage of section 6.

Original suggestions, kept for context –


- Vite + React + TypeScript single-page app, running from a local Node process. State in a store (Zustand or similar). Charts with Recharts or ECharts (secondary axis and dashed reference lines required). Excel export with ExcelJS (supports formulas, comments, number formats and charts are the weak point – if ExcelJS cannot write the charts, fall back to a small Python helper using openpyxl, reusing `build_reserve_model.py`, invoked by the app).
- Alternative – Python FastAPI backend reusing the openpyxl code directly, with the same React front end. Choose whichever makes the workbook export faithful with the least effort; the export is the hardest requirement.

## 12. Out of scope for v1

Partial start years, version history (section 8.2), keeping scenarios' facts in step automatically (section 3), unequal ownership shares, multiple reserve funds, loan financing of projects, tax, multi-user editing and permissions, hosting, mobile layout.

## 13. Reference files

The reference workbook, its v1.0 generator script and the handoff notes are kept in the private data repository under `ReferenceFiles/`, with the private appendix. The public repo carries the demo project and the demo workbook built from the same formulas.
