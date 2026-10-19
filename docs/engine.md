# Calculation engine

The engine in `src/hoa_engine/` turns a baseline (the building's reserve facts) and one scenario (a funding plan) into a year-by-year projection and a set of summary measures. It is pure Python with no I/O, and every amount is a `Decimal`. This page describes the engine exactly as implemented, with the demo project's acceptance figures at the end.

The specification is [HOA_Reserve_Planner_REQUIREMENTS.md](../HOA_Reserve_Planner_REQUIREMENTS.md), section 6. Where the specification leaves a choice open, this page says what the engine does and marks it **Choice**.

## Entry point

```python
from hoa_engine import run, baseline_from_dict, scenario_from_dict

result = run(baseline, scenario)  # ScenarioResult
result.years  # tuple of YearResult, one per year in the horizon
result.summary  # Summary
```

`run` does three things, in this order.

1. Checks the baseline and the scenario (see [Input checks](#input-checks)). If anything is wrong it raises `InvalidInputs`, whose `problems` attribute lists every problem found in plain language – not just the first.
2. Projects each year from the start year to the end year.
3. Computes the summary measures from those years.

**Choice** – `run` works under its own decimal context, 28 significant digits with half-even rounding. A caller's decimal settings cannot change the figures. Divisions that do not terminate (percent funded, the averages) are carried to 28 significant digits. Nothing is rounded for display inside the engine; that is left to the screens and the exporter.

Rates and percentages are fractions throughout – `0.035` means 3.5%.

## Step 1 – resolve the dues path

Before the yearly loop, `resolve_dues` (in `dues.py`) produces dues per unit per month for every year of the horizon.

The specification offers three dues modes. The engine has two, and they cover all three.

| Spec mode (section 5) | Engine mode | How it is stored |
|---|---|---|
| (a) explicit value for each year | `EXPLICIT` | `explicit` – a value for every year |
| (b) first-year value + annual increase | `RATE` | `first_value`, `annual_increase`, empty `overrides` |
| (c) mode b with pinned years | `RATE` | as mode b, with `overrides` listing the pinned years |

**`EXPLICIT`** – each year's dues are the typed value, used as typed (never rounded).

**`RATE`** – the engine keeps an *anchor*, which starts as the first year and `first_value`. For each year in turn

- a pinned year takes its pinned value, used as typed, and becomes the new anchor
- otherwise the start year takes `first_value`, used as typed
- otherwise the value is `anchor_value × (1 + annual_increase) ^ (year − anchor_year)`, then rounded to whole dollars, half up, when the scenario's rounding is `dollar`

```
dues(year) = anchor_value × (1 + annual_increase) ^ (year − anchor_year)     # then ROUND_HALF_UP to $1 if rounding = dollar
```

**Choice** – rounding applies only to grown values, never to a typed first-year value or a pinned value. Each year is rounded from the *unrounded* growth since the anchor, so rounding never compounds from one year to the next. This matches the reference workbook, which grows an unrounded row and rounds a separate dues row. Pinning the start year replaces `first_value`.

## Step 2 – the yearly projection

`project_years` (in `engine.py`) groups the scenario's special assessments by year (several in one year add up) and the baseline's expense lines by year. It then runs from the start year to the end year. The first year's starting balance is the baseline's starting balance; each later year starts with the prior year's ending balance.

Each year, in the order the code computes them –

```
dues                = resolved dues per unit per month (step 1)
assessment_per_unit = sum of the scenario's assessments for this year, per unit
total_dues          = dues × units × 12
operating           = operating_start × (1 + operating_inflation) ^ (year − start_year)
contribution        = max(0, total_dues − operating)
assessment          = assessment_per_unit × units
interest            = starting_balance × interest_rate
expenses            = Σ this year's expense lines, each
                        amount                                                  if flagged nominal
                        amount × (1 + expense_inflation) ^ (year − expense_base_year)   otherwise
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
target              = the baseline's percent-funded target, repeated each year for charts
```

Each year's result also carries its expense lines, each with its amount for that year, so a screen can show what made up the year's reserve expenses.

A few consequences of these formulas are worth knowing.

- An operating shortfall is a warning only. When dues do not cover operating expenses the contribution is 0, and the gap is not taken from reserves (as in the reference workbook).
- The balance may go negative. Nothing stops the projection, and a negative starting balance earns negative interest, since interest is simply the starting balance times the rate.
- Interest is earned on the starting balance only, not on the year's contributions or assessments.
- `dues_increase_vs_current` is the dues part of the extra cost alone, kept as its own row ("increase vs current dues" in the Plan view).

**Choice** – percent funded is 0 when next year's Fully Funded Balance is 0, matching the reference workbook's `IF(FFB=0,0,…)` guard. The specification gives only the division.

**Choice** – an expense line dated before the expense base year is deflated by the same formula (the exponent is negative). Lines and explicit dues for years outside the horizon are kept in the project and ignored by the projection, so shortening the horizon never discards data.

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

**Choice** – `prior_dues` for the first year is the baseline's current dues, so a first-year rise over today's dues can need a vote. For later years it is the prior year's resolved dues.

**Choice** – the dues-jump rule is skipped when the prior year's dues are 0, because no percentage increase exists.

**Choice** – both comparisons are strict. A rise of exactly the limit, or an assessment of exactly the limit, needs no vote.

**Choice** – either limit may be absent (`None`), which turns that rule off.

## Step 3 – the summary measures

`summarise` reads the finished years. "Year 4" and "year 9" are offsets 3 and 8 from the start year.

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

## Input checks

`validate.py` returns every problem it finds as a plain-language sentence. `run` raises `InvalidInputs` with the whole list if there is any.

**Baseline**

- The horizon is 5–30 full years (end year − start year + 1).
- A Fully Funded Balance is present for every year from the start year through end year + 1. Extra years are allowed and ignored.
- The expense base year is between 50 years before the start year and the end year. **Choice** – the specification sets no bound; an older reserve study is taken to be a typo.
- Expense inflation, operating inflation, the interest rate and both governance limits (when set) are between 0% and 50%.
- The percent-funded target is above 0% and at most 100%. **Choice** – the specification does not bound the target.
- The starting balance, operating expenses, current dues, minimum cushion, every expense line and every Fully Funded Balance are not negative.
- There is at least one unit.

Years are contiguous by construction – the horizon is a start year and an end year, not a list.

**Scenario**

- The name is not blank.
- `EXPLICIT` – dues are present for every year of the horizon and none is negative.
- `RATE` – the first-year dues are not negative, the annual increase is between 0% and 50%, and every pinned year lies inside the horizon with a value that is not negative.
- Every special assessment lies inside the horizon and is not negative.

**Choice** – pinned dues and assessments outside the horizon are errors, because they express what a scenario intends for those years. Explicit dues and expense lines outside the horizon are not errors (see step 2).

## Project file format

A project is one JSON file. The demo project is [`demo/fixtures/project.json`](../demo/fixtures/project.json).

```json
{
 "schema_version": 1,
 "name": "Maple Row Condominiums (fictional demo)",
 "notes": "Invented figures for demonstration and testing. Not a real association.",
 "baseline": { "start_year": 2027, "end_year": 2042, "starting_balance": "185000", "...": "..." },
 "scenarios": [ { "name": "Dues only", "dues": { "mode": "rate", "first_value": "650", "annual_increase": "0.045", "overrides": {} }, "...": "..." } ]
}
```

The engine reads and writes the `baseline` object and each `scenarios` entry with `baseline_from_dict` / `baseline_to_dict` and `scenario_from_dict` / `scenario_to_dict`. The top-level fields (`schema_version`, `name`, `notes`) are part of the file but are not read by the engine.

**Numbers**

- Money and rates are decimal strings, such as `"185000"` or `"0.035"`. Whole numbers may also be written as JSON integers.
- Floats are refused. `0.035` written as a JSON number is an error, because a binary float cannot hold most decimal amounts exactly.
- Surrounding spaces in a number string are allowed. `NaN`, infinities and any magnitude of 10<sup>15</sup> or more are refused.
- Years and the unit count are whole numbers – a JSON integer or a string such as `"2027"`. A fraction such as `"2027.5"` is refused.
- `nominal` must be a real `true` or `false`.
- Year-keyed tables (`ffb`, `explicit`, `overrides`) use the year as a string key.

When writing, every amount is written as a decimal string and year-keyed tables are sorted by year.

**Baseline fields**

| Field | Type | Notes |
|---|---|---|
| `start_year`, `end_year` | whole number | The horizon, inclusive |
| `starting_balance` | money | January 1 of the start year |
| `expense_lines` | list | Each has `year`, `amount`, and optional `description`, `nominal` (default `false`) and `source` |
| `expense_inflation`, `expense_base_year` | rate, whole number | |
| `ffb` | year → money | Start year through end year + 1 |
| `operating_start`, `operating_inflation` | money, rate | |
| `interest_rate` | rate | |
| `units` | whole number | |
| `current_dues` | money | Per unit per month |
| `cushion` | money | |
| `target` | rate | |
| `max_dues_increase`, `max_assessment_share` | rate or `null` | Optional |
| `sources` | object | Optional – input name → where the figure came from |

**Choice** – in a project file, a governance limit that is missing or `null` means "no limit", and it is written back as `null`. The specification's 20% and 5% defaults apply only when a `Baseline` is built in code without those fields.

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

When a scenario is written back, only the fields for its dues mode are written.

A file that cannot be read raises `ProjectFormatError` with a plain-language message, such as "the baseline is missing 'units'" or "the scenario has a bad value – money and rates must be strings or integers, not float (0.035)".

## Acceptance figures – the demo project

The demo project is a fictional 24-unit association, Maple Row Condominiums, with a 2027–2042 horizon. Its four scenarios between them use every dues mode, a two-part special assessment, nominal and inflated expense lines, LOW years, operating-shortfall years, needs-vote years, a target met and targets never met.

| Scenario | Dues path |
|---|---|
| Dues only | $650 from 2027, +4.5% a year, rounded to whole dollars |
| Two-part assessment | $700 from 2027, +3.5% a year, pinned at $860 in 2032; $5,000 per unit in 2028 and in 2029 |
| Hold then catch up | Explicit dues for every year, starting below current dues; $2,500 per unit in 2033 |
| Steady increase | $640 from 2027, +4.2% a year, cents kept |

The key summary measures, from [`demo/fixtures/expected.json`](../demo/fixtures/expected.json). Money is shown to the cent and percentages to two decimals; the fixture itself holds the full figures.

| Measure | Dues only | Two-part assessment | Hold then catch up | Steady increase |
|---|---:|---:|---:|---:|
| Dues per unit per month, 2027 | $650.00 | $700.00 | $515.00 | $640.00 |
| Dues per unit per month, 2030 | $742.00 | $776.00 | $712.50 | $724.07 |
| Dues per unit per month, 2035 | $924.00 | $953.00 | $889.00 | $889.45 |
| Special assessments per unit, total | $0.00 | $10,000.00 | $2,500.00 | $0.00 |
| Lowest year-end balance | $61,783.75 | $225,375.00 | -$45,222.23 | $27,778.19 |
| Year of lowest balance | 2031 | 2027 | 2031 | 2035 |
| Years below cushion (LOW) | 1 | 0 | 10 | 6 |
| Balance, end of 2030 | $165,660.07 | $461,278.06 | $68,747.77 | $149,472.59 |
| Percent funded, end of 2030 | 23.27% | 64.79% | 9.66% | 20.99% |
| Balance, end of 2035 | $85,745.94 | $459,757.60 | -$4,862.06 | $27,778.19 |
| Percent funded, end of 2035 | 9.90% | 53.09% | -0.56% | 3.21% |
| Balance, end of 2042 | $410,632.30 | $806,017.25 | $222,606.96 | $232,124.31 |
| Percent funded, end of 2042 | 36.02% | 70.70% | 19.53% | 20.36% |
| First year target (60%) is met | not by 2042 | 2029 | not by 2042 | not by 2042 |
| Owner outlay per unit, 2027–2031 | $42,672.00 | $55,048.00 | $38,190.00 | $41,763.94 |
| Owner outlay per unit, 2027–2042 | $177,204.00 | $190,648.00 | $170,146.00 | $170,322.31 |
| Extra cost vs current dues, 2027–2030 | $6,492.00 | $18,532.00 | $2,370.00 | $5,830.12 |
| Extra cost vs current dues, 2027–2042 | $69,684.00 | $83,128.00 | $62,626.00 | $62,802.31 |
| Average owner cost per year | $11,075.25 | $11,915.50 | $10,634.13 | $10,645.14 |
| Average extra cost per year | $4,355.25 | $5,195.50 | $3,914.13 | $3,925.14 |
| Years needing an owner vote | 0 | 3 | 2 | 0 |
| Years with an operating shortfall | 0 | 0 | 2 | 0 |

Some of the open choices show up directly in these figures.

- Two-part assessment needs a vote in 2027 because $700 is a 25% rise over current dues of $560, above the 20% limit. It needs one again in 2028 and 2029 because each $120,000 assessment (24 units × $5,000) is more than 5% of that year's budget.
- Hold then catch up has operating shortfalls in 2027 and 2028, when dues do not cover operating expenses. Its balance goes negative, so its percent funded at the end of 2035 is negative too.
- Steady increase keeps cents, so its 2030 dues are the unrounded $640 × 1.042³ = $724.07429632.

The acceptance test (`tests/engine/test_acceptance.py`) checks every yearly row and every summary measure of every scenario against `expected.json` – money to within half a cent, ratios to within 10<sup>−9</sup>, counts, years and flags exactly.

### Where the expected figures come from

The expected figures never come from the engine. They are produced independently, from a spreadsheet, in three steps.

1. `demo/build_reference_workbook.py` writes `demo/fixtures/reference.xlsx` from `project.json` in the reference workbook's layout – Inputs, Expenses, one Plan sheet per scenario and Compare – with every result a live Excel formula. The script never imports the engine.
2. `tools/recalc.py` opens the workbook in LibreOffice headless, recalculates every formula, saves the computed values into the file and fails if any cell holds a formula error.
3. `tools/extract_expected.py` reads those computed values back – Plan rows matched by label, summary measures from the Compare sheet – and writes `demo/fixtures/expected.json`.

The builder runs all three steps. After changing the demo project, regenerate the fixtures with

```
uv run python demo/build_reference_workbook.py
```

This needs [LibreOffice](https://www.libreoffice.org/) installed. If it is not in the usual place, set `SOFFICE` to the path of `soffice`.

A private fixture set for a real project, in the same format, runs when `HOA_DATA_DIR` points at the private data folder. It is skipped otherwise.
