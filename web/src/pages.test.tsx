import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "./api";
import { BaselineEditor } from "./pages/BaselineEditor";
import { ScenarioEditor } from "./pages/ScenarioEditor";
import type { Baseline, Project, Scenario, StoredProject } from "./types";

vi.mock("./api", async (importOriginal) => {
  const real = await importOriginal<typeof import("./api")>();
  return {
    ...real,
    api: {
      getProject: vi.fn(),
      saveProject: vi.fn(),
      getDrafts: vi.fn(),
      saveDraft: vi.fn(),
      discardDraft: vi.fn(),
      run: vi.fn(),
      baselineImpact: vi.fn(),
    },
  };
});

type Mock = ReturnType<typeof vi.fn>;
const mocked = api as unknown as {
  getProject: Mock;
  saveProject: Mock;
  getDrafts: Mock;
  saveDraft: Mock;
  discardDraft: Mock;
  run: Mock;
  baselineImpact: Mock;
};

const years = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => from + i);

const baseline: Baseline = {
  start_year: 2027,
  end_year: 2031,
  starting_balance: "100000",
  expense_lines: [
    {
      id: "operating",
      frequency: "yearly",
      year: null,
      end_year: null,
      inflation: null,
      amount: "50000",
      description: "Operating",
      source: "",
    },
  ],
  expense_inflation: "0.03",
  expense_base_year: 2026,
  ffb: Object.fromEntries(years(2027, 2032).map((y) => [String(y), String(y * 100)])),
  operating_inflation: "0.03",
  interest_rate: "0.02",
  units: 10,
  current_dues: "500",
  cushion: "10000",
  target: "0.7",
  max_dues_increase: "0.2",
  max_assessment_share: "0.05",
  sources: {},
};

const scenario: Scenario = {
  name: "Plan A",
  description: "",
  dues: { mode: "rate", first_value: "600", annual_increase: "0.03", overrides: {} },
  assessments: [],
  rounding: "dollar",
};

function stored(project: Project, revision = 1): StoredProject {
  const t = { created: "2026-10-20T10:00:00+00:00", modified: "2026-10-20T10:00:00+00:00" };
  return {
    id: "abcdefabcdef",
    revision,
    times: t,
    baseline_times: t,
    scenario_times: Object.fromEntries(project.scenarios.map((s) => [s.name, t])),
    project,
  };
}

const project: Project = {
  schema_version: 2,
  name: "Demo",
  notes: "",
  baseline,
  scenarios: [scenario],
};

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function start(path: string, element: React.ReactNode) {
  const router = createMemoryRouter(
    [
      { path: "/projects/:id", element: <Where /> },
      {
        path: "/projects/:id/baseline",
        element: (
          <>
            {element}
            <Where />
          </>
        ),
      },
      {
        path: "/projects/:id/scenarios/new",
        element: (
          <>
            {element}
            <Where />
          </>
        ),
      },
      {
        path: "/projects/:id/scenarios/:name",
        element: (
          <>
            {element}
            <Where />
          </>
        ),
      },
    ],
    { initialEntries: [path] },
  );
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  let current = stored(project);
  mocked.getProject.mockImplementation(async () => current);
  mocked.saveProject.mockImplementation(async (_id: string, p: Project, base: number) => {
    current = stored(p, base + 1);
    return current;
  });
  mocked.getDrafts.mockResolvedValue({ drafts: {} });
  mocked.saveDraft.mockResolvedValue(undefined);
  mocked.discardDraft.mockResolvedValue(undefined);
  mocked.run.mockRejectedValue(
    new ApiError(422, "the inputs have problems", ["(results not under test)"]),
  );
  mocked.baselineImpact.mockResolvedValue({ changed: [], unchanged: ["Plan A"], invalid: [] });
});

afterEach(() => vi.clearAllMocks());

