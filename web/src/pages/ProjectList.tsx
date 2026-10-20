import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { ErrorBanner } from "../components/ui";
import { date } from "../format";
import type { ProjectSummary } from "../types";

export function ProjectList() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [unreadable, setUnreadable] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

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
      navigate(`/projects/${stored.id}/baseline`);
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
        <table className="list">
          <caption className="visually-hidden">Saved projects</caption>
          <thead>
            <tr>
              <th scope="col">Project</th>
              <th scope="col">Scenarios</th>
              <th scope="col">Last saved</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id}>
                <th scope="row">
                  <Link to={`/projects/${p.id}`}>{p.name}</Link>
                </th>
                <td className="num">{p.scenarios}</td>
                <td>{date(p.modified)}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
          Starts on January 1 of next year with the usual assumptions – 3% inflation, 2% interest, a
          70% target – ready for the building's own facts.
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
