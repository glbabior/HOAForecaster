// A scenario's own changes to the baseline (spec 5.1) – every value follows the baseline until
// the scenario sets its own, and each one can be put back.

import { dues, money, percent } from "../format";
import { applyChanges, plausibleHorizon } from "../template";
import {
  isOperating,
  type Baseline,
  type ChangeableKey,
  type Changes,
  type Dec,
  type ExpenseLine,
} from "../types";
import { FREQUENCIES, ExpenseRow, newLineId } from "./tables";
import { DecimalInput, YearInput } from "./ui";

type Kind = "money" | "dues" | "percent" | "year" | "count";

const ASSUMPTIONS: { key: ChangeableKey; label: string; kind: Kind; limit?: boolean }[] = [
  { key: "start_year", label: "Start year", kind: "year" },
  { key: "end_year", label: "End year", kind: "year" },
  { key: "starting_balance", label: "Starting reserve balance", kind: "money" },
  { key: "units", label: "Number of units", kind: "count" },
  { key: "current_dues", label: "Current dues per unit per month", kind: "dues" },
  { key: "operating_inflation", label: "Operating cost inflation", kind: "percent" },
  { key: "expense_inflation", label: "Reserve expense inflation", kind: "percent" },
  { key: "expense_base_year", label: "Expense base year", kind: "year" },
  { key: "interest_rate", label: "Interest earned on reserves", kind: "percent" },
  { key: "cushion", label: "Minimum working cushion", kind: "money" },
  { key: "target", label: "Percent-funded target", kind: "percent" },
  {
    key: "max_dues_increase",
    label: "Largest dues increase without an owner vote",
    kind: "percent",
    limit: true,
  },
  {
    key: "max_assessment_share",
    label: "Largest assessment without a vote, share of the budget",
    kind: "percent",
    limit: true,
  },
];

function shown(kind: Kind, value: Dec | number | null | undefined): string {
  if (value === null || value === undefined) return "no limit";
  if (kind === "year" || kind === "count") return String(value);
  if (kind === "percent") return percent(String(value));
  return kind === "dues" ? dues(String(value)) : money(String(value));
}

const without = <T,>(record: Record<string, T>, key: string): Record<string, T> =>
  Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));

/** How many of its own values the editor shows the scenario setting – for the section's
 * heading. A leave-out of a line the baseline no longer has, or a Fully Funded Balance outside
 * the scenario's years, is kept but not shown, so not counted. */
export function changeCount(baseline: Baseline, changes: Changes): number {
  const known = new Set(baseline.expense_lines.map((l) => l.id));
  const own = applyChanges(baseline, changes);
  const lines = Object.entries(changes.expense_lines).filter(([id, l]) => l || known.has(id));
  const ffb = Object.keys(changes.ffb).filter(
    (y) => Number(y) >= own.start_year && Number(y) <= own.end_year + 1,
  );
  return (
    Object.keys(changes.values).length +
    Object.keys(changes.sources).length +
    lines.length +
    ffb.length
  );
}

/** A source note of the scenario's own – blank follows the baseline's, shown as a hint. */
function SourceNote({
  label,
  baseline,
  changes,
  noteKey,
  onChange,
}: {
  label: string;
  baseline: string | undefined;
  changes: Changes;
  noteKey: string;
  onChange: (changes: Changes) => void;
}) {
  return (
    <input
      aria-label={`Source – this scenario's ${label.toLowerCase()}`}
      className="source"
      placeholder={baseline || "no note"}
      value={changes.sources[noteKey] ?? ""}
      onChange={(e) =>
        onChange({
          ...changes,
          sources: e.target.value
            ? { ...changes.sources, [noteKey]: e.target.value }
            : without(changes.sources, noteKey),
        })
      }
    />
  );
}

