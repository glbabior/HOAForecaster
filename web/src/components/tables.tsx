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

/** The first `<prefix>-N` identifier not yet taken – `line-N`, the form the server gives
 * new lines too. */
export function newLineId(taken: Iterable<string>, prefix = "line"): string {
  const used = new Set(taken);
  let n = 1;
  while (used.has(`${prefix}-${n}`)) n += 1;
  return `${prefix}-${n}`;
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
 * list replaced from outside gets fresh keys. */
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

/** The four kinds of expense, each in a table of its own with the columns it uses. */
const KINDS: {
  frequency: Frequency;
  title: string;
  hint: string;
  add: string;
}[] = [
  {
    frequency: "monthly",
    title: "Monthly costs",
    hint: "Operating costs paid from dues, an amount a month – each grows from its first year (blank – the start year) at its own inflation rate, or the operating rate when that is blank.",
    add: "Add a monthly cost",
  },
  {
    frequency: "yearly",
    title: "Yearly costs",
    hint: "Operating costs paid from dues, an amount a year – grown like monthly costs.",
    add: "Add a yearly cost",
  },
  {
    frequency: "every",
    title: "Every few years",
    hint: "Reserve expenses that come round again – an amount each time, in the expense base year's dollars and grown with reserve inflation unless already inflated.",
    add: "Add a cost every few years",
  },
  {
    frequency: "once",
    title: "One-time costs",
    hint: "Reserve expenses that fall once, in the expense base year's dollars and grown with reserve inflation unless already inflated. Paste rows from a spreadsheet – year, amount, description, yes/no, source – to add them here.",
    add: "Add a one-time cost",
  },
];

export function ExpenseTable({
  lines,
  onChange,
  defaultYear,
  onCopy,
  taken = [],
}: {
  lines: ExpenseLine[];
  onChange: (lines: ExpenseLine[]) => void;
  defaultYear: number;
  /** offer each line for copying into other scenarios */
  onCopy?: (line: ExpenseLine) => void;
  /** ids other scenarios use – a new line never takes one, so copying it never replaces a
   * different line there */
  taken?: string[];
}) {
  const [notice, setNotice] = useState("");
  const rows = useRowIds(lines.length);
  const ids = () => [...taken, ...lines.map((l) => l.id)];

  function paste(e: ClipboardEvent<HTMLElement>) {
    const text = e.clipboardData.getData("text/plain");
    if (!text.includes("\t")) return; // a single value – let the cell take it
    e.preventDefault();
    const { lines: pasted, skipped } = linesFromPaste(text, ids());
    rows.added(pasted.length);
    onChange([...lines, ...pasted]);
    setNotice(
      `Added ${pasted.length} one-time cost${pasted.length === 1 ? "" : "s"} from the clipboard` +
        (skipped
          ? ` – ${skipped} row${skipped === 1 ? "" : "s"} skipped (no year or amount).`
          : "."),
    );
  }

  /** One table's lines in year order, each kept in a place its kind already had in the list. */
  function sortByYear(frequency: Frequency) {
    const places = lines.flatMap((l, i) => (l.frequency === frequency ? [i] : []));
    const sorted = [...places].sort((a, b) => (lines[a]?.year ?? 0) - (lines[b]?.year ?? 0));
    const order = lines.map((_, i) => i);
    places.forEach((place, k) => {
      order[place] = sorted[k] ?? place;
    });
    rows.reordered(order);
    onChange(order.map((i) => lines[i] as ExpenseLine));
  }

  return (
    <div className="expense-tables">
      <p className="hint" role="status">
        {notice}
      </p>
      {KINDS.map((kind) => {
        const shown = lines.flatMap((line, i) => (line.frequency === kind.frequency ? [i] : []));
        return (
          // paste on the whole section, so it works before the first one-time cost exists
          <details
            key={kind.frequency}
            className="expense-kind"
            open
            onPaste={kind.frequency === "once" ? paste : undefined}
          >
            <summary>
              <h3>
                {kind.title} <span className="count">({shown.length})</span>
              </h3>
            </summary>
            <p className="hint">{kind.hint}</p>
            {shown.length > 0 && (
              <div className="table-scroll">
                <table className={`edit-table expenses ${kind.frequency}`}>
                  <caption className="visually-hidden">{kind.title}</caption>
                  <thead>
                    <tr>
                      <ExpenseHeadings frequency={kind.frequency} />
                      <th scope="col">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((i) => {
                      const line = lines[i] as ExpenseLine;
                      return (
                        <ExpenseRow
                          key={rows.ids[i]}
                          line={line}
                          index={i}
                          defaultYear={defaultYear}
                          onChange={(next) => onChange(lines.map((l, j) => (j === i ? next : l)))}
                          onMoved={(to) => {
                            const title = KINDS.find((k) => k.frequency === to)?.title ?? to;
                            setNotice(`Expense ${i + 1} moved to ${title}.`);
                          }}
                          onRemove={() => {
                            rows.removed(i);
                            onChange(lines.filter((_, j) => j !== i));
                          }}
                          onCopy={onCopy && (() => onCopy(line))}
                        />
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div className="row-actions">
              <button
                type="button"
                onClick={() => {
                  rows.added();
                  const blank = blankLine(newLineId(ids()), defaultYear);
                  onChange([...lines, withFrequency(blank, kind.frequency, defaultYear)]);
                }}
              >
                {kind.add}
              </button>
              {shown.length > 1 && (
                <button type="button" onClick={() => sortByYear(kind.frequency)}>
                  Sort by year
                </button>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

const ALREADY_INFLATED = "Already in that year's dollars – not grown by reserve inflation";

function ExpenseHeadings({ frequency }: { frequency: Frequency }) {
  const operating = isOperating(frequency);
  return (
    <>
      <th scope="col">{frequency === "once" ? "Year" : "First year"}</th>
      {frequency === "every" && <th scope="col">Every … years</th>}
      {frequency !== "once" && <th scope="col">Last year</th>}
      <th scope="col">
        {frequency === "monthly"
          ? "Amount a month"
          : frequency === "yearly"
            ? "Amount a year"
            : "Amount"}
      </th>
      <th scope="col">Description and source</th>
      {operating ? (
        <th scope="col">Own inflation</th>
      ) : (
        <th scope="col" title={ALREADY_INFLATED}>
          Already inflated?
        </th>
      )}
    </>
  );
}

/** One expense's inputs – the ones its kind uses, in its table's columns. */
function ExpenseRow({
  line,
  index,
  defaultYear,
  onChange,
  onRemove,
  onCopy,
  onMoved,
}: {
  line: ExpenseLine;
  index: number;
  defaultYear: number;
  onChange: (line: ExpenseLine) => void;
  onRemove: () => void;
  onCopy?: () => void;
  /** after the line has moved to another kind's table */
  onMoved: (to: Frequency) => void;
}) {
  const n = index + 1;
  const what = line.description ? `expense ${n} (${line.description})` : `expense ${n}`;
  const operating = isOperating(line.frequency);
  const update = (change: Partial<ExpenseLine>) => onChange({ ...line, ...change });
  return (
    <tr>
      <td>
        {operating ? (
          <OptionalYearInput
            label={`First year of expense ${n}`}
            name={`First year of ${what}`}
            value={line.year}
            placeholder="start"
            onChange={(year) => update({ year })}
          />
        ) : (
          <YearInput
            label={`Year of expense ${n}`}
            name={`Year of ${what}`}
            value={line.year ?? defaultYear}
            onChange={(year) => update({ year })}
          />
        )}
      </td>
      {line.frequency === "every" && (
        <td>
          <YearInput
            label={`Years between occurrences of expense ${n}`}
            name={`Years between occurrences of ${what}`}
            value={line.interval ?? 5}
            onChange={(interval) => update({ interval })}
          />
        </td>
      )}
      {line.frequency !== "once" && (
        <td>
          <OptionalYearInput
            label={`Last year of expense ${n}`}
            name={`Last year of ${what}`}
            value={line.end_year ?? null}
            placeholder="end"
            onChange={(end_year) => update({ end_year })}
          />
        </td>
      )}
      <td className="amount">
        <DecimalInput
          label={`Amount of expense ${n}${line.frequency === "monthly" ? " a month" : ""}`}
          name={`Amount of ${what}`}
          value={line.amount}
          onChange={(v) => v !== null && update({ amount: v })}
        />
      </td>
      <td className="described">
        <input
          aria-label={`Description of expense ${n}`}
          value={line.description}
          onChange={(e) => update({ description: e.target.value })}
        />
        {/* the source note under its description, so the description has the row's room */}
        <input
          aria-label={`Source of expense ${n}`}
          className="source"
          placeholder="Source – where the figure came from"
          title={line.source || undefined}
          value={line.source}
          onChange={(e) => update({ source: e.target.value })}
        />
      </td>
      {operating ? (
        <td>
          <DecimalInput
            label={`Own inflation rate of expense ${n}`}
            name={`Own inflation rate of ${what}`}
            percent
            allowBlank
            value={line.inflation ?? null}
            onChange={(inflation) => update({ inflation })}
          />
        </td>
      ) : (
        <td className="center">
          <input
            type="checkbox"
            aria-label={`Expense ${n} is already in that year's dollars`}
            title={ALREADY_INFLATED}
            checked={line.nominal ?? false}
            onChange={(e) => update({ nominal: e.target.checked })}
          />
        </td>
      )}
      <td className="row-buttons">
        <select
          aria-label={`How often expense ${n} falls`}
          title="How often – choosing another moves it to that table"
          value={line.frequency}
          onChange={(e) => {
            const to = e.target.value as Frequency;
            onChange(withFrequency(line, to, defaultYear));
            onMoved(to);
            // the row now sits in another table – keep the keyboard on its choice
            const label = `How often expense ${n} falls`;
            setTimeout(() =>
              document.querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`)?.focus(),
            );
          }}
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        {onCopy && (
          <button
            type="button"
            className="small"
            aria-label={`Copy expense ${n} to other scenarios`}
            onClick={onCopy}
          >
            Copy to…
          </button>
        )}
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
