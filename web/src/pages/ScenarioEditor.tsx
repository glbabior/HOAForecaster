import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { ApiError, api } from "../api";
import {
  BALANCE_LEGEND,
  BalanceChart,
  ChartFrame,
  OWNER_LEGEND,
  OwnerCostChart,
  balanceSummary,
} from "../components/charts";
import { BaselineChanges, changeCount } from "../components/changes";
import { DraftBanner, DraftStatus } from "../components/DraftBanner";
import { PlanTable } from "../components/PlanTable";
import { useRowIds } from "../components/tables";
import {
  Confirm,
  DecimalInput,
  ErrorBanner,
  Field,
  InvalidNotice,
  Problems,
  YearInput,
  useInvalidFields,
} from "../components/ui";
import { roundCents } from "../decimal";
import { dues as duesText, longDate, today } from "../format";
import { useDebounced, useDraftAutosave, useUnsavedGuard } from "../hooks";
import {
  applyChanges,
  baselineFor,
  blankScenario,
  currentAdoption,
  horizonOf,
  noChanges,
  plausibleHorizon,
  reshapeScenario,
  startFrom,
} from "../template";
import type { Assessment, Changes, Draft, Scenario, ScenarioResult, StoredProject } from "../types";

type Mode = "explicit" | "rate" | "pinned";

const modeOf = (s: Scenario): Mode =>
  s.dues.mode === "explicit"
    ? "explicit"
    : Object.keys(s.dues.overrides).length
      ? "pinned"
      : "rate";

/** A scenario from a draft saved before scenarios had changes of their own. */
const restored = (s: Scenario): Scenario => ({ ...s, changes: s.changes ?? noChanges() });

function uniqueName(base: string, taken: string[]): string {
  let name = base;
  for (let n = 2; taken.includes(name); n += 1) name = `${base} (${n})`;
  return name;
}

export function ScenarioEditor() {
  const { name: routeName } = useParams();
  const [query] = useSearchParams();
  const from = query.get("from");
  const { id, stored, error, setStored } = useProject();
  if (!stored) return <Loading error={error} />;
  const isNew = routeName === undefined;
  const existing = stored.project.scenarios.find((s) => s.name === routeName);
  if (!isNew && !existing) return <p>There is no scenario called “{routeName}” in this project.</p>;
  // a new scenario starts blank, or from the saved scenario named in ?from= (spec 7.2)
  const source = isNew ? stored.project.scenarios.find((s) => s.name === from) : undefined;
  const fresh = uniqueName(
    "New scenario",
    stored.project.scenarios.map((s) => s.name),
  );
  const original =
    existing ??
    (source
      ? startFrom(source, fresh, stored.project.baseline)
      : blankScenario(fresh, stored.project.baseline));
  // a fresh form for every saved revision, scenario and starting point – no copying state
  // about in effects
  return (
    <ScenarioForm
      key={`${stored.revision}:${routeName ?? ""}:${source?.name ?? ""}`}
      id={id}
      stored={stored}
      setStored={setStored}
      routeName={routeName}
      original={original}
      startedFrom={source?.name ?? null}
    />
  );
}

