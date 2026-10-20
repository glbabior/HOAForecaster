// US number formatting for display (spec 10.1). Rounding happens here and nowhere else.

import { num } from "./decimal";

const whole = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const cents = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const pct = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** $12,345 – or with cents when asked. Negative amounts show a leading minus. */
export function money(value: string | null | undefined, withCents = false): string {
  const n = num(value);
  if (Number.isNaN(n)) return "–";
  return (withCents ? cents : whole).format(n);
}

/** Dues and other per-unit figures – cents only when there are any. */
export function dues(value: string | null | undefined): string {
  const n = num(value);
  if (Number.isNaN(n)) return "–";
  return Number.isInteger(n) ? whole.format(n) : cents.format(n);
}

export function percent(value: string | null | undefined): string {
  const n = num(value);
  return Number.isNaN(n) ? "–" : pct.format(n);
}

export function date(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
}

/** "2027–2041" with an en-dash. */
export const span = (a: number, b: number): string => `${a}–${b}`;
