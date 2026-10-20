// The shared dollar scale for stacked charts – the same grid as the Excel export's Charts
// sheet (src/hoa_workbook/charts.py): five round steps up to the top, matched to 0–100%
// funded in 20% steps, with whole steps below zero on both axes so their zero lines stay level.

const ROUND = [1, 2, 2.5, 5, 10];
export const PERCENT_STEP = 0.2;

export interface Grid {
  domain: [number, number];
  step: number;
  /** the percent axis's matching range and ticks */
  percentDomain: [number, number];
  dollarTicks: number[];
  percentTicks: number[];
}

export function sharedGrid(low: number, high: number): Grid {
  const need = Math.max(high, 1) / 5;
  // the power of ten of the whole-number part – the same rule as charts.py, so the screen and
  // the workbook always agree
  const magnitude = 10 ** (String(Math.trunc(need)).length - 1);
  const step = (ROUND.find((m) => m * magnitude >= need) ?? 10) * magnitude;
  const below = low >= 0 ? 0 : Math.ceil(-low / step);
  const steps = Array.from({ length: below + 6 }, (_, i) => i - below);
  return {
    domain: [below === 0 ? 0 : -below * step, 5 * step],
    step,
    percentDomain: [below === 0 ? 0 : -below * PERCENT_STEP, 1],
    dollarTicks: steps.map((i) => i * step),
    percentTicks: steps.map((i) => Math.round(i * PERCENT_STEP * 100) / 100),
  };
}

/** The range alone. */
export const sharedDomain = (low: number, high: number): [number, number] =>
  sharedGrid(low, high).domain;
