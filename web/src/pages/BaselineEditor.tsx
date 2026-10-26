import { useEffect, useId, useMemo, useState } from "react";
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

interface Fact {
  key: keyof Baseline;
  label: string;
  hint: string; // what the figure means, in a board member's words
  example: string; // the kind of source note to write for it
  unit: "$" | "%" | "year" | "count";
  blank?: boolean; // may be left blank – no limit
}

// The baseline's figures, grouped by what they are about.
const FACTS: { title: string; facts: Fact[] }[] = [
  {
    title: "The reserve fund",
    facts: [
      {
        key: "starting_balance",
        label: "Starting reserve balance",
        hint: "The money in the reserve fund on January 1 of the start year – if that date is still ahead, the balance you expect on it",
        example: "e.g. Bank statement, December",
        unit: "$",
      },
      {
        key: "interest_rate",
        label: "Interest earned on reserves",
        hint: "What the reserve fund earns in a year, as a percentage of its balance",
        example: "e.g. Credit union savings rate",
        unit: "%",
      },
      {
        key: "cushion",
        label: "Minimum working cushion",
        hint: "The lowest year-end balance the board is comfortable with – any year below it is flagged LOW",
        example: "e.g. Board policy on reserves",
        unit: "$",
      },
      {
        key: "target",
        label: "Percent-funded target",
        hint: "The share of the reserve study's Fully Funded Balance the board aims to hold – drawn as the target line on charts",
        example: "e.g. Reserve study recommendation",
        unit: "%",
      },
    ],
  },
  {
    title: "Owners and dues",
    facts: [
      {
        key: "units",
        label: "Number of units",
        hint: "Dues and special assessments are per unit – every unit pays the same",
        example: "e.g. Condo declaration, Article 2",
        unit: "count",
      },
      {
        key: "current_dues",
        label: "Current dues per unit per month",
        hint: "What each unit pays today – the no-change figure every scenario's extra cost is measured against",
        example: "e.g. This year's budget",
        unit: "$",
      },
    ],
  },
  {
    title: "Inflation",
    facts: [
      {
        key: "operating_inflation",
        label: "Operating cost inflation",
        hint: "How fast running costs grow each year – used by monthly and yearly expenses that do not set a rate of their own",
        example: "e.g. Last three budgets, average increase",
        unit: "%",
      },
      {
        key: "expense_inflation",
        label: "Reserve expense inflation",
        hint: "How fast repair and replacement costs grow each year – used by once and every-few-years expenses",
        example: "e.g. Reserve study, inflation assumption",
        unit: "%",
      },
      {
        key: "expense_base_year",
        label: "Expense base year",
        hint: "The year whose prices the reserve expense amounts are in – usually the year of the reserve study",
        example: "e.g. Reserve study, its date",
        unit: "year",
      },
    ],
  },
  {
    title: "When owners must vote",
    facts: [
      {
        key: "max_dues_increase",
        label: "Largest dues increase without a vote",
        hint: "The biggest rise in dues from one year to the next the board may make on its own – leave blank for no limit",
        example: "e.g. Bylaws, section 6.3",
        unit: "%",
        blank: true,
      },
      {
        key: "max_assessment_share",
        label: "Largest assessment without a vote",
        hint: "The biggest special assessment the board may levy on its own, as a share of that year's operating costs plus reserve contribution – leave blank for no limit",
        example: "e.g. State condo act, assessment limit",
        unit: "%",
        blank: true,
      },
    ],
  },
];

/** One figure as a table row – its name and hint, its value, and where it came from. */
function FactRow({
  fact,
  baseline,
  onValue,
  onSource,
}: {
  fact: Fact;
  baseline: Baseline;
  onValue: (value: string | number | null) => void;
  onSource: (text: string) => void;
}) {
  const id = useId();
  const { key, label, hint, example, unit, blank } = fact;
  return (
    <tr>
      <th scope="row">
        <label htmlFor={id}>{label}</label>
        <small id={`${id}-hint`} className="hint">
          {hint}
        </small>
      </th>
      <td className="fact-value">
        <span className="with-unit">
          {/* the same slot on every row, so the boxes line up whether or not it holds a $ */}
          <span className="unit-prefix" aria-hidden="true">
            {unit === "$" ? "$" : ""}
          </span>
          {unit === "year" || unit === "count" ? (
            <YearInput
              id={id}
              name={label}
              describedBy={`${id}-hint`}
              value={baseline[key] as number}
              onChange={onValue}
            />
          ) : (
            <DecimalInput
              id={id}
              name={label}
              describedBy={`${id}-hint`}
              percent={unit === "%"}
              allowBlank={blank}
              value={baseline[key] as string | null}
              onChange={(v) => (v !== null || blank) && onValue(v)}
            />
          )}
        </span>
      </td>
      <td>
        <input
          aria-label={`Source – ${label.toLowerCase()}`}
          className="source"
          placeholder={example}
          value={baseline.sources[key] ?? ""}
          onChange={(e) => onSource(e.target.value)}
        />
      </td>
    </tr>
  );
}

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
    if (s.adoption) return s; // an adopted plan is read-only and keeps its own years
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
            Beside each figure, a source note says where it came from and when – a document, a page,
            a date – so anyone reading the plan later can check it. Notes are optional, and each
            travels into the exported workbook as a comment on that figure.
          </p>
          <table className="facts">
            <caption className="visually-hidden">Facts and assumptions</caption>
            <thead>
              <tr>
                <th scope="col">Figure</th>
                <th scope="col">Value</th>
                <th scope="col">Source note – where the figure came from</th>
              </tr>
            </thead>
            {FACTS.map((group) => (
              <tbody key={group.title}>
                <tr className="fact-group">
                  <th scope="rowgroup" colSpan={3}>
                    {group.title}
                  </th>
                </tr>
                {group.facts.map((fact) => (
                  <FactRow
                    key={fact.key}
                    fact={fact}
                    baseline={b}
                    onValue={(value) => set({ [fact.key]: value })}
                    onSource={(text) => setSource(fact.key, text)}
                  />
                ))}
              </tbody>
            ))}
          </table>
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
