import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { Confirm, ErrorBanner, Problems } from "../components/ui";
import { date, longDate, money, span } from "../format";
import { currentAdoption } from "../template";
import type { ProjectResults } from "../types";

/** The project's overview – what it holds, and the steps in the order they are done. */
export function ProjectPage() {
  const navigate = useNavigate();
  const { id, stored, error } = useProject();
  const [results, setResults] = useState<ProjectResults | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (stored) api.results(id).then(setResults).catch(setActionError);
  }, [id, stored]);

  if (!stored) return <Loading error={error} />;
  const { project } = stored;
  const b = project.baseline;
  const at = (path: string) => `/projects/${id}/${path}`;
  const adopted = currentAdoption(project.scenarios);
  const working = project.scenarios.filter((s) => !s.adoption).length;
  const earlier = project.scenarios.filter((s) => s.adoption && s !== adopted).length;
  const lines = { operating: 0, reserve: 0 };
  for (const line of b.expense_lines) {
    if (line.frequency === "monthly" || line.frequency === "yearly") lines.operating += 1;
    else lines.reserve += 1;
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

      <ol className="steps">
        <li>
          <h2>
            <Link to={at("baseline")}>Facts and assumptions</Link>
          </h2>
          <p>
            {span(b.start_year, b.end_year)} · {b.units} units · starting balance{" "}
            {money(b.starting_balance)} · current dues {money(b.current_dues, true)} a month
          </p>
          <p className="hint">
            The building's facts and the rates everything grows at. Last changed{" "}
            {date(stored.baseline_times.modified)}.
          </p>
        </li>
        <li>
          <h2>
            <Link to={at("expenses")}>Expenses</Link>
          </h2>
          <p>
            {lines.operating} running costs paid from dues · {lines.reserve} repairs and
            replacements paid from reserves
          </p>
        </li>
        <li>
          <h2>
            <Link to={at("ffb")}>Fully Funded Balance</Link>
          </h2>
          <p>
            From the reserve study{b.sources.ffb ? ` – ${b.sources.ffb}` : ""}, used for percent
            funded.
          </p>
        </li>
        <li>
          <h2>
            <Link to={at("scenarios")}>Scenarios</Link>
          </h2>
          <p>
            {working} {working === 1 ? "scenario" : "scenarios"}
            {adopted
              ? ` · adopted plan – ${adopted.name}, ${longDate(adopted.adoption?.date ?? "")}`
              : ""}
            {earlier > 0 ? ` · ${earlier} earlier adopted ${earlier === 1 ? "plan" : "plans"}` : ""}
          </p>
          <p className="hint">
            Ways to pay for the plan – dues each year, special assessments, and any assumption a
            scenario sets for itself.
          </p>
        </li>
        <li>
          <h2>
            <Link to={at("compare")}>Compare</Link> and <Link to={at("charts")}>Charts</Link>
          </h2>
          <p className="hint">The scenarios side by side, as tables and as charts.</p>
        </li>
        <li>
          <h2>
            <Link to={at("export")}>Export</Link>
          </h2>
          <p className="hint">An Excel workbook with live formulas, or a copy of the project.</p>
        </li>
      </ol>

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
        onConfirm={() => {
          setActionError(null);
          api.deleteProject(id).then(() => navigate("/"), setActionError);
        }}
      >
        <p>
          The project moves to the trash folder inside HOAForecaster's data folder. Export it first
          if you may want it back in the app.
        </p>
      </Confirm>
    </>
  );
}
