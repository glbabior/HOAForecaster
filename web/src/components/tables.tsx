import { useState, type ClipboardEvent } from "react";

import { parsePasted } from "../csv";
import { parseDecimal } from "../decimal";
import { isOperating, type ExpenseLine, type Frequency } from "../types";
import { DecimalInput, OptionalYearInput, YearInput } from "./ui";

export const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "yearly", label: "Yearly" },
  { value: "every", label: "Every few years" },
  { value: "once", label: "Once" },
];

/** The first `line-N` identifier not yet taken – the same form the server gives lines. */
export function newLineId(taken: Iterable<string>): string {
  const used = new Set(taken);
  let n = 1;
  while (used.has(`line-${n}`)) n += 1;
  return `line-${n}`;
}

const blankLine = (id: string, year: number): ExpenseLine => ({
  id,
  frequency: "once",
  year,
  amount: "0",
  description: "",
  nominal: false,
  source: "",
});

/** The line under another frequency – it keeps its amount, words and years, takes up the
 * fields the new frequency uses and drops the rest, so nothing stale is saved. */
export function withFrequency(line: ExpenseLine, frequency: Frequency, year: number): ExpenseLine {
  const { id, amount, description, source } = line;
  const common = { id, frequency, amount, description, source };
  if (isOperating(frequency))
    return {
      ...common,
      year: line.year,
      end_year: line.end_year ?? null,
      inflation: line.inflation ?? null,
    };
  const reserve = { ...common, year: line.year ?? year, nominal: line.nominal ?? false };
  if (frequency === "once") return reserve;
  return { ...reserve, interval: line.interval ?? 5, end_year: line.end_year ?? null };
}

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

/** Pasted cells as once expense lines – year, amount, description, then optionally "yes"/"no"
 * for already-in-that-year's-dollars and a source. Header rows and bad rows are reported.
 * Each line gets an identifier not in `taken`. */
