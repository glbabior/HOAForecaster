import { useId, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { ErrorBanner, Field } from "../components/ui";
import { currentAdoption, startFrom, uniqueName } from "../template";
import { scenarioPath } from "./ScenarioScreens";

/** Start a scenario – blank, or a copy of any scenario of the project (spec 7.2). */
export function NewScenario() {
  const navigate = useNavigate();
  const [query, setQuery] = useSearchParams();
  const { id, stored, error, save } = useProject();
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const uid = useId();
  if (!stored) return <Loading error={error} />;

  const scenarios = stored.project.scenarios;
  const from = scenarios.find((s) => s.name === query.get("from")) ?? null;
  const taken = scenarios.map((s) => s.name);
  const suggested = uniqueName(from ? `${from.name} – copy` : "New scenario", taken);
  const typed = (name ?? suggested).trim();
  const duplicate = taken.includes(typed);
  const current = currentAdoption(scenarios);
  // the adopted plan first, then the rest in their order
  const startingPoints = [...scenarios].sort(
    (a, b) => Number(b === current) - Number(a === current),
  );

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!typed || duplicate || !stored) return;
    setBusy(true);
    setSaveError(null);
    try {
      const blank = from ? null : await api.blankScenario(typed);
      // copied from the project as last saved – a scenario's edit still saving is included
      await save((project) => {
        const source = project.scenarios.find((s) => s.name === from?.name) ?? from;
        const scenario = blank ?? (source ? startFrom(source, typed) : null);
        if (!scenario) throw new Error("the scenario to start from is gone");
        return { ...project, scenarios: [...project.scenarios, scenario] };
      });
      // a copy is ready to compare; a blank one needs its facts first
      navigate(scenarioPath(id, typed, from ? "" : "facts"));
    } catch (err) {
      setSaveError(err);
      setBusy(false);
    }
  }

  return (
    <>
      <ProjectNav
        stored={stored}
        within={{ path: "scenarios", label: "Scenarios" }}
        here="New scenario"
      />
      <h1>New scenario</h1>
      <ErrorBanner error={saveError} />
      <form className="panel new-scenario" onSubmit={(e) => void create(e)}>
        <fieldset className="plain start-from" aria-describedby={`${uid}-hint`}>
          <legend>Start from</legend>
          <p id={`${uid}-hint`} className="hint">
            A copy takes all of that scenario's inputs – its facts and assumptions, expenses, Fully
            Funded Balance, dues and special assessments – but not its adoption. A blank scenario
            starts from the usual assumptions, ready for the building's own facts.
          </p>
          <div className="cards choices">
            {[null, ...startingPoints].map((s, i) => (
              <label key={s?.name ?? ""} className={`card${s === from ? " chosen" : ""}`}>
                {/* named by its title alone, the line under it its description */}
                <input
                  type="radio"
                  name="start-from"
                  value={s?.name ?? ""}
                  checked={s === from}
                  aria-labelledby={`${uid}-${i}-title`}
                  aria-describedby={`${uid}-${i}-caption`}
                  onChange={() => {
                    setName(null); // the suggested name follows the choice
                    setQuery(s ? { from: s.name } : {}, { replace: true });
                  }}
                />
                <span id={`${uid}-${i}-title`} className="card-title">
                  {s ? s.name : "A blank scenario"}
                </span>
                <span id={`${uid}-${i}-caption`} className="card-caption">
                  {!s
                    ? "The usual assumptions"
                    : s.adoption
                      ? s === current
                        ? "The adopted plan"
                        : "An earlier adopted plan"
                      : s.description || "A copy of every input"}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Name" error={duplicate ? "Another scenario already has this name" : null}>
          {(fid, d) => (
            <input
              id={fid}
              aria-describedby={d}
              value={name ?? suggested}
              onChange={(e) => setName(e.target.value)}
              required
            />
          )}
        </Field>
        <div className="row-actions">
          <button type="submit" className="primary" disabled={busy || !typed || duplicate}>
            Create
          </button>
          <button type="button" onClick={() => navigate(`/projects/${id}/scenarios`)}>
            Cancel
          </button>
        </div>
      </form>
    </>
  );
}
