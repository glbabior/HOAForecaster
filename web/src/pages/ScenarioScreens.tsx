import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { Link, Outlet, matchPath, useLocation, useNavigate, useParams } from "react-router-dom";

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
import { CopyDialog } from "../components/CopyDialog";
import { PlanTable } from "../components/PlanTable";
import { numberOf, useSort } from "../components/sort";
import { ExpenseTable, FfbTable, useRowIds } from "../components/tables";
import {
  Confirm,
  DecimalInput,
  ErrorBanner,
  Field,
  OptionalYearInput,
  Problems,
  YearInput,
  useInvalidFields,
} from "../components/ui";
import { roundCents } from "../decimal";
import { dues as duesText, longDate, money, percent, today } from "../format";
import { useAutosave, useDebounced, useUnsavedGuard, type SaveStatus } from "../hooks";
import {
  copyFact,
  copyFfb,
  copyLine,
  currentAdoption,
  horizonOf,
  plausibleHorizon,
  withHorizon,
  type FactKey,
} from "../template";
import type {
  Assessment,
  Facts,
  Increase,
  Scenario,
  ScenarioResult,
  StoredProject,
} from "../types";

// ---------------------------------------------------------------- the screens of a scenario

/** A scenario's screens, by the last part of their address (spec 7.2). */
export const SCENARIO_SCREENS: { path: string; label: string }[] = [
  { path: "", label: "Results" },
  { path: "facts", label: "Facts and assumptions" },
  { path: "expenses", label: "Expenses" },
  { path: "ffb", label: "Fully Funded Balance" },
  { path: "dues", label: "Dues" },
  { path: "assessments", label: "Special assessments" },
];

/** The screen part of a scenario address – "" for Results. */
function screenOf(pathname: string): string {
  return matchPath("/projects/:id/scenarios/:name/:screen", pathname)?.params.screen ?? "";
}

export const scenarioPath = (id: string, name: string, screen = ""): string =>
  `/projects/${encodeURIComponent(id)}/scenarios/${encodeURIComponent(name)}` +
  (screen ? `/${screen}` : "");

interface ScenarioScreen {
  id: string;
  stored: StoredProject;
  form: Scenario;
  setForm: (s: Scenario) => void;
  readOnly: boolean;
  result: ScenarioResult | null;
  problems: string[];
  /** the other scenarios of the project, as saved */
  others: Scenario[];
  /** copy something of this scenario into the scenarios named – `apply` makes each copy */
  copyTo: (names: string[], apply: (target: Scenario) => Scenario) => Promise<void>;
  /** an entry is not yet usable – nothing is copied while the screen shows other figures */
  blocked: boolean;
}

const ScenarioContext = createContext<ScenarioScreen | null>(null);

function useScenario(): ScenarioScreen {
  const screen = useContext(ScenarioContext);
  if (!screen) throw new Error("a scenario screen outside its scenario");
  return screen;
}

/** The layout of a scenario's screens – it stays mounted as they change, so one form holds the
 * scenario's edits across them, and every edit saves itself. */
export function ScenarioLayout() {
  const { name = "" } = useParams();
  const { stored, error } = useProject();
  // a rename moves the address – the same scenario, so the same form
  const [renamed, setRenamed] = useState<string | null>(null);
  const [seen, setSeen] = useState({ name, key: name });
  if (seen.name !== name) {
    setSeen({ name, key: renamed === name ? seen.key : name });
    setRenamed(null);
  }
  if (!stored) return <Loading error={error} />;
  const scenario = stored.project.scenarios.find((s) => s.name === name || s.name === renamed);
  if (!scenario) return <p>There is no scenario called “{name}” in this project.</p>;
  // adopting or un-adopting starts a fresh form – read-only, or editable again
  return (
    <ScenarioForm
      key={`${seen.key}:${scenario.adoption?.sequence ?? "open"}`}
      stored={stored}
      original={scenario}
      onRenamed={setRenamed}
    />
  );
}

function problemsOf(e: unknown): string[] {
  return e instanceof ApiError ? (e.problems.length ? e.problems : [e.message]) : [String(e)];
}

