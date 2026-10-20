// CSV of any table on screen (spec 7.6). Text that a spreadsheet would read as a formula
// is prefixed with an apostrophe, so opening the file can never run anything.

const FORMULA_START = /^[=+\-@\t\r]/;

export function csvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  // numbers are written as numbers; only text is guarded
  if (typeof value === "string" && FORMULA_START.test(text) && !/^-?\d+(\.\d+)?$/.test(text)) {
    text = `'${text}`;
  }
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(rows: (string | number | null | undefined)[][]): string {
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

/** Read a <table> as rows of cell text – what the user sees, header included. */
export function tableRows(table: HTMLTableElement): string[][] {
  return Array.from(table.rows).map((row) =>
    Array.from(row.cells).map((cell) => (cell.dataset.csv ?? cell.textContent ?? "").trim()),
  );
}

/** Split pasted spreadsheet cells (tab-separated, one row per line). */
export function parsePasted(text: string): string[][] {
  return text
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .filter((line) => line.trim() !== "")
    .map((line) => line.split("\t").map((cell) => cell.trim()));
}
