import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { ErrorBanner } from "../components/ui";
import { date } from "../format";
import type { ProjectSummary } from "../types";

// the ways to order the project cards – the last saved first unless another is chosen
const SORTS = {
  modified: {
    label: "Last saved (newest first)",
    compare: (a: ProjectSummary, b: ProjectSummary) => b.modified.localeCompare(a.modified),
  },
  name: {
    label: "Name (A–Z)",
    compare: (a: ProjectSummary, b: ProjectSummary) =>
      a.name.localeCompare(b.name, "en-US", { numeric: true, sensitivity: "base" }),
  },
  scenarios: {
    label: "Scenarios (most first)",
    compare: (a: ProjectSummary, b: ProjectSummary) => b.scenarios - a.scenarios,
  },
};
type SortBy = keyof typeof SORTS;

/** A building, for a project's card – decoration only. */
function BuildingIcon() {
  return (
    <svg className="card-icon" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path
        d="M6 28V6.5L17 3v25M17 28V11l9 3v14M3.5 28h25M10 10h3M10 15h3M10 20h3M21 18h2M21 22h2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ProjectList() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [unreadable, setUnreadable] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const [sortBy, setSortBy] = useState<SortBy>("modified");

  useEffect(() => {
    api
      .listProjects()
      .then((r) => {
        setProjects(r.projects);
        setUnreadable(r.unreadable);
      })
      .catch(setError);
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      const stored = await api.createBlank(name.trim());
      const first = stored.project.scenarios[0]?.name ?? "";
      navigate(`/projects/${stored.id}/scenarios/${encodeURIComponent(first)}/facts`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  async function importFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const stored = file.name.toLowerCase().endsWith(".xlsx")
        ? await api.importWorkbook(file)
        : await api.importProject(file);
      navigate(`/projects/${stored.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Projects</h1>
      <ErrorBanner error={error} />
      {projects === null && !error && <p aria-busy="true">Loading…</p>}
      {projects?.length === 0 && <p>No projects yet – create one or import a file below.</p>}
      {projects && projects.length > 0 && (
        <>
          <div className="toolbar">
            <label>
              Sort{" "}
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
                {Object.entries(SORTS).map(([key, s]) => (
                  <option key={key} value={key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <ul className="cards" aria-label="Saved projects">
            {[...projects].sort(SORTS[sortBy].compare).map((p) => (
              <li key={p.id} className="card">
                <BuildingIcon />
                <Link to={`/projects/${p.id}`} className="card-title">
                  {p.name}
                </Link>
                <span className="card-caption">
                  {p.scenarios === 1 ? "1 scenario" : `${p.scenarios} scenarios`} · saved{" "}
                  {date(p.modified)}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {unreadable.length > 0 && (
        <p className="warning">
          {unreadable.length === 1 ? "One file" : `${unreadable.length} files`} in the data folder
          could not be read as projects – {unreadable.join(", ")}.
        </p>
      )}

      <section className="panel">
        <h2>New project</h2>
        <form onSubmit={create} className="inline-form">
          <label htmlFor="new-name">Building or association name</label>
          <input id="new-name" value={name} onChange={(e) => setName(e.target.value)} required />
          <button type="submit" className="primary" disabled={busy || !name.trim()}>
            Create
          </button>
        </form>
        <p className="hint">
          Starts with one scenario on January 1 of next year with the usual assumptions – 3%
          inflation, 2% interest, a 70% target – ready for the building's own facts.
        </p>
      </section>

      <section className="panel">
        <h2>Import</h2>
        <p>
          A project file (.json) saved with Export project, or a workbook (.xlsx) exported from
          HOAForecaster.
        </p>
        <input
          ref={fileInput}
          type="file"
          accept=".json,.xlsx,application/json"
          aria-label="Project file or workbook to import"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void importFile(file);
            e.target.value = "";
          }}
        />
      </section>
    </>
  );
}
