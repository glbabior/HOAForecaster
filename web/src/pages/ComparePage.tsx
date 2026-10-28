import { Fragment, useEffect, useRef, useState, type RefObject } from "react";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { CsvButton } from "../components/CsvButton";
import { ScenarioPicker } from "../components/ScenarioPicker";
import { numberOf, useSort } from "../components/sort";
import { ErrorBanner } from "../components/ui";
import { num } from "../decimal";
import { dues, longDate, money, percent, today } from "../format";
import { printAs } from "../print";
import type { Facts, ProjectResults, ScenarioResult, Summary } from "../types";

type Kind = "dues" | "money" | "percent" | "count" | "year";

interface Measure {
  label: string;
  /** from the scenario's results – or, for a row of its own figures, its facts */
  value: (s: Summary, f: Facts) => string | number | null;
  kind: Kind;
  /** which way is better, for the difference colours – none for neutral facts */
  better?: "higher" | "lower";
}

/** The summary measures (spec 6). `span` is the horizon every shown scenario shares – the labels
 * name calendar years only then; otherwise they count years of each projection (spec 7.4). */
function measures(span: [number, number] | null, years: number, facts: Facts[]): Measure[] {
  const one = <T,>(of: (f: Facts) => T): T | undefined =>
    facts.length > 0 && facts.every((f) => of(f) === of(facts[0] as Facts))
      ? of(facts[0] as Facts)
      : undefined;
  const cushion = one((f) => f.cushion);
  const target = one((f) => f.target);
  const year = (offset: number) => (span ? String(span[0] + offset) : `year ${offset + 1}`);
  const first = (n: number) =>
    span ? `${span[0]}–${span[0] + n - 1}` : n === 5 ? "first five years" : "first four years";
  const whole = span ? `${span[0]}–${span[1]}` : "whole projection";
  const last = span ? String(span[1]) : "the projection";
  const list: (Measure | false)[] = [
    {
      label: `Dues per unit per month – ${year(0)}`,
      value: (s) => s.dues_y1,
      kind: "dues",
      better: "lower",
    },
    {
      label: `Dues per unit per month – ${year(3)}`,
      value: (s) => s.dues_y4,
      kind: "dues",
      better: "lower",
    },
    years >= 9 && {
      label: `Dues per unit per month – ${year(8)}`,
      value: (s) => s.dues_y9,
      kind: "dues",
      better: "lower",
    },
    {
      label: `Dues per unit per month – ${span ? last : "last year"}`,
      value: (s) => s.dues_end,
      kind: "dues",
      better: "lower",
    },
    {
      label: "Special assessments per unit, total",
      value: (s) => s.total_assessments,
      kind: "money",
      better: "lower",
    },
    {
      label: "Lowest year-end balance",
      value: (s) => s.lowest_balance,
      kind: "money",
      better: "higher",
    },
    { label: "Year of the lowest balance", value: (s) => s.lowest_balance_year, kind: "year" },
    // the scenarios' own cushions, in a row of their own when they differ
    cushion === undefined && {
      label: "Minimum cushion",
      value: (_s, f) => f.cushion,
      kind: "money",
    },
    {
      label:
        cushion !== undefined
          ? `Years below the cushion (${money(cushion)})`
          : "Years below each scenario's cushion",
      value: (s) => s.low_years,
      kind: "count",
      better: "lower",
    },
    {
      label: `Balance end of ${year(3)}`,
      value: (s) => s.balance_y4,
      kind: "money",
      better: "higher",
    },
    {
      label: `Percent funded end of ${year(3)}`,
      value: (s) => s.pf_y4,
      kind: "percent",
      better: "higher",
    },
    years >= 9 && {
      label: `Balance end of ${year(8)}`,
      value: (s) => s.balance_y9,
      kind: "money",
      better: "higher",
    },
    years >= 9 && {
      label: `Percent funded end of ${year(8)}`,
      value: (s) => s.pf_y9,
      kind: "percent",
      better: "higher",
    },
    {
      label: `Balance end of ${last}`,
      value: (s) => s.balance_end,
      kind: "money",
      better: "higher",
    },
    {
      label: `Percent funded end of ${last}`,
      value: (s) => s.pf_end,
      kind: "percent",
      better: "higher",
    },
    target === undefined && {
      label: "Percent-funded target",
      value: (_s, f) => f.target,
      kind: "percent",
    },
    {
      label:
        target !== undefined
          ? `First year the target (${percent(target)} funded) is met`
          : "First year each scenario's target is met",
      value: (s) => s.first_target_year,
      kind: "year",
    },
    {
      label: `Owner outlay per unit, ${first(5)}`,
      value: (s) => s.outlay_first5,
      kind: "money",
      better: "lower",
    },
    {
      label: `Owner outlay per unit, ${whole}`,
      value: (s) => s.outlay_total,
      kind: "money",
      better: "lower",
    },
    {
      label: `Extra cost vs current dues, ${first(4)}`,
      value: (s) => s.extra_first4,
      kind: "money",
      better: "lower",
    },
    {
      label: `Extra cost vs current dues, ${whole}`,
      value: (s) => s.extra_total,
      kind: "money",
      better: "lower",
    },
    {
      label: "Average owner cost per year",
      value: (s) => s.avg_owner_cost,
      kind: "money",
      better: "lower",
    },
    {
      label: "Average extra cost per year",
      value: (s) => s.avg_extra,
      kind: "money",
      better: "lower",
    },
    {
      label: "Years needing an owner vote",
      value: (s) => s.vote_years,
      kind: "count",
      better: "lower",
    },
    {
      label: "Years with an operating shortfall",
      value: (s) => s.shortfall_years,
      kind: "count",
      better: "lower",
    },
  ];
  return list.filter((m): m is Measure => m !== false);
}

