// The local server's API. Every call carries the per-launch token the server wrote into
// this page, so no other web page can talk to the app.

import type {
  Project,
  ProjectResults,
  ProjectSummary,
  Scenario,
  ScenarioResult,
  StoredProject,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly problems: string[];

  constructor(status: number, message: string, problems: string[] = []) {
    super(message);
    this.status = status;
    this.problems = problems;
  }
}

function token(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="hoa-token"]')?.content ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-HOA-Token", token());
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (e) {
    if (init.signal?.aborted) throw e; // cancelled on purpose – the caller ignores it
    throw new ApiError(0, "HOAForecaster is not running – start it again and reload this page");
  }
  if (response.status === 204) return undefined as T;
  if (response.ok) return (await response.json()) as T; // a broken reply is an error, not null
  const body: unknown = await response.json().catch(() => null);
  const { message, problems } = (body ?? {}) as { message?: string; problems?: string[] };
  throw new ApiError(
    response.status,
    message ?? `the server answered ${response.status}`,
    problems,
  );
}

async function download(path: string): Promise<{ blob: Blob; filename: string }> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { "X-HOA-Token": token() } });
  } catch {
    throw new ApiError(0, "HOAForecaster is not running – start it again and reload this page");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      message?: string;
      problems?: string[];
    };
    throw new ApiError(response.status, body.message ?? "the download failed", body.problems);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = /filename\*=UTF-8''([^;]+)/.exec(disposition)?.[1];
  const plain = /filename="([^"]+)"/.exec(disposition)?.[1];
  const filename = encoded ? decodeURIComponent(encoded) : (plain ?? "download");
  return { blob: await response.blob(), filename };
}

const json = (value: unknown): string => JSON.stringify(value);

/** A project's API address – the id is encoded, so no address text can steer a call elsewhere. */
const projectUrl = (id: string): string => `/api/projects/${encodeURIComponent(id)}`;

export const api = {
  listProjects: () => call<{ projects: ProjectSummary[]; unreadable: string[] }>("/api/projects"),
  createProject: (project: Project) =>
    call<StoredProject>("/api/projects", { method: "POST", body: json({ project }) }),
  /** A blank project with the spec's defaults, made by the server. */
  createBlank: (name: string) =>
    call<StoredProject>("/api/projects", { method: "POST", body: json({ name }) }),
  about: () => call<{ data_folder: string; version: string; can_restart: boolean }>("/api/about"),
  /** Ask the launcher for a fresh server – this one stops once it has answered. */
  restart: () => call<{ restarting: boolean }>("/api/restart", { method: "POST" }),
  getProject: (id: string) => call<StoredProject>(projectUrl(id)),
  saveProject: (id: string, project: Project, baseRevision: number) =>
    call<StoredProject>(projectUrl(id), {
      method: "PUT",
      body: json({ project, base_revision: baseRevision }),
    }),
  deleteProject: (id: string) => call<undefined>(projectUrl(id), { method: "DELETE" }),
  results: (id: string) => call<ProjectResults>(`${projectUrl(id)}/results`),
  /** Adopt a scenario as the board's plan (spec 5.2). */
  adopt: (id: string, name: string, date: string, note: string, baseRevision: number) =>
    call<StoredProject>(`${projectUrl(id)}/adopt`, {
      method: "POST",
      body: json({ name, date, note, base_revision: baseRevision }),
    }),
  /** Un-adopt the current adopted plan. */
  unadopt: (id: string, baseRevision: number) =>
    call<StoredProject>(`${projectUrl(id)}/unadopt`, {
      method: "POST",
      body: json({ base_revision: baseRevision }),
    }),
  /** A blank scenario with the spec's defaults (section 4), made by the server. */
  blankScenario: (name: string) =>
    call<Scenario>(`/api/blank-scenario?name=${encodeURIComponent(name)}`),
  run: (scenario: Scenario, signal?: AbortSignal) =>
    call<ScenarioResult>("/api/run", { method: "POST", body: json({ scenario }), signal }),
  exportProject: (id: string) => download(`${projectUrl(id)}/export.json`),
  exportWorkbook: (id: string, scenarios: string[]) =>
    download(
      `${projectUrl(id)}/export.xlsx?` +
        scenarios.map((s) => `scenario=${encodeURIComponent(s)}`).join("&"),
    ),
  importProject: (file: File) =>
    call<StoredProject>("/api/import/project", { method: "POST", body: file }),
  importWorkbook: (file: File) => {
    return call<StoredProject>("/api/import/workbook", { method: "POST", body: file });
  },
};

/** Hand a blob to the browser as a file to save. */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The token in a page's HTML, as the server wrote it there. */
export const tokenIn = (html: string): string =>
  new DOMParser()
    .parseFromString(html, "text/html")
    .querySelector<HTMLMetaElement>('meta[name="hoa-token"]')?.content ?? "";

/** Wait until a fresh server answers – its page carries a new token, so the old server still
 * stopping never counts – then load it. False if none answered in time. */
export async function reloadWhenFresh(
  timeoutMs = 120_000,
  pause = (ms: number) => new Promise<void>((done) => setTimeout(done, ms)),
  reload = () => window.location.reload(),
): Promise<boolean> {
  const old = token();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await pause(500);
    try {
      const response = await fetch("/", { cache: "no-store" });
      const fresh = response.ok ? tokenIn(await response.text()) : "";
      if (fresh && fresh !== old) {
        reload();
        return true;
      }
    } catch {
      // the old server has gone and the new one is not listening yet
    }
  }
  return false;
}
