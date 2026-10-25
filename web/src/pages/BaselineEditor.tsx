import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Loading, ProjectNav, useProject } from "../App";
import { ApiError, api } from "../api";
import { DraftBanner, DraftStatus } from "../components/DraftBanner";
import { ExpenseTable, FfbTable } from "../components/tables";
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
import { useDebounced, useDraftAutosave, useUnsavedGuard } from "../hooks";
import { applyChanges, plausibleHorizon, reshapeHorizon, reshapeScenario } from "../template";
import type { Baseline, Draft, Scenario, StoredProject } from "../types";

interface Form {
  name: string;
  notes: string;
  baseline: Baseline;
}

type Impact = { changed: string[]; unchanged: string[]; invalid: string[] };

const SCREEN = "baseline";

const SCALARS: {
  key: keyof Baseline;
  label: string;
  hint?: string;
  percent?: boolean;
  blank?: boolean;
  whole?: boolean;
}[] = [
  {
    key: "starting_balance",
    label: "Starting reserve balance",
    hint: "On January 1 of the start year",
  },
  { key: "units", label: "Number of units", whole: true },
  {
    key: "current_dues",
    label: "Current dues per unit per month",
    hint: "The no-change reference for extra cost",
  },
  {
    key: "operating_inflation",
    label: "Operating cost inflation",
    percent: true,
    hint: "For monthly and yearly expenses without a rate of their own",
  },
  { key: "expense_inflation", label: "Reserve expense inflation", percent: true },
  {
    key: "expense_base_year",
    label: "Expense base year",
    hint: "The year whose dollars the expense amounts are in – usually the reserve study's",
    whole: true,
  },
  { key: "interest_rate", label: "Interest earned on reserves", percent: true },
  {
    key: "cushion",
    label: "Minimum working cushion",
    hint: "A year-end balance below this is flagged LOW",
  },
  { key: "target", label: "Percent-funded target", percent: true },
  {
    key: "max_dues_increase",
    label: "Largest dues increase without an owner vote",
    percent: true,
    blank: true,
    hint: "Leave blank for no limit",
  },
  {
    key: "max_assessment_share",
    label: "Largest assessment without a vote, share of the budget",
    percent: true,
    blank: true,
    hint: "Leave blank for no limit",
  },
];

export function BaselineEditor() {
  const { id, stored, error, setStored } = useProject();
  if (!stored) return <Loading error={error} />;
  // a fresh form for every saved revision – no copying state about in effects
  return <BaselineForm key={stored.revision} id={id} stored={stored} setStored={setStored} />;
}

/** The scenarios as a save with this baseline stores them – typed dues stretched to cover each
 * one's horizon (its own, where it has one). */
function scenariosFor(stored: StoredProject, baseline: Baseline): Scenario[] {
  return stored.project.scenarios.map((s) => {
    const own = applyChanges(baseline, s.changes);
    return plausibleHorizon(own.start_year, own.end_year)
      ? reshapeScenario(s, own.start_year, own.end_year)
      : s;
  });
}

function problemsOf(e: unknown): string[] {
  return e instanceof ApiError ? (e.problems.length ? e.problems : [e.message]) : [String(e)];
}

