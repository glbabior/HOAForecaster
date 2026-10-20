// Shapes for new and reshaped scenarios. New projects come from the server, which holds
// the spec's defaults (src/hoa_app/template.py).

import type { Baseline, Scenario } from "./types";

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
  };
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
