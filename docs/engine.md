# Calculation engine

The engine in `src/hoa_engine/` turns a baseline (the building's reserve facts) and one scenario (a funding plan) into a year-by-year projection and a set of summary measures. It is pure Python with no I/O, and every amount is a `Decimal`. This page describes the engine exactly as implemented, with the demo project's acceptance figures at the end.

The specification is [HOAForecaster_REQUIREMENTS.md](../HOAForecaster_REQUIREMENTS.md) – section 6 for the formulas, section 4.1 for expense frequencies, section 5.1 for a scenario's changes to the baseline and section 5.2 for the adopted plan. Where the specification leaves a choice open, this page says what the engine does and marks it **Choice**.

## Entry point

```python
from hoa_engine import run, project_from_dict

project = project_from_dict(raw)  # a whole project file, read and checked
result = run(project.baseline, project.scenarios[0])  # ScenarioResult
result.years  # tuple of YearResult, one per year of the scenario's horizon
result.summary  # Summary
```

`run` does four things, in this order.

1. Works out the baseline the scenario runs on – its **own baseline** (see [Step 0](#step-0--the-scenarios-own-baseline)).
2. Checks that baseline and the scenario (see [Input checks](#input-checks)). If anything is wrong it raises `InvalidInputs`, whose `problems` attribute lists every problem found in plain language – not just the first.
3. Projects each year from the own baseline's start year to its end year.
4. Computes the summary measures from those years.

**Choice** – `run` works under its own decimal context, 28 significant digits with half-even rounding. A caller's decimal settings cannot change the figures. Divisions that do not terminate (percent funded, the averages) are carried to 28 significant digits. Nothing is rounded for display inside the engine; that is left to the screens and the exporter.

Rates and percentages are fractions throughout – `0.035` means 3.5%.

## Step 0 – the scenario's own baseline

Every input in the formulas below is the scenario's own (spec section 6). `baseline_for(baseline, scenario)` in `model.py` produces it.

```
own baseline = apply_changes(adopted plan's frozen baseline, changes)   if the scenario is adopted
             = apply_changes(project baseline, changes)                  otherwise
```

`apply_changes` builds the baseline as one scenario sees it from the scenario's `Changes`.

- **Values** – each input the scenario sets replaces the baseline's. These are the start and end year, starting balance, units, current dues, operating inflation, reserve expense inflation, expense base year, interest rate, cushion, target and the two governance limits. A limit set to `None` is the scenario's own "no limit".
- **Source notes** – the scenario's notes replace the baseline's, key by key.
- **Expense lines**, by line identifier
  - a changed baseline line is replaced by the scenario's full copy, in the baseline line's place
  - a line set to `None` is left out
  - the scenario's own lines (identifiers the baseline does not have) come after the baseline's lines, in the order the scenario lists them
  - every other line follows the baseline, including lines added to the baseline after the scenario was made
- **Fully Funded Balance** – the scenario's years replace the baseline's, year by year.

A scenario with no changes runs on the baseline itself.

**Choice** – a changed line whose baseline line has since been deleted stays as the scenario's own line, and a leave-out of a deleted line does nothing. When a project file is read, such leave-outs are dropped (except on adopted plans, which are kept exactly as adopted), so a later line given the same identifier is not left out by mistake.

**Choice** – a scenario that sets its own start year also moves the start of every monthly and yearly line without a first year, since those lines start at "the start year" of the baseline the scenario runs on (spec 5.1).

### Adopted plans

An adopted plan carries an `Adoption` – the date entered, a note, an adoption order (`sequence`) and a frozen copy of the baseline. Its figures come from its own inputs against that frozen copy, so they never change when the project's baseline is edited.

`frozen_baseline(baseline, scenario)` makes the frozen copy when a scenario is adopted.

```
frozen = apply_changes(project baseline, scenario's changes), with its Fully Funded Balance cut to the plan's years and one more
```

**Choice** – the frozen copy is stored with the plan's changes already applied. Applying them again when the plan is run leaves it as it is, because every changed value, note, line and Fully Funded Balance year is already in it, and every left-out line is already gone. The plan keeps its changes alongside, so the screens and the workbook can mark which figures were its own.

The current adopted plan is the one with the highest adoption order (`current_adoption`), whatever date was entered. Adopting is refused when the scenario has problems in its inputs. Un-adopting removes the `Adoption` and nothing else, so the scenario runs on today's baseline with its changes as they were.

## Step 1 – resolve the dues path

Before the yearly loop, `resolve_dues` (in `dues.py`) produces dues per unit per month for every year of the scenario's horizon.

The specification offers three dues modes. The engine has two, and they cover all three.

| Spec mode (section 5) | Engine mode | How it is stored |
|---|---|---|
| (a) explicit value for each year | `EXPLICIT` | `explicit` – a value for every year |
| (b) first-year value + annual increase | `RATE` | `first_value`, `annual_increase`, empty `overrides` |
| (c) mode b with pinned years | `RATE` | as mode b, with `overrides` listing the pinned years |

**`EXPLICIT`** – each year's dues are the typed value, used as typed (never rounded).

**`RATE`** – the engine keeps an *anchor*, which starts as the start year and `first_value`. For each year in turn

- a pinned year takes its pinned value, used as typed, and becomes the new anchor
- otherwise the start year takes `first_value`, used as typed
- otherwise the value is grown from the anchor, then rounded to whole dollars, half up, when the scenario's rounding is `dollar`

```
dues(year) = anchor_value × (1 + annual_increase) ^ (year − anchor_year)     # then ROUND_HALF_UP to $1 if rounding = dollar
```

**Choice** – rounding applies only to grown values, never to a typed first-year value or a pinned value. Each year is rounded from the *unrounded* growth since the anchor, so rounding never compounds from one year to the next. This matches the reference workbook, which grows an unrounded row and rounds a separate dues row. Pinning the start year replaces `first_value`.

## Step 2 – expense lines by frequency

Every expense line has a frequency (spec 4.1). Monthly and yearly lines are the operating expenses, paid from dues. Once and every-few-years lines are the reserve expenses, paid from reserves.

`falls_in(line, year)` decides whether a line has an amount in a year.

| Frequency | Falls in `year` when |
|---|---|
| Monthly, yearly | `year ≥ first year` (no first year – always) and `year ≤ last year` (no last year – always) |
| Every few years | `year ≥ first year`, `(year − first year)` is a whole multiple of the interval, and `year ≤ last year` (no last year – always) |
| Once | `year = its year` |

`line_amount(line, year)` gives its amount in that year's dollars, using the scenario's own baseline.

```
operating line   = amount × (12 if monthly, else 1) × (1 + rate) ^ (year − first)
                     rate  = the line's own inflation rate, else the operating inflation rate
                     first = the line's first year, else the start year
reserve line     = amount                                                    if marked as already in that year's dollars (nominal)
                 = amount × (1 + expense_inflation) ^ (year − expense_base_year)   otherwise
```

A monthly amount is per month and a yearly amount per year, both in the dollars of the line's first year. A once or every-few-years amount is per occurrence, in the expense base year's dollars unless the line is marked nominal.

**Choice** – a monthly or yearly line whose first year is before the start year grows from that first year, so its start-year amount already includes the growth since then. A line whose first year is after the start year has no amount before it.

**Choice** – a reserve line dated before the expense base year is deflated by the same formula (the exponent is negative).

**Choice** – each frequency keeps only the fields it uses. Operating lines are never nominal and reserve lines never have their own inflation rate – such a field is dropped when a line is read. Once lines have no last year or interval.

Lines, and occurrences of repeating lines, outside the horizon are kept in the project and ignored by the projection, so shortening the horizon never discards data.

## Step 3 – the yearly projection

`project_years` (in `engine.py`) groups the scenario's special assessments by year (several in one year add up). It then runs from the own baseline's start year to its end year. The first year's starting balance is the own baseline's starting balance; each later year starts with the prior year's ending balance.

Each year, in the order the code computes them –

```
dues                = resolved dues per unit per month (step 1)
assessment_per_unit = sum of the scenario's assessments for this year, per unit
total_dues          = dues × units × 12
operating           = Σ operating lines falling in the year, each at its amount for the year (step 2)
contribution        = max(0, total_dues − operating)
assessment          = assessment_per_unit × units
interest            = starting_balance × interest_rate
expenses            = Σ reserve lines falling in the year, each at its amount for the year (step 2)
ending_balance      = starting_balance + contribution + assessment + interest − expenses
ffb_next            = Fully Funded Balance for year + 1
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
- The balance may go negative. Nothing stops the projection, and a negative starting balance earns negative interest, since interest is simply the starting balance times the rate.
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

**Choice** – `prior_dues` for the first year is the current dues (the scenario's own, if it changes them), so a first-year rise over today's dues can need a vote. For later years it is the prior year's resolved dues.

**Choice** – the dues-jump rule is skipped when the prior year's dues are 0, because no percentage increase exists.

**Choice** – both comparisons are strict. A rise of exactly the limit, or an assessment of exactly the limit, needs no vote.

**Choice** – either limit may be absent (`None`), which turns that rule off. A scenario can turn a rule off for itself by changing the limit to "no limit".

## Step 4 – the summary measures

`summarise` reads the finished years. "Year 4" and "year 9" are offsets 3 and 8 from the scenario's own start year.

| Field | Meaning |
|---|---|
| `dues_y1`, `dues_y4`, `dues_y9` | Dues per unit per month in year 1, year 4 and year 9 |
| `total_assessments` | Total special assessments per unit over the horizon |
| `lowest_balance`, `lowest_balance_year` | Lowest year-end balance and its year – the earliest year on a tie, as the workbook's `MATCH` does |
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

**Choice** – `shortfall_years` is an extra measure beyond the section 6 list. It feeds the Compare view.

**Choice** – `dues_y9`, `balance_y9` and `pf_y9` are `None` when the horizon is shorter than 9 years. The minimum horizon of 5 years guarantees that the year 4 and first-five-years measures always exist.

Because each measure is by year of the scenario's own horizon, two scenarios with different horizons (one with its own start year, or an adopted plan from an earlier year) are compared year 1 to year 1, not calendar year to calendar year.

## Input checks

`validate.py` returns every problem it finds as a plain-language sentence. `run` checks the scenario's own baseline (step 0) and then the scenario, and raises `InvalidInputs` with the whole list if there is any. So a scenario with its own horizon needs a Fully Funded Balance through its own end year + 1, and its typed dues, pinned years and assessments must fall in its own years (spec 5.1).

**Baseline** (the project's, or a scenario's own)

- The horizon is 5–30 full years (end year − start year + 1). When it is not, that is the only problem reported, since nothing else can be checked over it.
- There are at most 1,000 expense lines, and a scenario changes at most 1,000.
- A Fully Funded Balance is present for every year from the start year through end year + 1. Extra years are allowed and ignored.
- The expense base year is between 50 years before the start year and the end year. **Choice** – the specification sets no bound; an older reserve study is taken to be a typo.
- Expense inflation, operating inflation, the interest rate, both governance limits (when set) and each line's own inflation rate (when set) are between 0% and 50%.
- The percent-funded target is above 0% and at most 100%. **Choice** – the specification does not bound the target.
- The starting balance, current dues, minimum cushion, every expense amount and every Fully Funded Balance are not negative.
- There is at least one unit.
- Every once and every-few-years line has a year, and every every-few-years line an interval of at least 1.
- No line's last year comes before its first year.
- No line's year or last year is more than 50 years before the start year or after the end year. **Choice** – the specification keeps and ignores lines outside the horizon; a year this far out is taken to be a typo, and it would grow amounts past any usable number.
- No two lines share an identifier.

Problems name the line in words, such as "the 2031 expense 'Gate' cannot be negative" or "the monthly expense 'Water' ends before it starts".

Years are contiguous by construction – the horizon is a start year and an end year, not a list.

**Scenario**

- The name is not blank.
- `EXPLICIT` – dues are present for every year of the horizon and none is negative.
- `RATE` – the first-year dues are not negative, the annual increase is between 0% and 50%, and every pinned year lies inside the horizon with a value that is not negative.
- Every special assessment lies inside the horizon and is not negative.

**Choice** – pinned dues and assessments outside the horizon are errors, because they express what a scenario intends for those years. Explicit dues and expense lines outside the horizon are not errors (see step 2).

## Project file format

A project is one JSON file, schema version 2. The demo project is [`demo/fixtures/project.json`](../demo/fixtures/project.json).

```json
{
 "schema_version": 2,
 "name": "Maple Row Condominiums (fictional demo)",
 "notes": "Invented figures for demonstration and testing. Not a real association.",
 "baseline": { "start_year": 2027, "end_year": 2042, "starting_balance": "185000", "...": "..." },
 "scenarios": [ { "name": "Dues only", "dues": { "mode": "rate", "first_value": "650", "annual_increase": "0.045", "overrides": {} }, "...": "..." } ]
}
```

`project_from_dict` / `project_to_dict` (in `model.py`) read and write the whole file as a `Project` – its name, notes, baseline and scenarios. `baseline_from_dict` / `baseline_to_dict` and `scenario_from_dict` / `scenario_to_dict` do the same for the parts. `run` itself takes only a baseline and one scenario.

A file saved by the app also carries its storage fields – `id`, `revision` and the created and modified times of the project, its baseline and each scenario. Those belong to `hoa_store`, not the engine, and an exported project file keeps the times but not the id or revision.

**Top-level fields**

| Field | Type | Notes |
|---|---|---|
| `schema_version` | whole number | 1 or 2. Missing means 2. Any other version is refused |
| `name` | text | Required – the association's name |
| `notes` | text | Optional |
| `baseline` | object | Required – see below |
| `scenarios` | list | Optional. Scenario names must be unique, and no two adopted plans may share an adoption order |

**Numbers and text**

- Money and rates are decimal strings, such as `"185000"` or `"0.035"`. Whole numbers may also be written as JSON integers.
- Floats are refused. `0.035` written as a JSON number is an error, because a binary float cannot hold most decimal amounts exactly.
- Surrounding spaces in a number string are allowed. `NaN`, infinities and any magnitude of 10<sup>15</sup> or more are refused.
- Years, intervals and the unit count are whole numbers – a JSON integer or a string such as `"2027"`. A fraction such as `"2027.5"` is refused.
- `nominal` must be a real `true` or `false`.
- Every text field must be a JSON string with no control characters – anything below a space other than tab, newline and carriage return.
- Year-keyed tables (`ffb`, `explicit`, `overrides`) use the year as a string key.

When writing, every amount is written as a decimal string and year-keyed tables are sorted by year.

**Baseline fields**

| Field | Type | Notes |
|---|---|---|
| `start_year`, `end_year` | whole number | The horizon, inclusive |
| `starting_balance` | money | January 1 of the start year |
| `expense_lines` | list | See below |
| `expense_inflation`, `expense_base_year` | rate, whole number | For once and every-few-years lines |
| `ffb` | year → money | Start year through end year + 1 |
| `operating_inflation` | rate | For monthly and yearly lines without a rate of their own |
| `interest_rate` | rate | |
| `units` | whole number | |
| `current_dues` | money | Per unit per month |
| `cushion` | money | |
| `target` | rate | |
| `max_dues_increase`, `max_assessment_share` | rate or `null` | Optional |
| `sources` | object | Optional – input name → where the figure came from (`ffb` for the Fully Funded Balance) |

**Expense line fields**

| Field | Used by | Notes |
|---|---|---|
| `id` | every line | Required in a baseline. Lower case, starting with a letter, then letters, digits, `-` or `_`, at most 40 characters. Unique in the baseline |
| `frequency` | every line | `"monthly"`, `"yearly"`, `"every"` or `"once"`. Missing means `"once"` |
| `amount` | every line | Per month for monthly lines, per year for yearly lines, per occurrence otherwise |
| `year` | every line | The year of a once line, the first occurrence of an every-few-years line, or the first year of a monthly or yearly line (`null` – from the start year) |
| `end_year` | monthly, yearly, every few years | Last year, or `null` for no end |
| `interval` | every few years | Years between occurrences |
| `inflation` | monthly, yearly | The line's own rate, or `null` to follow `operating_inflation` |
| `nominal` | once, every few years | `true` when the amount is already in that year's dollars |
| `description`, `source` | every line | Optional text |

**Choice** – in a project file, a governance limit that is missing or `null` means "no limit", and it is written back as `null`. The specification's 20% and 5% defaults are what a new project starts with (and what a `Baseline` built in code without those fields gets).

**Scenario fields**

| Field | Type | Notes |
|---|---|---|
| `name` | text | Required |
| `description` | text | Optional |
| `dues.mode` | `"explicit"` or `"rate"` | |
| `dues.explicit` | year → money | `explicit` mode |
| `dues.first_value`, `dues.annual_increase` | money, rate | `rate` mode, each defaulting to 0 |
| `dues.overrides` | year → money | `rate` mode – the pinned years |
| `assessments` | list | Each has `year`, `amount` (per unit) and optional `note` |
| `rounding` | `"dollar"` or `"none"` | Optional, default `"dollar"` |
| `changes` | object | Optional – the scenario's changes to the baseline, below |
| `adoption` | object or `null` | Optional – set only on an adopted plan, below |

When a scenario is written back, only the fields for its dues mode are written.

**`changes`**

| Field | Type | Notes |
|---|---|---|
| `values` | input name → value | Only the inputs listed in [Step 0](#step-0--the-scenarios-own-baseline). Years and units as whole numbers, the rest as decimal strings. Only a governance limit may be `null` (no limit) |
| `sources` | input name → text | The scenario's own source notes. A blank note is dropped – the scenario follows the baseline's |
| `expense_lines` | line id → line or `null` | A full line (without its `id`, which is the key) changes or adds a line; `null` leaves a baseline line out |
| `ffb` | year → money | The scenario's own Fully Funded Balance years |

**`adoption`**

| Field | Type | Notes |
|---|---|---|
| `date` | text | Written `YYYY-MM-DD` – the date the board adopted it, as entered |
| `note` | text | At most 2,000 characters |
| `sequence` | whole number | The adoption order, 1 to 10,000. The highest is the current adopted plan |
| `baseline` | object | The frozen baseline, in the baseline's own format |

### Version 1 files

A schema 1 file still opens and is saved as version 2 (spec 8.2). `upgrade_v1_baseline` turns its baseline into the new form with the same figures.

- Each expense line becomes a once line, with identifiers `line-1`, `line-2` and so on in file order.
- The start-year operating expenses (`operating_start`) become one yearly line with identifier `operating`, description "Operating expenses", no first year and no rate of its own, so it grows at the operating inflation rate from the start year – exactly the old formula. Its source note moves onto the line. A figure of 0 gives no line.

A file that cannot be read raises `ProjectFormatError` with a plain-language message, such as "the baseline is missing 'units'", "the scenario has a bad value – money and rates must be strings or integers, not float (0.035)" or "the project has a bad value – scenario names must be unique – 'Dues only'".

## Acceptance figures – the demo project

The demo project is a fictional 24-unit association, Maple Row Condominiums, with a 2027–2042 horizon, a starting balance of $185,000, current dues of $560 a unit a month and a 60% target.

Its baseline has an expense line of every frequency.

- Operating – management ($58,000 a year), utilities ($3,100 a month, at its own 3.5%), insurance ($41,000 a year, at its own 4.5%), a landscaping contract for 2027–2033 ($13,000 a year at 2.5%) and its renewal from 2034 ($16,500 a year at the operating rate of 4%). The start-year operating total is $149,200.
- Reserve – the reserve study's total for each year, already in that year's dollars, an exterior repaint every 8 years from 2031, gutters every 3 years from 2028 to 2040, and one-off railings (2031) and boiler (2035) in 2026 dollars, grown at 3.5%.

Its six scenarios between them use every dues mode, a two-part special assessment, changes to the baseline, an adopted plan, LOW years, operating-shortfall years, needs-vote years, a target met and targets never met.

| Scenario | Dues path and changes |
|---|---|
| Dues only | $650 from 2027, +4.5% a year, rounded to whole dollars |
| Two-part assessment | $700 from 2027, +3.5% a year, pinned at $860 in 2032; $5,000 per unit in 2028 and in 2029 |
| Hold then catch up | Explicit dues for every year, starting below current dues; $2,500 per unit in 2033 |
| Steady increase | $640 from 2027, +4.2% a year, cents kept |
| Insurance shock | $680 from 2027, +4.5% a year. Its own interest rate of 2.5% and no assessment limit. Insurance changed to $47,000 a year growing at 8%, the boiler left out, a pool resurfacing of its own ($12,000 every 6 years from 2030) and its own Fully Funded Balance of $700,000 for 2031 |
| Adopted – two-part assessment | The dues and assessments of Two-part assessment, with its own interest rate of 2% and the railings left out, adopted October 14, 2026. Its frozen baseline is the baseline as it stood then – a starting balance of $172,000, no boiler line yet and a lower Fully Funded Balance – plus its own $650,000 for 2030 |

The key summary measures, from [`demo/fixtures/expected.json`](../demo/fixtures/expected.json). Money is shown to the cent and percentages to two decimals; the fixture itself holds the full figures.

| Measure | Dues only | Two-part assessment | Hold then catch up | Steady increase | Insurance shock | Adopted – two-part assessment |
|---|---:|---:|---:|---:|---:|---:|
| Dues per unit per month, 2027 | $650.00 | $700.00 | $515.00 | $640.00 | $680.00 | $700.00 |
| Dues per unit per month, 2030 | $742.00 | $776.00 | $712.50 | $724.07 | $776.00 | $776.00 |
| Dues per unit per month, 2035 | $924.00 | $953.00 | $889.00 | $889.45 | $967.00 | $953.00 |
| Special assessments per unit, total | $0.00 | $10,000.00 | $2,500.00 | $0.00 | $0.00 | $10,000.00 |
| Lowest year-end balance | $57,739.07 | $226,175.00 | -$56,692.49 | -$28,256.61 | -$4,569.32 | $213,840.00 |
| Year of lowest balance | 2031 | 2027 | 2039 | 2039 | 2039 | 2027 |
| Years below cushion (LOW) | 1 | 0 | 14 | 10 | 6 | 0 |
| Balance, end of 2030 | $165,269.53 | $460,887.52 | $66,482.23 | $149,082.06 | $160,393.26 | $452,955.90 |
| Percent funded, end of 2030 | 23.21% | 64.73% | 9.34% | 20.94% | 22.91% | 64.99% |
| Balance, end of 2035 | $82,675.30 | $456,686.97 | -$9,952.61 | $24,707.55 | $111,622.80 | $569,332.31 |
| Percent funded, end of 2035 | 9.55% | 52.74% | -1.15% | 2.85% | 12.89% | 66.90% |
| Balance, end of 2042 | $264,372.93 | $659,757.88 | $74,105.79 | $85,864.94 | $6,315.09 | $808,668.69 |
| Percent funded, end of 2042 | 23.19% | 57.87% | 6.50% | 7.53% | 0.55% | 71.88% |
| First year target (60%) is met | not by 2042 | 2030 | not by 2042 | not by 2042 | not by 2042 | 2029 |
| Owner outlay per unit, 2027–2031 | $42,672.00 | $55,048.00 | $38,190.00 | $41,763.94 | $44,652.00 | $55,048.00 |
| Owner outlay per unit, 2027–2042 | $177,204.00 | $190,648.00 | $170,146.00 | $170,322.31 | $185,400.00 | $190,648.00 |
| Extra cost vs current dues, 2027–2030 | $6,492.00 | $18,532.00 | $2,370.00 | $5,830.12 | $8,040.00 | $18,532.00 |
| Extra cost vs current dues, 2027–2042 | $69,684.00 | $83,128.00 | $62,626.00 | $62,802.31 | $77,880.00 | $83,128.00 |
| Average owner cost per year | $11,075.25 | $11,915.50 | $10,634.13 | $10,645.14 | $11,587.50 | $11,915.50 |
| Average extra cost per year | $4,355.25 | $5,195.50 | $3,914.13 | $3,925.14 | $4,867.50 | $5,195.50 |
| Years needing an owner vote | 0 | 3 | 2 | 0 | 1 | 3 |
| Years with an operating shortfall | 0 | 0 | 2 | 0 | 0 | 0 |

Some of the formulas and open choices show up directly in these figures.

- The 2031 reserve expenses are $159,427.02 in the baseline – the study's $27,000 plus the repaint, railings and gutters, $111,500 in 2026 dollars grown by 1.035<sup>5</sup>. The adopted plan leaves the railings out, so its 2031 figure is $133,297.92.
- Insurance shock and the adopted plan both have reserve expenses of $35,400 in 2035, the study's figure alone – one because it leaves the boiler out, the other because its frozen baseline was taken before the boiler line was added.
- Insurance shock's 2027 operating expenses are $155,200, the baseline's $149,200 with insurance at $47,000 instead of $41,000. Its 2027 interest is $4,625 (2.5% of $185,000), against $2,775 at the baseline's 1.5%.
- The adopted plan and Two-part assessment have the same dues and assessments but different balances, because the plan runs on its frozen baseline – a $172,000 start and 2% interest ($3,440 in 2027).
- Two-part assessment needs a vote in 2027 because $700 is a 25% rise over current dues of $560, above the 20% limit. It needs one again in 2028 and 2029 because each $120,000 assessment (24 units × $5,000) is more than 5% of that year's budget. Insurance shock needs one only in 2027, where $680 is a 21.4% rise.
- Hold then catch up has operating shortfalls in 2027 and 2028, when dues do not cover operating expenses. It needs votes in 2029 (a 28.3% rise) and 2033 (its assessment). Its balance goes negative, so its percent funded at the end of 2035 is negative too.
- Steady increase keeps cents, so its 2030 dues are the unrounded $640 × 1.042³ = $724.07429632.

The acceptance test (`tests/engine/test_acceptance.py`) reads the whole project file, so an older schema passes through its upgrade, and checks every yearly row and every summary measure of every scenario against `expected.json` – money to within half a cent, ratios to within 10<sup>−9</sup>, counts, years and flags exactly.

### Where the expected figures come from

The expected figures never come from the engine. They are produced independently, from a spreadsheet, in three steps.

1. `demo/build_reference_workbook.py` exports `project.json` to `demo/fixtures/reference.xlsx` with the app's Excel exporter (see [workbook.md](workbook.md)) – Method, Inputs, Compare, Charts, Expenses and one Plan sheet per scenario, with every result a live Excel formula. Each Plan sheet works out its own expenses from the Expenses sheet and its own blocks of assumptions, Fully Funded Balance and expense changes, and the adopted plan's sheet from its frozen baseline typed in full. Neither the script nor the exporter runs the engine. The exporter imports only the project model and its input checks, and `tests/workbook/test_independence.py` keeps it that way.
2. `tools/recalc.py` opens the workbook in LibreOffice headless, recalculates every formula, saves the computed values into the file and fails if any cell holds a formula error.
3. `tools/extract_expected.py` reads those computed values back – Plan rows matched by label, summary measures from the Compare sheet – and writes `demo/fixtures/expected.json`.

The builder runs all three steps. After changing the demo project or the exporter's formulas, regenerate the fixtures with

```
uv run python demo/build_reference_workbook.py
```

This needs [LibreOffice](https://www.libreoffice.org/) installed. If it is not in the usual place, set `SOFFICE` to the path of `soffice`. A change to `expected.json` means a formula changed.

A private fixture set for a real project, in the same format, runs when `HOA_PRIVATE_DIR` points at the private data repository. It is skipped otherwise. Its project file is version 1, so it also checks that the upgrade keeps the reference workbook's figures.
