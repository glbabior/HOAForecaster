// Shapes for new, copied and reshaped scenarios. Blank scenarios come from the server, which
// holds the spec's defaults (src/hoa_app/template.py).

import { num } from "./decimal";
import type { DuesPath, ExpenseSet, Facts, Scenario } from "./types";

/** A new scenario started from another (spec 7.2) – a copy of its funding (dues path, special
 * assessments, rounding and description), not its name, its adoption or its timestamps. It uses
 * the project's facts and expenses, even when started from an adopted plan. */
export const startFrom = (source: Scenario, name: string): Scenario => ({
  ...structuredClone(source),
  name,
  facts: null,
  adoption: null,
});

/** A grown dues path carried on to a new start year (spec 5, as the server's rebase_dues) – the
 * figure it charged that year as its first-year value, a period over before the new start
 * dropped, one running into it starting with it, and years pinned up to it dropped. */
export function carriedOn(dues: DuesPath, charged: string, start: number): DuesPath {
  if (dues.mode !== "rate") return dues;
  return {
    ...dues,
    first_value: charged,
    increases: dues.increases
      .filter((i) => i.last_year === null || i.last_year > start)
      .map((i) =>
        i.first_year !== null && i.first_year <= start ? { ...i, first_year: null } : i,
      ),
    overrides: Object.fromEntries(
      Object.entries(dues.overrides).filter(([y]) => Number(y) > start),
    ),
  };
}

/** The current adopted plan – the one adopted most recently (spec 5.2). */
export function currentAdoption(scenarios: Scenario[]): Scenario | undefined {
  return scenarios
    .filter((s) => s.adoption)
    .sort((a, b) => (b.adoption?.sequence ?? 0) - (a.adoption?.sequence ?? 0))[0];
}

/** The scenarios with `name` put just `side` the scenario `past` – a move up or left puts it
 * before its neighbour, down or right after – so it moves past a run of scenarios a screen
 * does not show too, and a click repeated before the save comes back changes nothing more.
 * The project's order is the order every screen lists them in. */
export function moveScenario(
  scenarios: Scenario[],
  name: string,
  side: "before" | "after",
  past: string,
): Scenario[] {
  const moving = scenarios.find((s) => s.name === name);
  if (!moving || name === past || !scenarios.some((s) => s.name === past)) return scenarios;
  const rest = scenarios.filter((s) => s !== moving);
  const at = rest.findIndex((s) => s.name === past) + (side === "after" ? 1 : 0);
  return [...rest.slice(0, at), moving, ...rest.slice(at)];
}

/** The years a set of facts runs over – none while it is not a usable horizon (a year half
 * typed). */
export function horizonOf(facts: Facts): number[] {
  const { start_year: start, end_year: end } = facts;
  if (!plausibleHorizon(start, end)) return [];
  return Array.from({ length: end - start + 1 }, (_, i) => start + i);
}

/** A horizon the editor can act on – 5 to 30 full years (spec 4 #2). While a year is still
 * being typed the horizon is implausible, and nothing is reshaped. */
export const plausibleHorizon = (start: number, end: number): boolean =>
  start >= 1900 && end - start + 1 >= 5 && end - start + 1 <= 30;

/** The facts over a new horizon – every Fully Funded Balance figure already entered is kept
 * (shortening must never discard data), new years get a zero. A horizon still being typed only
 * changes the years. */
export function factsWithHorizon(facts: Facts, start: number, end: number): Facts {
  const moved = { ...facts, start_year: start, end_year: end };
  if (!plausibleHorizon(start, end)) return moved;
  const ffb: Record<string, string> = { ...moved.ffb };
  for (let y = start; y <= end + 1; y += 1) ffb[String(y)] ??= "0";
  return { ...moved, ffb };
}

/** A scenario's typed dues over a new horizon – every figure kept, new years the nearest
 * earlier figure (or the first one, before the old start). Grown dues need nothing. */
