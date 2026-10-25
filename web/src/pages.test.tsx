import { act, render, screen, waitFor, within } from "@testing-library/react";
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
      adopt: vi.fn(),
      unadopt: vi.fn(),
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
  adopt: Mock;
  unadopt: Mock;
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
  changes: { values: {}, sources: {}, expense_lines: {}, ffb: {} },
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

  it("saves only the changes to the baseline the scenario makes", async () => {
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Set this scenario's own interest earned on reserves",
      }),
    );
    const rate = screen.getByRole("textbox", {
      name: "This scenario's interest earned on reserves",
    });
    await userEvent.clear(rate);
    await userEvent.type(rate, "4");
    await userEvent.click(
      screen.getByRole("button", { name: "Set this scenario's own minimum working cushion" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Use the baseline's minimum working cushion" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Leave expense 1 out of this scenario" }),
    );
    await userEvent.type(
      screen.getByRole("textbox", {
        name: "This scenario's Fully Funded Balance at the start of 2028",
      }),
      "1000",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const saved = (mocked.saveProject.mock.calls[0]?.[1] as Project).scenarios[0];
    expect(saved?.changes).toEqual({
      values: { interest_rate: "0.04" },
      sources: {},
      expense_lines: { operating: null },
      ffb: { "2028": "1000" },
    });
  });

  it("gives a line of the scenario's own an own- id and keeps a note on its own", async () => {
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Add a line of this scenario's own" }),
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "Source – this scenario's minimum working cushion" }),
      "Board policy",
    );
    expect(screen.getByRole("group", { name: /Changes to the baseline \(2\)/ })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const changes = (mocked.saveProject.mock.calls[0]?.[1] as Project).scenarios[0]?.changes;
    expect(Object.keys(changes?.expense_lines ?? {})).toEqual(["own-1"]);
    expect(changes?.sources).toEqual({ cushion: "Board policy" });
    expect(changes?.values).toEqual({});
  });

  it("stretches typed dues to the scenario's own horizon", async () => {
    const typed: Scenario = {
      ...scenario,
      dues: {
        mode: "explicit",
        explicit: Object.fromEntries(years(2027, 2031).map((y) => [String(y), "600"])),
      },
    };
    let current = stored({ ...project, scenarios: [typed] });
    mocked.getProject.mockImplementation(async () => current);
    mocked.saveProject.mockImplementation(async (_id: string, p: Project, base: number) => {
      current = stored(p, base + 1);
      return current;
    });
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Set this scenario's own end year" }),
    );
    const end = screen.getByRole("textbox", { name: "This scenario's end year" });
    await userEvent.clear(end);
    await userEvent.type(end, "2033");
    expect(screen.getByRole("textbox", { name: "Dues in 2033" })).toBeTruthy();
  });
});