function ScenarioForm({
  stored,
  original,
  onRenamed,
}: {
  stored: StoredProject;
  original: Scenario;
  onRenamed: (name: string) => void;
}) {
  const { id, save: saveProject, act } = useProject();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [form, setForm] = useState<Scenario>(original);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [adopting, setAdopting] = useState<{ date: string; note: string } | null>(null);
  const [confirmUnadopt, setConfirmUnadopt] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null); // the new name being typed
  const { invalid, Provider } = useInvalidFields();
  // the name it is saved under – in state for the screen, in a ref for saves in flight
  const [savedName, setSavedName] = useState(original.name);
  const savedNameRef = useRef(original.name);
  const mounted = useRef(true);
  const deleted = useRef(false); // a last pending edit must not bring it back
  const screen = useRef(screenOf(pathname));
  useEffect(() => {
    screen.current = screenOf(pathname);
  }, [pathname]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; // before the autosave's last save, so it never navigates
    };
  }, []);

  const adoption = original.adoption ?? null;
  const readOnly = adoption !== null; // an adopted plan is read-only (spec 5.2)
  const others = stored.project.scenarios.filter((s) => s.name !== savedName);
  const name = form.name.trim();
  const nameProblem = !name
    ? "The scenario needs a name – on Facts and assumptions."
    : others.some((s) => s.name === name)
      ? `Another scenario is already called “${name}” – choose another name on Facts and assumptions.`
      : null;

  const renameProblem =
    renaming === null
      ? null
      : !renaming.trim()
        ? "A scenario needs a name."
        : others.some((s) => s.name === renaming.trim())
          ? `Another scenario is already called “${renaming.trim()}”.`
          : null;
  const renameHint = useId();

  function rename() {
    // the form takes the new name; it saves itself and the address follows
    if (renaming === null || renameProblem) return;
    setForm({ ...form, name: renaming.trim() });
    setRenaming(null);
  }

  /** Save the project's scenarios as `build` makes them from the latest saved ones. */
  async function saveScenarios(build: (scenarios: Scenario[]) => Scenario[]): Promise<void> {
    await saveProject((project) => ({ ...project, scenarios: build(project.scenarios) }));
  }

  async function save(s: Scenario) {
    if (deleted.current) return;
    const current = { ...s, name: s.name.trim() };
    const was = savedNameRef.current;
    await saveScenarios((list) => {
      if (!list.some((x) => x.name === was))
        throw new Error("this scenario is no longer in the project – it was deleted elsewhere");
      return list.map((x) => (x.name === was ? current : x));
    });
    if (current.name !== was) {
      savedNameRef.current = current.name;
      setSavedName(current.name);
      if (mounted.current) {
        onRenamed(current.name);
        navigate(scenarioPath(id, current.name, screen.current), { replace: true });
      }
    }
  }

  const blocked = invalid.length > 0 || nameProblem !== null;
  const autosave = useAutosave(form, original, !readOnly && !blocked, save);
  const { status } = autosave;
  // an entry that is not yet usable is lost on leaving its screen, and an edit whose save
  // failed would be – ask first
  const { blocker } = useUnsavedGuard(blocked || status.state === "failed");

  // Live results as the inputs change (spec 7.2) – debounced, and a newer run cancels an older one.
  const settled = useDebounced(form, 250);
  useEffect(() => {
    const controller = new AbortController();
    api.run(settled, controller.signal).then(
      (r) => {
        if (controller.signal.aborted) return;
        setResult(r);
        setProblems([]);
      },
      (e: unknown) => {
        if (controller.signal.aborted) return;
        setProblems(problemsOf(e));
      },
    );
    return () => controller.abort();
  }, [settled]);

  async function copyTo(names: string[], apply: (target: Scenario) => Scenario) {
    setActionError(null);
    try {
      await saveScenarios((list) => list.map((x) => (names.includes(x.name) ? apply(x) : x)));
    } catch (e) {
      setActionError(e);
    }
  }

  async function remove() {
    setConfirmDelete(false);
    deleted.current = true;
    try {
      await saveScenarios((list) => list.filter((s) => s.name !== savedNameRef.current));
      navigate(`/projects/${id}/scenarios`);
    } catch (e) {
      deleted.current = false;
      setActionError(e);
    }
  }

  async function adopt() {
    setAdopting(null);
    if (!adopting) return;
    setActionError(null);
    try {
      // the plan adopted is the one on screen – its last edit saved first
      if (!(await autosave.flushNow())) {
        setActionError(new Error("the last edit is not saved yet – fix it, then adopt"));
        return;
      }
      const { date, note } = adopting;
      await act((current) => api.adopt(id, savedNameRef.current, date, note, current.revision));
    } catch (e) {
      setActionError(e);
    }
  }

  async function unadopt() {
    setConfirmUnadopt(false);
    try {
      await act((current) => api.unadopt(id, current.revision));
    } catch (e) {
      setActionError(e);
    }
  }

  const current = currentAdoption(stored.project.scenarios);
  const isCurrent = current?.name === original.name;
  const title = form.name.trim() || original.name;
  const here = SCENARIO_SCREENS.find((s) => s.path === screenOf(pathname))?.label;

  return (
    <ScenarioContext.Provider
      value={{ id, stored, form, setForm, readOnly, result, problems, others, copyTo, blocked }}
    >
      <ProjectNav stored={stored} within={{ path: "scenarios", label: "Scenarios" }} here={title} />
      <div className="scenario-head">
        <h1>
          {title}
          {here && here !== "Results" && <span className="screen-title"> – {here}</span>}
        </h1>
        {!readOnly && <SaveNote status={blocked ? { state: "waiting" } : status} />}
      </div>
      <div className="row-actions no-print">
        <Link
          className="button"
          to={`/projects/${id}/scenarios/new?from=${encodeURIComponent(savedName)}`}
        >
          Copy as a new scenario
        </Link>
        {!readOnly && (
          <>
            <button
              type="button"
              disabled={blocked}
              title={blocked ? "Fix the entries below first" : undefined}
              onClick={() => setAdopting({ date: today(), note: "" })}
            >
              Adopt…
            </button>
            <button
              type="button"
              disabled={blocked}
              title={blocked ? "Fix the entries below first" : undefined}
              onClick={() => setRenaming(form.name)}
            >
              Rename…
            </button>
            <button type="button" onClick={() => setConfirmDelete(true)}>
              Delete…
            </button>
          </>
        )}
        {readOnly && isCurrent && (
          <button type="button" onClick={() => setConfirmUnadopt(true)}>
            Un-adopt…
          </button>
        )}
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
      </div>
      {adoption && (
        <section className="panel adopted" aria-label="Adopted plan">
          <p>
            <strong>{isCurrent ? "The adopted plan" : "An earlier adopted plan"}</strong> – adopted{" "}
            {longDate(adoption.date)}.{adoption.note && ` ${adoption.note}`}
          </p>
          <p className="hint">
            It is read-only, so its figures never change – copy it as a new scenario to revise it.
          </p>
        </section>
      )}
      <ErrorBanner error={actionError} />
      {status.state === "failed" && (
        <div className="row-actions">
          <ErrorBanner error={status.error} />
          <button type="button" onClick={() => void autosave.flushNow()}>
            Try saving again
          </button>
        </div>
      )}
      {nameProblem && !readOnly && (
        <p className="warning" role="alert">
          {nameProblem} Nothing is saved until it is fixed.
        </p>
      )}
      {invalid.length > 0 && (
        <Problems
          title="These entries are not usable numbers or years yet – they are saved once fixed"
          items={invalid}
        />
      )}
      <Provider>
        <fieldset className="plain" disabled={readOnly}>
          <Outlet />
        </fieldset>
      </Provider>

      <Confirm
        open={renaming !== null}
        title={`Rename ${savedName}`}
        confirmLabel="Rename"
        onCancel={() => setRenaming(null)}
        onConfirm={rename}
      >
        <label className="field">
          <span>New name</span>
          <input
            value={renaming ?? ""}
            onChange={(e) => setRenaming(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && rename()}
            aria-invalid={renameProblem ? true : undefined}
            aria-describedby={renameProblem ? renameHint : undefined}
            autoFocus
          />
        </label>
        {renameProblem && (
          <p id={renameHint} className="warning" role="alert">
            {renameProblem}
          </p>
        )}
      </Confirm>
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
        title={`Adopt ${savedName}?`}
        confirmLabel="Adopt"
        onCancel={() => setAdopting(null)}
        onConfirm={() => void adopt()}
      >
        <p>
          It becomes the adopted plan – read-only, so its figures never change.
          {current ? ` ${current.name} stays as an earlier adopted plan.` : ""}
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
        open={confirmUnadopt}
        title={`Un-adopt ${original.name}?`}
        confirmLabel="Un-adopt"
        onCancel={() => setConfirmUnadopt(false)}
        onConfirm={() => void unadopt()}
      >
        <p>
          It becomes an ordinary scenario again, and the plan adopted before it – if any – becomes
          the adopted plan. Use this only to correct a mistake.
        </p>
      </Confirm>
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
            : nameProblem
              ? "The scenario's name is blank or another scenario's, so the edits since it changed are not saved and will be lost."
              : "The last edit could not be saved – it will be lost."}
        </p>
      </Confirm>
    </ScenarioContext.Provider>
  );
}

