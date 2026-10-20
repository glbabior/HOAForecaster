// The JSON the local server sends and receives. Money and rates are exact decimal strings;
// rates and percentages are fractions ("0.03" is 3%).

export type Dec = string;

export interface ExpenseLine {
  year: number;
  amount: Dec;
  description: string;
  nominal: boolean;
  source: string;
}

export interface Baseline {
  start_year: number;
  end_year: number;
  starting_balance: Dec;
  expense_lines: ExpenseLine[];
  expense_inflation: Dec;
  expense_base_year: number;
  ffb: Record<string, Dec>;
  operating_start: Dec;
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

export interface Scenario {
  name: string;
  description: string;
  dues: DuesPath;
  assessments: Assessment[];
  rounding: "dollar" | "none";
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

export interface YearResult {
  year: number;
  dues: Dec;
  assessment_per_unit: Dec;
  total_dues: Dec;
  operating: Dec;
  contribution: Dec;
  assessment: Dec;
  total_from_owners: Dec;
  interest: Dec;
  expenses: Dec;
  expense_lines: { description: string; source: string; nominal: boolean; amount: Dec }[];
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
