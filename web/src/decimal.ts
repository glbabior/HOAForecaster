// Exact decimal strings. The server holds money as decimals, never binary floats; the
// screens edit those strings directly and convert to numbers only for display and charts.

const DECIMAL = /^-?\d+(\.\d+)?$/;

/** A user's typed number tidied into a decimal string, or null if it is not one.
 * Thousands separators, a leading $ and surrounding spaces are allowed. */
export function parseDecimal(text: string): string | null {
  const cleaned = text.trim().replace(/^\$/, "").replace(/,/g, "");
  if (!DECIMAL.test(cleaned)) return null;
  return normalise(cleaned);
}

function normalise(value: string): string {
  const negative = value.startsWith("-");
  let [whole = "0", frac = ""] = value.replace(/^-/, "").split(".");
  whole = whole.replace(/^0+(?=\d)/, "");
  frac = frac.replace(/0+$/, "");
  const out = frac ? `${whole}.${frac}` : whole;
  return negative && out !== "0" ? `-${out}` : out;
}

/** Move the decimal point – shift(“3.5”, -2) is “0.035”. Exact, no floating point. */
export function shift(value: string, places: number): string {
  // Python writes very small decimals with an exponent ("1E-7") – fold it into the shift
  const exponent = /^(-?[\d.]+)[eE]([+-]?\d+)$/.exec(value);
  if (exponent) return shift(exponent[1] ?? "0", places + Number(exponent[2]));
  const negative = value.startsWith("-");
  const [whole = "0", frac = ""] = value.replace(/^-/, "").split(".");
  let digits = whole + frac;
  let point = whole.length + places;
  if (point <= 0) {
    digits = "0".repeat(1 - point) + digits;
    point = 1;
  }
  if (point > digits.length) digits = digits + "0".repeat(point - digits.length);
  const out = normalise(`${digits.slice(0, point)}.${digits.slice(point)}`);
  return negative && out !== "0" ? `-${out}` : out;
}

/** A fraction shown as a percentage – "0.035" → "3.5". */
export const toPercent = (fraction: string): string => shift(fraction, 2);

/** A typed percentage stored as a fraction – "3.5" → "0.035", or null if not a number. */
export function fromPercent(text: string): string | null {
  const parsed = parseDecimal(text.replace(/%$/, ""));
  return parsed === null ? null : shift(parsed, -2);
}

/** For display and charts only. */
export const num = (value: string | null | undefined): number =>
  value === null || value === undefined ? NaN : Number(value);

/** A decimal string rounded half-up to whole cents, exactly – for copying a computed figure
 * into a typed one. */
export function roundCents(raw: string): string {
  const value = shift(raw, 0); // plain digits, whatever form the server wrote
  const negative = value.startsWith("-");
  const [whole = "0", frac = ""] = value.replace(/^-/, "").split(".");
  const cents = BigInt(whole + (frac + "00").slice(0, 2)) + (Number(frac[2] ?? "0") >= 5 ? 1n : 0n);
  const digits = cents.toString().padStart(3, "0");
  const out = normalise(`${digits.slice(0, -2)}.${digits.slice(-2)}`);
  return negative && out !== "0" ? `-${out}` : out;
}