describe("the scenario editor", () => {
  it("renames and saves, and ends on the renamed scenario's page", async () => {
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan B");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(screen.getByTestId("where").textContent).toBe(
        "/projects/abcdefabcdef/scenarios/Plan%20B",
      ),
    );
    expect(await screen.findByRole("heading", { name: "Plan B" })).toBeTruthy();
    expect(screen.queryByText(/Leave without saving/)).toBeNull();
    expect(mocked.saveProject).toHaveBeenCalledTimes(1);
  });

  it("saves a new scenario once and opens it", async () => {
    start("/projects/abcdefabcdef/scenarios/new", <ScenarioEditor />);
    await screen.findByRole("heading", { name: "New scenario" });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(screen.getByTestId("where").textContent).toBe(
        "/projects/abcdefabcdef/scenarios/New%20scenario",
      ),
    );
    const saved = mocked.saveProject.mock.calls[0]?.[1] as Project;
    expect(saved.scenarios.map((s) => s.name)).toEqual(["Plan A", "New scenario"]);
  });

  it("does not offer to save, or ask before leaving, when nothing changed", async () => {
    start("/projects/abcdefabcdef/scenarios/new", <ScenarioEditor />);
    await screen.findByRole("heading", { name: "New scenario" });
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    expect(mocked.saveDraft).not.toHaveBeenCalled();
  });

  it("refuses to save while a figure is not a number, and says which", async () => {
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    const dues = await screen.findByRole("textbox", { name: "Dues in 2027" });
    await userEvent.type(dues, "x");
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent ?? "");
    expect(alerts.some((t) => t.includes("not usable") && t.includes("Dues in 2027"))).toBe(true);
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("the baseline editor", () => {
  it("keeps the Fully Funded Balance while the end year is retyped", async () => {
    start("/projects/abcdefabcdef/baseline", <BaselineEditor />);
    const end = await screen.findByRole("textbox", { name: "End year" });
    await userEvent.clear(end);
    await userEvent.type(end, "2");
    await userEvent.clear(end);
    await userEvent.type(end, "2031");
    const ffb2030 = screen.getByRole("textbox", {
      name: "Fully Funded Balance at the start of 2030",
    });
    expect((ffb2030 as HTMLInputElement).value).toBe("203000");
  });

  it("refuses to save while a figure is not a number, and says which", async () => {
    start("/projects/abcdefabcdef/baseline", <BaselineEditor />);
    const balance = await screen.findByRole("textbox", { name: "Starting reserve balance" });
    await userEvent.type(balance, "abc");
    expect(screen.getByRole("alert").textContent).toContain("Starting reserve balance");
    expect(
      (screen.getByRole("button", { name: "Save baseline" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("edits an expense's frequency, own rate and years, and saves only what it uses", async () => {
    start("/projects/abcdefabcdef/baseline", <BaselineEditor />);
    const how = await screen.findByRole("combobox", { name: "How often expense 1 falls" });
    await userEvent.type(
      screen.getByRole("textbox", { name: "Own inflation rate of expense 1" }),
      "6",
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Last year of expense 1" }), "2030");
    await userEvent.selectOptions(how, "monthly");
    expect(screen.getByRole("textbox", { name: "Amount of expense 1 a month" })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Add expense" }));
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "How often expense 2 falls" }),
      "every",
    );
    expect(screen.queryByRole("textbox", { name: "Own inflation rate of expense 2" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save baseline" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const saved = (mocked.saveProject.mock.calls[0]?.[1] as Project).baseline.expense_lines;
    expect(saved[0]).toMatchObject({ frequency: "monthly", inflation: "0.06", end_year: 2030 });
    expect(saved[1]).toEqual({
      id: "line-1",
      frequency: "every",
      year: 2027,
      interval: 5,
      end_year: null,
      amount: "0",
      description: "",
      nominal: false,
      source: "",
    });
  });

  it("confirms against the baseline being saved and then leaves for the project page", async () => {
    start("/projects/abcdefabcdef/baseline", <BaselineEditor />);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    mocked.baselineImpact.mockResolvedValueOnce({
      changed: ["Plan A"],
      unchanged: [],
      invalid: [],
    });
    await userEvent.click(screen.getByRole("button", { name: "Save baseline" }));
    const call = mocked.baselineImpact.mock.calls.at(-1);
    expect((call?.[1] as Baseline).units).toBe(12);
    expect(await screen.findByText("Plan A")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(screen.getByTestId("where").textContent).toBe("/projects/abcdefabcdef"),
    );
  });
});
