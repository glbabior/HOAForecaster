import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, createBrowserRouter, useParams } from "react-router-dom";

import { api, reloadWhenFresh } from "./api";
import { Confirm, ErrorBanner } from "./components/ui";
import { BaselineEditor } from "./pages/BaselineEditor";
import { ChartsPage } from "./pages/ChartsPage";
import { ComparePage } from "./pages/ComparePage";
import { ProjectList } from "./pages/ProjectList";
import { ExportPage } from "./pages/ExportPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ScenarioEditor } from "./pages/ScenarioEditor";
import { ScenariosPage } from "./pages/ScenariosPage";
import type { StoredProject } from "./types";

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
          and this page reloads once it is back. Save first: edits on the screen are kept only as a
          draft.
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

function Layout() {
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="app-header no-print">
        <Link to="/" className="brand">
          HOAForecaster
        </Link>
        <RestartButton />
      </header>
      <main id="main">
        <Outlet />
      </main>
    </>
  );
}

/** The project named in the address, with a way to load it again after a save. */
export function useProject(): {
  id: string;
  stored: StoredProject | null;
  error: unknown;
  reload: () => Promise<void>;
  setStored: (s: StoredProject) => void;
} {
  const { id = "" } = useParams();
  const [stored, setStored] = useState<StoredProject | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reload = useCallback(
    () =>
      api.getProject(id).then(
        (s) => {
          setStored(s);
          setError(null);
        },
        (e: unknown) => setError(e),
      ),
    [id],
  );
  useEffect(() => {
    let current = true;
    api.getProject(id).then(
      (s) => current && setStored(s),
      (e: unknown) => current && setError(e),
    );
    return () => {
      current = false;
    };
  }, [id]);
  return { id, stored, error, reload, setStored };
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

// The project's screens, in the order they are used.
const SCREENS: { path: string; label: string }[] = [
  { path: "", label: "Overview" },
  { path: "baseline", label: "Facts and assumptions" },
  { path: "expenses", label: "Expenses" },
  { path: "ffb", label: "Fully Funded Balance" },
  { path: "scenarios", label: "Scenarios" },
  { path: "compare", label: "Compare" },
  { path: "charts", label: "Charts" },
  { path: "export", label: "Export" },
];

/** A project's screens – the index on the left, the screen beside it. */
export function ProjectLayout() {
  const { id = "" } = useParams();
  return (
    <div className="project-layout">
      <nav className="screen-index no-print" aria-label="Project screens">
        <ul>
          {SCREENS.map((s) => (
            <li key={s.path}>
              <NavLink
                to={`/projects/${encodeURIComponent(id)}${s.path ? `/${s.path}` : ""}`}
                end={s.path === ""}
              >
                {s.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="screen">
        <Outlet />
      </div>
    </div>
  );
}

export function Loading({ error }: { error: unknown }) {
  return error ? <ErrorBanner error={error} /> : <p aria-busy="true">Loading…</p>;
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <ProjectList /> },
      {
        path: "/projects/:id",
        element: <ProjectLayout />,
        children: [
          { index: true, element: <ProjectPage /> },
          {
            // one form across the baseline's three screens
            element: <BaselineEditor />,
            children: [{ path: "baseline" }, { path: "expenses" }, { path: "ffb" }],
          },
          { path: "scenarios", element: <ScenariosPage /> },
          { path: "scenarios/new", element: <ScenarioEditor /> },
          { path: "scenarios/:name", element: <ScenarioEditor /> },
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
]);
