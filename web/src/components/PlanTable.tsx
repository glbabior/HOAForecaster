import { useRef, useState } from "react";

import { CsvButton } from "./CsvButton";

import { dues, money, percent } from "../format";
import {
  isOperating,
  type Frequency,
  type LineAmount,
  type ScenarioResult,
  type YearResult,
} from "../types";

type Kind = "dues" | "money" | "percent" | "flag";

interface Row {
  label: string;
  value: (y: YearResult) => string | boolean;
  kind: Kind;
  input?: boolean;
  strong?: boolean;
  /** for flags – the value that is a warning; for the target, "yes" is good and "no" neutral */
  warnWhen?: boolean;
  /** shown first, in the headline table (spec 7.3) – the rest are the details */
  headline?: boolean;
}

// Spec 7.3, in its order.
const ROWS: Row[] = [
  {
    label: "Dues per unit per month",
    value: (y) => y.dues,
    kind: "dues",
    input: true,
    headline: true,
  },
  {
    label: "Special assessment per unit",
    value: (y) => y.assessment_per_unit,
    kind: "dues",
    input: true,
    headline: true,
  },
  { label: "Total dues collected", value: (y) => y.total_dues, kind: "money" },
  { label: "Operating expenses", value: (y) => y.operating, kind: "money", headline: true },
  { label: "Reserve contribution from dues", value: (y) => y.contribution, kind: "money" },
  { label: "Special assessment to reserves", value: (y) => y.assessment, kind: "money" },
  { label: "Total collected from owners", value: (y) => y.total_from_owners, kind: "money" },
  { label: "Interest earned", value: (y) => y.interest, kind: "money" },
  { label: "Reserve expenses", value: (y) => y.expenses, kind: "money", headline: true },
  { label: "Starting reserve balance", value: (y) => y.starting_balance, kind: "money" },
  {
    label: "Ending reserve balance",
    value: (y) => y.ending_balance,
    kind: "money",
    strong: true,
    headline: true,
  },
  { label: "Fully funded balance (start of next year)", value: (y) => y.ffb_next, kind: "money" },
  {
    label: "Percent funded",
    value: (y) => y.percent_funded,
    kind: "percent",
    strong: true,
    headline: true,
  },
  {
    label: "Below cushion?",
    value: (y) => y.low_flag,
    kind: "flag",
    warnWhen: true,
    headline: true,
  },
  { label: "Meets target?", value: (y) => y.target_met, kind: "flag" },
  { label: "Needs owner vote?", value: (y) => y.needs_vote, kind: "flag", warnWhen: true },
  {
    label: "Operating shortfall?",
    value: (y) => y.operating_shortfall,
    kind: "flag",
    warnWhen: true,
  },
  {
    label: "Owner cost – dues per year",
    value: (y) => y.owner_dues_year,
    kind: "money",
    headline: true,
  },
  {
    label: "Owner cost – dues + assessment",
    value: (y) => y.owner_cost_year,
    kind: "money",
  },
  { label: "Increase vs current dues", value: (y) => y.dues_increase_vs_current, kind: "money" },
  { label: "Cumulative owner cost", value: (y) => y.cumulative_owner_cost, kind: "money" },
  { label: "Cumulative extra cost", value: (y) => y.cumulative_extra, kind: "money" },
  { label: "Percent-funded target", value: (y) => y.target, kind: "percent" },
];

function cell(row: Row, y: YearResult): { text: string; csv: string; className: string } {
  const v = row.value(y);
  if (row.kind === "flag") {
    const flagged = v === true;
    const style =
      row.warnWhen === undefined
        ? flagged
          ? "flag-good"
          : ""
        : flagged === row.warnWhen
          ? "flag-warn"
          : "flag-good";
    const text = row.label === "Below cushion?" ? (flagged ? "LOW" : "ok") : flagged ? "yes" : "no";
    return { text, csv: text, className: `flag ${style}`.trim() };
  }
  const raw = String(v);
  const text = row.kind === "dues" ? dues(raw) : row.kind === "percent" ? percent(raw) : money(raw);
  const negative = raw.startsWith("-") ? " negative" : "";
  return { text, csv: raw, className: `num${negative}` };
}

// the headline rows in the order shown first – dues, then the money, then what it leaves
const HEADLINE_ORDER = [
  "Dues per unit per month",
  "Special assessment per unit",
  "Operating expenses",
  "Reserve expenses",
  "Ending reserve balance",
  "Percent funded",
  "Owner cost – dues per year",
  "Below cushion?",
];

type LineKind = "operating" | "reserve";

