import { useState } from "react";

import { Loading, ProjectNav, useProject } from "../App";
import { api, saveFile } from "../api";
import { ScenarioPicker } from "../components/ScenarioPicker";
import { ErrorBanner } from "../components/ui";

/** The Excel workbook (spec 7.6) and the project file to keep a copy (spec 8.2). */
export function ExportPage() {
  const { id, stored, error } = useProject();
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  if (!stored) return <Loading error={error} />;
  const names = stored.project.scenarios.map((s) => s.name);
  const selected = chosen ?? names;

  async function download(get: () => Promise<{ blob: Blob; filename: string }>) {
    setActionError(null);
    try {
      const { blob, filename } = await get();
      saveFile(blob, filename);
    } catch (e) {
      setActionError(e);
    }
  }

  return (
    <>
      <ProjectNav stored={stored} here="Export" />
      <h1>Export</h1>
      <ErrorBanner error={actionError} />
      <section className="panel">
        <h2>Excel workbook</h2>
        <p className="hint">
          The baseline, the expenses and one sheet per chosen scenario, with live formulas that
          recalculate in Excel, and the charts – for sharing with the board.
        </p>
        <div className="row-actions">
          <ScenarioPicker names={names} selected={selected} onChange={setChosen} />
          <button
            type="button"
            className="primary"
            disabled={selected.length === 0}
            onClick={() => void download(() => api.exportWorkbook(id, selected))}
          >
            Download the workbook
          </button>
        </div>
      </section>
      <section className="panel">
        <h2>Project file</h2>
        <p className="hint">
          A copy of the whole project you can import later – a snapshot to keep before a big change.
        </p>
        <button type="button" onClick={() => void download(() => api.exportProject(id))}>
          Download the project file
        </button>
      </section>
    </>
  );
}