function SaveNote({ status }: { status: SaveStatus }) {
  const text = {
    saved: "All changes saved",
    saving: "Saving…",
    waiting: "Not saved yet – see below",
    failed: "Not saved – see below",
  }[status.state];
  return (
    <span className={`save-note ${status.state}`} role="status">
      {text}
    </span>
  );
}

/** A few results beside the inputs, so the effect of an edit shows on every screen. */
function KeyResults() {
  const { result, problems, id, form } = useScenario();
  if (problems.length > 0) return <Problems title="Fix these to see results" items={problems} />;
  if (!result) return null;
  const s = result.summary;
  const end = result.years.at(-1)?.year;
  return (
    <aside className="key-results" aria-label="Key results" aria-live="polite">
      <dl>
        <div>
          <dt>Lowest balance</dt>
          <dd className={s.lowest_balance.startsWith("-") ? "negative" : undefined}>
            {money(s.lowest_balance)} ({s.lowest_balance_year})
          </dd>
        </div>
        <div>
          <dt>Funded at end of {end}</dt>
          <dd>{percent(s.pf_end)}</dd>
        </div>
        <div>
          <dt>Target first met</dt>
          <dd>{s.first_target_year ?? `not by ${end}`}</dd>
        </div>
        <div>
          <dt>Years below cushion</dt>
          <dd>{s.low_years}</dd>
        </div>
        <div>
          <dt>Years needing a vote</dt>
          <dd>{s.vote_years}</dd>
        </div>
      </dl>
      <Link to={scenarioPath(id, form.name.trim() || form.name)}>All results</Link>
    </aside>
  );
}