export function BaselineChanges({
  baseline,
  changes,
  onChange,
}: {
  baseline: Baseline;
  changes: Changes;
  onChange: (changes: Changes) => void;
}) {
  const own = applyChanges(baseline, changes);
  const set = (part: Partial<Changes>) => onChange({ ...changes, ...part });

  function setValue(key: ChangeableKey, value: Dec | number | null) {
    set({ values: { ...changes.values, [key]: value } });
  }

  function follow(key: ChangeableKey) {
    set({ values: without(changes.values, key), sources: without(changes.sources, key) });
  }

  return (
    <>
      <p className="hint">
        Everything here follows the baseline until this scenario sets its own value – a later edit
        to the baseline then reaches this scenario everywhere except those values.
      </p>
      <table className="edit-table changes">
        <caption>Assumptions</caption>
        <thead>
          <tr>
            <th scope="col">Assumption</th>
            <th scope="col">Baseline</th>
            <th scope="col">This scenario</th>
            <th scope="col">Source</th>
          </tr>
        </thead>
        <tbody>
          {ASSUMPTIONS.map(({ key, label, kind, limit }) => {
            const isOwn = key in changes.values;
            const value = changes.values[key];
            return (
              <tr key={key} className={isOwn ? "own" : undefined}>
                <th scope="row">{label}</th>
                <td className="num">{shown(kind, baseline[key])}</td>
                <td>
                  {!isOwn ? (
                    <button
                      type="button"
                      className="small"
                      aria-label={`Set this scenario's own ${label.toLowerCase()}`}
                      onClick={() => setValue(key, baseline[key])}
                    >
                      Set its own
                    </button>
                  ) : (
                    <span className="own-value">
                      {kind === "year" || kind === "count" ? (
                        <YearInput
                          label={`This scenario's ${label.toLowerCase()}`}
                          name={`This scenario's ${label.toLowerCase()}`}
                          value={Number(value)}
                          onChange={(n) => setValue(key, n)}
                        />
                      ) : (
                        <DecimalInput
                          label={`This scenario's ${label.toLowerCase()}`}
                          name={`This scenario's ${label.toLowerCase()}`}
                          percent={kind === "percent"}
                          allowBlank={limit}
                          value={value === undefined ? null : (value as Dec | null)}
                          onChange={(v) => (v !== null || limit) && setValue(key, v)}
                        />
                      )}
                      <button
                        type="button"
                        className="small"
                        aria-label={`Use the baseline's ${label.toLowerCase()}`}
                        onClick={() => follow(key)}
                      >
                        Use baseline
                      </button>
                      {limit && <small className="hint"> blank – no limit</small>}
                    </span>
                  )}
                </td>
                <td>
                  <SourceNote
                    label={label}
                    baseline={baseline.sources[key]}
                    changes={changes}
                    noteKey={key}
                    onChange={onChange}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <LineChanges baseline={baseline} own={own} changes={changes} onChange={onChange} />
      <FfbChanges baseline={baseline} own={own} changes={changes} onChange={onChange} />
    </>
  );
}

const describe = (line: ExpenseLine): string => {
  const frequency = FREQUENCIES.find((f) => f.value === line.frequency)?.label ?? "";
  const when =
    line.frequency === "once"
      ? `${line.year}`
      : line.frequency === "every"
        ? `every ${line.interval} years from ${line.year}`
        : `from ${line.year ?? "the start"}`;
  const amount =
    line.frequency === "monthly" ? `${money(line.amount)} a month` : money(line.amount);
  return `${frequency} · ${when}${line.end_year ? ` to ${line.end_year}` : ""} · ${amount}`;
};

function LineChanges({
  baseline,
  own,
  changes,
  onChange,
}: {
  baseline: Baseline;
  own: Baseline;
  changes: Changes;
  onChange: (changes: Changes) => void;
}) {
  const lines = changes.expense_lines;
  const setLine = (id: string, line: ExpenseLine | null) => {
    // stored by id, so the line itself carries none
    const value =
      line === null
        ? null
        : (Object.fromEntries(Object.entries(line).filter(([k]) => k !== "id")) as Omit<
            ExpenseLine,
            "id"
          >);
    onChange({ ...changes, expense_lines: { ...lines, [id]: value } });
  };
  const restore = (id: string) => onChange({ ...changes, expense_lines: without(lines, id) });
  const known = new Set(baseline.expense_lines.map((l) => l.id));
  const ownLines = own.expense_lines.filter((l) => !known.has(l.id));

  return (
    <div className="table-scroll">
      <table className="edit-table expenses">
        <caption>
          Expenses – change a baseline line, leave it out, or add one of this scenario's own
        </caption>
        <thead>
          <tr>
            <th scope="col">Line</th>
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
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {baseline.expense_lines.map((line, i) => {
            const n = i + 1;
            if (!(line.id in lines))
              return (
                <tr key={line.id}>
                  <td>Baseline</td>
                  <td colSpan={9}>
                    {line.description || "(no description)"} – {describe(line)}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="small"
                      aria-label={`Change expense ${n} for this scenario`}
                      onClick={() => setLine(line.id, line)}
                    >
                      Change
                    </button>
                    <button
                      type="button"
                      className="small"
                      aria-label={`Leave expense ${n} out of this scenario`}
                      onClick={() => setLine(line.id, null)}
                    >
                      Leave out
                    </button>
                  </td>
                </tr>
              );
            const changed = lines[line.id];
            if (!changed)
              return (
                <tr key={line.id} className="left-out">
                  <td>Left out</td>
                  <td colSpan={9}>
                    <s>{line.description || "(no description)"}</s> – {describe(line)}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="small"
                      aria-label={`Put expense ${n} back`}
                      onClick={() => restore(line.id)}
                    >
                      Put back
                    </button>
                  </td>
                </tr>
              );
            const copy = { id: line.id, ...changed };
            return (
              <ExpenseRow
                key={line.id}
                line={copy}
                index={i}
                defaultYear={own.start_year}
                marker="Changed"
                onChange={(next) => setLine(line.id, next)}
                onUpdate={(part) => setLine(line.id, { ...copy, ...part })}
                actions={
                  <button
                    type="button"
                    className="small"
                    aria-label={`Use the baseline's expense ${n}`}
                    onClick={() => restore(line.id)}
                  >
                    Use baseline
                  </button>
                }
              />
            );
          })}
          {ownLines.map((line, j) => (
            <ExpenseRow
              key={line.id}
              line={line}
              index={baseline.expense_lines.length + j}
              defaultYear={own.start_year}
              marker={isOperating(line.frequency) ? "Its own (operating)" : "Its own"}
              onChange={(next) => setLine(line.id, next)}
              onUpdate={(part) => setLine(line.id, { ...line, ...part })}
              onRemove={() => restore(line.id)}
            />
          ))}
        </tbody>
      </table>
      <div className="row-actions">
        <button
          type="button"
          onClick={() => {
            const id = newLineId([...known, ...Object.keys(lines)], "own");
            setLine(id, {
              id,
              frequency: "once",
              year: own.start_year,
              amount: "0",
              description: "",
              nominal: false,
              source: "",
            });
          }}
        >
          Add a line of this scenario's own
        </button>
      </div>
    </div>
  );
}

function FfbChanges({
  baseline,
  own,
  changes,
  onChange,
}: {
  baseline: Baseline;
  own: Baseline;
  changes: Changes;
  onChange: (changes: Changes) => void;
}) {
  if (!plausibleHorizon(own.start_year, own.end_year))
    return <p className="hint">Set a horizon of 5 to 30 years to see the Fully Funded Balance.</p>;
  const years = Array.from(
    { length: own.end_year - own.start_year + 2 },
    (_, i) => own.start_year + i,
  );
  return (
    <div className="table-scroll">
      <table className="edit-table ffb">
        <caption>Fully Funded Balance – blank follows the baseline</caption>
        <thead>
          <tr>
            <th scope="col">Start of year</th>
            <th scope="col">Baseline</th>
            <th scope="col">This scenario</th>
          </tr>
        </thead>
        <tbody>
          {years.map((y) => {
            const key = String(y);
            const base = baseline.ffb[key];
            return (
              <tr key={y} className={key in changes.ffb ? "own" : undefined}>
                <th scope="row">{y}</th>
                <td className="num">{base === undefined ? "none" : money(base)}</td>
                <td>
                  <DecimalInput
                    label={`This scenario's Fully Funded Balance at the start of ${y}`}
                    name={`This scenario's Fully Funded Balance for ${y}`}
                    allowBlank
                    value={changes.ffb[key] ?? null}
                    onChange={(v) =>
                      onChange({
                        ...changes,
                        ffb: v === null ? without(changes.ffb, key) : { ...changes.ffb, [key]: v },
                      })
                    }
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <label className="field">
        <span>Source – this scenario's Fully Funded Balance</span>
        <SourceNote
          label="Fully Funded Balance"
          baseline={baseline.sources.ffb}
          changes={changes}
          noteKey="ffb"
          onChange={onChange}
        />
      </label>
    </div>
  );
}
