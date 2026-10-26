import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { CsvButton } from "../components/CsvButton";
import { ErrorBanner, Problems } from "../components/ui";
import { date, longDate, money, percent } from "../format";
import { currentAdoption } from "../template";
import type { ProjectResults } from "../types";

/** The project's scenarios with their key results – each opens in the scenario editor. */
export function ScenariosPage() {
  const { id, stored, error } = useProject();
  const [results, setResults] = useState<ProjectResults | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const table = useRef<HTMLTableElement>(null);

  useEffect(() => {
    if (stored) api.results(id).then(setResults).catch(setLoadError);
  }, [id, stored]);

  if (!stored) return <Loading error={error} />;
  const { project } = stored;
  // the adopted plan first, then the working scenarios, then earlier adopted plans, latest first
  const current = currentAdoption(project.scenarios);
  const earlier = project.scenarios
    .filter((s) => s.adoption && s !== current)
    .sort((a, b) => (b.adoption?.sequence ?? 0) - (a.adoption?.sequence ?? 0));
  const listed = [
    ...(current ? [current] : []),
    ...project.scenarios.filter((s) => !s.adoption),
    ...earlier,
  ];
  const pending = "…"; // while results load – each scenario then has figures or problems

  return (
    <>
      <ProjectNav stored={stored} here="Scenarios" />
      <h1>Scenarios</h1>
      <p className="hint">
        A scenario is one way to pay for the plan – its dues each year (a yearly increase, pinned
        years, or a figure typed for every year), any special assessments, and any fact or
        assumption it sets for itself. Open one to change it, or start a new one – blank or from any
        scenario here.
      </p>
      <ErrorBanner error={loadError} />
      <Problems
        title="The baseline has problems – fix them to see results"
        items={results?.baseline_problems ?? []}
      />
      <section className="panel">
        <div className="section-head">
          <Link className="button primary" to={`/projects/${id}/scenarios/new`}>
            New scenario
          </Link>
          <CsvButton table={table} filename={`${project.name} - scenarios.csv`} />
        </div>
        <table className="list" ref={table}>
          <caption className="visually-hidden">Scenarios and their key results</caption>
          <thead>
            <tr>
              <th scope="col">Scenario</th>
              <th scope="col">Lowest balance</th>
              <th scope="col">Years below cushion</th>
              <th scope="col">Funded at end</th>
              <th scope="col">Target first met</th>
              <th scope="col">Last changed</th>
            </tr>
          </thead>
          <tbody>
            {listed.map((s) => {
              const outcome = results?.scenarios[s.name];
              const r = outcome && "result" in outcome ? outcome.result.summary : null;
              const end = outcome && "result" in outcome ? outcome.result.years.at(-1)?.year : null;
              return (
                <tr key={s.name} className={s === current ? "adopted" : undefined}>
                  <th scope="row">
                    <Link to={`/projects/${id}/scenarios/${encodeURIComponent(s.name)}`}>
                      {s.name}
                    </Link>
                    {s.adoption && (
                      <div className="badge">
                        {s === current ? "Adopted plan" : "Earlier adopted plan"} · adopted{" "}
                        {longDate(s.adoption.date)}
                      </div>
                    )}
                    {s.description && <div className="hint">{s.description}</div>}
                  </th>
                  {outcome && "problems" in outcome ? (
                    <td colSpan={4} className="warning">
                      Has problems – open it to fix them
                    </td>
                  ) : (
                    <>
                      <td
                        className={`num${r && r.lowest_balance.startsWith("-") ? " negative" : ""}`}
                      >
                        {r ? `${money(r.lowest_balance)} (${r.lowest_balance_year})` : pending}
                      </td>
                      <td className="num">{r?.low_years ?? pending}</td>
                      <td className="num">{r ? percent(r.pf_end) : pending}</td>
                      <td>{r ? (r.first_target_year ?? `not by ${end}`) : pending}</td>
                    </>
                  )}
                  <td>{date(stored.scenario_times[s.name]?.modified ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}
