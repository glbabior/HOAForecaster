import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { api, saveFile } from "../api";
import { CsvButton } from "../components/CsvButton";
import { ScenarioPicker } from "../components/ScenarioPicker";
import { Confirm, ErrorBanner, Problems } from "../components/ui";
import { date, money, percent, span } from "../format";
import type { ProjectResults } from "../types";

export function ProjectPage() {
  const navigate = useNavigate();
  const { id, stored, error } = useProject();
  const [results, setResults] = useState<ProjectResults | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const scenarioTable = useRef<HTMLTableElement>(null);

  useEffect(() => {
    if (stored) api.results(id).then(setResults).catch(setActionError);
  }, [id, stored]);

  if (!stored) return <Loading error={error} />;
  const { project } = stored;
  const b = project.baseline;
  const names = project.scenarios.map((s) => s.name);
  const selected = chosen ?? names;
  // "…" while results load; a dash once it is known they cannot be worked out
  const pending = results && results.baseline_problems.length ? "–" : "…";

  async function run(action: () => Promise<void>) {
    setActionError(null);
    try {
      await action();
    } catch (e) {
      setActionError(e);
    }
  }

  return (
    <>
      <ProjectNav stored={stored} />
      <h1>{project.name}</h1>
      {project.notes && <p className="notes">{project.notes}</p>}
      <ErrorBanner error={actionError} />
      <Problems
        title="The baseline has problems – fix them to see results"
        items={results?.baseline_problems ?? []}
      />

      <section className="panel">
        <h2>Baseline</h2>
        <p>
          {span(b.start_year, b.end_year)} · {b.units} units · starting balance{" "}
          {money(b.starting_balance)} · current dues {money(b.current_dues, true)} a month ·{" "}
          {b.expense_lines.length} expense lines
        </p>
        <p className="hint">
          Last changed {date(stored.baseline_times.modified)}
          {b.sources.ffb ? ` · Reserve study – ${b.sources.ffb}` : ""}
        </p>
        <Link className="button" to={`/projects/${id}/baseline`}>
          Edit baseline
        </Link>
      </section>

      <section className="panel">
        <h2>Scenarios</h2>
        <div className="section-head">
          <span />
          <CsvButton table={scenarioTable} filename={`${project.name} - scenarios.csv`} />
        </div>
        <table className="list" ref={scenarioTable}>
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
            {project.scenarios.map((s) => {
              const outcome = results?.scenarios[s.name];
              const r = outcome && "result" in outcome ? outcome.result.summary : null;
              return (
                <tr key={s.name}>
                  <th scope="row">
                    <Link to={`/projects/${id}/scenarios/${encodeURIComponent(s.name)}`}>
                      {s.name}
                    </Link>
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
                      <td>{r ? (r.first_target_year ?? `not by ${b.end_year}`) : pending}</td>
                    </>
                  )}
                  <td>{date(stored.scenario_times[s.name]?.modified ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="row-actions">
          <Link className="button" to={`/projects/${id}/scenarios/new`}>
            New scenario
          </Link>
          <Link className="button" to={`/projects/${id}/compare`}>
            Compare scenarios
          </Link>
          <Link className="button" to={`/projects/${id}/charts`}>
            Charts
          </Link>
        </div>
      </section>

      <section className="panel">
        <h2>Export</h2>
        <div className="row-actions">
          <ScenarioPicker names={names} selected={selected} onChange={setChosen} />
          <button
            type="button"
            className="primary"
            disabled={selected.length === 0}
            onClick={() =>
              run(async () => {
                const { blob, filename } = await api.exportWorkbook(id, selected);
                saveFile(blob, filename);
              })
            }
          >
            Excel workbook
          </button>
          <button
            type="button"
            onClick={() =>
              run(async () => {
                const { blob, filename } = await api.exportProject(id);
                saveFile(blob, filename);
              })
            }
          >
            Export project
          </button>
        </div>
        <p className="hint">
          The workbook has live formulas and recalculates in Excel. Export project saves a copy you
          can import later – a snapshot before a big change.
        </p>
      </section>

      <section className="panel danger no-print">
        <h2>Delete project</h2>
        <button type="button" onClick={() => setConfirmDelete(true)}>
          Delete this project…
        </button>
      </section>
      <Confirm
        open={confirmDelete}
        title={`Delete ${project.name}?`}
        confirmLabel="Delete"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() =>
          run(async () => {
            await api.deleteProject(id);
            navigate("/");
          })
        }
      >
        <p>
          The project moves to the trash folder inside HOAForecaster's data folder. Export it first
          if you may want it back in the app.
        </p>
      </Confirm>
    </>
  );
}
