import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Link,
  NavLink,
  Navigate,
  type RouteObject,
  Outlet,
  createBrowserRouter,
  useParams,
} from "react-router-dom";

import { ApiError, api, reloadWhenFresh } from "./api";
import { Confirm, ErrorBanner } from "./components/ui";
import { ChartsPage } from "./pages/ChartsPage";
import { ComparePage } from "./pages/ComparePage";
import { ExportPage } from "./pages/ExportPage";
import { NewScenario } from "./pages/NewScenario";
import { ProjectList } from "./pages/ProjectList";
import {
  AssessmentsScreen,
  DuesScreen,
  ExpensesScreen,
  FactsScreen,
  FfbScreen,
  ResultsScreen,
  SCENARIO_SCREENS,
  ScenarioLayout,
  scenarioPath,
} from "./pages/ScenarioScreens";
import { ScenariosPage } from "./pages/ScenariosPage";
import { type Theme, applyTheme } from "./theme";
import type { Project, StoredProject } from "./types";

/** Restart the server and reload the page – shown only when the launcher can start a fresh
 * server. The old one stops once it has answered; the page waits for the new one. */
function RestartButton() {
  const [can, setCan] = useState(false);
  const [asking, setAsking] = useState(false);
  const [state, setState] = useState<"idle" | "waiting" | "failed">("idle");
  useEffect(() => {
    api.about().then(
      (a) => setCan(a.can_restart),
      () => setCan(false),
    );
  }, []);
  if (!can) return null;

  async function restart() {
    setAsking(false);
    setState("waiting");
    try {
      await api.restart();
    } catch {
      // the answer can be lost as the server stops – wait for the fresh one all the same
    }
    if (!(await reloadWhenFresh())) {
      setState("failed");
      return;
    }
    // still here a moment later – the reload was stopped (Stay on the leave-page question)
    setTimeout(() => setState("failed"), 4000);
  }

  return (
    <>
      <button type="button" className="small" onClick={() => setAsking(true)}>
        Restart
      </button>
      <Confirm
        open={asking}
        title="Restart HOAForecaster?"
        confirmLabel="Restart"
        onCancel={() => setAsking(false)}
        onConfirm={() => void restart()}
      >
        <p>
          The server stops and a fresh one starts – rebuilding the screens first if they changed –
          and this page reloads once it is back. Every edit is already saved, apart from an entry
          that is not yet a usable number.
        </p>
      </Confirm>
      {state !== "idle" && (
        <div className="restarting" role="status">
          {state === "waiting"
            ? "Restarting HOAForecaster – this page reloads when it is back…"
            : "Reload this page to use HOAForecaster – if it does not load, look at its window for a message."}
        </div>
      )}
    </>
  );
}

/** Dark screens on or off – an on/off switch, remembered in this browser. */
function ThemeSwitch() {
  // what the screens show – the one source, even when the browser keeps nothing
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  return (
    <button
      type="button"
      role="switch"
      aria-checked={theme === "dark"}
      className="switch"
      onClick={() => {
        const next = theme === "dark" ? "light" : "dark";
        applyTheme(next);
        setTheme(next);
      }}
    >
      <span className="switch-track" aria-hidden="true">
        <span className="switch-knob" />
      </span>
      Dark screens
    </button>
  );
}

function Layout() {
  useEffect(() => {
    const openAll = () => {
      for (const d of document.querySelectorAll("details")) d.open = true;
    };
    window.addEventListener("beforeprint", openAll);
    return () => window.removeEventListener("beforeprint", openAll);
  }, []);
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="app-header no-print">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true" />
          HOAForecaster
        </Link>
        <div className="header-tools">
          <ThemeSwitch />
          <RestartButton />
        </div>
      </header>
      <main id="main">
        <Outlet />
      </main>
    </>
  );
}

interface OpenProject {
  id: string;
  stored: StoredProject | null;
  error: unknown;
  /** Save the project as `build` makes it from the latest saved one – one save at a time, so
   * every screen saves on the revision the save before produced. A save that another save
   * beat (someone saved elsewhere) is made again once on the project as it now is. */
  save: (build: (project: Project) => Project) => Promise<StoredProject>;
  /** Anything else that changes the project – adopting, un-adopting – in the same queue. */
  act: (change: (current: StoredProject) => Promise<StoredProject>) => Promise<StoredProject>;
}

const ProjectContext = createContext<OpenProject | null>(null);

/** The project the screens share – loaded once for all of them, so a screen opened while
 * another's last edit is still saving sees that edit. */
