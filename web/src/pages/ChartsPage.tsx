import { useEffect, useState } from "react";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { BALANCE_LEGEND, BalanceChart, ChartFrame, balanceSummary } from "../components/charts";
import { ScenarioPicker } from "../components/ScenarioPicker";
import { ErrorBanner, Problems } from "../components/ui";
import { num } from "../decimal";
import { sharedGrid } from "../scale";
import type { ProjectResults, ScenarioResult } from "../types";

/** Chart 1 for each chosen scenario, stacked on one dollar scale (spec 7.5). */
export function ChartsPage() {
  const { id, stored, error } = useProject();
  const [results, setResults] = useState<ProjectResults | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [chosen, setChosen] = useState<string[] | null>(null);

  useEffect(() => {
    api.results(id).then(setResults).catch(setLoadError);
  }, [id]);

  if (!stored || !results) return <Loading error={error ?? loadError} />;
  const names = stored.project.scenarios.map((s) => s.name);
  const shown: [string, ScenarioResult][] = (chosen ?? names).flatMap((n) => {
    const o = results.scenarios[n];
    return o && "result" in o ? [[n, o.result] as [string, ScenarioResult]] : [];
  });
  const values = shown.flatMap(([, r]) =>
    r.years.flatMap((y) => [num(y.expenses), num(y.total_from_owners), num(y.ending_balance)]),
  );
  const grid = values.length ? sharedGrid(Math.min(...values), Math.max(...values)) : undefined;

  return (
    <>
      <ProjectNav stored={stored} here="Charts" />
      <h1>Charts</h1>
      <ErrorBanner error={loadError} />
      <Problems title="The baseline has problems" items={results.baseline_problems} />
      <div className="row-actions no-print">
        <ScenarioPicker names={names} selected={chosen ?? names} onChange={setChosen} />
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
      </div>
      <p className="hint">
        Every chart uses the same dollar scale, so the scenarios compare at a glance. Dollar lines
        on the left axis; percent funded and the target on the right. Hover for a year's values.
      </p>
      {shown.map(([n, r]) => (
        <ChartFrame
          key={n}
          title={n}
          summary={balanceSummary(r)}
          filename={`${n} - balance.png`}
          legend={BALANCE_LEGEND}
        >
          <BalanceChart result={r} grid={grid} />
        </ChartFrame>
      ))}
      {shown.length === 0 && <p>Choose at least one scenario.</p>}
    </>
  );
}