function BaselineForm({
  id,
  stored,
  setStored,
}: {
  id: string;
  stored: StoredProject;
  setStored: (s: StoredProject) => void;
}) {
  const navigate = useNavigate();
  const original = useMemo<Form>(
    () => ({
      name: stored.project.name,
      notes: stored.project.notes,
      baseline: stored.project.baseline,
    }),
    [stored],
  );
  const [form, setForm] = useState<Form>(original);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [confirming, setConfirming] = useState<Impact | null>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const { invalid, Provider } = useInvalidFields();

  useEffect(() => {
    api.getDrafts(id).then(
      (r) => setDraft(r.drafts[SCREEN] ?? null),
      () => setDraft(null),
    );
  }, [id]);

  const dirty = JSON.stringify(form) !== JSON.stringify(original);
  const { blocker, allowNextNavigation } = useUnsavedGuard(dirty);
  const status = useDraftAutosave(
    id,
    SCREEN,
    stored.revision,
    dirty ? { kind: "baseline", ...form } : null,
  );

  // Live checks as you type – problems, and which saved scenarios this baseline would change.
  const settled = useDebounced(form.baseline, 400);
  useEffect(() => {
    const controller = new AbortController();
    api.baselineImpact(id, settled, scenariosFor(stored, settled), controller.signal).then(
      (r) => {
        if (controller.signal.aborted) return;
        setProblems([]);
        setImpact(r);
      },
      (e: unknown) => {
        if (controller.signal.aborted) return;
        setImpact(null);
        setProblems(problemsOf(e));
      },
    );
    return () => controller.abort();
  }, [id, settled, stored]);

  const b = form.baseline;
  const set = (change: Partial<Baseline>) => setForm({ ...form, baseline: { ...b, ...change } });
  const setSource = (key: string, text: string) => set({ sources: { ...b.sources, [key]: text } });
  const horizonChanged =
    b.start_year !== stored.project.baseline.start_year ||
    b.end_year !== stored.project.baseline.end_year;

  function setHorizon(start: number, end: number) {
    // reshape only a horizon that makes sense – a year half typed must not wipe the tables
    setForm({
      ...form,
      baseline: plausibleHorizon(start, end)
        ? reshapeHorizon(b, start, end)
        : { ...b, start_year: start, end_year: end },
    });
  }

  async function review() {
    // judge exactly what will be saved – not the last debounced check
    setSaveError(null);
    try {
      setConfirming(
        await api.baselineImpact(id, form.baseline, scenariosFor(stored, form.baseline)),
      );
    } catch (e) {
      setProblems(problemsOf(e));
    }
  }

  async function save() {
    setConfirming(null);
    try {
      const saved = await api.saveProject(
        id,
        {
          ...stored.project,
          name: form.name.trim(),
          notes: form.notes,
          baseline: form.baseline,
          scenarios: scenariosFor(stored, form.baseline),
        },
        stored.revision,
      );
      void api.discardDraft(id, SCREEN).catch(() => undefined);
      allowNextNavigation();
      navigate(`/projects/${id}`);
      setStored(saved);
    } catch (e) {
      setSaveError(e);
    }
  }

  const cannotSave = !dirty || problems.length > 0 || invalid.length > 0 || !form.name.trim();

  return (
    <Provider>
      <ProjectNav stored={stored} here="Baseline" />
      <h1>Baseline</h1>
      {draft && (
        <DraftBanner
          draft={draft}
          revision={stored.revision}
          onRestore={() => {
            if (draft.edits.kind === "baseline") {
              const { name, notes, baseline } = draft.edits;
              setForm({ name, notes, baseline });
            }
            setDraft(null);
          }}
          onDiscard={() => {
            void api.discardDraft(id, SCREEN).catch(() => undefined);
            setDraft(null);
          }}
        />
      )}
      <ErrorBanner error={saveError} />

      <form
        className="editor"
        onSubmit={(e) => {
          e.preventDefault();
          if (!cannotSave) void review();
        }}
      >
        <section className="panel">
          <h2>Project</h2>
          <Field label="Name">
            {(fid) => (
              <input
                id={fid}
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
                rows={3}
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            )}
          </Field>
        </section>

        <section className="panel">
          <h2>Horizon</h2>
          <div className="grid-2">
            <Field
              label="Start year"
              hint="January 1 of this year. If it is mid-year, start next year with the expected January 1 balance."
            >
              {(fid, d) => (
                <YearInput
                  id={fid}
                  name="Start year"
                  describedBy={d}
                  value={b.start_year}
                  onChange={(y) => setHorizon(y, b.end_year)}
                />
              )}
            </Field>
            <Field label="End year" hint="5 to 30 full years">
              {(fid, d) => (
                <YearInput
                  id={fid}
                  name="End year"
                  describedBy={d}
                  value={b.end_year}
                  onChange={(y) => setHorizon(b.start_year, y)}
                />
              )}
            </Field>
          </div>
        </section>

        <section className="panel">
          <h2>Facts and assumptions</h2>
          <p className="hint">
            Each figure has a source note – where it came from and when. It travels into the
            exported workbook as a cell comment.
          </p>
          <div className="grid-2">
            {SCALARS.map(({ key, label, hint, percent, blank, whole }) => (
              <div key={key} className="fact">
                <Field label={label} hint={hint}>
                  {(fid, d) =>
                    whole ? (
                      <YearInput
                        id={fid}
                        name={label}
                        describedBy={d}
                        value={b[key] as number}
                        onChange={(n) => set({ [key]: n })}
                      />
                    ) : (
                      <DecimalInput
                        id={fid}
                        name={label}
                        describedBy={d}
                        percent={percent}
                        allowBlank={blank}
                        value={b[key] as string | null}
                        onChange={(v) => (v !== null || blank) && set({ [key]: v })}
                      />
                    )
                  }
                </Field>
                <Field label={`Source – ${label.toLowerCase()}`}>
                  {(fid) => (
                    <input
                      id={fid}
                      className="source"
                      value={b.sources[key] ?? ""}
                      onChange={(e) => setSource(key, e.target.value)}
                    />
                  )}
                </Field>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>Expenses</h2>
          <ExpenseTable
            lines={b.expense_lines}
            defaultYear={b.start_year}
            reserved={stored.project.scenarios.flatMap((s) => Object.keys(s.changes.expense_lines))}
            onChange={(expense_lines) => set({ expense_lines })}
          />
        </section>

        <section className="panel">
          <h2>Fully Funded Balance by year</h2>
          {plausibleHorizon(b.start_year, b.end_year) ? (
            <FfbTable
              years={Array.from(
                { length: b.end_year - b.start_year + 2 },
                (_, i) => b.start_year + i,
              )}
              values={b.ffb}
              onChange={(ffb) => set({ ffb })}
            />
          ) : (
            <p className="hint">Set a horizon of 5 to 30 years to see this table.</p>
          )}
          <Field label="Source – Fully Funded Balance">
            {(fid) => (
              <input
                id={fid}
                className="source"
                value={b.sources.ffb ?? ""}
                onChange={(e) => setSource("ffb", e.target.value)}
              />
            )}
          </Field>
        </section>

        <div className="sticky-actions">
          <InvalidNotice fields={invalid} />
          <Problems title="Fix these before saving" items={problems} />
          {problems.length === 0 && impact && dirty && (
            <p className="hint">
              {impact.changed.length === 0
                ? "No saved scenario's figures change."
                : `Saving changes the figures of ${impact.changed.join(", ")}.`}
            </p>
          )}
          <button type="submit" className="primary" disabled={cannotSave}>
            Save baseline
          </button>
          <button type="button" onClick={() => navigate(`/projects/${id}`)}>
            Cancel
          </button>
          <DraftStatus status={status} />
        </div>
      </form>

      <Confirm
        open={confirming !== null}
        title="Save the baseline?"
        confirmLabel="Save"
        onCancel={() => setConfirming(null)}
        onConfirm={() => void save()}
      >
        {confirming && confirming.changed.length > 0 ? (
          <>
            <p>These saved scenarios will show different figures –</p>
            <ul>
              {confirming.changed.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </>
        ) : (
          <p>No saved scenario's figures change.</p>
        )}
        {confirming && confirming.invalid.length > 0 && (
          <p className="warning">
            {confirming.invalid.join(", ")} will have problems with this baseline – open{" "}
            {confirming.invalid.length === 1 ? "it" : "them"} after saving to fix them.
          </p>
        )}
        {horizonChanged && (
          <p>
            Scenarios with dues typed for each year are extended to the new horizon with their
            nearest figure.
          </p>
        )}
      </Confirm>

      <Confirm
        open={blocker.state === "blocked"}
        title="Leave without saving?"
        confirmLabel="Leave"
        onCancel={() => blocker.reset?.()}
        onConfirm={() => blocker.proceed?.()}
      >
        <p>Your changes are kept as a draft and offered next time you open the baseline.</p>
      </Confirm>
    </Provider>
  );
}
