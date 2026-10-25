// Shapes for new and reshaped scenarios. New projects come from the server, which holds
// the spec's defaults (src/hoa_app/template.py).

import type { Baseline, Changes, ExpenseLine, Scenario } from "./types";

export const noChanges = (): Changes => ({ values: {}, sources: {}, expense_lines: {}, ffb: {} });

export function blankScenario(name: string, baseline: Baseline): Scenario {
  return {
    name,
    description: "",
    dues: {
      mode: "rate",
      first_value: baseline.current_dues,
      annual_increase: "0.03",
      overrides: {},
    },
    assessments: [],
    rounding: "dollar",
    changes: noChanges(),
  };
}

/** The baseline as a scenario sees it (spec 5.1) – for showing it; the server works out the
 * figures. Mirrors `apply_changes` in src/hoa_engine/model.py. */
export function applyChanges(baseline: Baseline, changes: Changes): Baseline {
  const known = new Set(baseline.expense_lines.map((l) => l.id));
  const own = (id: string): ExpenseLine | null => {
    const line = changes.expense_lines[id];
    return line ? { id, ...line } : null;
  };
  const lines = baseline.expense_lines.flatMap((l) =>
    l.id in changes.expense_lines ? (own(l.id) ?? []) : [l],
  );
  for (const id of Object.keys(changes.expense_lines)) {
    const line = own(id);
    if (!known.has(id) && line) lines.push(line);
  }
  return {
    ...baseline,
    ...(changes.values as Partial<Baseline>),
    expense_lines: lines,
    ffb: { ...baseline.ffb, ...changes.ffb },
    sources: { ...baseline.sources, ...changes.sources },
  };
}

/** Every input a scenario runs on – an adopted plan's frozen baseline, never today's. Mirrors
 * `baseline_for` in src/hoa_engine/model.py. */
export const baselineFor = (baseline: Baseline, scenario: Scenario): Baseline =>
  applyChanges(scenario.adoption?.baseline ?? baseline, scenario.changes);

/** The current adopted plan – the one adopted most recently (spec 5.2). */
export function currentAdoption(scenarios: Scenario[]): Scenario | undefined {
  return scenarios
    .filter((s) => s.adoption)
    .sort((a, b) => (b.adoption?.sequence ?? 0) - (a.adoption?.sequence ?? 0))[0];
}

/** The years a scenario runs over – its own horizon, or the baseline's; none while it is not a
 * usable horizon (a year half typed). */
export function horizonOf(baseline: Baseline, scenario: Scenario): number[] {
  const { start_year: start, end_year: end } = baselineFor(baseline, scenario);
  if (!plausibleHorizon(start, end)) return [];
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

/** A horizon the editor can act on – 5 to 30 full years (spec 4 #2). While a year is still
 * being typed the horizon is implausible, and nothing is reshaped. */
export const plausibleHorizon = (start: number, end: number): boolean =>
  start >= 1900 && end - start + 1 >= 5 && end - start + 1 <= 30;

/** The horizon changed – every Fully Funded Balance already entered is kept (shortening
 * must never discard data), and new years get zero. */
export function reshapeHorizon(baseline: Baseline, start: number, end: number): Baseline {
  const ffb: Record<string, string> = { ...baseline.ffb };
  for (let y = start; y <= end + 1; y += 1) ffb[String(y)] ??= "0";
  return { ...baseline, start_year: start, end_year: end, ffb };
}

/** Typed dues keep every year they had; new years take the nearest earlier figure (or the
 * first one, before the old start). Grown dues need nothing. */
export function reshapeScenario(scenario: Scenario, start: number, end: number): Scenario {
  if (scenario.dues.mode !== "explicit") return scenario;
  const explicit: Record<string, string> = { ...scenario.dues.explicit };
  const known = Object.keys(explicit)
    .map(Number)
    .sort((a, b) => a - b);
  for (let y = start; y <= end; y += 1) {
    if (explicit[String(y)] !== undefined) continue;
    const earlier = known.filter((k) => k < y).at(-1) ?? known[0];
    explicit[String(y)] = earlier === undefined ? "0" : (explicit[String(earlier)] ?? "0");
  }
  return { ...scenario, dues: { mode: "explicit", explicit } };
}
