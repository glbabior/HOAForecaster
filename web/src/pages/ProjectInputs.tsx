import { useEffect, useState } from "react";
import { Link, Outlet, matchPath, useLocation } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { api } from "../api";
import { Confirm, ErrorBanner, Field, Problems, useInvalidFields } from "../components/ui";
import { money, percent } from "../format";
import { useAutosave, useDebounced, useUnsavedGuard } from "../hooks";
import { duesWithHorizon, expensesOf, sameExpenses, uniqueName, withExpenses } from "../template";
import { num } from "../decimal";
import type {
  ExpenseSet,
  Facts,
  Project,
  ProjectResults,
  ProjectRun,
  StoredProject,
} from "../types";
import { FactsContext, SaveNote, scenarioPath } from "./ScenarioScreens";

/** The project's own screens – its facts, expenses and Fully Funded Balance (spec 7.1). */
export const PROJECT_INPUTS: { path: string; label: string }[] = [
  { path: "facts", label: "Facts and assumptions" },
  { path: "expenses", label: "Expenses" },
  { path: "ffb", label: "Fully Funded Balance" },
];

/** The project with new facts – its expenses marked edited when they changed since a set was
 * loaded, and every scenario's typed dues stretched to a new horizon. */
export function withProjectFacts(project: Project, facts: Facts): Project {
  const changed = !sameExpenses(project.facts, facts);
  const horizon =
    facts.start_year !== project.facts.start_year || facts.end_year !== project.facts.end_year;
  return {
    ...project,
    facts,
    expenses_edited: project.expenses_edited || (changed && project.expenses_from !== null),
    scenarios: horizon
      ? project.scenarios.map((s) =>
          s.adoption ? s : duesWithHorizon(s, facts.start_year, facts.end_year),
        )
      : project.scenarios,
  };
}

/** The layout of the project's facts screens – it stays mounted as they change, so one form
 * holds the facts across them, and every edit saves itself. */
export function ProjectInputsLayout() {
  const { stored, error } = useProject();
  if (!stored) return <Loading error={error} />;
  return <ProjectInputsForm stored={stored} />;
}

function ProjectInputsForm({ stored }: { stored: StoredProject }) {
  const { id, save } = useProject();
  const { pathname } = useLocation();
  const [facts, setFacts] = useState<Facts>(stored.project.facts);
  const [results, setResults] = useState<ProjectRun | null>(null);
  const { invalid, Provider } = useInvalidFields();
  const blocked = invalid.length > 0;
  const autosave = useAutosave(facts, stored.project.facts, !blocked, async (f) => {
    await save((project) => withProjectFacts(project, f));
  });
  const { blocker } = useUnsavedGuard(blocked || autosave.status.state === "failed");

  // every scenario's key results as the facts change (spec 7.1) – debounced
  const settled = useDebounced(facts, 250);
  const project = stored.project;
  useEffect(() => {
    const controller = new AbortController();
    api.runProject({ ...project, facts: settled }, controller.signal).then(
      (r) => !controller.signal.aborted && setResults(r),
      () => !controller.signal.aborted && setResults(null),
    );
    return () => controller.abort();
  }, [settled, project]);

  const screen = matchPath("/projects/:id/:screen", pathname)?.params.screen;
  const here = PROJECT_INPUTS.find((s) => s.path === screen)?.label ?? "Facts and assumptions";
  const taken = project.scenarios.flatMap((s) => s.facts?.expense_lines.map((l) => l.id) ?? []);
  // the project's own worked-out figures – never an adopted plan's, on its own facts
  const ffb = results && Object.keys(results.ffb).length > 0 ? results.ffb : null;
  return (
    <FactsContext.Provider
      value={{
        facts,
        setFacts,
        readOnly: false,
        ffb,
        aside: <AllResults id={id} project={project} results={results} />,
        takenIds: taken,
        setsPanel: (
          <ExpenseSets
            project={project}
            facts={facts}
            blocked={blocked}
            flush={autosave.flushNow}
            onLoaded={setFacts}
          />
        ),
      }}
    >
      <ProjectNav stored={stored} here={here} />
      <div className="scenario-head">
        <h1>{here}</h1>
        <SaveNote status={blocked ? { state: "waiting" } : autosave.status} />
      </div>
      {invalid.length > 0 && (
        <Problems title="These entries are not usable numbers or years yet" items={invalid} />
      )}
      {results && results.problems.length > 0 && (
        <Problems title="Fix these to see results" items={results.problems} />
      )}
      <Provider>
        <Outlet />
      </Provider>
      <Confirm
        open={blocker.state === "blocked"}
        title="Leave this screen?"
        confirmLabel="Leave"
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      >
        <p>
          {invalid.length > 0
            ? `${invalid.join(", ")} ${invalid.length === 1 ? "is" : "are"} not a usable number or year, so ${invalid.length === 1 ? "it is" : "they are"} not saved and will be lost.`
            : "The last edit could not be saved – it will be lost."}
        </p>
      </Confirm>
    </FactsContext.Provider>
  );
}