export function linesFromPaste(
  text: string,
  taken: string[] = [],
): { lines: ExpenseLine[]; skipped: number } {
  const lines: ExpenseLine[] = [];
  const ids = [...taken];
  let skipped = 0;
  for (const cells of parsePasted(text)) {
    const [yearText = "", amountText = "", description = "", nominal = "", source = ""] = cells;
    const amount = parseDecimal(amountText);
    if (!/^\d{4}$/.test(yearText) || amount === null) {
      skipped += 1;
      continue;
    }
    const id = newLineId(ids);
    ids.push(id);
    lines.push({
      id,
      frequency: "once",
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
    const { lines: pasted, skipped } = linesFromPaste(
      text,
      lines.map((l) => l.id),
    );
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
    // lines without a year – monthly and yearly lines from the start – come first
    const order = lines
      .map((_, i) => i)
      .sort((a, b) => (lines[a]?.year ?? 0) - (lines[b]?.year ?? 0));
    rows.reordered(order);
    onChange(order.map((i) => lines[i] as ExpenseLine));
  }

  return (
    <div>
      <p className="hint">
        Monthly and yearly expenses are operating costs, paid from dues – each grows from its first
        year (blank – the start year) at its own inflation rate, or the operating rate when that is
        blank. Once and every-few-years expenses come out of reserves; their amounts are in the
        expense base year's dollars and grow with reserve inflation, unless marked as already in
        that year's dollars. Paste rows from a spreadsheet – year, amount, description, yes/no,
        source – to add them as one-off expenses.
      </p>
      <div className="table-scroll">
        <table className="edit-table expenses" onPaste={paste}>
          <caption className="visually-hidden">Expenses</caption>
          <thead>
            <tr>
              <th scope="col">How often</th>
              <th scope="col">Year, or first year</th>
              <th scope="col">Last year</th>
              <th scope="col">Every … years</th>
              <th scope="col">Amount</th>
              <th scope="col">Description</th>
              <th scope="col">Own inflation</th>
              <th scope="col">Already in that year's dollars</th>
              <th scope="col">Source</th>
              <th scope="col">
                <span className="visually-hidden">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, i) => (
              <ExpenseRow
                key={rows.ids[i]}
                line={line}
                index={i}
                defaultYear={defaultYear}
                onChange={(next) => onChange(lines.map((l, j) => (j === i ? next : l)))}
                onUpdate={(change) => update(i, change)}
                onRemove={() => {
                  rows.removed(i);
                  onChange(lines.filter((_, j) => j !== i));
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
      <div className="row-actions">
        <button
          type="button"
          onClick={() => {
            rows.added();
            onChange([...lines, blankLine(newLineId(lines.map((l) => l.id)), defaultYear)]);
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

/** One expense's inputs – only the ones its frequency uses are shown. */
function ExpenseRow({
  line,
  index,
  defaultYear,
  onChange,
  onUpdate,
  onRemove,
}: {
  line: ExpenseLine;
  index: number;
  defaultYear: number;
  onChange: (line: ExpenseLine) => void;
  onUpdate: (change: Partial<ExpenseLine>) => void;
  onRemove: () => void;
}) {
  const n = index + 1;
  const what = line.description ? `expense ${n} (${line.description})` : `expense ${n}`;
  const operating = isOperating(line.frequency);
  return (
    <tr>
      <td>
        <select
          aria-label={`How often expense ${n} falls`}
          value={line.frequency}
          onChange={(e) => onChange(withFrequency(line, e.target.value as Frequency, defaultYear))}
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </td>
      <td>
        {operating ? (
          <OptionalYearInput
            label={`First year of expense ${n}`}
            name={`First year of ${what}`}
            value={line.year}
            placeholder="start"
            onChange={(year) => onUpdate({ year })}
          />
        ) : (
          <YearInput
            label={`Year of expense ${n}`}
            name={`Year of ${what}`}
            value={line.year ?? defaultYear}
            onChange={(year) => onUpdate({ year })}
          />
        )}
      </td>
      <td>
        {line.frequency !== "once" && (
          <OptionalYearInput
            label={`Last year of expense ${n}`}
            name={`Last year of ${what}`}
            value={line.end_year ?? null}
            placeholder="end"
            onChange={(end_year) => onUpdate({ end_year })}
          />
        )}
      </td>
      <td>
        {line.frequency === "every" && (
          <YearInput
            label={`Years between occurrences of expense ${n}`}
            name={`Years between occurrences of ${what}`}
            value={line.interval ?? 5}
            onChange={(interval) => onUpdate({ interval })}
          />
        )}
      </td>
      <td>
        <DecimalInput
          label={`Amount of expense ${n}${line.frequency === "monthly" ? " a month" : ""}`}
          name={`Amount of ${what}`}
          value={line.amount}
          onChange={(v) => v !== null && onUpdate({ amount: v })}
        />
        {line.frequency === "monthly" && <small className="hint"> a month</small>}
      </td>
      <td>
        <input
          aria-label={`Description of expense ${n}`}
          value={line.description}
          onChange={(e) => onUpdate({ description: e.target.value })}
        />
      </td>
      <td>
        {operating && (
          <DecimalInput
            label={`Own inflation rate of expense ${n}`}
            name={`Own inflation rate of ${what}`}
            percent
            allowBlank
            value={line.inflation ?? null}
            onChange={(inflation) => onUpdate({ inflation })}
          />
        )}
      </td>
      <td className="center">
        {!operating && (
          <input
            type="checkbox"
            aria-label={`Expense ${n} is already in that year's dollars`}
            checked={line.nominal ?? false}
            onChange={(e) => onUpdate({ nominal: e.target.checked })}
          />
        )}
      </td>
      <td>
        <input
          aria-label={`Source of expense ${n}`}
          value={line.source}
          onChange={(e) => onUpdate({ source: e.target.value })}
        />
      </td>
      <td>
        <button
          type="button"
          className="small"
          aria-label={`Remove expense ${n}`}
          onClick={onRemove}
        >
          Remove
        </button>
      </td>
    </tr>
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
