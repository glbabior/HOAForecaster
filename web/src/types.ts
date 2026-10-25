// The JSON the local server sends and receives. Money and rates are exact decimal strings;
// rates and percentages are fractions ("0.03" is 3%).

export type Dec = string;

/** How often an expense falls (spec 4.1) – monthly and yearly lines are operating costs paid
 * from dues; once and every-few-years lines are reserve expenses. */
export type Frequency = "monthly" | "yearly" | "every" | "once";

export interface ExpenseLine {
  id: string;
  frequency: Frequency;
  /** the year of a once line, the first of an every-few-years line, or the first year of a
   * monthly or yearly line (null – from the start year) */
  year: number | null;
  amount: Dec;
  description: string;
  source: string;
  /** repeating lines – the last year it applies (null – to the end) */
  end_year?: number | null;
  /** every-few-years lines – the years between occurrences */
  interval?: number | null;
  /** monthly and yearly lines – their own inflation rate (null – the operating rate) */
  inflation?: Dec | null;
  /** once and every-few-years lines – already in that year's dollars */
  nominal?: boolean;
}

export const isOperating = (f: Frequency): boolean => f === "monthly" || f === "yearly";

export interface Baseline {
  start_year: number;
  end_year: number;
  starting_balance: Dec;
  expense_lines: ExpenseLine[];
  expense_inflation: Dec;
  expense_base_year: number;
  ffb: Record<string, Dec>;
  operating_inflation: Dec;
  interest_rate: Dec;
  units: number;
  current_dues: Dec;
  cushion: Dec;
  target: Dec;
  max_dues_increase: Dec | null;
  max_assessment_share: Dec | null;
  sources: Record<string, string>;
}

export interface Assessment {
  year: number;
  amount: Dec;
  note: string;
}

export type DuesPath =
  | { mode: "explicit"; explicit: Record<string, Dec> }
  | { mode: "rate"; first_value: Dec; annual_increase: Dec; overrides: Record<string, Dec> };

/** The baseline inputs a scenario can change for itself (spec 5.1). */
export type ChangeableKey =
  | "start_year"
  | "end_year"
  | "starting_balance"
  | "units"
  | "current_dues"
  | "operating_inflation"
  | "expense_inflation"
  | "expense_base_year"
  | "interest_rate"
  | "cushion"
  | "target"
  | "max_dues_increase"
  | "max_assessment_share";

/** A scenario's own values – only what it changes; the rest follows the baseline. */
export interface Changes {
  /** years and counts as numbers, money and rates as decimal strings; null for "no limit" */
  values: Partial<Record<ChangeableKey, Dec | number | null>>;
  sources: Record<string, string>;
  /** by line id – its own full copy of a baseline line, a line of its own, or null to leave a
   * baseline line out */
  expense_lines: Record<string, Omit<ExpenseLine, "id"> | null>;
  ffb: Record<string, Dec>;
}

/** The board's adoption of a scenario (spec 5.2). */
export interface Adoption {
  date: string; // YYYY-MM-DD, as entered
  note: string;
  /** adoption order – the highest is the current adopted plan */
  sequence: number;
  /** the baseline as the plan saw it when adopted, its changes already applied */
  baseline: Baseline;
}

export interface Scenario {
  name: string;
  description: string;
  dues: DuesPath;
  assessments: Assessment[];
  rounding: "dollar" | "none";
  changes: Changes;
  /** set once the board has adopted it – then read-only, run on its frozen baseline */
  adoption?: Adoption | null;
}

export interface Project {
  schema_version: number;
  name: string;
  notes: string;
  baseline: Baseline;
  scenarios: Scenario[];
}

export interface Times {
  created: string;
  modified: string;
}

export interface StoredProject {
  id: string;
  revision: number;
  times: Times;
  baseline_times: Times;
  scenario_times: Record<string, Times>;
  project: Project;
}

export interface ProjectSummary {
  id: string;
  name: string;
  modified: string;
  scenarios: number;
}

/** An expense line's amount in one year of the results. */
export interface LineAmount {
  id: string;
  frequency: Frequency;
  description: string;
  source: string;
  nominal: boolean;
  amount: Dec;
}

export interface YearResult {
  year: number;
  dues: Dec;
  assessment_per_unit: Dec;
  total_dues: Dec;
  operating: Dec;
  operating_lines: LineAmount[];
  contribution: Dec;
  assessment: Dec;
  total_from_owners: Dec;
  interest: Dec;
  expenses: Dec;
  expense_lines: LineAmount[];
  starting_balance: Dec;
  ending_balance: Dec;
  ffb_next: Dec;
  percent_funded: Dec;
  target: Dec;
  low_flag: boolean;
  target_met: boolean;
  needs_vote: boolean;
  operating_shortfall: boolean;
  owner_dues_year: Dec;
  owner_cost_year: Dec;
  dues_increase_vs_current: Dec;
  extra_vs_current: Dec;
  cumulative_owner_cost: Dec;
  cumulative_extra: Dec;
}

export interface Summary {
  dues_y1: Dec;
  dues_y4: Dec;
  dues_y9: Dec | null;
  total_assessments: Dec;
  lowest_balance: Dec;
  lowest_balance_year: number;
  low_years: number;
  balance_y4: Dec;
  pf_y4: Dec;
  balance_y9: Dec | null;
  pf_y9: Dec | null;
  balance_end: Dec;
  pf_end: Dec;
  first_target_year: number | null;
  outlay_first5: Dec;
  outlay_total: Dec;
  extra_first4: Dec;
  extra_total: Dec;
  avg_owner_cost: Dec;
  avg_extra: Dec;
  vote_years: number;
  shortfall_years: number;
}

export interface ScenarioResult {
  years: YearResult[];
  summary: Summary;
}

export type ScenarioOutcome = { result: ScenarioResult } | { problems: string[] };

export interface ProjectResults {
  baseline_problems: string[];
  scenarios: Record<string, ScenarioOutcome>;
}

export interface Draft {
  saved: string;
  base_revision: number;
  edits:
    | { kind: "baseline"; baseline: Baseline; name: string; notes: string }
    | {
        kind: "scenario";
        original: string | null;
        scenario: Scenario;
      };
}