function ScenarioForm({
  id,
  stored,
  setStored,
  routeName,
  original,
  startedFrom,
}: {
  id: string;
  stored: StoredProject;
  setStored: (s: StoredProject) => void;
  routeName: string | undefined;
  original: Scenario;
  startedFrom: string | null;
}) {
  const navigate = useNavigate();
  const isNew = routeName === undefined;
  const screen = isNew ? "new-scenario" : `scenario:${routeName}`;
  const [form, setForm] = useState<Scenario>(original);
  const [mode, setMode] = useState<Mode>(modeOf(original));
  const [draft, setDraft] = useState<Draft | null>(null);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [adopting, setAdopting] = useState<{ date: string; note: string } | null>(null);
  const [confirmUnadopt, setConfirmUnadopt] = useState(false);
  const [replacing, setReplacing] = useState<string | null>(null); // a starting point to go to
  const { invalid, Provider } = useInvalidFields();
  const assessmentRows = useRowIds(form.assessments.length);

  useEffect(() => {
    api.getDrafts(id).then(
      (r) => setDraft(r.drafts[screen] ?? null),
      () => setDraft(null),
    );
  }, [id, screen]);

  const dirty = JSON.stringify(form) !== JSON.stringify(original);
  const { blocker, allowNextNavigation } = useUnsavedGuard(dirty);
  const status = useDraftAutosave(
    id,
    screen,
    stored.revision,
    dirty
      ? { kind: "scenario", original: isNew ? null : (routeName ?? null), scenario: form }
      : null,
  );

  // Live results as the inputs change (spec 7.2) – debounced, and a newer run cancels an older one.
  const settled = useDebounced(form, 250);
  useEffect(() => {
    const controller = new AbortController();
    api.run(stored.project.baseline, settled, controller.signal).then(
      (r) => {
        if (controller.signal.aborted) return;
        setResult(r);
        setProblems([]);
      },
      (e: unknown) => {
        if (controller.signal.aborted) return;
        setProblems(
          e instanceof ApiError ? (e.problems.length ? e.problems : [e.message]) : [String(e)],
        );
      },
    );
    return () => controller.abort();
  }, [settled, stored.project.baseline]);

  const b = baselineFor(stored.project.baseline, form); // as this scenario sees it
  const years = horizonOf(stored.project.baseline, form);
  const resolved = new Map(result?.years.map((y) => [y.year, y.dues]) ?? []);
  const others = stored.project.scenarios.filter((s) => s.name !== (isNew ? null : routeName));
  const name = form.name.trim();
  const duplicate = others.some((s) => s.name === name);

  function changeMode(next: Mode) {
    setMode(next);
    if (next === "explicit" && form.dues.mode !== "explicit") {
      // start from what the grown path produced, to the cent, so nothing jumps
      const fallback = form.dues.first_value;
      const explicit = Object.fromEntries(
        years.map((y) => [String(y), roundCents(resolved.get(y) ?? fallback)]),
      );
      setForm({ ...form, dues: { mode: "explicit", explicit } });
    } else if (next !== "explicit") {
      const base =
        form.dues.mode === "rate"
          ? form.dues
          : {
              mode: "rate" as const,
              first_value: form.dues.explicit[String(b.start_year)] ?? b.current_dues,
              annual_increase: "0.03",
              overrides: {},
            };
      setForm({ ...form, dues: { ...base, overrides: next === "rate" ? {} : base.overrides } });
    }
  }

  function setAssessments(assessments: Assessment[]) {
    setForm({ ...form, assessments });
  }

  /** New changes to the baseline – typed dues are stretched to the scenario's own horizon once
   * it is a usable one, as the baseline editor does for the baseline's. */
  function setChanges(changes: Changes) {
    const next = { ...form, changes };
    const { start_year: start, end_year: end } = applyChanges(stored.project.baseline, changes);
    setForm(plausibleHorizon(start, end) ? reshapeScenario(next, start, end) : next);
  }

  async function save(asCopy: boolean) {
    setSaveError(null);
    const current = { ...form, name };
    const taken = [...others.map((s) => s.name), ...(isNew ? [name] : [routeName ?? ""])];
    const copy = { ...current, name: uniqueName(`${name} – copy`, taken) };
    const list = stored.project.scenarios;
    let scenarios: Scenario[];
    if (isNew) scenarios = asCopy ? [...list, current, copy] : [...list, current];
    else if (asCopy)
      scenarios = [...list, copy]; // the open scenario stays as saved
    else scenarios = list.map((s) => (s.name === routeName ? current : s));
    try {
      const saved = await api.saveProject(id, { ...stored.project, scenarios }, stored.revision);
      void api.discardDraft(id, screen).catch(() => undefined);
      allowNextNavigation();
      const target = asCopy ? copy.name : current.name;
      navigate(`/projects/${id}/scenarios/${encodeURIComponent(target)}`, { replace: !asCopy });
      setStored(saved);
    } catch (e) {
      setSaveError(e);
    }
  }

  async function remove() {
    setConfirmDelete(false);
    try {
      const scenarios = stored.project.scenarios.filter((s) => s.name !== routeName);
      const saved = await api.saveProject(id, { ...stored.project, scenarios }, stored.revision);
      void api.discardDraft(id, screen).catch(() => undefined);
      allowNextNavigation();
      navigate(`/projects/${id}`);
      setStored(saved);
    } catch (e) {
      setSaveError(e);
    }
  }

  const cannotSave = !name || duplicate || invalid.length > 0;
  // an adopted plan is shown on the baseline it was frozen with, never today's
  const shownBaseline = original.adoption?.baseline ?? stored.project.baseline;
  const changes = changeCount(shownBaseline, form.changes);
  const adoption = original.adoption ?? null; // an adopted plan is read-only (spec 5.2)
  const current = currentAdoption(stored.project.scenarios);
  const isCurrent = current?.name === original.name;
  // the adopted plan first, then the rest in their order
  const startingPoints = [...stored.project.scenarios].sort(
    (a, b) => Number(b === current) - Number(a === current),
  );

  /** Start from another scenario – after asking, when there are edits to lose. */
  function chooseStart(name: string) {
    const to = `/projects/${id}/scenarios/new` + (name ? `?from=${encodeURIComponent(name)}` : "");
    if (dirty) setReplacing(to);
    else navigate(to, { replace: true });
  }

  async function adopt() {
    setAdopting(null);
    if (!adopting) return;
    try {
      const saved = await api.adopt(
        id,
        original.name,
        adopting.date,
        adopting.note,
        stored.revision,
      );
      void api.discardDraft(id, screen).catch(() => undefined); // it can no longer be edited
      setStored(saved);
    } catch (e) {
      setSaveError(e);
    }
  }

  async function unadopt() {
    setConfirmUnadopt(false);
    try {
      setStored(await api.unadopt(id, stored.revision));
    } catch (e) {
      setSaveError(e);
    }
  }

  return (
    <Provider>
      <ProjectNav stored={stored} here={isNew ? "New scenario" : original.name} />
      <h1>{isNew ? "New scenario" : original.name}</h1>
      {draft && draft.edits.kind === "scenario" && !original.adoption && (
        <DraftBanner
          draft={draft}
          revision={stored.revision}
          onRestore={() => {
            if (draft.edits.kind === "scenario") {
              setForm(restored(draft.edits.scenario));
              setMode(modeOf(restored(draft.edits.scenario)));
            }
            setDraft(null);
          }}
          onDiscard={() => {
            void api.discardDraft(id, screen).catch(() => undefined);
            setDraft(null);
          }}
        />
      )}
      <ErrorBanner error={saveError} />
      {adoption && (
        <section className="panel adopted" aria-label="Adopted plan">
          <p>
            <strong>{isCurrent ? "The adopted plan" : "An earlier adopted plan"}</strong> – adopted{" "}
            {longDate(adoption.date)}.{adoption.note && ` ${adoption.note}`}
          </p>
          <p className="hint">
            Its figures are frozen with the baseline it was adopted against, so later baseline edits
            do not change them. It is read-only – start a new scenario from it to revise it.
          </p>
          <div className="row-actions">
            <Link
              className="button"
              to={`/projects/${id}/scenarios/new?from=${encodeURIComponent(original.name)}`}
            >
              Start a new scenario from it
            </Link>
            {isCurrent && (
              <button type="button" onClick={() => setConfirmUnadopt(true)}>
                Un-adopt…
              </button>
            )}
          </div>
        </section>
      )}

      <div className="split">
        <form
          className="editor inputs"
          onSubmit={(e) => {
            e.preventDefault();
            if (!cannotSave && !adoption) void save(false);
          }}
        >
          {isNew && (
            <Field
              label="Start from"
              hint="Copies its dues, assessments, rounding, description and changes to the baseline – it then runs on today's baseline. Choosing replaces what is typed below."
            >
              {(fid, d) => (
                <select
                  id={fid}
                  aria-describedby={d}
                  value={startedFrom ?? ""}
                  onChange={(e) => chooseStart(e.target.value)}
                >
                  <option value="">A blank scenario</option>
                  {startingPoints.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name}
                      {s.adoption
                        ? s === current
                          ? " (the adopted plan)"
                          : " (an earlier adopted plan)"
                        : ""}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          )}
          <fieldset className="plain" disabled={adoption !== null}>
            <Field label="Name" error={duplicate ? "Another scenario already has this name" : null}>
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
            <Field label="Description">
              {(fid) => (
                <textarea
                  id={fid}
                  rows={2}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              )}
            </Field>

            <fieldset>
              <legend>Dues per unit per month</legend>
              <label>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === "rate"}
                  onChange={() => changeMode("rate")}
                />{" "}
                A first-year figure, then a yearly increase
              </label>
              <label>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === "pinned"}
                  onChange={() => changeMode("pinned")}
                />{" "}
                The same, with some years pinned to a figure
              </label>
              <label>
                <input
                  type="radio"
                  name="mode"
                  checked={mode === "explicit"}
                  onChange={() => changeMode("explicit")}
                />{" "}
                Typed for each year
              </label>

              {form.dues.mode === "rate" && (
                <div className="grid-2">
                  <Field label={`Dues in ${b.start_year}`}>
                    {(fid) => (
                      <DecimalInput
                        id={fid}
                        name={`Dues in ${b.start_year}`}
                        value={form.dues.mode === "rate" ? form.dues.first_value : null}
                        onChange={(v) =>
                          v !== null &&
                          form.dues.mode === "rate" &&
                          setForm({ ...form, dues: { ...form.dues, first_value: v } })
                        }
                      />
                    )}
                  </Field>
                  <Field label="Yearly increase">
                    {(fid) => (
                      <DecimalInput
                        id={fid}
                        name="Yearly increase"
                        percent
                        value={form.dues.mode === "rate" ? form.dues.annual_increase : null}
                        onChange={(v) =>
                          v !== null &&
                          form.dues.mode === "rate" &&
                          setForm({ ...form, dues: { ...form.dues, annual_increase: v } })
                        }
                      />
                    )}
                  </Field>
                </div>
              )}

              <table className="edit-table dues-table">
                <caption>
                  Dues each year
                  {mode === "pinned" ? " – pin a year to a figure; later years grow from it" : ""}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Year</th>
                    {mode !== "rate" && (
                      <th scope="col">{mode === "explicit" ? "Dues" : "Pinned"}</th>
                    )}
                    <th scope="col" className="num">
                      Resolved
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {years.map((y) => {
                    const key = String(y);
                    return (
                      <tr key={y}>
                        <th scope="row">{y}</th>
                        {form.dues.mode === "explicit" && (
                          <td>
                            <DecimalInput
                              label={`Dues in ${y}`}
                              name={`Dues in ${y}`}
                              value={form.dues.explicit[key] ?? null}
                              onChange={(v) =>
                                v !== null &&
                                form.dues.mode === "explicit" &&
                                setForm({
                                  ...form,
                                  dues: {
                                    mode: "explicit",
                                    explicit: { ...form.dues.explicit, [key]: v },
                                  },
                                })
                              }
                            />
                          </td>
                        )}
                        {form.dues.mode === "rate" && mode === "pinned" && (
                          <td>
                            <DecimalInput
                              label={`Pinned dues in ${y}`}
                              name={`Pinned dues in ${y}`}
                              allowBlank
                              value={form.dues.overrides[key] ?? null}
                              onChange={(v) => {
                                if (form.dues.mode !== "rate") return;
                                const overrides = Object.fromEntries(
                                  Object.entries(form.dues.overrides).filter(
                                    ([year]) => year !== key,
                                  ),
                                );
                                if (v !== null) overrides[key] = v;
                                setForm({ ...form, dues: { ...form.dues, overrides } });
                              }}
                            />
                          </td>
                        )}
                        <td className="num">{duesText(resolved.get(y))}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {form.dues.mode === "rate" && (
                <Field label="Rounding of grown dues">
                  {(fid) => (
                    <select
                      id={fid}
                      value={form.rounding}
                      onChange={(e) =>
                        setForm({ ...form, rounding: e.target.value as Scenario["rounding"] })
                      }
                    >
                      <option value="dollar">Whole dollars</option>
                      <option value="none">None – keep cents</option>
                    </select>
                  )}
                </Field>
              )}
            </fieldset>

            <fieldset>
              <legend>Special assessments</legend>
              <p className="hint">Per unit. Several installments are separate rows.</p>
              <table className="edit-table">
                <caption className="visually-hidden">Special assessments</caption>
                <thead>
                  <tr>
                    <th scope="col">Year</th>
                    <th scope="col">Per unit</th>
                    <th scope="col">Note</th>
                    <th scope="col">
                      <span className="visually-hidden">Remove</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {form.assessments.map((a, i) => (
                    <tr key={assessmentRows.ids[i]}>
                      <td>
                        <YearInput
                          label={`Year of assessment ${i + 1}`}
                          name={`Year of assessment ${i + 1}`}
                          value={a.year}
                          onChange={(year) =>
                            setAssessments(
                              form.assessments.map((x, j) => (j === i ? { ...x, year } : x)),
                            )
                          }
                        />
                      </td>
                      <td>
                        <DecimalInput
                          label={`Amount of assessment ${i + 1}`}
                          name={`Amount of assessment ${i + 1}`}
                          value={a.amount}
                          onChange={(v) =>
                            v !== null &&
                            setAssessments(
                              form.assessments.map((x, j) => (j === i ? { ...x, amount: v } : x)),
                            )
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Note for assessment ${i + 1}`}
                          value={a.note}
                          onChange={(e) =>
                            setAssessments(
                              form.assessments.map((x, j) =>
                                j === i ? { ...x, note: e.target.value } : x,
                              ),
                            )
                          }
                        />
                      </td>
                      <td>
                        <button
                          type="button"
                          className="small"
                          aria-label={`Remove assessment ${i + 1}`}
                          onClick={() => {
                            assessmentRows.removed(i);
                            setAssessments(form.assessments.filter((_, j) => j !== i));
                          }}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button
                type="button"
                onClick={() => {
                  assessmentRows.added();
                  setAssessments([
                    ...form.assessments,
                    { year: b.start_year, amount: "0", note: "" },
                  ]);
                }}
              >
                Add assessment
              </button>
            </fieldset>
          </fieldset>

          <div className="sticky-actions">
            {adoption ? (
              <>
                <button type="button" onClick={() => window.print()}>
                  Print
                </button>
                <button type="button" onClick={() => navigate(`/projects/${id}`)}>
                  Back to the project
                </button>
              </>
            ) : (
              <>
                <InvalidNotice fields={invalid} />
                <button
                  type="submit"
                  className="primary"
                  disabled={(!dirty && !isNew) || cannotSave}
                >
                  Save
                </button>
                <button type="button" disabled={cannotSave} onClick={() => void save(true)}>
                  Save as copy
                </button>
                {!isNew && (
                  <button type="button" onClick={() => setConfirmDelete(true)}>
                    Delete…
                  </button>
                )}
                <button
                  type="button"
                  disabled={isNew || dirty}
                  title={isNew || dirty ? "Save the scenario first" : undefined}
                  onClick={() => setAdopting({ date: today(), note: "" })}
                >
                  Adopt…
                </button>
                <button type="button" onClick={() => window.print()}>
                  Print
                </button>
                <button type="button" onClick={() => navigate(`/projects/${id}`)}>
                  Cancel
                </button>
                <DraftStatus status={status} />
              </>
            )}
          </div>
        </form>

        <section className="results" aria-live="polite" aria-label="Results">
          <Problems title="Fix these to see results" items={problems} />
          {result && problems.length === 0 && (
            <>
              <PlanTable
                result={result}
                caption={`${form.name} – year by year`}
                filename={`${form.name} - plan.csv`}
              />
              <ChartFrame
                title={`${form.name} – expenses, dues, reserve balance and percent funded`}
                summary={balanceSummary(result)}
                filename={`${form.name} - balance.png`}
                legend={BALANCE_LEGEND}
              >
                <BalanceChart result={result} />
              </ChartFrame>
              <ChartFrame
                title={`${form.name} – owner cost per unit and percent funded`}
                summary={`Owner cost per unit runs from ${duesText(result.years[0]?.owner_cost_year)} to ${duesText(result.years.at(-1)?.owner_cost_year)} a year.`}
                filename={`${form.name} - owner cost.png`}
                legend={OWNER_LEGEND}
              >
                <OwnerCostChart result={result} />
              </ChartFrame>
            </>
          )}
        </section>
      </div>

      {/* full width below the results – its tables are wider than the inputs column */}
      <section className="panel changes-panel">
        <fieldset disabled={adoption !== null}>
          <legend>
            Changes to the baseline
            {changes > 0 ? ` (${changes})` : ""}
          </legend>
          <BaselineChanges
            baseline={shownBaseline}
            frozen={adoption !== null}
            changes={form.changes}
            onChange={setChanges}
          />
        </fieldset>
      </section>

      <Confirm
        open={confirmDelete}
        title={`Delete ${original.name}?`}
        confirmLabel="Delete"
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => void remove()}
      >
        <p>The scenario is removed from the project when you confirm.</p>
      </Confirm>
      <Confirm
        open={adopting !== null}
        title={`Adopt ${original.name}?`}
        confirmLabel="Adopt"
        onCancel={() => setAdopting(null)}
        onConfirm={() => void adopt()}
      >
        <p>
          It becomes the adopted plan – read-only, with its figures frozen on today's baseline.
          {currentAdoption(stored.project.scenarios)
            ? ` ${currentAdoption(stored.project.scenarios)?.name} stays as an earlier adopted plan.`
            : ""}
        </p>
        <label className="field">
          <span>Adopted on</span>
          <input
            type="date"
            required
            value={adopting?.date ?? ""}
            onChange={(e) => adopting && setAdopting({ ...adopting, date: e.target.value })}
          />
        </label>
        <label className="field">
          <span>Note – the meeting and vote, for example</span>
          <textarea
            rows={2}
            value={adopting?.note ?? ""}
            onChange={(e) => adopting && setAdopting({ ...adopting, note: e.target.value })}
          />
        </label>
      </Confirm>
      <Confirm
        open={replacing !== null}
        title="Replace what you typed?"
        confirmLabel="Replace"
        onCancel={() => setReplacing(null)}
        onConfirm={() => {
          if (replacing) navigate(replacing, { replace: true });
          setReplacing(null);
        }}
      >
        <p>The new scenario starts again from your choice, and what you typed is lost.</p>
      </Confirm>
      <Confirm
        open={confirmUnadopt}
        title={`Un-adopt ${original.name}?`}
        confirmLabel="Un-adopt"
        onCancel={() => setConfirmUnadopt(false)}
        onConfirm={() => void unadopt()}
      >
        <p>
          It becomes an ordinary scenario again, running on today's baseline, and the plan adopted
          before it – if any – becomes the adopted plan. Use this only to correct a mistake.
        </p>
      </Confirm>
      <Confirm
        open={blocker.state === "blocked"}
        title="Leave without saving?"
        confirmLabel="Leave"
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      >
        <p>Your changes are kept as a draft and offered next time you open this scenario.</p>
      </Confirm>
    </Provider>
  );
}