function show(kind: Kind, value: string | number | null, end: number): string {
  if (value === null) return kind === "year" ? `not by ${end}` : "–";
  if (kind === "dues") return dues(String(value));
  if (kind === "money") return money(String(value));
  if (kind === "percent") return percent(String(value));
  return String(value);
}

/** A figure below zero – flagged like a year below the cushion. */
function below(value: string | number | null): boolean {
  return value !== null && num(String(value)) < 0;
}

// The smallest difference worth showing, per kind – a hundredth of a point for percentages
// (stored as fractions), a cent for money.
const SMALLEST: Record<Kind, number> = {
  dues: 0.005,
  money: 0.5,
  percent: 0.00005,
  count: 0.5,
  year: 0,
};

/** Difference from the first scenario, as a short signed label and a better/worse class. */
function difference(
  kind: Kind,
  better: Measure["better"],
  value: string | number | null,
  base: string | number | null,
) {
  if (value === null || base === null || kind === "year") return null;
  const delta = num(String(value)) - num(String(base));
  if (Math.abs(delta) < SMALLEST[kind]) return null;
  const sign = delta > 0 ? "+" : "−";
  const size = Math.abs(delta);
  const text =
    kind === "percent"
      ? `${sign}${(size * 100).toFixed(1)} pts`
      : kind === "count"
        ? `${sign}${size}`
        : `${sign}${kind === "dues" ? dues(String(size)) : money(String(size))}`;
  const good = better ? (better === "higher") === delta > 0 : null;
  return { text, className: good === null ? "" : good ? "better" : "worse" };
}