export function duesWithHorizon(scenario: Scenario, start: number, end: number): Scenario {
  if (scenario.dues.mode !== "explicit" || !plausibleHorizon(start, end)) return scenario;
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

/** A scalar fact or assumption, as a key of Facts. */
export type FactKey = Exclude<keyof Facts, "expense_lines" | "ffb" | "sources">;

// ---------------------------------------------------------------- expense sets (spec 4.3)

/** The source notes that belong with the expenses, and so travel with a set. */
const EXPENSE_SOURCES = ["ffb", "expense_base_year"];

/** The expenses of a set of facts saved as a set named `name` – an operating line's blank
 * first year (the start year) written as that year, so the set means the same figures whenever
 * it is loaded, and the reserve inflation it was saved with. */
export function expensesOf(facts: Facts, name: string): ExpenseSet {
  return {
    name,
    expense_lines: facts.expense_lines.map((l) =>
      (l.frequency === "monthly" || l.frequency === "yearly") && l.year === null
        ? { ...structuredClone(l), year: facts.start_year }
        : structuredClone(l),
    ),
    expense_base_year: facts.expense_base_year,
    ffb: { ...facts.ffb },
    ffb_from_lines: facts.ffb_from_lines,
    sources: Object.fromEntries(
      Object.entries(facts.sources).filter(([k]) => EXPENSE_SOURCES.includes(k)),
    ),
    saved_inflation: facts.expense_inflation,
  };
}

/** The facts with a set loaded in place of their expenses – every other fact as it was, and
 * the Fully Funded Balance years the set lacks kept. */
export function withExpenses(facts: Facts, set: ExpenseSet): Facts {
  const kept = Object.fromEntries(
    Object.entries(facts.sources).filter(([k]) => !EXPENSE_SOURCES.includes(k)),
  );
  return {
    ...facts,
    expense_lines: structuredClone(set.expense_lines),
    expense_base_year: set.expense_base_year,
    ffb: { ...facts.ffb, ...set.ffb },
    ffb_from_lines: set.ffb_from_lines,
    sources: { ...kept, ...set.sources },
  };
}

/** Whether two sets of facts have the same expenses – what a set holds, whatever its name. */
export function sameExpenses(a: Facts, b: Facts): boolean {
  // in any order, and amounts as numbers – sorting a table or typing 41000.00 for 41000 changes
  // nothing (spec 4.3, as the server's same_set)
  const value = (v: string | null | undefined) => (v === null || v === undefined ? null : num(v));
  const key = (f: Facts) => {
    const s = expensesOf(f, "");
    // each line as the fields its frequency uses, in one order, blanks as null – however the
    // line was made (the form, a paste, the server)
    const lines = [...s.expense_lines]
      .sort((x, y) => (x.id < y.id ? -1 : x.id > y.id ? 1 : 0))
      .map((l) => {
        const operating = l.frequency === "monthly" || l.frequency === "yearly";
        return [
          l.id,
          l.frequency,
          l.year ?? null,
          value(l.amount),
          l.description,
          l.source,
          l.frequency === "once" ? null : (l.end_year ?? null),
          l.frequency === "every" ? (l.interval ?? null) : null,
          operating ? value(l.inflation) : null,
          operating ? null : Boolean(l.nominal),
          l.frequency === "once" ? (l.useful_life ?? null) : null,
        ];
      });
    const sources = Object.fromEntries(
      Object.entries(s.sources).sort(([x], [y]) => (x < y ? -1 : 1)),
    );
    const ffb = Object.fromEntries(
      Object.entries(s.ffb)
        .sort(([x], [y]) => Number(x) - Number(y))
        .map(([y, v]) => [y, value(v)]),
    );
    return JSON.stringify([lines, s.expense_base_year, ffb, s.ffb_from_lines, sources]);
  };
  return key(a) === key(b);
}

export function uniqueName(base: string, taken: string[]): string {
  let name = base;
  for (let n = 2; taken.includes(name); n += 1) name = `${base} (${n})`;
  return name;
}