describe("starting a new scenario from another", () => {
  it("copies the chosen scenario's inputs and saves a new, unadopted scenario", async () => {
    const own: Scenario = {
      ...scenario,
      description: "Own rate",
      changes: { ...scenario.changes, values: { interest_rate: "0.04" } },
      adoption: { date: "2026-11-03", note: "", sequence: 1, baseline },
    };
    mocked.getProject.mockImplementation(async () => stored({ ...project, scenarios: [own] }));
    start("/projects/abcdefabcdef/scenarios/new", <ScenarioEditor />);
    const choice = await screen.findByRole("combobox", { name: "Start from" });
    expect(screen.getByRole("option", { name: "Plan A (the adopted plan)" })).toBeTruthy();
    await userEvent.selectOptions(choice, "Plan A");
    await waitFor(() =>
      expect(
        (screen.getByRole("textbox", { name: "Description" }) as HTMLTextAreaElement).value,
      ).toBe("Own rate"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const saved = (mocked.saveProject.mock.calls[0]?.[1] as Project).scenarios[1];
    expect(saved?.name).toBe("New scenario");
    expect(saved?.adoption).toBeNull();
    expect(saved?.changes.values).toEqual({ interest_rate: "0.04" });
  });

  it("asks before a new starting point replaces what was typed", async () => {
    start("/projects/abcdefabcdef/scenarios/new", <ScenarioEditor />);
    await userEvent.type(await screen.findByRole("textbox", { name: "Description" }), "mine");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Start from" }), "Plan A");
    const dialog = screen.getByRole("dialog", { name: "Replace what you typed?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(
      (screen.getByRole("textbox", { name: "Description" }) as HTMLTextAreaElement).value,
    ).toBe("mine");
  });

  it("starts from the scenario named in the address", async () => {
    start("/projects/abcdefabcdef/scenarios/new?from=Plan%20A", <ScenarioEditor />);
    const choice = await screen.findByRole("combobox", { name: "Start from" });
    expect((choice as HTMLSelectElement).value).toBe("Plan A");
  });
});

describe("adopted plans", () => {
  const adoption = { date: "2026-11-03", note: "Board vote", sequence: 1, baseline };
  const adopted: Scenario = { ...scenario, adoption };

  it("adopts a saved scenario with a date and a note", async () => {
    mocked.adopt.mockImplementation(async () => stored({ ...project, scenarios: [adopted] }, 2));
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    await userEvent.click(await screen.findByRole("button", { name: "Adopt…" }));
    const note = screen.getByRole("textbox", { name: /Note/ });
    await userEvent.type(note, "Board vote");
    await userEvent.click(screen.getByRole("button", { name: "Adopt" }));
    await waitFor(() => expect(mocked.adopt).toHaveBeenCalled());
    const [, name, date, typed, revision] = mocked.adopt.mock.calls[0] ?? [];
    expect([name, typed, revision]).toEqual(["Plan A", "Board vote", 1]);
    expect(date).toMatch(/^\d{4}-\d\d-\d\d$/);
    expect(await screen.findByText(/The adopted plan/)).toBeTruthy();
  });

  it("asks for a save before adopting edited inputs", async () => {
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    await userEvent.type(await screen.findByRole("textbox", { name: "Description" }), "x");
    expect((screen.getByRole("button", { name: "Adopt…" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("opens an adopted plan read-only, with a way to revise it and to un-adopt it", async () => {
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [adopted] }));
    mocked.unadopt.mockResolvedValue(stored(project, 2));
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    expect(await screen.findByText(/adopted November 3, 2026\. Board vote/)).toBeTruthy();
    // disabled through its fieldset, which the element's own property does not show
    expect(screen.getByRole("textbox", { name: "Name" }).matches(":disabled")).toBe(true);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(
      screen.getByRole("link", { name: "Start a new scenario from it" }).getAttribute("href"),
    ).toBe("/projects/abcdefabcdef/scenarios/new?from=Plan%20A");
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt" }));
    await waitFor(() => expect(mocked.unadopt).toHaveBeenCalledWith("abcdefabcdef", 1));
  });

  it("shows an adopted plan on its frozen baseline and offers no draft", async () => {
    const frozen = {
      ...adopted,
      adoption: { ...adoption, baseline: { ...baseline, starting_balance: "50000" } },
    };
    const draft = {
      saved: "2026-11-01T10:00:00+00:00",
      base_revision: 1,
      edits: {
        kind: "scenario",
        original: "Plan A",
        scenario: { ...scenario, description: "old" },
      },
    };
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [frozen] }));
    mocked.getDrafts.mockResolvedValue({ drafts: { "scenario:Plan A": draft } });
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    const row = await screen.findByRole("row", { name: /Starting reserve balance/ });
    expect(row.textContent).toContain("$50,000"); // not today's $100,000
    expect(screen.getByRole("columnheader", { name: "As adopted" })).toBeTruthy();
    await act(async () => new Promise((r) => setTimeout(r, 20)));
    expect(screen.queryByRole("button", { name: /Restore/ })).toBeNull();
  });

  it("names the lines an adopted plan left out, though its frozen baseline lacks them", async () => {
    const frozenWithout = { ...baseline, expense_lines: [] };
    const leaving = {
      ...adopted,
      changes: { ...scenario.changes, expense_lines: { operating: null } },
      adoption: { ...adoption, baseline: frozenWithout },
    };
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [leaving] }));
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    expect(await screen.findByText(/left out when the plan was adopted/)).toBeTruthy();
    expect(screen.getByText("Operating")).toBeTruthy(); // named from today's baseline
    expect(screen.getByRole("group", { name: /Changes to the baseline \(1\)/ })).toBeTruthy();
  });

  it("shows no leave-out of a line today's baseline does not have", async () => {
    const leaving = {
      ...adopted,
      changes: { ...scenario.changes, expense_lines: { gone: null } },
      adoption: { ...adoption, baseline: { ...baseline, expense_lines: [] } },
    };
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [leaving] }));
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    expect(await screen.findByRole("group", { name: "Changes to the baseline" })).toBeTruthy();
    expect(screen.queryByText(/left out when the plan was adopted/)).toBeNull();
  });

  it("shows and counts no stale leave-out on an ordinary scenario", async () => {
    const stale = { ...scenario, changes: { ...scenario.changes, expense_lines: { gone: null } } };
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [stale] }));
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    expect(await screen.findByRole("group", { name: "Changes to the baseline" })).toBeTruthy();
    expect(screen.queryByText(/Left out/)).toBeNull();
  });

  it("offers no un-adopt on an earlier adopted plan", async () => {
    const later = { ...scenario, name: "Plan B", adoption: { ...adoption, sequence: 2 } };
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [adopted, later] }));
    start("/projects/abcdefabcdef/scenarios/Plan%20A", <ScenarioEditor />);
    expect(await screen.findByText(/An earlier adopted plan/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Un-adopt…" })).toBeNull();
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

  it("never gives a new line an id a scenario already uses", async () => {
    const leaving = {
      ...scenario,
      changes: { ...scenario.changes, expense_lines: { "line-1": null } },
    };
    mocked.getProject.mockResolvedValue(stored({ ...project, scenarios: [leaving] }));
    start("/projects/abcdefabcdef/baseline", <BaselineEditor />);
    await userEvent.click(await screen.findByRole("button", { name: "Add expense" }));
    await userEvent.click(screen.getByRole("button", { name: "Save baseline" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const lines = (mocked.saveProject.mock.calls[0]?.[1] as Project).baseline.expense_lines;
    expect(lines.map((l) => l.id)).toEqual(["operating", "line-2"]);
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