export function ComparePage() {
  const { id, stored, error } = useProject();
  const [results, setResults] = useState<ProjectResults | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [diffs, setDiffs] = useState(false);
  const summaryTable = useRef<HTMLTableElement>(null);
  const balanceTable = useRef<HTMLTableElement>(null);
  const pfTable = useRef<HTMLTableElement>(null);

  useEffect(() => {
    api.results(id).then(setResults).catch(setLoadError);
  }, [id]);

  if (!stored || !results) return <Loading error={error ?? loadError} />;
  const names = stored.project.scenarios.map((s) => s.name);
  const ok: [string, ScenarioResult][] = names.flatMap((n) => {
    const o = results.scenarios[n];
    return o && "result" in o ? [[n, o.result] as [string, ScenarioResult]] : [];
  });
  const failing = names.filter((n) => !ok.some(([m]) => m === n));
  const selected = (chosen ?? names).filter((n) => ok.some(([m]) => m === n));
  const shown = selected.map(
    (n) => [n, ok.find(([m]) => m === n)?.[1]] as [string, ScenarioResult],
  );
  // scenarios may run over different years – their own horizon, or an earlier adopted one
  const spans = new Set(shown.map(([, r]) => `${r.years[0]?.year}–${r.years.at(-1)?.year}`));
  const shared = spans.size === 1 && shown[0] ? shown[0][1].years : null;
  const span: [number, number] | null = shared
    ? [shared[0]?.year ?? 0, shared.at(-1)?.year ?? 0]
    : null;
  const factsOf = (n: string) => stored.project.scenarios.find((s) => s.name === n)?.facts as Facts;
  const list = measures(
    span,
    Math.max(0, ...shown.map(([, r]) => r.years.length)),
    shown.map(([n]) => factsOf(n)),
  );
  const allYears = [...new Set(shown.flatMap(([, r]) => r.years.map((y) => y.year)))].sort(
    (x, y) => x - y,
  );
  const name = stored.project.name;

  return (
    <>
      <ProjectNav stored={stored} here="Compare" />
      <h1>Compare scenarios</h1>
      <p className="print-only">
        {name} – {longDate(today())}
      </p>
      <ErrorBanner error={loadError} />
      {failing.length > 0 && (
        <p className="warning">
          Left out because of problems in their inputs – {failing.join(", ")}.
        </p>
      )}
      <div className="row-actions no-print">
        <ScenarioPicker names={names} selected={chosen ?? names} onChange={setChosen} />
        <label>
          <input type="checkbox" checked={diffs} onChange={(e) => setDiffs(e.target.checked)} />{" "}
          Show differences from {shown[0]?.[0] ?? "the first scenario"}
        </label>
        <button type="button" onClick={() => printAs(`${name} – Compare scenarios`)}>
          Save as PDF…
        </button>
        <span className="hint">
          Choose “Save as PDF” (or “Microsoft Print to PDF”) as the printer, or a printer to print.
        </span>
      </div>

      {shown.length === 0 ? (
        <p>Choose at least one scenario.</p>
      ) : (
        <>
          <section className="panel">
            <div className="section-head">
              <h2>Summary</h2>
              <CsvButton table={summaryTable} filename={`${name} - compare.csv`} />
            </div>
            <div className="table-scroll">
              <table className="compare" ref={summaryTable}>
                <caption className="visually-hidden">Summary measures by scenario</caption>
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    {shown.map(([n]) => (
                      <th scope="col" key={n} className="num">
                        {n}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {list.map((m) => {
                    const base = shown[0]
                      ? m.value(shown[0][1].summary, factsOf(shown[0][0]))
                      : null;
                    return (
                      <tr key={m.label}>
                        <th scope="row">{m.label}</th>
                        {shown.map(([n, r], i) => {
                          const v = m.value(r.summary, factsOf(n));
                          const d = diffs && i > 0 ? difference(m.kind, m.better, v, base) : null;
                          return (
                            <td
                              key={n}
                              className={`num${m.better === "higher" && below(v) ? " flag-warn" : ""}`}
                              data-csv={v === null ? "" : String(v)}
                            >
                              {show(m.kind, v, r.years.at(-1)?.year ?? 0)}
                              {d && <span className={`diff ${d.className}`}> ({d.text})</span>}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {(
            [
              ["Year-end reserve balance by year", balanceTable, "ending_balance", "balances"],
              ["Percent funded by year", pfTable, "percent_funded", "percent funded"],
            ] as const
          ).map(([title, ref, field, file]) => (
            <ByYearTable
              key={field}
              title={title}
              tableRef={ref}
              field={field}
              filename={`${name} - ${file}.csv`}
              shown={shown}
              years={allYears}
              diffs={diffs}
            />
          ))}
        </>
      )}
    </>
  );
}

/** One figure by year for every scenario shown – sortable by the year or by any scenario. */
function ByYearTable({
  title,
  tableRef,
  field,
  filename,
  shown,
  years,
  diffs,
}: {
  title: string;
  tableRef: RefObject<HTMLTableElement | null>;
  field: "ending_balance" | "percent_funded";
  filename: string;
  shown: [string, ScenarioResult][];
  years: number[];
  diffs: boolean;
}) {
  const value = (r: ScenarioResult, year: number) =>
    r.years.find((y) => y.year === year)?.[field] ?? null;
  const { order, header } = useSort(years, {
    year: (y) => y,
    ...Object.fromEntries(shown.map(([n, r]) => [`s:${n}`, (y: number) => numberOf(value(r, y))])),
  });
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{title}</h2>
        <CsvButton table={tableRef} filename={filename} />
      </div>
      <div className="table-scroll">
        <table className="compare" ref={tableRef}>
          <caption className="visually-hidden">{title}</caption>
          <thead>
            <tr>
              {header("year", "Year")}
              {shown.map(([n]) => (
                <Fragment key={n}>{header(`s:${n}`, n, { className: "num" })}</Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {order.map((i) => {
              const year = years[i] as number;
              return (
                <tr key={year}>
                  <th scope="row">{year}</th>
                  {shown.map(([n, r], k) => {
                    // the same calendar year in each scenario, blank where it has none
                    const at = r.years.find((y) => y.year === year);
                    const v = at?.[field] ?? null;
                    const low = (field === "ending_balance" && at?.low_flag) || below(v);
                    const first = shown[0]?.[1].years.find((y) => y.year === year);
                    const base = first?.[field] ?? null;
                    const kind = field === "ending_balance" ? "money" : "percent";
                    const d = diffs && k > 0 ? difference(kind, "higher", v, base) : null;
                    return (
                      <td key={n} className={`num${low ? " flag-warn" : ""}`} data-csv={v ?? ""}>
                        {field === "ending_balance" ? money(v) : percent(v)}
                        {d && <span className={`diff ${d.className}`}> ({d.text})</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
