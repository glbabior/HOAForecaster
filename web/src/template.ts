// Shapes for new, copied and reshaped scenarios. Blank scenarios come from the server, which
// holds the spec's defaults (src/hoa_app/template.py).

import type { ExpenseLine, Facts, Scenario } from "./types";

/** A new scenario started from another (spec 7.2) – a copy of all its inputs, but not its
 * name, its adoption or its timestamps. */
export const startFrom = (source: Scenario, name: string): Scenario => ({
  ...structuredClone(source),
  name,
  adoption: null,
});

/** The current adopted plan – the one adopted most recently (spec 5.2). */
export function currentAdoption(scenarios: Scenario[]): Scenario | undefined {
  return scenarios
    .filter((s) => s.adoption)
    .sort((a, b) => (b.adoption?.sequence ?? 0) - (a.adoption?.sequence ?? 0))[0];
}

/** The years a scenario runs over – none while it is not a usable horizon (a year half
 * typed). */
export function horizonOf(scenario: Scenario): number[] {
  const { start_year: start, end_year: end } = scenario.facts;
  if (!plausibleHorizon(start, end)) return [];
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

/** A horizon the editor can act on – 5 to 30 full years (spec 4 #2). While a year is still
 * being typed the horizon is implausible, and nothing is reshaped. */
export const plausibleHorizon = (start: number, end: number): boolean =>
  start >= 1900 && end - start + 1 >= 5 && end - start + 1 <= 30;

/** The scenario over a new horizon – every Fully Funded Balance and typed dues figure already
 * entered is kept (shortening must never discard data); new years get a zero Fully Funded
 * Balance, and typed dues the nearest earlier figure (or the first one, before the old
 * start). A horizon still being typed only changes the years. */
export function withHorizon(scenario: Scenario, start: number, end: number): Scenario {
  const facts = { ...scenario.facts, start_year: start, end_year: end };
  if (!plausibleHorizon(start, end)) return { ...scenario, facts };
  const ffb: Record<string, string> = { ...facts.ffb };
  for (let y = start; y <= end + 1; y += 1) ffb[String(y)] ??= "0";
  const reshaped = { ...scenario, facts: { ...facts, ffb } };
  if (scenario.dues.mode !== "explicit") return reshaped;
  const explicit: Record<string, string> = { ...scenario.dues.explicit };
  const known = Object.keys(explicit)
    .map(Number)
    .sort((a, b) => a - b);
  for (let y = start; y <= end; y += 1) {
    if (explicit[String(y)] !== undefined) continue;
    const earlier = known.filter((k) => k < y).at(-1) ?? known[0];
    explicit[String(y)] = earlier === undefined ? "0" : (explicit[String(earlier)] ?? "0");
  }
  return { ...reshaped, dues: { mode: "explicit", explicit } };
}

// ---------------------------------------------------------------- copying into other scenarios

/** Source notes with one note set – or removed, when the copied figure has none. */
function withNote(sources: Record<string, string>, key: string, note: string | undefined) {
  const rest = Object.fromEntries(Object.entries(sources).filter(([k]) => k !== key));
  return note ? { ...rest, [key]: note } : rest;
}

/** A scalar fact or assumption, as a key of Facts. */
export type FactKey = Exclude<keyof Facts, "expense_lines" | "ffb" | "sources">;

/** The target with this scenario's figure and source note for one fact – the horizon
 * reshaping the target's tables as typing it there would. */
export function copyFact(target: Scenario, from: Facts, key: FactKey): Scenario {
  const sources = withNote(target.facts.sources, key, from.sources[key]);
  const next = { ...target, facts: { ...target.facts, [key]: from[key], sources } };
  if (key === "start_year" || key === "end_year")
    return withHorizon(next, next.facts.start_year, next.facts.end_year);
  return next;
}

/** The target with this expense line – replacing its line of the same id, or added last. */
export function copyLine(target: Scenario, line: ExpenseLine): Scenario {
  const lines = target.facts.expense_lines;
  const copy = structuredClone(line);
  const expense_lines = lines.some((l) => l.id === line.id)
    ? lines.map((l) => (l.id === line.id ? copy : l))
    : [...lines, copy];
  return { ...target, facts: { ...target.facts, expense_lines } };
}

/** The target with this Fully Funded Balance – every year this scenario has replaces the
 * target's, years only the target has are kept – and its source note. */
export function copyFfb(target: Scenario, from: Facts): Scenario {
  const sources = withNote(target.facts.sources, "ffb", from.sources.ffb);
  return {
    ...target,
    facts: { ...target.facts, ffb: { ...target.facts.ffb, ...from.ffb }, sources },
  };
}

export function uniqueName(base: string, taken: string[]): string {
  let name = base;
  for (let n = 2; taken.includes(name); n += 1) name = `${base} (${n})`;
  return name;
}
