import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { CsvButton } from "../components/CsvButton";
import { numberOf, useSort } from "../components/sort";
import { Confirm, ErrorBanner, Field } from "../components/ui";
import { date, longDate, money, percent } from "../format";
import { useAutosave, useUnsavedGuard } from "../hooks";
import { currentAdoption } from "../template";
import type { ProjectResults, StoredProject } from "../types";

/** The project's name and notes – saved as they are typed. */
function ProjectDetails({ stored }: { stored: StoredProject }) {
  const { save } = useProject();
  const initial = { name: stored.project.name, notes: stored.project.notes };
  const [form, setForm] = useState(initial);
  const { status } = useAutosave(form, initial, form.name.trim() !== "", async (f) => {
    await save((project) => ({ ...project, name: f.name.trim(), notes: f.notes }));
  });
  const { blocker } = useUnsavedGuard(!form.name.trim() || status.state === "failed");
  return (
    <section className="panel">
      <h2>Project</h2>
      <div className="grid-2">
        <Field
          label="Name"
          error={
            form.name.trim() ? null : "The project needs a name – nothing is saved until it has one"
          }
        >
          {(fid, d) => (
            <input
              id={fid}
              aria-describedby={d}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          )}
        </Field>
        <Field label="Notes">
          {(fid) => (
            <textarea
              id={fid}
              rows={2}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          )}
        </Field>
      </div>
      {status.state === "failed" && <ErrorBanner error={status.error} />}
      <Confirm
        open={blocker.state === "blocked"}
        title="Leave this screen?"
        confirmLabel="Leave"
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      >
        <p>
          {form.name.trim()
            ? "The last change to the project's name or notes could not be saved – it will be lost."
            : "The project needs a name, so the changes to its name and notes are not saved and will be lost."}
        </p>
      </Confirm>
    </section>
  );
}

/** The project's scenarios with their key results – each opens on its own screens. */
export function ScenariosPage() {
  const { id, stored, error } = useProject();
  const [results, setResults] = useState<ProjectResults | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const table = useRef<HTMLTableElement>(null);

  useEffect(() => {
    if (stored) api.results(id).then(setResults).catch(setLoadError);
  }, [id, stored]);

  // the adopted plan first, then the working scenarios, then earlier adopted plans, latest first
  const scenarios = stored?.project.scenarios ?? [];
  const current = currentAdoption(scenarios);
  const earlier = scenarios
    .filter((s) => s.adoption && s !== current)
    .sort((a, b) => (b.adoption?.sequence ?? 0) - (a.adoption?.sequence ?? 0));
  const listed = [
    ...(current ? [current] : []),
    ...scenarios.filter((s) => !s.adoption),
    ...earlier,
  ];
  const summary = (name: string) => {
    const outcome = results?.scenarios[name];
    return outcome && "result" in outcome ? outcome.result.summary : null;
  };
  const { order, header } = useSort(listed, {
    name: (s) => s.name,
    lowest: (s) => numberOf(summary(s.name)?.lowest_balance),
    low: (s) => summary(s.name)?.low_years,
    funded: (s) => numberOf(summary(s.name)?.pf_end),
    target: (s) => summary(s.name)?.first_target_year,
    changed: (s) => stored?.scenario_times[s.name]?.modified,
  });

  if (!stored) return <Loading error={error} />;
  const { project } = stored;
  const pending = "…"; // while results load – each scenario then has figures or problems

  return (
    <>
      <ProjectNav stored={stored} here="Scenarios" />
      <h1>Scenarios</h1>
      <p className="hint">
        A scenario is one way to pay for the plan, complete in itself – its facts and assumptions,
        its expenses, the reserve study's Fully Funded Balance, its dues each year and any special
        assessments. Open one to see and change it; every edit is saved as you make it. Start a new
        one blank, or as a copy of any scenario here.
      </p>
      <ErrorBanner error={loadError} />
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
              {header("name", "Scenario")}
              {header("lowest", "Lowest balance")}
              {header("low", "Years below cushion")}
              {header("funded", "Funded at end")}
              {header("target", "Target first met")}
              {header("changed", "Last changed")}
            </tr>
          </thead>
          <tbody>
            {order
              .map((i) => listed[i] as (typeof listed)[number])
              .map((s) => {
                const outcome = results?.scenarios[s.name];
                const r = outcome && "result" in outcome ? outcome.result.summary : null;
                const end =
                  outcome && "result" in outcome ? outcome.result.years.at(-1)?.year : null;
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
      <ProjectDetails key={stored.id} stored={stored} />
    </>
  );
}
