# Calculation engine

The engine in `src/hoa_engine/` turns one scenario into a year-by-year projection and a set of summary measures. A scenario is complete in itself – its facts and assumptions, its expenses, its Fully Funded Balance, its dues path and its special assessments – so nothing else goes in. The engine is pure Python with no I/O, and every amount is a `Decimal`. This page describes it exactly as implemented, in the order it works, with the demo project's acceptance figures at the end.

The specification is [HOAForecaster_REQUIREMENTS.md](../HOAForecaster_REQUIREMENTS.md) (v1.9) – section 6 for the formulas, section 4 for the facts and assumptions, 4.1 for expense frequencies, 4.2 for a worked-out Fully Funded Balance, 5 and 5.1 for the dues path and 5.2 for adopted plans. Where the specification leaves a choice open, this page says what the engine does and marks it **Choice**.

## Entry point

```python
import json
from pathlib import Path

from hoa_engine import project_from_dict, run

project = project_from_dict(
    json.loads(Path("demo/fixtures/project.json").read_text(encoding="utf-8"))
)
result = run(project.scenarios[0])  # ScenarioResult for "Dues only"
result.years  # tuple of YearResult, one per year of the scenario's horizon
result.summary  # Summary
result.ffb  # {year: Decimal} – the Fully Funded Balance used, start year to end year + 1
```

`run(scenario)` is the only entry point. It does five things, in this order.

