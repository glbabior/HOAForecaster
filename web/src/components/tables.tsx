import { useState, type ClipboardEvent } from "react";

import { parsePasted } from "../csv";
import { parseDecimal } from "../decimal";
import type { ExpenseLine } from "../types";
import { DecimalInput, YearInput } from "./ui";

const blankLine = (year: number): ExpenseLine => ({
  year,
  amount: "0",
  description: "",
  nominal: false,
  source: "",
});

let counter = 0;
const newId = (): string => `row-${(counter += 1)}`;

/** Stable keys for the rows of an editable list, so removing or sorting rows never moves
 * half-typed text or focus onto a different row. Kept in step with the list's length; a
 * list replaced from outside (a restored draft) gets fresh keys. */
export function useRowIds(length: number) {
  const [ids, setIds] = useState<string[]>(() => Array.from({ length }, newId));
  if (ids.length !== length) setIds(Array.from({ length }, newId));
  return {
    ids,
    added: (count = 1) =>
      setIds((current) => [...current, ...Array.from({ length: count }, newId)]),
    removed: (i: number) => setIds((current) => current.filter((_, j) => j !== i)),
    reordered: (order: number[]) => setIds((current) => order.map((i) => current[i] ?? newId())),
  };
}

/** Pasted cells as expense lines – year, amount, description, then optionally "yes"/"no"
 * for already-in-that-year's-dollars and a source. Header rows and bad rows are reported. */
export function linesFromPaste(text: string): { lines: ExpenseLine[]; skipped: number } {
  const lines: ExpenseLine[] = [];
  let skipped = 0;
  for (const cells of parsePasted(text)) {
    const [yearText = "", amountText = "", description = "", nominal = "", source = ""] = cells;
    const amount = parseDecimal(amountText);
    if (!/^\d{4}$/.test(yearText) || amount === null) {
      skipped += 1;
      continue;
    }
    lines.push({
      year: Number(yearText),
      amount,
      description,
      nominal: /^(yes|y|true|1|nominal)$/i.test(nominal),
      source,
    });
  }
  return { lines, skipped };
}

export function ExpenseTable({
  lines,
  onChange,
  defaultYear,
}: {
  lines: ExpenseLine[];
  onChange: (lines: ExpenseLine[]) => void;
  defaultYear: number;
}) {
  const [notice, setNotice] = useState("");
  const rows = useRowIds(lines.length);

  function update(i: number, change: Partial<ExpenseLine>) {
    onChange(lines.map((line, j) => (j === i ? { ...line, ...change } : line)));
  }

  function paste(e: ClipboardEvent<HTMLTableElement>) {
    const text = e.clipboardData.getData("text/plain");
    if (!text.includes("\t")) return; // a single value – let the cell take it
    e.preventDefault();
    const { lines: pasted, skipped } = linesFromPaste(text);
    rows.added(pasted.length);
    onChange([...lines, ...pasted]);
    setNotice(
      `Added ${pasted.length} expense${pasted.length === 1 ? "" : "s"} from the clipboard` +
        (skipped
          ? ` – ${skipped} row${skipped === 1 ? "" : "s"} skipped (no year or amount).`
          : "."),
    );
  }

  function sortByYear() {
    const order = lines
      .map((_, i) => i)
      .sort((a, b) => (lines[a]?.year ?? 0) - (lines[b]?.year ?? 0));
    rows.reordered(order);
    onChange(order.map((i) => lines[i] as ExpenseLine));
  }

  return (
    <div>
      <p className="hint">
        Amounts are in the expense base year's dollars and grow with inflation, unless marked as
        already in that year's dollars. Paste rows from a spreadsheet – year, amount, description,
        yes/no, source – into the table to add them.
      </p>
      <div className="table-scroll">
        <table className="edit-table" onPaste={paste}>
          <caption className="visually-hidden">Reserve expenses</caption>
          <thead>
            <tr>
              <th scope="col">Year</th>
              <th scope="col">Amount</th>
              <th scope="col">Description</th>
              <th scope="col">Already in that year's dollars</th>
              <th scope="col">Source</th>
              <th scope="col">
                <span className="visually-hidden">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, i) => {
              const what = line.description
                ? `expense ${i + 1} (${line.description})`
                : `expense ${i + 1}`;
              return (
                <tr key={rows.ids[i]}>
                  <td>
                    <YearInput
                      label={`Year of expense ${i + 1}`}
                      name={`Year of ${what}`}
                      value={line.year}
                      onChange={(year) => update(i, { year })}
                    />
                  </td>
                  <td>
                    <DecimalInput
                      label={`Amount of expense ${i + 1}`}
                      name={`Amount of ${what}`}
                      value={line.amount}
                      onChange={(v) => v !== null && update(i, { amount: v })}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`Description of expense ${i + 1}`}
                      value={line.description}
                      onChange={(e) => update(i, { description: e.target.value })}
                    />
                  </td>
                  <td className="center">
                    <input
                      type="checkbox"
                      aria-label={`Expense ${i + 1} is already in that year's dollars`}
                      checked={line.nominal}
                      onChange={(e) => update(i, { nominal: e.target.checked })}
                    />
                  </td>
                  <td>
                    <input
                      aria-label={`Source of expense ${i + 1}`}
                      value={line.source}
                      onChange={(e) => update(i, { source: e.target.value })}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="small"
                      aria-label={`Remove expense ${i + 1}`}
                      onClick={() => {
                        rows.removed(i);
                        onChange(lines.filter((_, j) => j !== i));
                      }}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="row-actions">
        <button
          type="button"
          onClick={() => {
            rows.added();
            onChange([...lines, blankLine(defaultYear)]);
          }}
        >
          Add expense
        </button>
        <button type="button" onClick={sortByYear}>
          Sort by year
        </button>
        <span role="status">{notice}</span>
      </div>
    </div>
  );
}