/** The rows whose figure is a sum of expense lines, which a click opens. */
const LINE_ROWS: Record<string, LineKind | undefined> = {
  "Operating expenses": "operating",
  "Reserve expenses": "reserve",
};

const linesOf = (y: YearResult, kind: LineKind): LineAmount[] =>
  kind === "operating" ? y.operating_lines : y.expense_lines;

const FREQUENCY_WORDS: Record<Frequency, string> = {
  monthly: "monthly",
  yearly: "yearly",
  every: "every few years",
  once: "once",
};

/** The year-by-year Plan table for one scenario – the equivalent of a Plan sheet: the headline
 * rows, then the rest in a details table that opens beneath. The CSV holds every row. */
export function PlanTable({
  result,
  caption,
  filename,
  cushion,
  target,
}: {
  result: ScenarioResult;
  caption: string;
  filename: string;
  /** the scenario's cushion and target, shown in their rows' labels */
  cushion?: string;
  target?: string;
}) {
  // a row's label as shown – the flags name the figure they are judged against
  const labelOf = (row: Row): string =>
    row.label === "Below cushion?" && cushion !== undefined
      ? `Below cushion (${money(cushion)})?`
      : row.label === "Meets target?" && target !== undefined
        ? `Meets target (${percent(target)} funded)?`
        : row.label;
  const [opened, setOpened] = useState<{ year: number; kind: LineKind } | null>(null);
  const headline = useRef<HTMLTableElement>(null);
  const details = useRef<HTMLTableElement>(null);
  const open = result.years.find((y) => y.year === opened?.year);
  const openLines = open && opened ? linesOf(open, opened.kind) : [];
  // the headline rows in the order a board reads them; the details in the spec's order
  const headlineRows = HEADLINE_ORDER.flatMap((label) =>
    ROWS.filter((r) => r.headline && r.label === label),
  );
  const detailRows = ROWS.filter((r) => !r.headline);

  function table(rows: Row[], ref: typeof headline, title: string) {
    return (
      <div className="table-scroll">
        <table className="plan" ref={ref}>
          <caption>{title}</caption>
          <thead>
            <tr>
              <th scope="col">Year</th>
              {result.years.map((y) => (
                <th scope="col" key={y.year} className="num">
                  {y.year}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.label}
                className={[row.input ? "input-row" : "", row.strong ? "strong" : ""].join(" ")}
              >
                <th scope="row">{labelOf(row)}</th>
                {result.years.map((y) => {
                  const c = cell(row, y);
                  const kind = LINE_ROWS[row.label];
                  const lines = kind ? linesOf(y, kind) : [];
                  if (kind && lines.length > 0) {
                    const isOpen = opened?.year === y.year && opened.kind === kind;
                    return (
                      <td key={y.year} className={c.className} data-csv={c.csv}>
                        <button
                          type="button"
                          className="link"
                          aria-expanded={isOpen}
                          title={lines
                            .map(
                              (l) => `${money(l.amount)} – ${l.description || "(no description)"}`,
                            )
                            .join("\n")}
                          onClick={() => setOpened(isOpen ? null : { year: y.year, kind })}
                        >
                          {c.text}
                        </button>
                      </td>
                    );
                  }
                  return (
                    <td key={y.year} className={c.className} data-csv={c.csv}>
                      {c.text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <div className="section-head">
        <span />
        <CsvButton table={[headline, details]} filename={filename} order={ROWS.map(labelOf)} />
      </div>
      <details className="plan-details" open>
        <summary>
          <span className="summary-title">Headline figures</span>
        </summary>
        {table(headlineRows, headline, caption)}
      </details>
      {open && opened && (
        <section className="expense-detail" aria-live="polite">
          <h4>
            {opened.kind === "operating" ? "Operating expenses" : "Reserve expenses"} in {open.year}
          </h4>
          <ul>
            {openLines.map((line, i) => (
              <li key={i}>
                {money(line.amount)} – {line.description || "(no description)"} (
                {FREQUENCY_WORDS[line.frequency]}
                {isOperating(line.frequency)
                  ? ""
                  : !line.nominal
                    ? ", grown with inflation"
                    : line.frequency === "every"
                      ? ", grown from its first year's dollars"
                      : ", already in that year's dollars"}
                ){line.source && <span className="source"> · Source – {line.source}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      <details className="plan-details">
        <summary>
          <span className="summary-title">Details</span>
        </summary>
        <p className="hint">Collections, interest, balances, flags and owner costs.</p>
        {table(detailRows, details, `${caption} – details`)}
      </details>
    </div>
  );
}