1. Checks the scenario's inputs (see [Input checks](#input-checks)). If anything is wrong it raises `InvalidInputs`, whose `problems` attribute lists every problem found in plain language – not just the first.
2. Settles the Fully Funded Balance for each year – typed, or worked out from the expenses ([step 1](#step-1--the-fully-funded-balance)).
3. Resolves the dues path to a figure for every year ([step 2](#step-2--the-dues-path)).
4. Projects each year from the start year to the end year, working out each expense line's amount as it goes ([steps 3](#step-3--expense-lines-by-frequency) and [4](#step-4--the-yearly-projection)).
5. Computes the summary measures from those years ([step 5](#step-5--the-summary-measures)).

**Choice** – `run` works under its own decimal context, 28 significant digits with half-even rounding. A caller's decimal settings cannot change the figures. Divisions that do not terminate (percent funded, the averages, a worked-out Fully Funded Balance) are carried to 28 significant digits. Nothing is rounded for display inside the engine; that is left to the screens and the exporter.

Rates and percentages are fractions throughout – `0.035` means 3.5%.

## Step 1 – the Fully Funded Balance

`ffb_of(facts)` gives the Fully Funded Balance at the start of each year. A scenario chooses where it comes from with `ffb_from_lines`.

- **Typed** (`ffb_from_lines` false) – the reserve study's figures in `ffb`, one for every year from the start year to end year + 1.
- **Worked out** (`ffb_from_lines` true) – `worked_out_ffb(facts)` adds up `line_ffb` over every expense line, for each year Y from the start year to end year + 1. The typed figures are kept in the scenario, unused, so switching back loses nothing.

`line_ffb(line, Y, facts)` is the line's share at the start of year Y (spec 4.2).

```
L      = the line's useful life – an every-few-years line's interval, a once line's useful_life
         (monthly and yearly lines, and once lines without a useful life, count 0)
next   = the line's year (for an every-few-years line, its first occurrence)
ahead  = next − Y
rem    = L                     if ahead ≥ L   (not yet in service)
       = ahead mod L           otherwise      (Python's %, which takes the sign of L)
age    = L − rem
cost_Y = amount × (1 + expense_inflation) ^ (Y − from)
           from = the line's year if it is marked already inflated (nominal),
                  else the expense base year
share  = cost_Y × age ÷ L
```

An every-few-years line with a last year counts 0 for every year after it – it has been retired. Because the remainder takes the sign of L, a line whose year has passed keeps ageing on the same cycle, as if replaced on schedule. In the year a line falls due, `rem` is 0 and the line counts at its full cost.

`result.ffb` holds the figures the projection used, start year to end year + 1, whichever way they came. Typed years outside that range are kept in the scenario and left out of the result.

**Choice** – a once line's useful life is optional. Without one, the line counts 0 towards a worked-out figure (the Fully Funded Balance screen says how many one-time costs have none). The `useful_life` field is read only for once lines; an every-few-years line's life is always its interval.

## Step 2 – the dues path

`resolve_dues` (in `dues.py`) produces dues per unit per month for every year of the horizon.

The specification offers three dues modes. The engine has two, and they cover all three.

| Spec mode (section 5) | Engine mode | How it is stored |
|---|---|---|
| (a) explicit value for each year | `EXPLICIT` | `explicit` – a value for every year |
| (b) first-year value + yearly increase | `RATE` | `first_value`, `increases`, empty `overrides` |
| (c) mode b with pinned years | `RATE` | as mode b, with `overrides` listing the pinned years |

**`EXPLICIT`** – each year's dues are the typed value, used as typed (never rounded).

**`RATE`** – a grown path has one or more yearly increases (spec 5.1). Each `Increase(rate, first_year, last_year)` covers the years from `first_year` to `last_year`, with `None` meaning the scenario's start or end. A period's years are the years whose dues rise by its rate over the year before. The start year takes `first_value` and is never raised.

The engine keeps an *anchor*, which starts as the start year and `first_value`. For each year in turn

- a pinned year takes its pinned value, used as typed, and becomes the new anchor
- otherwise the start year takes `first_value`, used as typed
- otherwise the value is grown from the anchor by each year's own rate, then rounded to whole dollars, half up, when the scenario's rounding is `dollar`

```
dues(Y) = anchor_value × Π (1 + rate of year y)   for y = anchor_year + 1 … Y
          then ROUND_HALF_UP to $1 if rounding = dollar
```

The product is worked out as a power per run of equal rates, so a single increase over every year gives exactly `anchor_value × (1 + rate) ^ (Y − anchor_year)`.

In the demo, Stepped increases starts at $650 in 2027, rises 7% a year for 2028–2030 and 3.5% after, and is pinned at $900 in 2034. Its 2028 dues are $650 × 1.07 = $695.50, rounded half up to $696. Its 2031 dues are $650 × 1.07³ × 1.035 = $824.15, so $824. Its 2035 dues grow from the pin – $900 × 1.035 = $931.50, so $932.

**Choice** – rounding applies only to grown values, never to a typed first-year value or a pinned value. Each year is rounded from the *unrounded* growth since the anchor, so rounding never compounds from one year to the next. This matches the reference workbook, which grows an unrounded row and rounds a separate dues row. Pinning the start year replaces `first_value`.

**Choice** – a project file written before increases had periods holds a single `annual_increase`. It reads as one increase over every year, which gives the same figures.

## Step 3 – expense lines by frequency

Every expense line has a frequency (spec 4.1). Monthly and yearly lines are the operating expenses, paid from dues. Once and every-few-years lines are the reserve expenses, paid from reserves.

`falls_in(line, year)` decides whether a line has an amount in a year.

| Frequency | Falls in `year` when |
|---|---|
| Monthly, yearly | `year ≥ first year` (no first year – always) and `year ≤ last year` (no last year – always) |
| Every few years | `year ≥ first year`, `(year − first year)` is a whole multiple of the interval, and `year ≤ last year` (no last year – always) |
| Once | `year = its year` |

`line_amount(line, year, facts)` gives its amount in that year's dollars.

```
operating line = amount × (12 if monthly, else 1) × (1 + rate) ^ (year − first)
                   rate  = the line's own inflation rate, else operating_inflation
                   first = the line's first year, else the start year
reserve line   = amount × (1 + expense_inflation) ^ (year − from)
                   from  = the line's year if marked already inflated (nominal),
                           else the expense base year
```

A monthly amount is per month and a yearly amount per year, both in the dollars of the line's first year. A once or every-few-years amount is per occurrence, in the expense base year's dollars unless the line is marked already inflated. Marked, the amount is in the dollars of the line's own (first) year – a once line is charged exactly as entered, and each later occurrence of an every-few-years line is grown from its first at reserve inflation (spec v1.9). If the demo's exterior repaint ($85,000, every 8 years from 2031) were marked already inflated, the 2031 repaint would be $85,000 and the 2039 one $85,000 × 1.035⁸ = $111,928.77.

**Choice** – a monthly or yearly line whose first year is before the start year grows from that first year, so its start-year amount already includes the growth since then. A line whose first year is after the start year has no amount before it, and is never grown before it starts (confirmed by the board after the first math audit).

**Choice** – a reserve line dated before the expense base year is deflated by the same formula (the exponent is negative).

**Choice** – each frequency keeps only the fields it uses. Operating lines are never already inflated and reserve lines never have their own inflation rate – such a field is dropped when a line is read. Once lines have no last year or interval, and only once lines carry a `useful_life`.

Lines, and occurrences of repeating lines, outside the horizon are kept in the scenario and ignored by the projection, so shortening the horizon never discards data.

## Step 4 – the yearly projection

`project_years` (in `engine.py`) groups the scenario's special assessments by year (several in one year add up). It then runs from the start year to the end year. The first year's starting balance is the scenario's starting balance; each later year starts with the prior year's ending balance.

Each year, in the order the code computes them –

```
dues                = resolved dues per unit per month (step 2)
assessment_per_unit = sum of the scenario's assessments for this year, per unit
total_dues          = dues × units × 12
operating           = Σ operating lines falling in the year, each at its amount for the year (step 3)
contribution        = max(0, total_dues − operating)
assessment          = assessment_per_unit × units
interest            = max(0, starting_balance) × interest_rate
expenses            = Σ reserve lines falling in the year, each at its amount for the year (step 3)
ending_balance      = starting_balance + contribution + assessment + interest − expenses
ffb_next            = Fully Funded Balance for year + 1 (step 1)
percent_funded      = 0 if ffb_next = 0, else ending_balance / ffb_next
owner_dues_year     = dues × 12
dues_increase_vs_current = (dues − current_dues) × 12
cumulative_owner_cost   += owner_dues_year + assessment_per_unit
cumulative_extra        += dues_increase_vs_current + assessment_per_unit
total_from_owners   = total_dues + assessment
low_flag            = ending_balance < cushion
target_met          = percent_funded ≥ target
needs_vote          = (see below)
operating_shortfall = total_dues < operating
owner_cost_year     = owner_dues_year + assessment_per_unit
extra_vs_current    = dues_increase_vs_current + assessment_per_unit
target              = the scenario's percent-funded target, repeated each year for charts
```

Each year's result also carries its operating lines and its reserve lines (`operating_lines`, `expense_lines`), each with its amount for that year, so a screen can show what made up the year's operating and reserve expenses.

A few consequences of these formulas are worth knowing.

- An operating shortfall is a warning only. When dues do not cover operating expenses the contribution is 0, and the gap is not taken from reserves (as in the reference workbook).
- The balance may go negative. Nothing stops the projection. No interest is earned or charged while the starting balance is negative (spec 6, v1.9) – the fund cannot borrow at its savings rate, and a negative balance is already flagged.
- Interest is earned on the starting balance only, not on the year's contributions or assessments.
- `dues_increase_vs_current` is the dues part of the extra cost alone, kept as its own row ("increase vs current dues" in the Plan view).

**Choice** – percent funded is 0 when next year's Fully Funded Balance is 0, matching the reference workbook's `IF(FFB=0,0,…)` guard. The specification gives only the division.

**Choice** – explicit dues for years outside the horizon are kept and ignored, like expense lines.

### Needs owner vote

A year needs an owner vote when either rule fires.

```
dues jump        = max_dues_increase is set
                   and prior_dues > 0
                   and dues / prior_dues − 1 > max_dues_increase
large assessment = max_assessment_share is set
                   and assessment (all units) > max_assessment_share × (operating + contribution)
needs_vote       = dues jump or large assessment
```

**Choice** – `prior_dues` for the first year is the scenario's current dues, so a first-year rise over today's dues can need a vote. For later years it is the prior year's resolved dues.

**Choice** – the dues-jump rule is skipped when the prior year's dues are 0, because no percentage increase exists.

**Choice** – both comparisons are strict. A rise of exactly the limit, or an assessment of exactly the limit, needs no vote.

**Choice** – either limit may be absent (`None`, "no limit"), which turns that rule off.

## Step 5 – the summary measures

`summarise` reads the finished years. "Year 4" and "year 9" are offsets 3 and 8 from the scenario's start year.

| Field | Meaning |
|---|---|
| `dues_y1`, `dues_y4`, `dues_y9`, `dues_end` | Dues per unit per month in year 1, year 4, year 9 and the end year |
| `total_assessments` | Total special assessments per unit over the horizon |
| `lowest_balance`, `lowest_balance_year` | Lowest year-end balance and its year |
| `low_years` | Count of years ending below the minimum cushion |
| `balance_y4`, `pf_y4` | Year-end balance and percent funded in year 4 |
| `balance_y9`, `pf_y9` | Year-end balance and percent funded in year 9 |
| `balance_end`, `pf_end` | Year-end balance and percent funded in the end year |
| `first_target_year` | First year percent funded meets the target, or `None` – shown as "not by {end year}" |
| `outlay_first5` | Owner outlay per unit (dues + assessments) over the first five years – cumulative owner cost at year 5 |
| `outlay_total` | Owner outlay per unit over the whole horizon |
| `extra_first4` | Extra cost vs current dues over the first four years – cumulative extra at year 4 |
| `extra_total` | Extra cost vs current dues over the whole horizon |
| `avg_owner_cost` | `outlay_total` ÷ number of years |
| `avg_extra` | `extra_total` ÷ number of years |
| `vote_years` | Count of years needing an owner vote |
| `shortfall_years` | Count of years with an operating shortfall |

**Choice** – the lowest balance's year is the earliest on a tie, as the workbook's `MATCH` does.

**Choice** – `shortfall_years` is an extra measure beyond the section 6 list. It feeds the Compare view.

**Choice** – `dues_y9`, `balance_y9` and `pf_y9` are `None` when the horizon is shorter than 9 years. The minimum horizon of 5 years guarantees that the year 4 and first-five-years measures always exist.

Because each measure is by year of the scenario's own horizon, two scenarios with different horizons (an adopted plan from an earlier year, say) are compared year 1 to year 1, not calendar year to calendar year.

## Adopted plans

An adopted plan carries an `Adoption` – the date entered, a note and an adoption order (`sequence`). Its own inputs are its record, so nothing is frozen separately, and `run` treats it like any other scenario. The app keeps it read-only (spec 5.2), so its figures never change.

The current adopted plan is the one with the highest adoption order (`current_adoption`), whatever date was entered. Adopting is refused when the scenario has problems in its inputs. Un-adopting removes the `Adoption` and nothing else.

## Input checks

`validate.py` returns every problem it finds as a plain-language sentence. `validate_run(scenario)` checks the scenario's facts and then its dues and assessments, and `run` raises `InvalidInputs` with the whole list if there is any.

**Facts and assumptions**

- The horizon is 5–30 full years (end year − start year + 1). When it is not, that is the only problem reported, since nothing else can be checked over it.
- There are at most 1,000 expense lines.
- A Fully Funded Balance is present for every year from the start year through end year + 1, unless it is worked out. Extra years are allowed and ignored.
- The expense base year is between 50 years before the start year and the end year. **Choice** – the specification sets no bound; an older reserve study is taken to be a typo.
- Expense inflation, operating inflation, the interest rate, both governance limits (when set) and each line's own inflation rate (when set) are between 0% and 50%.
- The percent-funded target is above 0% and at most 100%. **Choice** – the specification does not bound the target.
- The starting balance, current dues, minimum cushion, every expense amount and every Fully Funded Balance are not negative.
- There is at least one unit.
- Every once and every-few-years line has a year, and every every-few-years line an interval of at least 1.
- A useful life, when given, is at least 1 year.
- No line's last year comes before its first year.
- No line's year or last year is more than 50 years before the start year or after the end year. **Choice** – the specification keeps and ignores lines outside the horizon; a year this far out is taken to be a typo, and it would grow amounts past any usable number.
- No two lines share an identifier.

Problems name the line in words, such as "the 2031 expense 'Gate' cannot be negative" or "the monthly expense 'Water' ends before it starts".

Years are contiguous by construction – the horizon is a start year and an end year, not a list.

**Dues and assessments**

- The name is not blank.
- `EXPLICIT` – dues are present for every year of the horizon and none is negative.
- `RATE` – the first-year dues are not negative, every pinned year lies inside the horizon with a value that is not negative, and the yearly increases are sound (spec 5.1)
  - each rate is between 0% and 50%
  - no period names a year outside the horizon, or ends before it starts
  - every year after the start year is covered by exactly one period – gaps and overlaps are each named as runs of years, such as "no yearly dues increase covers 2031, 2033–2035"
- Every special assessment lies inside the horizon and is not negative.

**Choice** – pinned dues and assessments outside the horizon are errors, because they express what a scenario intends for those years. Explicit dues and expense lines outside the horizon are not errors (see step 3).

## Project file format

A project is one JSON file, schema version 3. The demo project is [`demo/fixtures/project.json`](../demo/fixtures/project.json).

```json
{
 "schema_version": 3,
 "name": "Maple Row Condominiums (fictional demo)",
 "notes": "Invented figures for demonstration and testing. Not a real association.",
 "scenarios": [
  {
   "name": "Dues only",
   "facts": { "start_year": 2027, "end_year": 2042, "starting_balance": "185000", "...": "..." },
   "dues": { "mode": "rate", "first_value": "650", "increases": [ { "first_year": null, "last_year": null, "rate": "0.045" } ], "overrides": {} },
   "...": "..."
  }
 ]
}
```

`project_from_dict` / `project_to_dict` (in `model.py`) read and write the whole file as a `Project` – its name, notes and scenarios. `scenario_from_dict` / `scenario_to_dict` and `facts_from_dict` / `facts_to_dict` do the same for the parts. Saving always writes schema 3.

A file saved by the app also carries its storage fields – `id`, `revision`, the project's `times` and each scenario's `scenario_times` (created and modified). Those belong to `hoa_store`, not the engine, and an exported project file keeps the times but not the id or revision.

**Top-level fields**

| Field | Type | Notes |
|---|---|---|
| `schema_version` | whole number | 1, 2 or 3. Missing means 3. Any other version is refused |
| `name` | text | Required – the association's name |
| `notes` | text | Optional |
| `scenarios` | list | Optional, at most 200. Scenario names must be unique, and no two adopted plans may share an adoption order |

**Numbers and text**

- Money and rates are decimal strings, such as `"185000"` or `"0.035"`. Whole numbers may also be written as JSON integers.
- Floats are refused. `0.035` written as a JSON number is an error, because a binary float cannot hold most decimal amounts exactly.
- Surrounding spaces in a number string are allowed. `NaN`, infinities and any magnitude of 10<sup>15</sup> or more are refused.
- Years, intervals, useful lives and the unit count are whole numbers – a JSON integer or a string such as `"2027"`. A fraction such as `"2027.5"` is refused.
- `nominal` and `ffb_from_lines` must be a real `true` or `false`.
- Every text field must be a JSON string with no control characters – anything below a space other than tab, newline and carriage return.
- Year-keyed tables (`ffb`, `explicit`, `overrides`) use the year as a string key.

When writing, every amount is written as a decimal string and year-keyed tables are sorted by year.

**Scenario fields**

| Field | Type | Notes |
|---|---|---|
| `name` | text | Required |
| `description` | text | Optional |
| `facts` | object | Required – the facts and assumptions, below |
| `dues.mode` | `"explicit"` or `"rate"` | |
| `dues.explicit` | year → money | `explicit` mode |
| `dues.first_value` | money | `rate` mode, default 0 |
| `dues.increases` | list | `rate` mode – each `{ "first_year", "last_year", "rate" }`, a year or `null` for the start or end. At most 100. A file without it reads `dues.annual_increase` as one increase over every year |
| `dues.overrides` | year → money | `rate` mode – the pinned years |
| `assessments` | list | Each has `year`, `amount` (per unit) and optional `note` |
| `rounding` | `"dollar"` or `"none"` | Optional, default `"dollar"` |
| `adoption` | object or `null` | Optional – set only on an adopted plan, below |

When a scenario is written back, only the fields for its dues mode are written.

**Facts and assumptions (`facts`)**

| Field | Type | Notes |
|---|---|---|
| `start_year`, `end_year` | whole number | The horizon, inclusive |
| `starting_balance` | money | January 1 of the start year |
| `expense_lines` | list | See below |
| `expense_inflation`, `expense_base_year` | rate, whole number | For once and every-few-years lines |
| `ffb` | year → money | The reserve study's figures, start year through end year + 1 |
| `ffb_from_lines` | `true` or `false` | Optional, default `false`. `true` works the Fully Funded Balance out from the expenses (step 1); `ffb` is then kept but not used, and may be incomplete |
| `operating_inflation` | rate | For monthly and yearly lines without a rate of their own |
| `interest_rate` | rate | |
| `units` | whole number | |
| `current_dues` | money | Per unit per month |
| `cushion` | money | |
| `target` | rate | |
| `max_dues_increase`, `max_assessment_share` | rate or `null` | Optional |
| `sources` | object | Optional – input name → where the figure came from (`ffb` for the Fully Funded Balance) |

**Choice** – a governance limit that is missing or `null` means "no limit", and it is written back as `null`. The specification's 20% and 5% defaults are what a new scenario starts with (and what `Facts` built in code without those fields gets).

**Expense line fields**

| Field | Used by | Notes |
|---|---|---|
| `id` | every line | Required. Lower case, starting with a letter, then letters, digits, `-` or `_`, at most 40 characters. Unique in the scenario, and kept when a scenario is copied, so the same id names the same line across a project's scenarios |
| `frequency` | every line | `"monthly"`, `"yearly"`, `"every"` or `"once"`. Missing means `"once"` |
| `amount` | every line | Per month for monthly lines, per year for yearly lines, per occurrence otherwise |
| `year` | every line | The year of a once line, the first occurrence of an every-few-years line, or the first year of a monthly or yearly line (`null` – from the start year) |
| `end_year` | monthly, yearly, every few years | Last year, or `null` for no end |
| `interval` | every few years | Years between occurrences – also the line's useful life |
| `useful_life` | once | Years between replacements, or `null`. Used only for a worked-out Fully Funded Balance |
| `inflation` | monthly, yearly | The line's own rate, or `null` to follow `operating_inflation` |
| `nominal` | once, every few years | `true` when the amount is already in the dollars of the line's own (first) year |
| `description`, `source` | every line | Optional text |

**`adoption`**

| Field | Type | Notes |
|---|---|---|
| `date` | text | Written `YYYY-MM-DD` – the date the board adopted it, as entered |
| `note` | text | At most 2,000 characters |
| `sequence` | whole number | The adoption order, 1 to 10,000. The highest is the current adopted plan |

### Older files

Older files are upgraded as they are read (`upgrade.py`, spec 8.2), with the same figures, and saved as schema 3.

**Schema 2** had one baseline per project, each scenario holding only its changes to it and an adopted plan a frozen copy of the baseline. `upgrade_v2_project` gives each scenario the baseline as it saw it.

- A working scenario gets the project's baseline with its changes applied – its own values and notes over the baseline's, a changed line in the baseline line's place, its own lines after the baseline's, left-out lines gone, and its own Fully Funded Balance years over the baseline's.
- An adopted plan gets its frozen baseline, with its changes applied again (which changes nothing, since the frozen copy already held them).
- Schema 2 numbered each scenario's own lines from `own-1`. A scenario's own line whose id another scenario already uses for a different line is renumbered to the first free `line-N`, so an id still names one line across the project.
- A project with no scenarios gets one, "Current dues" – the baseline, with grown dues starting at the current dues and a 0% increase.
- The upgrade refuses a baseline of more than 1,000 lines, a scenario changing more than 1,000, and a file that would write more than 50,000 lines in all – each scenario gets its own copy of the baseline's, so a small crafted file must not grow into a huge one.

**Schema 1** had a single operating-expense figure. `upgrade_v1_baseline` first turns its baseline into the schema 2 form.

- Each expense line becomes a once line, with identifiers `line-1`, `line-2` and so on in file order.
- The start-year operating expenses (`operating_start`) become one yearly line with identifier `operating`, description "Operating expenses", no first year and no rate of its own, so it grows at the operating inflation rate from the start year – exactly the old formula. Its source note moves onto the line. A figure of 0 gives no line.

A file that cannot be read raises `ProjectFormatError` with a plain-language message. Each level of the file adds its own words, so a missing figure reads "the project has a bad value – the scenario has a bad value – the set of facts and assumptions is missing 'units'", a float interest rate ends "money and rates must be strings or integers, not float (0.035)", and a repeated name reads "the project has a bad value – scenario names must be unique – 'Dues only'".

## Acceptance figures – the demo project

The demo project is a fictional 24-unit association, Maple Row Condominiums, with a 2027–2042 horizon, a starting balance of $185,000, current dues of $560 a unit a month, 1.5% interest and a 60% target.

Its scenarios start from the same facts, with an expense line of every frequency.

- Operating – management ($58,000 a year), utilities ($3,100 a month, at its own 3.5%), insurance ($41,000 a year, at its own 4.5%), a landscaping contract for 2027–2033 ($13,000 a year at 2.5%) and its renewal from 2034 ($16,500 a year at the operating rate of 4%). The start-year operating total is $149,200.
- Reserve – the reserve study's total for each year, already in that year's dollars, an exterior repaint every 8 years from 2031, gutters every 3 years from 2028 to 2040, and one-time railings (2031) and boiler (2035), the last four in 2026 dollars grown at 3.5%.

Its eight scenarios between them use every dues mode, increases by period, a two-part special assessment, scenarios whose facts differ, a worked-out Fully Funded Balance, an adopted plan, LOW years, operating-shortfall years, needs-vote years, a target met and targets never met.

| Scenario | Dues path, and how its facts differ |
|---|---|
| Dues only | $650 from 2027, +4.5% a year, rounded to whole dollars |
| Two-part assessment | $700 from 2027, +3.5% a year, pinned at $860 in 2032; $5,000 per unit in 2028 and in 2029 |
| Hold then catch up | Explicit dues for every year, starting below current dues; $2,500 per unit in 2033 |
| Steady increase | $640 from 2027, +4.2% a year, cents kept |
| Insurance shock | $680 from 2027, +4.5% a year. Its own interest rate of 2.5% and no assessment limit. Insurance at $47,000 a year growing at 8%, no boiler, a pool resurfacing ($12,000 every 6 years from 2030) and a Fully Funded Balance of $700,000 for 2031 |
| Adopted – two-part assessment | The dues and assessments of Two-part assessment, adopted October 14, 2026, on that autumn's facts – a starting balance of $172,000, 2% interest, no railings or boiler, and a lower Fully Funded Balance with $650,000 for 2030 |
| Worked-out Fully Funded Balance | The dues of Dues only, with its Fully Funded Balance worked out from the expenses. Useful lives of 30 years on the 2029 study total, 25 on the railings and 20 on the boiler, and a clubhouse roof ($40,000 in 2050, 10 years) that falls after the horizon |
| Stepped increases | $650 from 2027, +7% a year for 2028–2030, then +3.5%, pinned at $900 in 2034 |

The key summary measures, from [`demo/fixtures/expected.json`](../demo/fixtures/expected.json). Money is shown to the cent and percentages to two decimals; the fixture itself holds the full figures.

| Measure | Dues only | Two-part assessment | Hold then catch up | Steady increase |
|---|---:|---:|---:|---:|
| Dues per unit per month, 2027 | $650.00 | $700.00 | $515.00 | $640.00 |
| Dues per unit per month, 2030 | $742.00 | $776.00 | $712.50 | $724.07 |
| Dues per unit per month, 2035 | $924.00 | $953.00 | $889.00 | $889.45 |
| Dues per unit per month, 2042 | $1,258.00 | $1,213.00 | $1,211.00 | $1,186.30 |
| Special assessments per unit, total | $0.00 | $10,000.00 | $2,500.00 | $0.00 |
| Lowest year-end balance | $57,739.07 | $226,175.00 | -$55,200.87 | -$28,256.61 |
| Year of lowest balance | 2031 | 2027 | 2039 | 2039 |
| Years below cushion (LOW) | 1 | 0 | 13 | 10 |
| Balance, end of 2030 | $165,269.53 | $460,887.52 | $66,482.23 | $149,082.06 |
| Percent funded, end of 2030 | 23.21% | 64.73% | 9.34% | 20.94% |
| Balance, end of 2035 | $82,675.30 | $456,686.97 | -$8,776.53 | $24,707.55 |
| Percent funded, end of 2035 | 9.55% | 52.74% | -1.01% | 2.85% |
| Balance, end of 2042 | $264,372.93 | $659,757.88 | $76,664.50 | $86,301.60 |
| Percent funded, end of 2042 | 23.19% | 57.87% | 6.72% | 7.57% |
| First year target (60%) is met | not by 2042 | 2030 | not by 2042 | not by 2042 |
| Owner outlay per unit, 2027–2031 | $42,672.00 | $55,048.00 | $38,190.00 | $41,763.94 |
| Owner outlay per unit, 2027–2042 | $177,204.00 | $190,648.00 | $170,146.00 | $170,322.31 |
| Extra cost vs current dues, 2027–2030 | $6,492.00 | $18,532.00 | $2,370.00 | $5,830.12 |
| Extra cost vs current dues, 2027–2042 | $69,684.00 | $83,128.00 | $62,626.00 | $62,802.31 |
| Average owner cost per year | $11,075.25 | $11,915.50 | $10,634.13 | $10,645.14 |
| Average extra cost per year | $4,355.25 | $5,195.50 | $3,914.13 | $3,925.14 |
| Years needing an owner vote | 0 | 3 | 2 | 0 |
| Years with an operating shortfall | 0 | 0 | 2 | 0 |

| Measure | Insurance shock | Adopted – two-part assessment | Worked-out Fully Funded Balance | Stepped increases |
|---|---:|---:|---:|---:|
| Dues per unit per month, 2027 | $680.00 | $700.00 | $650.00 | $650.00 |
| Dues per unit per month, 2030 | $776.00 | $776.00 | $742.00 | $796.00 |
| Dues per unit per month, 2035 | $967.00 | $953.00 | $924.00 | $932.00 |
| Dues per unit per month, 2042 | $1,316.00 | $1,213.00 | $1,258.00 | $1,185.00 |
| Special assessments per unit, total | $0.00 | $10,000.00 | $0.00 | $0.00 |
| Lowest year-end balance | -$4,569.32 | $213,840.00 | $57,739.07 | $102,843.96 |
| Year of lowest balance | 2039 | 2027 | 2031 | 2031 |
| Years below cushion (LOW) | 6 | 0 | 1 | 0 |
| Balance, end of 2030 | $160,393.26 | $452,955.90 | $165,269.53 | $195,804.40 |
| Percent funded, end of 2030 | 22.91% | 64.99% | 82.57% | 27.50% |
| Balance, end of 2035 | $111,622.80 | $569,332.31 | $82,675.30 | $161,164.54 |
| Percent funded, end of 2035 | 12.89% | 66.90% | 61.63% | 18.61% |
| Balance, end of 2042 | $6,435.10 | $808,668.69 | $264,372.93 | $278,858.92 |
| Percent funded, end of 2042 | 0.56% | 71.88% | 96.79% | 24.46% |
| First year target (60%) is met | not by 2042 | 2029 | 2027 | not by 2042 |
| Owner outlay per unit, 2027–2031 | $44,652.00 | $55,048.00 | $42,672.00 | $44,520.00 |
| Owner outlay per unit, 2027–2042 | $185,400.00 | $190,648.00 | $177,204.00 | $177,336.00 |
| Extra cost vs current dues, 2027–2030 | $8,040.00 | $18,532.00 | $6,492.00 | $7,752.00 |
| Extra cost vs current dues, 2027–2042 | $77,880.00 | $83,128.00 | $69,684.00 | $69,816.00 |
| Average owner cost per year | $11,587.50 | $11,915.50 | $11,075.25 | $11,083.50 |
| Average extra cost per year | $4,867.50 | $5,195.50 | $4,355.25 | $4,363.50 |
| Years needing an owner vote | 1 | 3 | 0 | 0 |
| Years with an operating shortfall | 0 | 0 | 0 | 0 |

Some of the formulas and open choices show up directly in these figures.

- The 2031 reserve expenses are $159,427.02 in most scenarios – the study's $27,000 plus the repaint, railings and gutters, $111,500 in 2026 dollars grown by 1.035⁵. The adopted plan has no railings line, so its 2031 figure is $133,297.92.
- Insurance shock and the adopted plan both have reserve expenses of $35,400 in 2035, the study's figure alone, because neither has a boiler line.
- Insurance shock's 2027 operating expenses are $155,200, the usual $149,200 with insurance at $47,000 instead of $41,000. Its 2027 interest is $4,625 (2.5% of $185,000), against $2,775 at 1.5%.
- The adopted plan and Two-part assessment have the same dues and assessments but different balances, because the plan runs on the facts it was adopted with – a $172,000 start and 2% interest ($3,440 in 2027).
- Two-part assessment needs a vote in 2027 because $700 is a 25% rise over current dues of $560, above the 20% limit. It needs one again in 2028 and 2029 because each $120,000 assessment (24 units × $5,000) is more than 5% of that year's budget. Insurance shock needs one only in 2027, where $680 is a 21.4% rise.
- Hold then catch up has operating shortfalls in 2027 and 2028, when dues do not cover operating expenses. It needs votes in 2029 (a 28.3% rise) and 2033 (its assessment). Its balance goes negative – 2032 starts at -$51,170.04, so it earns no interest that year – and its percent funded at the end of 2035 is negative too.
- Steady increase keeps cents, so its 2030 dues are the unrounded $640 × 1.042³ = $724.07429632.
- Stepped increases shows periods, a pin and half-up rounding – see [step 2](#step-2--the-dues-path).
- Worked-out Fully Funded Balance has the same dues, expenses and balances as Dues only – only its percent funded differs. Its Fully Funded Balance at the start of 2027 is $234,170.80 – the repaint $43,987.50 (4 of 8 years, at $85,000 × 1.035), the gutters $3,105.00 (2 of 3 years), the 2029 study total $130,691.50 (28 of 30 years, already in 2029 dollars, so moved back two years), the railings $19,126.80 (21 of 25 years) and the boiler $37,260.00 (12 of 20 years). The clubhouse roof, due in 2050 with a 10-year life, is not yet in service and counts 0.

The acceptance test (`tests/engine/test_acceptance.py`) reads the whole project file, so an older schema passes through its upgrade, and checks every yearly row and every summary measure of every scenario against `expected.json` – money to within half a cent, ratios to within 10<sup>−9</sup>, counts, years and flags exactly.

### Where the expected figures come from

The expected figures never come from the engine. They are produced independently, from a spreadsheet, in three steps.

1. `demo/build_reference_workbook.py` exports `project.json` to `demo/fixtures/reference.xlsx` with the app's Excel exporter (see [workbook.md](workbook.md)) – Method, Project, Compare, Charts and one Plan sheet per scenario, with every result a live Excel formula. Each Plan sheet works out its own expenses and, where it is worked out, its own Fully Funded Balance from the facts and expense rows below its charts. Neither the script nor the exporter runs the engine. The exporter imports only the project model and its input checks, and `tests/workbook/test_independence.py` keeps it that way.
2. `tools/recalc.py` opens the workbook in LibreOffice headless, recalculates every formula, saves the computed values into the file and fails if any cell holds a formula error.
3. `tools/extract_expected.py` reads those computed values back – Plan rows matched by label, summary measures from the Compare sheet – and writes `demo/fixtures/expected.json`.

The builder runs all three steps. After changing the demo project or the exporter's formulas, regenerate the fixtures with

```
uv run python demo/build_reference_workbook.py
```

This needs [LibreOffice](https://www.libreoffice.org/) installed. If it is not in the usual place, set `SOFFICE` to the path of `soffice`. A change to `expected.json` means a formula changed.

A private fixture set for a real project, in the same format, runs when `HOA_PRIVATE_DIR` points at the private data repository. It is skipped otherwise. Its project file is version 1, so it also checks that the version 1 and version 2 upgrades keep the reference workbook's figures.
