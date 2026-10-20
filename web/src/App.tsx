import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, createBrowserRouter, useParams } from "react-router-dom";

import { api } from "./api";
import { ErrorBanner } from "./components/ui";
import { BaselineEditor } from "./pages/BaselineEditor";
import { ChartsPage } from "./pages/ChartsPage";
import { ComparePage } from "./pages/ComparePage";
import { ProjectList } from "./pages/ProjectList";
import { ProjectPage } from "./pages/ProjectPage";
import { ScenarioEditor } from "./pages/ScenarioEditor";
import type { StoredProject } from "./types";

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

/** Breadcrumbs back to the project – every project screen starts with one. */
export function ProjectNav({ stored, here }: { stored: StoredProject; here?: string }) {
  return (
    <nav aria-label="Breadcrumb" className="crumbs no-print">
      <Link to="/">Projects</Link> ›{" "}
      <Link to={`/projects/${stored.id}`}>{stored.project.name}</Link>
      {here && (
        <>
          {" "}
          › <span aria-current="page">{here}</span>
        </>
      )}
    </nav>
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
      { path: "/projects/:id", element: <ProjectPage /> },
      { path: "/projects/:id/baseline", element: <BaselineEditor /> },
      { path: "/projects/:id/scenarios/new", element: <ScenarioEditor /> },
      { path: "/projects/:id/scenarios/:name", element: <ScenarioEditor /> },
      { path: "/projects/:id/compare", element: <ComparePage /> },
      { path: "/projects/:id/charts", element: <ChartsPage /> },
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