/** Every scenario's key results beside the project's inputs, so a change shows across every
 * funding plan at once – adopted plans apart, unchanged (spec 7.1). */
function AllResults({
  id,
  project,
  results,
}: {
  id: string;
  project: Project;
  results: ProjectResults | null;
}) {
  const open = project.scenarios.filter((s) => !s.adoption);
  const adopted = project.scenarios.filter((s) => s.adoption);
  return (
    <aside className="key-results" aria-label="Key results" aria-live="polite">
      <table className="all-results">
        <caption className="visually-hidden">Each scenario's key results</caption>
        <thead>
          <tr>
            <th scope="col">Scenario</th>
            <th scope="col" className="num">
              Lowest balance
            </th>
            <th scope="col" className="num">
              Funded at end
            </th>
            <th scope="col" className="num">
              Years below cushion
            </th>
          </tr>
        </thead>
        <tbody>
          {open.map((s) => {
            const outcome = results?.scenarios[s.name];
            const r = outcome && "result" in outcome ? outcome.result.summary : null;
            return (
              <tr key={s.name}>
                <th scope="row">
                  <Link to={scenarioPath(id, s.name)}>{s.name}</Link>
                </th>
                {outcome && "problems" in outcome ? (
                  <td colSpan={3} className="warning">
                    Has problems
                  </td>
                ) : (
                  <>
                    <td className={`num${r?.lowest_balance.startsWith("-") ? " negative" : ""}`}>
                      {r ? `${money(r.lowest_balance)} (${r.lowest_balance_year})` : "…"}
                    </td>
                    <td className="num">{r ? percent(r.pf_end) : "…"}</td>
                    <td className="num">{r?.low_years ?? "…"}</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {adopted.length > 0 && (
        <p className="hint">
          Adopted plans keep the facts they were adopted with, so these figures do not change them –{" "}
          {adopted.map((s) => s.name).join(", ")}.
        </p>
      )}
    </aside>
  );
}

/** The expense sets (spec 4.3) – where the expenses came from, saving them as a set, saving
 * changes back, loading another, renaming and deleting. */
function ExpenseSets({
  project,
  facts,
  blocked,
  flush,
  onLoaded,
}: {
  project: Project;
  facts: Facts;
  blocked: boolean;
  flush: () => Promise<boolean>;
  /** the form takes the facts a loaded set gave the project */
  onLoaded: (facts: Facts) => void;
}) {
  const { save } = useProject();
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState<string | null>(null); // a new set's name being typed
  const [loading, setLoading] = useState<ExpenseSet | null>(null);
  const [renaming, setRenaming] = useState<{ from: string; to: string } | null>(null);
  const [switchRate, setSwitchRate] = useState(true);
  const [keepChoice, setKeepChoice] = useState<"save" | "new" | "discard">("save");
  const [saveFirst, setSaveFirst] = useState(true); // expenses from no set – keep them as one?
  const [deleting, setDeleting] = useState<string | null>(null);
  const sets = project.expense_sets;
  const from = project.expenses_from;
  const names = sets.map((s) => s.name);
  const nameProblem = (name: string, except?: string) =>
    !name.trim()
      ? "A set needs a name."
      : name.trim().length > 100
        ? "A set's name may be at most 100 characters."
        : names.some((n) => n === name.trim() && n !== except)
          ? `There is already a set called “${name.trim()}”.`
          : null;

  async function act(change: (p: Project) => Project): Promise<StoredProject | null> {
    setError(null);
    try {
      if (!(await flush())) throw new Error("the last edit is not saved yet – fix it first");
      return await save(change);
    } catch (e) {
      setError(e);
      return null;
    }
  }

  const saveAs = (name: string) =>
    act((p) => ({
      ...p,
      expense_sets: [...p.expense_sets, expensesOf(p.facts, name.trim())],
      expenses_from: name.trim(),
      expenses_edited: false,
    }));
  const saveChanges = () =>
    act((p) => ({
      ...p,
      expense_sets: p.expense_sets.map((s) => (s.name === from ? expensesOf(p.facts, s.name) : s)),
      expenses_edited: false,
    }));
  function load(set: ExpenseSet, keepCurrent: "save" | "new" | "discard", newName: string) {
    void act((p) => {
      let expense_sets = p.expense_sets;
      if (keepCurrent === "save" && p.expenses_from)
        expense_sets = expense_sets.map((s) =>
          s.name === p.expenses_from ? expensesOf(p.facts, s.name) : s,
        );
      if (keepCurrent === "new") expense_sets = [...expense_sets, expensesOf(p.facts, newName)];
      let facts = withExpenses(p.facts, set);
      if (switchRate && set.saved_inflation !== null)
        facts = { ...facts, expense_inflation: set.saved_inflation };
      return {
        ...withProjectFacts(p, facts),
        expense_sets,
        expenses_from: set.name,
        expenses_edited: false,
      };
    }).then((done) => done && onLoaded(done.project.facts));
    setLoading(null);
  }

  const saved =
    from !== null &&
    sameExpenses(
      facts,
      withExpenses(facts, sets.find((s) => s.name === from) ?? expensesOf(facts, "")),
    );
  const keep = from === null ? "new" : project.expenses_edited || !saved ? "ask" : "none";
  const suggested = uniqueName(`Expenses of ${new Date().toISOString().slice(0, 10)}`, names);
  const [keepAs, setKeepAs] = useState(suggested);
  const rateDiffers =
    loading?.saved_inflation != null &&
    num(loading.saved_inflation) !== num(facts.expense_inflation); // 0.03 is 0.030
  return (
    <section className="panel expense-sets" aria-label="Expense sets">
      <h2>Expense set</h2>
      <p>
        {from === null
          ? "These expenses are not saved as a set."
          : `From the set “${from}”${project.expenses_edited || !saved ? " – edited since it was loaded" : ""}.`}
      </p>
      <ErrorBanner error={error} />
      <div className="row-actions">
        <button type="button" disabled={blocked} onClick={() => setSaving(suggested)}>
          Save as a set…
        </button>
        {from !== null && (project.expenses_edited || !saved) && (
          <button type="button" disabled={blocked} onClick={() => void saveChanges()}>
            Save changes to “{from}”
          </button>
        )}
      </div>
      {sets.length > 0 && (
        <table className="list sets">
          <caption className="visually-hidden">Saved expense sets</caption>
          <thead>
            <tr>
              <th scope="col">Saved set</th>
              <th scope="col">Base year</th>
              <th scope="col">Lines</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sets.map((s) => (
              <tr key={s.name}>
                <th scope="row">
                  {s.name}
                  {s.name === from && <span className="hint"> – loaded</span>}
                </th>
                <td>{s.expense_base_year}</td>
                <td>{s.expense_lines.length}</td>
                <td className="row-buttons">
                  <button
                    type="button"
                    className="small"
                    disabled={blocked}
                    aria-label={`Load ${s.name}`}
                    onClick={() => {
                      setKeepAs(suggested);
                      setSwitchRate(true);
                      setLoading(s);
                    }}
                  >
                    Load…
                  </button>
                  <button
                    type="button"
                    className="small"
                    aria-label={`Rename ${s.name}`}
                    onClick={() => setRenaming({ from: s.name, to: s.name })}
                  >
                    Rename…
                  </button>
                  <button
                    type="button"
                    className="small"
                    aria-label={`Delete ${s.name}`}
                    onClick={() => setDeleting(s.name)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Confirm
        open={saving !== null}
        title="Save these expenses as a set"
        confirmLabel="Save"
        onCancel={() => setSaving(null)}
        onConfirm={() => {
          if (saving === null || nameProblem(saving)) return;
          void saveAs(saving);
          setSaving(null);
        }}
      >
        <Field label="Name of the set" error={saving === null ? null : nameProblem(saving)}>
          {(fid) => (
            <input id={fid} value={saving ?? ""} onChange={(e) => setSaving(e.target.value)} />
          )}
        </Field>
        <p className="hint">
          It keeps the expenses, the Fully Funded Balance and the expense base year, to load again
          later.
        </p>
      </Confirm>
      <Confirm
        open={loading !== null}
        title={`Load “${loading?.name ?? ""}”?`}
        confirmLabel="Load"
        onCancel={() => setLoading(null)}
        onConfirm={() => {
          if (!loading) return;
          const asNew = (keep === "new" && saveFirst) || (keep === "ask" && keepChoice === "new");
          if (asNew && nameProblem(keepAs)) return;
          load(loading, keep === "ask" ? keepChoice : asNew ? "new" : "discard", keepAs.trim());
        }}
      >
        <p>
          Its expenses, Fully Funded Balance and expense base year replace the project's – for every
          scenario but an adopted plan.
        </p>
        {keep === "new" && (
          <>
            <label className="check">
              <input
                type="checkbox"
                checked={saveFirst}
                onChange={(e) => setSaveFirst(e.target.checked)}
              />{" "}
              First save the current expenses as a set – they are not saved as one
            </label>
            {saveFirst && (
              <Field label="Name of the set" error={nameProblem(keepAs)}>
                {(fid) => (
                  <input id={fid} value={keepAs} onChange={(e) => setKeepAs(e.target.value)} />
                )}
              </Field>
            )}
          </>
        )}
        {keep === "ask" && (
          <KeepChoice
            from={from ?? ""}
            value={keepChoice}
            onChange={setKeepChoice}
            keepAs={keepAs}
            onKeepAs={setKeepAs}
            problem={nameProblem(keepAs)}
          />
        )}
        {rateDiffers && loading?.saved_inflation != null && (
          <label className="check">
            <input
              type="checkbox"
              checked={switchRate}
              onChange={(e) => setSwitchRate(e.target.checked)}
            />{" "}
            This set was saved with {percent(loading.saved_inflation)} reserve inflation – the
            project uses {percent(facts.expense_inflation)}. Switch the project's rate to{" "}
            {percent(loading.saved_inflation)}.
          </label>
        )}
      </Confirm>
      <Confirm
        open={deleting !== null}
        title={`Delete the set “${deleting ?? ""}”?`}
        confirmLabel="Delete"
        onCancel={() => setDeleting(null)}
        onConfirm={() => {
          const name = deleting;
          setDeleting(null);
          void act((p) => ({
            ...p,
            expense_sets: p.expense_sets.filter((x) => x.name !== name),
            expenses_from: p.expenses_from === name ? null : p.expenses_from,
            expenses_edited: p.expenses_from === name ? false : p.expenses_edited,
          }));
        }}
      >
        <p>
          The saved set is removed. The project's expenses stay as they are
          {deleting === from ? " – no longer from a saved set" : ""}.
        </p>
      </Confirm>
      <Confirm
        open={renaming !== null}
        title="Rename the set"
        confirmLabel="Rename"
        onCancel={() => setRenaming(null)}
        onConfirm={() => {
          if (!renaming || nameProblem(renaming.to, renaming.from)) return;
          const { from: old, to } = renaming;
          setRenaming(null);
          void act((p) => ({
            ...p,
            expense_sets: p.expense_sets.map((s) =>
              s.name === old ? { ...s, name: to.trim() } : s,
            ),
            expenses_from: p.expenses_from === old ? to.trim() : p.expenses_from,
          }));
        }}
      >
        <Field label="New name" error={renaming ? nameProblem(renaming.to, renaming.from) : null}>
          {(fid) => (
            <input
              id={fid}
              value={renaming?.to ?? ""}
              onChange={(e) => renaming && setRenaming({ ...renaming, to: e.target.value })}
            />
          )}
        </Field>
      </Confirm>
    </section>
  );
}

/** What to do with the current expenses, edited since their set was loaded, before loading
 * another (spec 4.3). */
function KeepChoice({
  from,
  value,
  onChange,
  keepAs,
  onKeepAs,
  problem,
}: {
  from: string;
  value: "save" | "new" | "discard";
  onChange: (v: "save" | "new" | "discard") => void;
  keepAs: string;
  onKeepAs: (name: string) => void;
  problem: string | null;
}) {
  return (
    <fieldset className="plain">
      <legend>The expenses have been edited since “{from}” was loaded</legend>
      {(
        [
          ["save", `Save the changes to “${from}”`],
          ["new", "Save them as a new set"],
          ["discard", "Discard them"],
        ] as const
      ).map(([key, label]) => (
        <label key={key} className="check">
          <input type="radio" name="keep" checked={value === key} onChange={() => onChange(key)} />{" "}
          {label}
        </label>
      ))}
      {value === "new" && (
        <Field label="Name of the new set" error={problem}>
          {(fid) => <input id={fid} value={keepAs} onChange={(e) => onKeepAs(e.target.value)} />}
        </Field>
      )}
    </fieldset>
  );
}