function useOpenProject(id: string): OpenProject {
  const [stored, setStored] = useState<StoredProject | null>(null);
  const [error, setError] = useState<unknown>(null);
  const latest = useRef<StoredProject | null>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  useEffect(() => {
    let current = true;
    latest.current = null;
    api.getProject(id).then(
      (s) => {
        if (!current) return;
        latest.current = s;
        setStored(s);
      },
      (e: unknown) => current && setError(e),
    );
    return () => {
      current = false;
    };
  }, [id]);

  const act = useCallback(
    (change: (current: StoredProject) => Promise<StoredProject>) => {
      const run = async () => {
        const current = latest.current ?? (await api.getProject(id));
        const next = await change(current);
        latest.current = next;
        setStored(next);
        return next;
      };
      const done = queue.current.then(run, run);
      queue.current = done.catch(() => undefined);
      return done;
    },
    [id],
  );

  const save = useCallback(
    (build: (project: Project) => Project) =>
      act(async (current) => {
        try {
          return await api.saveProject(id, build(current.project), current.revision);
        } catch (e) {
          if (!(e instanceof ApiError) || e.status !== 409) throw e;
          const fresh = await api.getProject(id); // saved elsewhere – once more on the new one
          latest.current = fresh;
          setStored(fresh);
          return await api.saveProject(id, build(fresh.project), fresh.revision);
        }
      }),
    [act, id],
  );

  return useMemo(() => ({ id, stored, error, save, act }), [id, stored, error, save, act]);
}

/** The open project, for the screens inside a project. */
export function useProject(): OpenProject {
  const project = useContext(ProjectContext);
  if (!project) throw new Error("a project screen outside its project");
  return project;
}

/** Breadcrumbs back to the project – every project screen starts with one. The screen index
 * marks the current screen, so the last crumb is plain text. */
export function ProjectNav({
  stored,
  here,
  within,
}: {
  stored: StoredProject;
  here?: string;
  within?: { path: string; label: string };
}) {
  const project = `/projects/${stored.id}`;
  return (
    <nav aria-label="Breadcrumb" className="crumbs no-print">
      <Link to="/">Projects</Link> › <Link to={project}>{stored.project.name}</Link>
      {within && (
        <>
          {" "}
          › <Link to={`${project}/${within.path}`}>{within.label}</Link>
        </>
      )}
      {here && <> › {here}</>}
    </nav>
  );
}

// The project's screens – a scenario's own screens open under Scenarios (spec 7.1, 7.2).
const SCREENS: { path: string; label: string }[] = [
  { path: "scenarios", label: "Scenarios" },
  { path: "compare", label: "Compare" },
  { path: "charts", label: "Charts" },
  { path: "export", label: "Export" },
];

/** A project's screens, started afresh for each project – nothing queued for one is ever
 * saved into another. */
export function ProjectLayout() {
  const { id = "" } = useParams();
  return <ProjectScreens key={id} id={id} />;
}

/** The project's sections in a bar across the top, the screen beneath. A scenario's own
 * screens are tabs on the scenario (`ScenarioTabs`). */
function ProjectScreens({ id }: { id: string }) {
  const project = useOpenProject(id);
  return (
    <div className="project-layout">
      <div className="project-bar no-print">
        {project.stored && (
          <Link to={`/projects/${encodeURIComponent(id)}`} className="project-name">
            {project.stored.project.name}
          </Link>
        )}
        <nav aria-label="Project screens">
          <ul>
            {SCREENS.map((s) => (
              <li key={s.path}>
                <NavLink
                  to={`/projects/${encodeURIComponent(id)}/${s.path}`}
                  end={s.path !== "scenarios"}
                >
                  {s.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <div className="screen">
        <ProjectContext.Provider value={project}>
          <Outlet />
        </ProjectContext.Provider>
      </div>
    </div>
  );
}

export function Loading({ error }: { error: unknown }) {
  return error ? <ErrorBanner error={error} /> : <p aria-busy="true">Loading…</p>;
}

/** A scenario's screens as a row of tabs under its name (spec 7.2). */
export function ScenarioTabs({ id, scenario }: { id: string; scenario: string }) {
  return (
    <nav className="tabs no-print" aria-label="Scenario screens">
      <ul aria-label={`${scenario} – screens`}>
        {SCENARIO_SCREENS.map((sc) => (
          <li key={sc.path}>
            <NavLink to={scenarioPath(id, scenario, sc.path)} end>
              {sc.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The app's screens – exported so the tests drive the same routes. */
export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { path: "/", element: <ProjectList /> },
      {
        path: "/projects/:id",
        element: <ProjectLayout />,
        children: [
          { index: true, element: <Navigate to="scenarios" replace /> },
          { path: "scenarios", element: <ScenariosPage /> },
          { path: "scenarios/new", element: <NewScenario /> },
          {
            // one form across a scenario's screens, saving itself
            path: "scenarios/:name",
            element: <ScenarioLayout />,
            children: [
              { index: true, element: <ResultsScreen /> },
              { path: "facts", element: <FactsScreen /> },
              { path: "expenses", element: <ExpensesScreen /> },
              { path: "ffb", element: <FfbScreen /> },
              { path: "dues", element: <DuesScreen /> },
              { path: "assessments", element: <AssessmentsScreen /> },
            ],
          },
          { path: "compare", element: <ComparePage /> },
          { path: "charts", element: <ChartsPage /> },
          { path: "export", element: <ExportPage /> },
        ],
      },
      {
        path: "*",
        element: (
          <p>
            There is nothing at this address. <Link to="/">Back to projects</Link>
          </p>
        ),
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