/** The reserve study's Fully Funded Balance for every year of the horizon and one more. */
export function FfbTable({
  years,
  values,
  onChange,
}: {
  years: number[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}) {
  const [notice, setNotice] = useState("");
  const [focused, setFocused] = useState(years[0] ?? 0);

  function paste(e: ClipboardEvent<HTMLTableElement>) {
    const rows = parsePasted(e.clipboardData.getData("text/plain"));
    if (rows.length === 1 && rows[0]?.length === 1) return; // a single value – the cell takes it
    e.preventDefault();
    const next = { ...values };
    let used = 0;
    const pairs = rows.every((r) => r.length >= 2);
    const from = Math.max(0, years.indexOf(focused));
    rows.forEach((cells, i) => {
      // "year<TAB>amount" rows, or a column of amounts filled down from the focused year
      const year = pairs ? Number(cells[0]) : years[from + i];
      const amount = parseDecimal((pairs ? cells[1] : cells[0]) ?? "");
      if (year !== undefined && years.includes(year) && amount !== null) {
        next[String(year)] = amount;
        used += 1;
      }
    });
    onChange(next);
    setNotice(`Filled ${used} year${used === 1 ? "" : "s"} from the clipboard.`);
  }

  return (
    <div>
      <p className="hint">
        From the reserve study – the balance it calls fully funded at the start of each year,
        through the year after the last. Paste a column of amounts (filled down from the box you are
        in), or year and amount pairs.
      </p>
      <div className="table-scroll">
        <table className="edit-table ffb" onPaste={paste}>
          <caption className="visually-hidden">Fully Funded Balance by year</caption>
          <thead>
            <tr>
              <th scope="col">Start of year</th>
              <th scope="col">Fully Funded Balance</th>
            </tr>
          </thead>
          <tbody>
            {years.map((year) => (
              <tr key={year} onFocus={() => setFocused(year)}>
                <th scope="row">{year}</th>
                <td>
                  <DecimalInput
                    label={`Fully Funded Balance at the start of ${year}`}
                    name={`Fully Funded Balance for ${year}`}
                    value={values[String(year)] ?? null}
                    onChange={(v) => v !== null && onChange({ ...values, [String(year)]: v })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span role="status">{notice}</span>
    </div>
  );
}
