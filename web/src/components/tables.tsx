import { Fragment, useState, type ClipboardEvent, type ReactNode } from "react";

import { parsePasted } from "../csv";
import { num, parseDecimal } from "../decimal";
import { money } from "../format";
import { isOperating, type ExpenseLine, type Frequency } from "../types";
import { numberOf, useSort } from "./sort";
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
  // a useful life typed on a one-time cost becomes an every-few-years interval – never the
  // reverse, where the interval may only be the default
  if (frequency === "once") return { ...reserve, useful_life: line.useful_life ?? null };
  return {
    ...reserve,
    interval: line.interval ?? line.useful_life ?? 5,
    end_year: line.end_year ?? null,
  };
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
    hint: "Reserve expenses that come round again – an amount each time, in the expense base year's dollars and grown with reserve inflation – or, when already inflated, in its first year's dollars with each repeat grown from there. For an already-inflated amount, enter as the first year the year that amount is priced in: a past year is grown from then.",
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
  horizon,
}: {
  lines: ExpenseLine[];
  onChange: (lines: ExpenseLine[]) => void;
  defaultYear: number;
  /** the scenario's years and reserve inflation – to show each every-few-years line's repeats */
  horizon?: Horizon;
  /** offer each line for copying into other scenarios */
  onCopy?: (line: ExpenseLine) => void;
  /** ids other scenarios use – a new line never takes one, so copying it never replaces a
   * different line there */
  taken?: string[];
}) {
  const [notice, setNotice] = useState("");
  const [showRepeats, setShowRepeats] = useState(true);
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
              <span className="summary-title">{kind.title}</span>{" "}
              <span className="count">({shown.length})</span>
            </summary>
            <p className="hint">{kind.hint}</p>
            {kind.frequency === "every" && horizon && shown.length > 0 && (
              <label className="check">
                <input
                  type="checkbox"
                  checked={showRepeats}
                  onChange={(e) => setShowRepeats(e.target.checked)}
                />{" "}
                Show each one's repeats in {horizon.start}–{horizon.end}, in year order
              </label>
            )}
            {shown.length > 0 && (
              <KindTable
                repeats={kind.frequency === "every" && showRepeats ? horizon : undefined}
                frequency={kind.frequency}
                title={kind.title}
                lines={lines}
                shown={shown}
                rowKey={(i) => rows.ids[i] ?? String(i)}
                defaultYear={defaultYear}
                row={(i, number) => {
                  const line = lines[i] as ExpenseLine;
                  return (
                    <ExpenseRow
                      key={rows.ids[i]}
                      line={line}
                      index={i}
                      number={number}
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
                }}
              />
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

const ALREADY_INFLATED =
  "Already in that year's dollars – not grown from the base year. An every-few-years line's later repeats grow from it at reserve inflation.";

/** A scenario's years and reserve inflation, as the expense tables need them. */
export interface Horizon {
  start: number;
  end: number;
  inflation: string;
  baseYear: number;
}

/** The years after its first that an every-few-years line falls in the scenario, each with
 * its cost in that year's dollars – what the engine charges (spec 4.1). */
export function repeatsOf(line: ExpenseLine, h: Horizon): { year: number; amount: number }[] {
  if (line.frequency !== "every" || line.year === null || !line.interval || line.interval < 1)
    return [];
  const last = Math.min(line.end_year ?? h.end, h.end);
  const out = [];
  // from its first occurrence after the line's own row that falls in the scenario
  const skip = Math.max(1, Math.ceil((h.start - line.year) / line.interval));
  for (let y = line.year + skip * line.interval; y <= last; y += line.interval) {
    // already inflated – in its first year's dollars, each repeat grown from there
    const grown = (1 + num(h.inflation)) ** (y - (line.nominal ? line.year : h.baseYear));
    out.push({ year: y, amount: num(line.amount) * grown });
  }
  return out;
}

/** One kind's table, its headers sorting what is shown (never the saved order). */
function KindTable({
  frequency,
  title,
  lines,
  shown,
  rowKey,
  defaultYear,
  row,
  repeats,
}: {
  frequency: Frequency;
  title: string;
  /** given, each every-few-years line's later years show read-only, in year order among the
   * lines (beneath it while a header sorts the table) */
  repeats?: Horizon;
  lines: ExpenseLine[];
  /** the positions in `lines` of this kind's lines */
  shown: number[];
  /** a line's row key – the sorted order is held by it, so typing never moves a row */
  rowKey: (i: number) => string;
  /** a blank first year is the start year, so it sorts as one */
  defaultYear: number;
  /** a line's editable row – `number` is its place in an every-few-years table */
  row: (i: number, number?: number) => ReactNode;
}) {
  const at = (i: number) => lines[i] as ExpenseLine;
  const { order, header, sorted } = useSort(
    shown,
    {
      year: (i) => at(i).year ?? defaultYear,
      interval: (i) => at(i).interval,
      end: (i) => at(i).end_year,
      amount: (i) => numberOf(at(i).amount),
      description: (i) => at(i).description,
      life: (i) => at(i).useful_life,
      inflation: (i) => numberOf(at(i).inflation),
      nominal: (i) => (at(i).nominal ? 1 : 0),
    },
    rowKey,
  );
  const operating = isOperating(frequency);
  // Unsorted, the every-few-years table runs in year order, each repeat in its own year's place.
  // A line's place is the year it had when the table last changed shape (opened, a line added
  // or removed) or the focus last left a box, so a first year being typed never moves its row
  // from under the keyboard – it moves once the box is left.
  const keys = shown.map(rowKey).join("|");
  const yearsNow = () => new Map(shown.map((i) => [rowKey(i), at(i).year ?? defaultYear]));
  const [placed, setPlaced] = useState(() => ({ keys, years: yearsNow() }));
  if (placed.keys !== keys) setPlaced({ keys, years: yearsNow() });
  const byYear = frequency === "every" && !sorted;
  type Entry = { i: number; year: number; repeat?: { year: number; amount: number } };
  const entries: Entry[] = byYear
    ? (
        [
          ...shown.map((i) => ({
            i,
            year: placed.years.get(rowKey(i)) ?? at(i).year ?? defaultYear,
          })),
          ...(repeats
            ? shown.flatMap((i) =>
                repeatsOf(at(i), repeats).map((r) => ({ i, year: r.year, repeat: r })),
              )
            : []),
        ] as Entry[]
      ).sort((a, b) => a.year - b.year || Number(Boolean(a.repeat)) - Number(Boolean(b.repeat)))
    : order.flatMap((k) => {
        const i = shown[k] as number;
        const later = repeats ? repeatsOf(at(i), repeats) : [];
        return [{ i, year: 0 }, ...later.map((r) => ({ i, year: r.year, repeat: r }))];
      });
  // every-few-years lines are numbered in the order shown, so #1 is the first listed
  const numbers = new Map(
    frequency === "every" ? entries.filter((e) => !e.repeat).map((e, k) => [e.i, k + 1]) : [],
  );
  return (
    <div className="table-scroll">
      <table className={`edit-table expenses ${frequency}`}>
        <caption className="visually-hidden">{title}</caption>
        <thead>
          <tr>
            {frequency === "every" && (
              <th scope="col" title="Each line's number – its repeats name it">
                #
              </th>
            )}
            {header("year", frequency === "once" ? "Year" : "First year")}
            {frequency === "every" &&
              header("interval", "Every … years (its useful life)", {
                title: "How many years the component lasts between replacements",
              })}
            {frequency !== "once" && header("end", "Last year")}
            {header(
              "amount",
              frequency === "monthly"
                ? "Amount a month"
                : frequency === "yearly"
                  ? "Amount a year"
                  : "Amount",
            )}
            {header("description", "Description and source")}
            {frequency === "once" &&
              header("life", "Useful life", {
                title:
                  "How many years the component lasts between replacements – for a Fully Funded Balance worked out from the expenses; blank leaves it out of that",
              })}
            {operating
              ? header("inflation", "Own inflation")
              : header("nominal", "Already inflated?", { title: ALREADY_INFLATED })}
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody onBlur={byYear ? () => setPlaced({ keys, years: yearsNow() }) : undefined}>
          {entries.map(({ i, repeat }) => {
            if (!repeat) return <Fragment key={rowKey(i)}>{row(i, numbers.get(i))}</Fragment>;
            const line = at(i);
            return (
              <tr key={`${rowKey(i)}:${repeat.year}`} className="repeat">
                <td className="line-number" aria-hidden="true">
                  ↳
                </td>
                <td>
                  <span className="as-input">{repeat.year}</span>
                </td>
                <td />
                <td />
                <td title="In that year's dollars">
                  <span className="as-input">{money(String(repeat.amount))}</span>
                </td>
                <td>
                  <span className="as-input wraps">
                    Repeat of #{numbers.get(i)}
                    {line.description ? ` – ${line.description}` : ""}
                  </span>
                </td>
                <td />
                <td />
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
  number,
}: {
  line: ExpenseLine;
  index: number;
  /** its number in the every-few-years table, which its repeats name */
  number?: number;
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
      {number !== undefined && <td className="line-number">#{number}</td>}
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
      {line.frequency === "once" && (
        <td>
          <OptionalYearInput
            label={`Useful life of expense ${n} in years`}
            name={`Useful life of ${what}`}
            value={line.useful_life ?? null}
            placeholder="years"
            onChange={(useful_life) => update({ useful_life })}
          />
        </td>
      )}
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

/** The typed Fully Funded Balance – the reserve study's – for every year of the horizon and one more. */
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
  const { order, header } = useSort(
    years,
    { year: (y) => y, ffb: (y) => numberOf(values[String(y)]) },
    (y) => y,
  );
  const shownYears = order.map((k) => years[k] as number);

  function paste(e: ClipboardEvent<HTMLTableElement>) {
    const rows = parsePasted(e.clipboardData.getData("text/plain"));
    if (rows.length === 1 && rows[0]?.length === 1) return; // a single value – the cell takes it
    e.preventDefault();
    const next = { ...values };
    let used = 0;
    const pairs = rows.every((r) => r.length >= 2);
    // filled down from the box you are in, in the order the rows are shown
    const from = Math.max(0, shownYears.indexOf(focused));
    rows.forEach((cells, i) => {
      // "year<TAB>amount" rows, or a column of amounts filled down from the focused year
      const year = pairs ? Number(cells[0]) : shownYears[from + i];
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
              {header("year", "Start of year")}
              {header("ffb", "Fully Funded Balance")}
            </tr>
          </thead>
          <tbody>
            {shownYears.map((year) => (
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