// ---------------------------------------------------------------- Results

export function ResultsScreen() {
  const { result, problems, form } = useScenario();
  return (
    <section className="results" aria-live="polite" aria-label="Results">
      <Problems title="Fix these to see results" items={problems} />
      {result && problems.length === 0 && (
        <>
          <PlanTable
            result={result}
            cushion={form.facts.cushion}
            target={form.facts.target}
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
            summary={`Dues per unit run from ${duesText(result.years[0]?.owner_dues_year)} to ${duesText(result.years.at(-1)?.owner_dues_year)} a year${result.summary.total_assessments && Number(result.summary.total_assessments) > 0 ? `, with ${duesText(result.summary.total_assessments)} per unit in special assessments over the projection` : ", with no special assessment"}.`}
            filename={`${form.name} - owner cost.png`}
            legend={OWNER_LEGEND}
          >
            <OwnerCostChart result={result} />
          </ChartFrame>
        </>
      )}
    </section>
  );
}

/** An inputs screen – its inputs, with the key results beside them, or above a table too wide
 * to share the row. */
function InputsScreen({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  if (wide)
    return (
      <div className="wide-inputs">
        <KeyResults />
        {children}
      </div>
    );
  return (
    <div className="split">
      <div className="inputs">{children}</div>
      <KeyResults />
    </div>
  );
}

/** "Copy to…" for one thing on a screen, with its dialog. Hidden on an adopted plan. */
function CopyButton({
  what,
  label,
  apply,
}: {
  what: string;
  label: string;
  apply: (target: Scenario) => Scenario;
}) {
  const { readOnly, others, copyTo, blocked } = useScenario();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState("");
  if (readOnly) return null;
  return (
    <>
      <button
        type="button"
        className="small"
        aria-label={label}
        disabled={blocked}
        title={blocked ? "Fix the entries that are not usable first" : undefined}
        onClick={() => setOpen(true)}
      >
        Copy to…
      </button>
      {done && (
        <span className="hint" role="status">
          {" "}
          {done}
        </span>
      )}
      {open && (
        <CopyDialog
          what={what}
          others={others}
          onClose={() => setOpen(false)}
          onCopy={(names) => {
            setOpen(false);
            void copyTo(names, apply).then(() => setDone(`Copied to ${names.join(", ")}.`));
          }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------- Facts and assumptions

interface Fact {
  key: FactKey;
  label: string;
  hint: string; // what the figure means, in a board member's words
  example: string; // the kind of source note to write for it
  unit: "$" | "%" | "year" | "count";
  blank?: boolean; // may be left blank – no limit
}

// The facts and assumptions, grouped by what they are about.
const FACTS: { title: string; facts: Fact[] }[] = [
  {
    title: "The years it covers",
    facts: [
      {
        key: "start_year",
        label: "Start year",
        hint: "January 1 of this year. If it is mid-year, start next year with the expected January 1 balance",
        example: "e.g. Next budget year",
        unit: "year",
      },
      {
        key: "end_year",
        label: "End year",
        hint: "5 to 30 full years after the start year",
        example: "e.g. Reserve study horizon",
        unit: "year",
      },
    ],
  },
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
        hint: "What each unit pays today – the no-change figure this scenario's extra cost is measured against",
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

/** One figure as a table row – its name and hint, its value, where it came from, and a way to
 * copy it into other scenarios. */
function FactRow({
  fact,
  facts,
  onValue,
  onSource,
}: {
  fact: Fact;
  facts: Facts;
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
              value={facts[key] as number}
              onChange={onValue}
            />
          ) : (
            <DecimalInput
              id={id}
              name={label}
              describedBy={`${id}-hint`}
              percent={unit === "%"}
              allowBlank={blank}
              value={facts[key] as string | null}
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
          value={facts.sources[key] ?? ""}
          onChange={(e) => onSource(e.target.value)}
        />
      </td>
      <td className="no-print">
        <CopyButton
          what={`the ${label.toLowerCase()}`}
          label={`Copy ${label.toLowerCase()} to other scenarios`}
          apply={(target) => copyFact(target, facts, key)}
        />
      </td>
    </tr>
  );
}

export function FactsScreen() {
  const { form, setForm } = useScenario();
  const f = form.facts;
  const set = (change: Partial<Facts>) => setForm({ ...form, facts: { ...f, ...change } });

  function setValue(key: FactKey, value: string | number | null) {
    if (key === "start_year") setForm(withHorizon(form, value as number, f.end_year));
    else if (key === "end_year") setForm(withHorizon(form, f.start_year, value as number));
    else set({ [key]: value });
  }

  return (
    <InputsScreen>
      <section className="panel">
        <h2>This scenario</h2>
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
      </section>
      <section className="panel">
        <h2>Figures, and where they came from</h2>
        <p className="hint">
          Beside each figure, a source note says where it came from and when – a document, a page, a
          date – so anyone reading the plan later can check it. Notes are optional, and each travels
          into the exported workbook. Copy to… puts a figure and its note into other scenarios – a
          new balance or a revised rate, for example.
        </p>
        <table className="facts">
          <caption className="visually-hidden">Facts and assumptions</caption>
          <thead>
            <tr>
              <th scope="col">Figure</th>
              <th scope="col">Value</th>
              <th scope="col">Source note – where the figure came from</th>
              <th scope="col" className="no-print">
                <span className="visually-hidden">Copy</span>
              </th>
            </tr>
          </thead>
          {FACTS.map((group) => (
            <tbody key={group.title}>
              <tr className="fact-group">
                <th scope="rowgroup" colSpan={4}>
                  {group.title}
                </th>
              </tr>
              {group.facts.map((fact) => (
                <FactRow
                  key={fact.key}
                  fact={fact}
                  facts={f}
                  onValue={(value) => setValue(fact.key, value)}
                  onSource={(text) => set({ sources: { ...f.sources, [fact.key]: text } })}
                />
              ))}
            </tbody>
          ))}
        </table>
      </section>
    </InputsScreen>
  );
}

// ---------------------------------------------------------------- Expenses

export function ExpensesScreen() {
  const { form, setForm, others, copyTo, readOnly, blocked } = useScenario();
  const [copying, setCopying] = useState<Facts["expense_lines"][number] | null>(null);
  const [done, setDone] = useState("");
  const f = form.facts;
  return (
    <InputsScreen wide>
      <section className="panel">
        <ExpenseTable
          lines={f.expense_lines}
          defaultYear={f.start_year}
          onChange={(expense_lines) => setForm({ ...form, facts: { ...f, expense_lines } })}
          onCopy={readOnly || blocked ? undefined : setCopying}
          taken={others.flatMap((s) => s.facts.expense_lines.map((l) => l.id))}
          horizon={{
            start: f.start_year,
            end: f.end_year,
            inflation: f.expense_inflation,
            baseYear: f.expense_base_year,
          }}
        />
        {done && (
          <p className="hint" role="status">
            {done}
          </p>
        )}
      </section>
      {copying && (
        <CopyDialog
          what={copying.description ? `“${copying.description}”` : "this expense"}
          others={others}
          onClose={() => setCopying(null)}
          onCopy={(names) => {
            const line = copying;
            setCopying(null);
            void copyTo(names, (target) => copyLine(target, line)).then(() =>
              setDone(
                `Copied ${line.description ? `“${line.description}”` : "the expense"} to ${names.join(", ")} – it replaces the same expense there, or is added.`,
              ),
            );
          }}
        />
      )}
    </InputsScreen>
  );
}

// ---------------------------------------------------------------- Fully Funded Balance

export function FfbScreen() {
  const { form, setForm, result } = useScenario();
  const f = form.facts;
  const years = plausibleHorizon(f.start_year, f.end_year)
    ? Array.from({ length: f.end_year - f.start_year + 2 }, (_, i) => f.start_year + i)
    : [];
  const set = (change: Partial<Facts>) => setForm({ ...form, facts: { ...f, ...change } });
  // the reserve lines that count towards a worked-out figure, and those that cannot yet
  const reserve = f.expense_lines.filter((l) => l.frequency === "every" || l.frequency === "once");
  const lifeless = reserve.filter((l) => l.frequency === "once" && !l.useful_life);
  const worked = useSort(years, {
    year: (y) => y,
    ffb: (y) => numberOf(result?.ffb[String(y)]),
  });
  return (
    <InputsScreen>
      <section className="panel explainer" aria-label="What the Fully Funded Balance means">
        <p>
          The Fully Funded Balance is what should have been saved by a given year, added up across
          every component in the building.
        </p>
        <p>
          Each year the building wears a little, and the owners living there that year are the ones
          using it up. The Fully Funded Balance is what the fund would hold if every owner had paid
          exactly for the wear during their time.
        </p>
        <ul>
          <li>At 100% funded, the fund has kept pace – owners pay only for future wear.</li>
          <li>
            Below 100%, past wear wasn't fully paid for. Owners will make up the difference later,
            through higher dues or special assessments.
          </li>
        </ul>
        <p>
          Percent funded predicts special-assessment risk. At 25% funded, three quarters of the wear
          already done hasn't been paid for, so the money for those replacements has to come from
          somewhere when they fall due.
        </p>
      </section>
      <section className="panel">
        <fieldset className="plain">
          <legend className="visually-hidden">Where the Fully Funded Balance comes from</legend>
          <label className="check">
            <input
              type="radio"
              name="ffb-from"
              checked={!f.ffb_from_lines}
              onChange={() => set({ ffb_from_lines: false })}
            />{" "}
            The reserve study's figures, typed below
          </label>
          <label className="check">
            <input
              type="radio"
              name="ffb-from"
              checked={f.ffb_from_lines}
              onChange={() => set({ ffb_from_lines: true })}
            />{" "}
            Worked out from this scenario's expenses and their useful lives
          </label>
        </fieldset>
        {f.ffb_from_lines ? (
          <>
            <p className="hint">
              Each reserve expense counts its cost in that year's dollars times how far it is
              through its useful life – an every-few-years expense's interval, or a one-time cost's
              useful life – from when it next falls due. Monthly and yearly costs do not count.{" "}
              {reserve.length - lifeless.length} of {reserve.length} reserve expenses count
              {lifeless.length > 0
                ? ` – ${lifeless.length} one-time cost${lifeless.length === 1 ? " has" : "s have"} no useful life yet.`
                : "."}
            </p>
            {result && (
              <table className="list ffb-worked">
                <caption className="visually-hidden">Fully Funded Balance, worked out</caption>
                <thead>
                  <tr>
                    {worked.header("year", "Start of year")}
                    {worked.header("ffb", "Fully Funded Balance", { className: "num" })}
                  </tr>
                </thead>
                <tbody>
                  {worked.order
                    .map((k) => years[k] as number)
                    .map((y) => (
                      <tr key={y}>
                        <th scope="row">{y}</th>
                        <td className="num">{money(result.ffb[String(y)])}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
            <p className="hint">The typed figures are kept, for switching back.</p>
          </>
        ) : years.length > 0 ? (
          <FfbTable years={years} values={f.ffb} onChange={(ffb) => set({ ffb })} />
        ) : (
          <p className="hint">
            Set a start and end year 5 to 30 years apart on Facts and assumptions to see this table.
          </p>
        )}
        <Field label="Source – Fully Funded Balance">
          {(fid) => (
            <input
              id={fid}
              className="source"
              value={f.sources.ffb ?? ""}
              onChange={(e) => set({ sources: { ...f.sources, ffb: e.target.value } })}
            />
          )}
        </Field>
        <div className="row-actions">
          <CopyButton
            what="the Fully Funded Balance"
            label="Copy the Fully Funded Balance to other scenarios"
            apply={(target) => copyFfb(target, f)}
          />
        </div>
      </section>
    </InputsScreen>
  );
}

// ---------------------------------------------------------------- Dues

type Mode = "explicit" | "rate" | "pinned";

const modeOf = (s: Scenario): Mode =>
  s.dues.mode === "explicit"
    ? "explicit"
    : Object.keys(s.dues.overrides).length
      ? "pinned"
      : "rate";

/** The increases with one more – starting the year after the last one's to year, at its
 * rate, running to the end. Rows already there are never changed: when the last one runs to
 * the end, the new one starts blank and the overlap is listed until its years are set. */
export function withAnother(increases: Increase[]): Increase[] {
  const last = increases.at(-1);
  const from = last?.last_year != null ? last.last_year + 1 : null;
  return [...increases, { first_year: from, last_year: null, rate: last?.rate ?? "0.03" }];
}

/** A grown path's yearly increases (spec 5.1) – a rate for each stretch of years, every year
 * after the start in exactly one; the server names overlaps and gaps. */
function Increases({
  increases,
  start,
  end,
  problems,
  onChange,
}: {
  increases: Increase[];
  start: number;
  end: number;
  problems: string[];
  onChange: (increases: Increase[]) => void;
}) {
  const rows = useRowIds(increases.length);
  const set = (i: number, change: Partial<Increase>) =>
    onChange(increases.map((x, j) => (j === i ? { ...x, ...change } : x)));
  return (
    <div className="increases">
      <table className="edit-table">
        <caption>
          Yearly increases – each year's dues rise by the increase whose years include it; a blank
          from or to year is the start or end
        </caption>
        <thead>
          <tr>
            <th scope="col">From</th>
            <th scope="col">To</th>
            <th scope="col">Increase</th>
            <th scope="col">
              <span className="visually-hidden">Remove</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {increases.map((inc, i) => (
            <tr key={rows.ids[i]}>
              <td>
                <OptionalYearInput
                  label={`First year of yearly increase ${i + 1}`}
                  name={`First year of yearly increase ${i + 1}`}
                  value={inc.first_year}
                  placeholder={`start (${start})`}
                  onChange={(first_year) => set(i, { first_year })}
                />
              </td>
              <td>
                <OptionalYearInput
                  label={`Last year of yearly increase ${i + 1}`}
                  name={`Last year of yearly increase ${i + 1}`}
                  value={inc.last_year}
                  placeholder={`end (${end})`}
                  onChange={(last_year) => set(i, { last_year })}
                />
              </td>
              <td>
                <DecimalInput
                  label={`Yearly increase ${i + 1}`}
                  name={`Yearly increase ${i + 1}`}
                  percent
                  value={inc.rate}
                  onChange={(v) => v !== null && set(i, { rate: v })}
                />
              </td>
              <td>
                {increases.length > 1 && (
                  <button
                    type="button"
                    className="small"
                    aria-label={`Remove yearly increase ${i + 1}`}
                    onClick={() => {
                      rows.removed(i);
                      onChange(increases.filter((_, j) => j !== i));
                    }}
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Problems title="Yearly increases to fix" items={problems} />
      <button
        type="button"
        onClick={() => {
          rows.added();
          onChange(withAnother(increases));
        }}
      >
        Add yearly % increase
      </button>
    </div>
  );
}

export function DuesScreen() {
  const { form, setForm, result, problems } = useScenario();
  const [mode, setMode] = useState<Mode>(modeOf(form));
  const years = horizonOf(form);
  const f = form.facts;
  const resolved = new Map(result?.years.map((y) => [y.year, y.dues]) ?? []);
  const typedFor = (y: number) =>
    form.dues.mode === "explicit"
      ? form.dues.explicit[String(y)]
      : form.dues.mode === "rate"
        ? form.dues.overrides[String(y)]
        : undefined;
  const sorted = useSort(
    years,
    {
      year: (y) => y,
      typed: (y) => numberOf(typedFor(y)),
      resolved: (y) => numberOf(resolved.get(y)),
    },
    (y) => y, // held when sorted, so typing a figure never moves its row
  );

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
              first_value: form.dues.explicit[String(f.start_year)] ?? f.current_dues,
              increases: [{ first_year: null, last_year: null, rate: "0.03" }],
              overrides: {},
            };
      setForm({ ...form, dues: { ...base, overrides: next === "rate" ? {} : base.overrides } });
    }
  }

  return (
    <InputsScreen>
      <section className="panel">
        <fieldset className="dues-settings">
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
              <Field label={`Dues in ${f.start_year}`}>
                {(fid) => (
                  <DecimalInput
                    id={fid}
                    name={`Dues in ${f.start_year}`}
                    value={form.dues.mode === "rate" ? form.dues.first_value : null}
                    onChange={(v) =>
                      v !== null &&
                      form.dues.mode === "rate" &&
                      setForm({ ...form, dues: { ...form.dues, first_value: v } })
                    }
                  />
                )}
              </Field>
            </div>
          )}
          {form.dues.mode === "rate" && (
            <Increases
              increases={form.dues.increases}
              start={f.start_year}
              end={f.end_year}
              problems={problems.filter((p) => p.includes("yearly dues increase"))}
              onChange={(increases) =>
                form.dues.mode === "rate" && setForm({ ...form, dues: { ...form.dues, increases } })
              }
            />
          )}

          <table className="edit-table dues-table">
            <caption>
              Dues each year
              {mode === "pinned" ? " – pin a year to a figure; later years grow from it" : ""}
            </caption>
            <thead>
              <tr>
                {sorted.header("year", "Year")}
                {mode !== "rate" && sorted.header("typed", mode === "explicit" ? "Dues" : "Pinned")}
                {sorted.header("resolved", "Resolved", { className: "num" })}
              </tr>
            </thead>
            <tbody>
              {sorted.order
                .map((k) => years[k] as number)
                .map((y) => {
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
      </section>
    </InputsScreen>
  );
}

// ---------------------------------------------------------------- Special assessments

export function AssessmentsScreen() {
  const { form, setForm } = useScenario();
  const rows = useRowIds(form.assessments.length);
  const setAssessments = (assessments: Assessment[]) => setForm({ ...form, assessments });
  const { order, header } = useSort(
    form.assessments,
    { year: (a) => a.year, amount: (a) => numberOf(a.amount), note: (a) => a.note },
    (_, i) => rows.ids[i] ?? String(i), // held when sorted, so typing never moves a row
  );
  return (
    <InputsScreen>
      <section className="panel">
        <p className="hint">Per unit. Several installments are separate rows.</p>
        <table className="edit-table">
          <caption className="visually-hidden">Special assessments</caption>
          <thead>
            <tr>
              {header("year", "Year")}
              {header("amount", "Per unit")}
              {header("note", "Note")}
              <th scope="col">
                <span className="visually-hidden">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {order
              .map((i) => [form.assessments[i] as Assessment, i] as const)
              .map(([a, i]) => (
                <tr key={rows.ids[i]}>
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
                        rows.removed(i);
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
            rows.added();
            setAssessments([
              ...form.assessments,
              { year: form.facts.start_year, amount: "0", note: "" },
            ]);
          }}
        >
          Add assessment
        </button>
      </section>
    </InputsScreen>
  );
}
