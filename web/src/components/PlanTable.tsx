import { useRef, useState } from "react";

import { CsvButton } from "./CsvButton";

import { dues, money, percent } from "../format";
import type { ScenarioResult, YearResult } from "../types";

type Kind = "dues" | "money" | "percent" | "flag";

interface Row {
  label: string;
  value: (y: YearResult) => string | boolean;
  kind: Kind;
  input?: boolean;
  strong?: boolean;
  /** for flags – the value that is a warning; for the target, "yes" is good and "no" neutral */
  warnWhen?: boolean;
}

// Spec 7.3, in its order.
const ROWS: Row[] = [
  { label: "Dues per unit per month", value: (y) => y.dues, kind: "dues", input: true },
  {
    label: "Special assessment per unit",
    value: (y) => y.assessment_per_unit,
    kind: "dues",
    input: true,
  },
  { label: "Total dues collected", value: (y) => y.total_dues, kind: "money" },
  { label: "Operating expenses", value: (y) => y.operating, kind: "money" },
  { label: "Reserve contribution from dues", value: (y) => y.contribution, kind: "money" },
  { label: "Special assessment to reserves", value: (y) => y.assessment, kind: "money" },
  { label: "Total collected from owners", value: (y) => y.total_from_owners, kind: "money" },
  { label: "Interest earned", value: (y) => y.interest, kind: "money" },
  { label: "Reserve expenses", value: (y) => y.expenses, kind: "money" },
  { label: "Starting reserve balance", value: (y) => y.starting_balance, kind: "money" },
  { label: "Ending reserve balance", value: (y) => y.ending_balance, kind: "money", strong: true },
  { label: "Fully funded balance (start of next year)", value: (y) => y.ffb_next, kind: "money" },
  { label: "Percent funded", value: (y) => y.percent_funded, kind: "percent", strong: true },
  { label: "Below cushion?", value: (y) => y.low_flag, kind: "flag", warnWhen: true },
  { label: "Meets target?", value: (y) => y.target_met, kind: "flag" },
  { label: "Needs owner vote?", value: (y) => y.needs_vote, kind: "flag", warnWhen: true },
  {
    label: "Operating shortfall?",
    value: (y) => y.operating_shortfall,
    kind: "flag",
    warnWhen: true,
  },
  { label: "Owner cost – dues per year", value: (y) => y.owner_dues_year, kind: "money" },
  { label: "Owner cost – dues + assessment", value: (y) => y.owner_cost_year, kind: "money" },
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

/** The year-by-year Plan table for one scenario – the equivalent of a Plan sheet. */
export function PlanTable({
  result,
  caption,
  filename,
}: {
  result: ScenarioResult;
  caption: string;
  filename: string;
}) {
  const [openYear, setOpenYear] = useState<number | null>(null);
  const table = useRef<HTMLTableElement>(null);
  const open = result.years.find((y) => y.year === openYear);
  return (
    <div>
      <div className="section-head">
        <span />
        <CsvButton table={table} filename={filename} />
      </div>
      <div className="table-scroll">
        <table className="plan" ref={table}>
          <caption>{caption}</caption>
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
            {ROWS.map((row) => (
              <tr
                key={row.label}
                className={[row.input ? "input-row" : "", row.strong ? "strong" : ""].join(" ")}
              >
                <th scope="row">{row.label}</th>
                {result.years.map((y) => {
                  const c = cell(row, y);
                  if (row.label === "Reserve expenses" && y.expense_lines.length > 0) {
                    return (
                      <td key={y.year} className={c.className} data-csv={c.csv}>
                        <button
                          type="button"
                          className="link"
                          aria-expanded={openYear === y.year}
                          title={y.expense_lines.map((l) => l.description).join("\n")}
                          onClick={() => setOpenYear(openYear === y.year ? null : y.year)}
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
      {open && (
        <section className="expense-detail" aria-live="polite">
          <h4>Reserve expenses in {open.year}</h4>
          <ul>
            {open.expense_lines.map((line, i) => (
              <li key={i}>
                {money(line.amount)} – {line.description || "(no description)"}
                {line.nominal ? " (already in that year's dollars)" : " (grown with inflation)"}
                {line.source && <span className="source"> · Source – {line.source}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
