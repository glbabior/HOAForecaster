import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "./App";
import { ApiError, api } from "./api";
import type { ExpenseLine, Facts, Project, Scenario, StoredProject } from "./types";

vi.mock("./api", async (importOriginal) => {
  const real = await importOriginal<typeof import("./api")>();
  return {
    ...real,
    api: {
      about: vi.fn(),
      getProject: vi.fn(),
      saveProject: vi.fn(),
      blankScenario: vi.fn(),
      run: vi.fn(),
      adopt: vi.fn(),
      unadopt: vi.fn(),
      results: vi.fn(),
    },
  };
});

type Mock = ReturnType<typeof vi.fn>;
const mocked = api as unknown as {
  about: Mock;
  getProject: Mock;
  saveProject: Mock;
  blankScenario: Mock;
  run: Mock;
  adopt: Mock;
  unadopt: Mock;
  results: Mock;
};

const years = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => from + i);

const facts: Facts = {
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
    {
      id: "roof",
      frequency: "once",
      year: 2029,
      amount: "80000",
      description: "Roof",
      source: "",
      nominal: false,
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
  ffb_from_lines: false,
};

const scenario = (name: string, change: Partial<Scenario> = {}): Scenario => ({
  name,
  description: "",
  facts: structuredClone(facts),
  dues: { mode: "rate", first_value: "600", annual_increase: "0.03", overrides: {} },
  assessments: [],
  rounding: "dollar",
  ...change,
});

function stored(project: Project, revision = 1): StoredProject {
  const t = { created: "2026-10-20T10:00:00+00:00", modified: "2026-10-20T10:00:00+00:00" };
  return {
    id: "abcdefabcdef",
    revision,
    times: t,
    scenario_times: Object.fromEntries(project.scenarios.map((s) => [s.name, t])),
    project,
  };
}

const projectOf = (...scenarios: Scenario[]): Project => ({
  schema_version: 3,
  name: "Demo",
  notes: "",
  scenarios,
});

let current: StoredProject;

function serve(project: Project) {
  current = stored(project);
}

/** The app's screens at `path`, as the app routes them. */
function start(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

const at = (router: ReturnType<typeof start>) => router.state.location.pathname;
/** The heading of a collapsible section – its summary, found by its title. */
const summaryOf = (title: string): HTMLElement =>
  screen.getByText(title, { selector: ".summary-title" }).closest("summary") as HTMLElement;
const lastSaved = (): Project => mocked.saveProject.mock.calls.at(-1)?.[1] as Project;
const savedScenario = (name: string): Scenario | undefined =>
  lastSaved().scenarios.find((s) => s.name === name);
const A = "/projects/abcdefabcdef/scenarios/Plan%20A";
const SLOW = { timeout: 3000 }; // edits save themselves 0.6 s after typing stops

beforeEach(() => {
  serve(projectOf(scenario("Plan A"), scenario("Plan B")));
  mocked.about.mockResolvedValue({ data_folder: "", version: "", can_restart: false });
  mocked.getProject.mockImplementation(async () => current);
  mocked.saveProject.mockImplementation(async (_id: string, p: Project, base: number) => {
    current = stored(p, base + 1);
    return current;
  });
  mocked.run.mockRejectedValue(
    new ApiError(422, "the inputs have problems", ["(results not under test)"]),
  );
  mocked.results.mockResolvedValue({ scenarios: {} });
});

afterEach(() => vi.clearAllMocks());

describe("a scenario's screens", () => {
  it("are listed under Scenarios in the index once a scenario is open", async () => {
    start(`${A}/facts`);
    const index = await screen.findByRole("list", { name: "Plan A – screens" });
    const links = within(index).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual([
      "Results",
      "Facts and assumptions",
      "Expenses",
      "Fully Funded Balance",
      "Dues",
      "Special assessments",
    ]);
    expect(links[2]?.getAttribute("href")).toBe(`${A}/expenses`);
    expect(
      within(index)
        .getByRole("link", { name: "Facts and assumptions" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("save an edit by themselves once typing stops", async () => {
    start(`${A}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    expect(savedScenario("Plan A")?.facts.units).toBe(12);
    expect(savedScenario("Plan B")?.facts.units).toBe(10); // the others as they were
    expect(await screen.findByText("All changes saved")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Save/ })).toBeNull(); // no Save button
  });

  it("keep one form across the screens", async () => {
    const router = start(`${A}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "14");
    await userEvent.click(screen.getByRole("link", { name: "Dues" }));
    expect(at(router)).toBe(`${A}/dues`);
    await screen.findByRole("textbox", { name: "Dues in 2027" });
    await userEvent.click(screen.getByRole("link", { name: "Facts and assumptions" }));
    expect(
      ((await screen.findByRole("textbox", { name: "Number of units" })) as HTMLInputElement).value,
    ).toBe("14");
    await waitFor(() => expect(savedScenario("Plan A")?.facts.units).toBe(14), SLOW);
  });

  it("do not save an entry that is not a number, and ask before leaving it", async () => {
    start(`${A}/facts`);
    const balance = await screen.findByRole("textbox", { name: "Starting reserve balance" });
    await userEvent.type(balance, "x");
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent ?? "");
    expect(alerts.some((t) => t.includes("Starting reserve balance"))).toBe(true);
    expect(await screen.findByText("Not saved yet – see below", {}, SLOW)).toBeTruthy();
    expect(mocked.saveProject).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("link", { name: "Expenses" }));
    expect(await screen.findByText("Leave this screen?")).toBeTruthy();
  });

  it("do not save a name another scenario has", async () => {
    start(`${A}/facts`);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan B");
    expect(await screen.findByText(/Another scenario is already called “Plan B”/)).toBeTruthy();
    await new Promise((r) => setTimeout(r, 900));
    expect(mocked.saveProject).not.toHaveBeenCalled();
  });

  it("rename the scenario, move its address and keep the form", async () => {
    const router = start(`${A}/facts`);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan C");
    await waitFor(
      () => expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/Plan%20C/facts"),
      SLOW,
    );
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan C", "Plan B"]);
    expect(await screen.findByRole("heading", { name: /Plan C/ })).toBeTruthy();
    // the same form – an edit after the rename saves on the renamed scenario
    const units = screen.getByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "11");
    await waitFor(() => expect(savedScenario("Plan C")?.facts.units).toBe(11), SLOW);
    expect(lastSaved().scenarios).toHaveLength(2);
  });

  it("stretch the Fully Funded Balance when the end year changes", async () => {
    start(`${A}/facts`);
    const end = await screen.findByRole("textbox", { name: "End year" });
    await userEvent.clear(end);
    await userEvent.type(end, "2033");
    await waitFor(() => expect(savedScenario("Plan A")?.facts.end_year).toBe(2033), SLOW);
    expect(savedScenario("Plan A")?.facts.ffb["2034"]).toBe("0");
    expect(savedScenario("Plan A")?.facts.ffb["2027"]).toBe("202700");
  });

  it("delete the scenario after asking, and go back to the list", async () => {
    const router = start(A);
    await userEvent.click(await screen.findByRole("button", { name: "Delete…" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(at(router)).toBe("/projects/abcdefabcdef/scenarios"));
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan B"]);
  });
});

describe("copying into other scenarios", () => {
  beforeEach(() => {
    const adopted = scenario("Adopted", {
      adoption: { date: "2026-10-01", note: "", sequence: 1 },
    });
    serve(projectOf(scenario("Plan A"), scenario("Plan B"), scenario("Plan C"), adopted));
  });

  it("copies a figure and its note into the scenarios chosen – All picks every open one", async () => {
    start(`${A}/facts`);
    const rate = await screen.findByRole("textbox", { name: "Interest earned on reserves" });
    await userEvent.clear(rate);
    await userEvent.type(rate, "4");
    await userEvent.type(
      screen.getByRole("textbox", { name: "Source – interest earned on reserves" }),
      "New bank",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Copy interest earned on reserves to other scenarios" }),
    );
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog)
        .getByRole("checkbox", { name: /Adopted/ })
        .matches(":disabled"),
    ).toBe(true);
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "All scenarios" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(savedScenario("Plan C")?.facts.interest_rate).toBe("0.04"));
    expect(savedScenario("Plan B")?.facts.sources.interest_rate).toBe("New bank");
    expect(savedScenario("Adopted")?.facts.interest_rate).toBe("0.02"); // read-only
    expect(await screen.findByText("Copied to Plan B, Plan C.")).toBeTruthy();
  });

  it("copies an expense line, replacing the same line in the chosen scenario", async () => {
    start(`${A}/expenses`);
    const amount = await screen.findByRole("textbox", { name: "Amount of expense 2" });
    await userEvent.clear(amount);
    await userEvent.type(amount, "95000");
    await userEvent.click(
      screen.getByRole("button", { name: "Copy expense 2 to other scenarios" }),
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Plan B" }));
    await userEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const b = savedScenario("Plan B");
    expect(b?.facts.expense_lines.map((l) => `${l.id} ${l.amount}`)).toEqual([
      "operating 50000",
      "roof 95000",
    ]);
    expect(savedScenario("Plan C")?.facts.expense_lines[1]?.amount).toBe("80000");
  });
});

describe("adopted plans", () => {
  const adopted = scenario("Plan A", {
    adoption: { date: "2026-11-03", note: "Board vote", sequence: 1 },
  });

  it("adopts the scenario with a date and a note", async () => {
    mocked.adopt.mockImplementation(async () => stored(projectOf(adopted, scenario("Plan B")), 2));
    start(A);
    await userEvent.click(await screen.findByRole("button", { name: "Adopt…" }));
    await userEvent.type(screen.getByRole("textbox", { name: /Note/ }), "Board vote");
    await userEvent.click(screen.getByRole("button", { name: "Adopt" }));
    await waitFor(() => expect(mocked.adopt).toHaveBeenCalled());
    const [, name, date, typed, revision] = mocked.adopt.mock.calls[0] ?? [];
    expect([name, typed, revision]).toEqual(["Plan A", "Board vote", 1]);
    expect(date).toMatch(/^\d{4}-\d\d-\d\d$/);
    expect(await screen.findByText(/The adopted plan/)).toBeTruthy();
  });

  it("opens read-only, with a way to revise it and to un-adopt it", async () => {
    serve(projectOf(adopted, scenario("Plan B")));
    mocked.unadopt.mockResolvedValue(stored(projectOf(scenario("Plan A"), scenario("Plan B")), 2));
    start(`${A}/facts`);
    expect(await screen.findByText(/adopted November 3, 2026\. Board vote/)).toBeTruthy();
    // disabled through its fieldset, which the element's own property does not show
    expect(screen.getByRole("textbox", { name: "Number of units" }).matches(":disabled")).toBe(
      true,
    );
    expect(screen.queryByRole("button", { name: /Copy .* to other scenarios/ })).toBeNull();
    expect(screen.queryByText("All changes saved")).toBeNull();
    expect(screen.getByRole("link", { name: "Copy as a new scenario" }).getAttribute("href")).toBe(
      "/projects/abcdefabcdef/scenarios/new?from=Plan%20A",
    );
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt" }));
    await waitFor(() => expect(mocked.unadopt).toHaveBeenCalledWith("abcdefabcdef", 1));
  });

  it("offers no un-adopt on an earlier adopted plan", async () => {
    const later = scenario("Plan B", { adoption: { date: "2027-01-01", note: "", sequence: 2 } });
    serve(projectOf(adopted, later));
    start(A);
    expect(await screen.findByText(/An earlier adopted plan/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Un-adopt…" })).toBeNull();
  });
});

describe("a new scenario", () => {
  it("starts blank from the server's defaults and opens on its facts", async () => {
    mocked.blankScenario.mockImplementation(async (name: string) => ({
      ...scenario(name),
      facts: { ...facts, units: 1 },
    }));
    const router = start("/projects/abcdefabcdef/scenarios/new");
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect((name as HTMLInputElement).value).toBe("New scenario");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/New%20scenario/facts"),
    );
    expect(mocked.blankScenario).toHaveBeenCalledWith("New scenario");
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan A", "Plan B", "New scenario"]);
  });

  it("copies every input of the scenario it starts from, but not its adoption", async () => {
    const own = scenario("Plan A", {
      facts: { ...facts, interest_rate: "0.04" },
      assessments: [{ year: 2029, amount: "100", note: "" }],
      adoption: { date: "2026-11-03", note: "", sequence: 1 },
    });
    serve(projectOf(own, scenario("Plan B")));
    const router = start("/projects/abcdefabcdef/scenarios/new?from=Plan%20A");
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect((name as HTMLInputElement).value).toBe("Plan A – copy");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/Plan%20A%20%E2%80%93%20copy"),
    );
    const copy = savedScenario("Plan A – copy");
    expect(copy?.facts.interest_rate).toBe("0.04");
    expect(copy?.assessments).toEqual(own.assessments);
    expect(copy?.adoption).toBeNull();
    expect(mocked.blankScenario).not.toHaveBeenCalled();
  });

  it("refuses a name another scenario has", async () => {
    start("/projects/abcdefabcdef/scenarios/new");
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan B");
    expect(screen.getByText("Another scenario already has this name")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Create" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});

describe("the project's screens", () => {
  it("open on Scenarios, the adopted plan first, then working scenarios, then earlier plans", async () => {
    const adopted = (name: string, sequence: number): Scenario =>
      scenario(name, { adoption: { date: "2026-10-01", note: "", sequence } });
    serve(projectOf(adopted("Old plan", 1), scenario("Plan A"), adopted("Plan now", 2)));
    const router = start("/projects/abcdefabcdef");
    const table = await screen.findByRole("table");
    expect(at(router)).toBe("/projects/abcdefabcdef/scenarios");
    const names = within(table)
      .getAllByRole("rowheader")
      .map((th) => within(th).getByRole("link").textContent);
    expect(names).toEqual(["Plan now", "Plan A", "Old plan"]);
    const index = screen.getByRole("navigation", { name: "Project screens" });
    expect(
      within(index)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Scenarios", "Compare", "Charts", "Export"]);
  });

  it("save the project's name and notes as they are typed", async () => {
    start("/projects/abcdefabcdef/scenarios");
    const notes = await screen.findByRole("textbox", { name: "Notes" });
    await userEvent.type(notes, "Board copy");
    await waitFor(() => expect(lastSaved().notes).toBe("Board copy"), SLOW);
    expect(lastSaved().scenarios).toHaveLength(2);
  });

  it("offer the workbook only with at least one scenario chosen", async () => {
    start("/projects/abcdefabcdef/export");
    const download = await screen.findByRole("button", { name: "Download the workbook" });
    expect((download as HTMLButtonElement).disabled).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: /All scenarios/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Plan A" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Plan B" }));
    expect((download as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("saving without a Save button", () => {
  it("lets a plan that is un-adopted be edited and saved again", async () => {
    const adopted = scenario("Plan A", { adoption: { date: "2026-11-03", note: "", sequence: 1 } });
    serve(projectOf(adopted, scenario("Plan B")));
    mocked.unadopt.mockImplementation(async () => {
      current = stored(projectOf(scenario("Plan A"), scenario("Plan B")), 2);
      return current;
    });
    start(`${A}/facts`);
    await userEvent.click(await screen.findByRole("button", { name: "Un-adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt" }));
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await waitFor(() => expect(units.matches(":disabled")).toBe(false));
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    await waitFor(() => expect(savedScenario("Plan A")?.facts.units).toBe(12), SLOW);
    expect(savedScenario("Plan A")?.adoption ?? null).toBeNull();
  });

  it("makes a save that another save beat again on the project as it now is", async () => {
    mocked.saveProject.mockRejectedValueOnce(new ApiError(409, "saved elsewhere"));
    start(`${A}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    current = stored(projectOf(scenario("Plan A"), scenario("Plan B", { description: "New" })), 5);
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalledTimes(2), SLOW);
    expect(mocked.saveProject.mock.calls[1]?.[2]).toBe(5);
    expect(savedScenario("Plan A")?.facts.units).toBe(12);
    expect(savedScenario("Plan B")?.description).toBe("New"); // the other save is kept
    expect(await screen.findByText("All changes saved")).toBeTruthy();
  });

  it("saves the last edit before adopting, so the plan adopted is the one on screen", async () => {
    mocked.adopt.mockImplementation(async () => current);
    start(`${A}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "13");
    await userEvent.click(screen.getByRole("button", { name: "Adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Adopt" }));
    await waitFor(() => expect(mocked.adopt).toHaveBeenCalled());
    expect(savedScenario("Plan A")?.facts.units).toBe(13);
    const saved = mocked.saveProject.mock.invocationCallOrder.at(-1) ?? 0;
    expect(saved).toBeLessThan(mocked.adopt.mock.invocationCallOrder[0] ?? 0);
  });

  it("copies a scenario with an edit made a moment before", async () => {
    const router = start(`${A}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "15");
    await userEvent.click(screen.getByRole("link", { name: "Copy as a new scenario" }));
    await userEvent.click(await screen.findByRole("button", { name: "Create" }));
    await waitFor(() => expect(at(router)).toMatch(/Plan%20A%20%E2%80%93%20copy$/), SLOW);
    expect(savedScenario("Plan A – copy")?.facts.units).toBe(15);
    expect(savedScenario("Plan A")?.facts.units).toBe(15);
  });

  it("offers no copy while an entry is not usable", async () => {
    start(`${A}/facts`);
    await userEvent.type(
      await screen.findByRole("textbox", { name: "Starting reserve balance" }),
      "x",
    );
    const copy = screen.getByRole("button", {
      name: "Copy starting reserve balance to other scenarios",
    });
    expect((copy as HTMLButtonElement).disabled).toBe(true);
  });

  it("gives a new expense an id no other scenario uses", async () => {
    const other = scenario("Plan B");
    const roof = other.facts.expense_lines.find((l) => l.id === "roof");
    if (roof) other.facts.expense_lines.push({ ...roof, id: "line-1" });
    serve(projectOf(scenario("Plan A"), other));
    start(`${A}/expenses`);
    await userEvent.click(await screen.findByRole("button", { name: "Add a one-time cost" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    expect(savedScenario("Plan A")?.facts.expense_lines.at(-1)?.id).toBe("line-2");
  });
});

describe("leaving with something unsaved", () => {
  it("asks when the name is another scenario's, since nothing after it is saved", async () => {
    start(`${A}/facts`);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan B");
    await userEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(await screen.findByText(/name is blank or another scenario's/)).toBeTruthy();
  });

  it("asks after a save failed, says so, and can try the save again", async () => {
    mocked.saveProject.mockRejectedValueOnce(new ApiError(500, "the data folder is busy"));
    start(`${A}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    expect(await screen.findByText("The data folder is busy", {}, SLOW)).toBeTruthy();
    await userEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(
      await screen.findByText("The last edit could not be saved – it will be lost."),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Try saving again" }));
    await waitFor(() => expect(savedScenario("Plan A")?.facts.units).toBe(12));
    expect(await screen.findByText("All changes saved")).toBeTruthy();
  });

  it("asks on Scenarios when the project has no name", async () => {
    start("/projects/abcdefabcdef/scenarios");
    await userEvent.clear(await screen.findByRole("textbox", { name: "Name" }));
    await userEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(await screen.findByText(/The project needs a name, so the changes/)).toBeTruthy();
  });
});

describe("the expense tables", () => {
  it("show each kind in a table of its own, and move a line when its kind changes", async () => {
    start(`${A}/expenses`);
    const once = await screen.findByRole("table", { name: "One-time costs" });
    expect(within(once).getByRole("textbox", { name: "Description of expense 2" })).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Monthly costs" })).toBeNull(); // none yet
    expect(summaryOf("Monthly costs").textContent).toBe("Monthly costs (0)");
    // a one-time cost has no last year or interval; a yearly one no "already inflated"
    expect(within(once).queryByRole("columnheader", { name: "Last year" })).toBeNull();
    const yearly = screen.getByRole("table", { name: "Yearly costs" });
    expect(within(yearly).queryByRole("columnheader", { name: "Already inflated?" })).toBeNull();
    await userEvent.selectOptions(
      within(once).getByRole("combobox", { name: "How often expense 2 falls" }),
      "every",
    );
    const every = screen.getByRole("table", { name: "Every few years" });
    expect(within(every).getByRole("textbox", { name: "Description of expense 2" })).toBeTruthy();
    expect(screen.queryByRole("table", { name: "One-time costs" })).toBeNull();
    await waitFor(
      () => expect(savedScenario("Plan A")?.facts.expense_lines[1]?.frequency).toBe("every"),
      SLOW,
    );
  });
});

describe("the expense tables' own tools", () => {
  const once = (id: string, year: number) => ({
    id,
    frequency: "once" as const,
    year,
    amount: "1",
    description: id,
    source: "",
    nominal: false,
  });
  const section = (title: string) => summaryOf(title).closest("details") as HTMLElement;

  it("take pasted rows as one-time costs before there are any", async () => {
    const empty = scenario("Plan A");
    empty.facts.expense_lines = [];
    serve(projectOf(empty, scenario("Plan B")));
    start(`${A}/expenses`);
    await screen.findByText("One-time costs", { selector: ".summary-title" });
    expect(summaryOf("One-time costs").textContent).toBe("One-time costs (0)");
    const text = ["2030\t12000\tGate\tno\tQuote", "2031\t5000\tPaint"].join("\n");
    fireEvent.paste(
      within(section("One-time costs")).getByRole("button", { name: "Add a one-time cost" }),
      {
        clipboardData: { getData: () => text },
      },
    );
    expect(await screen.findByText("Added 2 one-time costs from the clipboard.")).toBeTruthy();
    await waitFor(() => expect(savedScenario("Plan A")?.facts.expense_lines).toHaveLength(2), SLOW);
    expect(savedScenario("Plan A")?.facts.expense_lines.map((l) => l.year)).toEqual([2030, 2031]);
  });

  it("sort one kind by year within the places it holds, leaving the others where they are", async () => {
    const mixed = scenario("Plan A");
    const yearly = { ...(mixed.facts.expense_lines[0] as ExpenseLine), id: "y" };
    const every = { ...once("d", 2029), frequency: "every" as const, interval: 5, end_year: null };
    mixed.facts.expense_lines = [once("a", 2030), yearly, once("c", 2027), every, once("e", 2025)];
    serve(projectOf(mixed, scenario("Plan B")));
    start(`${A}/expenses`);
    await screen.findByText("One-time costs", { selector: ".summary-title" });
    expect(summaryOf("One-time costs").textContent).toBe("One-time costs (3)");
    await userEvent.click(
      within(section("One-time costs")).getByRole("button", { name: "Sort by year" }),
    );
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    expect(savedScenario("Plan A")?.facts.expense_lines.map((l) => l.id)).toEqual([
      "e",
      "y",
      "c",
      "d",
      "a",
    ]);
  });

  it("keep the keyboard on a line's choice after it moves to another table", async () => {
    start(`${A}/expenses`);
    const choice = await screen.findByRole("combobox", { name: "How often expense 2 falls" });
    await userEvent.selectOptions(choice, "every");
    await waitFor(() =>
      expect(document.activeElement?.getAttribute("aria-label")).toBe("How often expense 2 falls"),
    );
    expect(screen.getByText("Expense 2 moved to Every few years.")).toBeTruthy();
  });
});

describe("a worked-out Fully Funded Balance", () => {
  it("is chosen on its screen, shows the server's figures and keeps the typed ones", async () => {
    mocked.run.mockResolvedValue({
      years: [],
      summary: {
        lowest_balance: "0",
        lowest_balance_year: 2027,
        pf_end: "0.5",
        first_target_year: null,
        low_years: 0,
        vote_years: 0,
      },
      ffb: Object.fromEntries(years(2027, 2032).map((y) => [String(y), String(y * 10)])),
    });
    start(`${A}/ffb`);
    await userEvent.click(
      await screen.findByRole("radio", { name: /Worked out from this scenario's expenses/ }),
    );
    const table = await screen.findByRole("table", { name: "Fully Funded Balance, worked out" });
    expect(within(table).getByRole("row", { name: /2032/ }).textContent).toContain("$20,320");
    expect(
      screen.getByText(/0 of 1 reserve expenses count – 1 one-time cost has no useful life yet/),
    ).toBeTruthy();
    await waitFor(() => expect(savedScenario("Plan A")?.facts.ffb_from_lines).toBe(true), SLOW);
    expect(savedScenario("Plan A")?.facts.ffb["2027"]).toBe("202700"); // kept for switching back
  });

  it("takes a one-time cost's useful life", async () => {
    start(`${A}/expenses`);
    const life = await screen.findByRole("textbox", { name: "Useful life of expense 2 in years" });
    await userEvent.type(life, "30");
    await waitFor(
      () => expect(savedScenario("Plan A")?.facts.expense_lines[1]?.useful_life).toBe(30),
      SLOW,
    );
  });
});

describe("sortable tables", () => {
  it("sort by a header, then the other way, then back to the original order", async () => {
    serve(projectOf(scenario("Plan B"), scenario("Plan C"), scenario("Plan A")));
    start("/projects/abcdefabcdef/scenarios");
    const table = await screen.findByRole("table", { name: "Scenarios and their key results" });
    const names = () =>
      within(table)
        .getAllByRole("rowheader")
        .map((th) => within(th).getByRole("link").textContent);
    const heading = within(table).getByRole("columnheader", { name: "Scenario" });
    expect(heading.getAttribute("aria-sort")).toBeNull();
    await userEvent.click(within(heading).getByRole("button"));
    expect(names()).toEqual(["Plan A", "Plan B", "Plan C"]);
    expect(heading.getAttribute("aria-sort")).toBe("ascending");
    await userEvent.click(within(heading).getByRole("button"));
    expect(names()).toEqual(["Plan C", "Plan B", "Plan A"]);
    await userEvent.click(within(heading).getByRole("button"));
    expect(names()).toEqual(["Plan B", "Plan C", "Plan A"]);
    expect(heading.getAttribute("aria-sort")).toBeNull();
  });

  it("only reorder what is shown – an edit in a sorted table changes its own line", async () => {
    const two = scenario("Plan A");
    two.facts.expense_lines = [
      { id: "b", frequency: "yearly", year: null, amount: "900", description: "Big", source: "" },
      { id: "s", frequency: "yearly", year: null, amount: "100", description: "Small", source: "" },
    ];
    serve(projectOf(two, scenario("Plan B")));
    start(`${A}/expenses`);
    const yearly = await screen.findByRole("table", { name: "Yearly costs" });
    await userEvent.click(
      within(within(yearly).getByRole("columnheader", { name: "Amount a year" })).getByRole(
        "button",
      ),
    );
    const first = within(yearly).getAllByRole("textbox", { name: /^Description of expense/ })[0];
    expect((first as HTMLInputElement).value).toBe("Small");
    await userEvent.type(first as HTMLElement, "er");
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    // the saved order is untouched, and the edit went to the line it was typed in
    expect(savedScenario("Plan A")?.facts.expense_lines.map((l) => l.description)).toEqual([
      "Big",
      "Smaller",
    ]);
  });
});

describe("renaming a scenario", () => {
  it("is offered on a scenario's screens, refuses a blank or taken name, and moves the address", async () => {
    const router = start(`${A}/dues`);
    await userEvent.click(await screen.findByRole("button", { name: "Rename…" }));
    const box = screen.getByRole("textbox", { name: "New name" });
    await userEvent.clear(box);
    expect(screen.getByText("A scenario needs a name.")).toBeTruthy();
    await userEvent.type(box, "Plan B");
    expect(screen.getByText("Another scenario is already called “Plan B”.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    expect(screen.getByRole("textbox", { name: "New name" })).toBeTruthy(); // still open
    await userEvent.clear(box);
    await userEvent.type(box, "Steady dues{Enter}"); // Enter confirms
    await waitFor(
      () => expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/Steady%20dues/dues"),
      SLOW,
    );
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Steady dues", "Plan B"]);
  });

  it("waits while an entry is not usable, since nothing could be saved", async () => {
    start(`${A}/facts`);
    await userEvent.type(
      await screen.findByRole("textbox", { name: "Starting reserve balance" }),
      "x",
    );
    expect((screen.getByRole("button", { name: "Rename…" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("is not offered on an adopted plan", async () => {
    serve(
      projectOf(
        scenario("Plan A", { adoption: { date: "2026-11-03", note: "", sequence: 1 } }),
        scenario("Plan B"),
      ),
    );
    start(A);
    await screen.findByText(/The adopted plan/);
    expect(screen.queryByRole("button", { name: "Rename…" })).toBeNull();
  });
});

describe("sorted editable tables", () => {
  const sortBy = async (table: HTMLElement, name: string) =>
    userEvent.click(within(within(table).getByRole("columnheader", { name })).getByRole("button"));

  it("keep a row in place while a figure in it is typed, until the next click", async () => {
    const two = scenario("Plan A");
    two.facts.expense_lines = [
      { id: "b", frequency: "yearly", year: null, amount: "900", description: "Big", source: "" },
      { id: "s", frequency: "yearly", year: null, amount: "100", description: "Small", source: "" },
    ];
    serve(projectOf(two, scenario("Plan B")));
    start(`${A}/expenses`);
    const yearly = await screen.findByRole("table", { name: "Yearly costs" });
    await sortBy(yearly, "Amount a year");
    const amounts = () =>
      within(yearly)
        .getAllByRole("textbox", { name: /^Amount of expense/ })
        .map((b) => (b as HTMLInputElement).value);
    expect(amounts()).toEqual(["100", "900"]);
    const small = within(yearly).getByRole("textbox", { name: "Amount of expense 2" });
    await userEvent.clear(small);
    await userEvent.type(small, "1500"); // now the larger – but the row stays where it was
    expect(amounts()).toEqual(["1500", "900"]);
    await waitFor(
      () => expect(savedScenario("Plan A")?.facts.expense_lines[1]?.amount).toBe("1500"),
      SLOW,
    );
    await sortBy(yearly, "Amount a year"); // the next click sorts again – descending
    expect(amounts()).toEqual(["1,500", "900"]);
  });

  it("put yearless costs first when sorted by year, as the start year", async () => {
    const three = scenario("Plan A");
    three.facts.expense_lines = [
      { id: "a", frequency: "yearly", year: 2030, amount: "1", description: "Later", source: "" },
      {
        id: "b",
        frequency: "yearly",
        year: null,
        amount: "1",
        description: "From start",
        source: "",
      },
      { id: "c", frequency: "yearly", year: 2029, amount: "1", description: "Sooner", source: "" },
    ];
    serve(projectOf(three, scenario("Plan B")));
    start(`${A}/expenses`);
    const yearly = await screen.findByRole("table", { name: "Yearly costs" });
    await sortBy(yearly, "First year");
    const order = within(yearly)
      .getAllByRole("textbox", { name: /^Description of expense/ })
      .map((b) => (b as HTMLInputElement).value);
    expect(order).toEqual(["From start", "Sooner", "Later"]);
  });

  it("remove the assessment it shows, not the one in its saved place", async () => {
    const plan = scenario("Plan A", {
      assessments: [
        { year: 2030, amount: "500", note: "late" },
        { year: 2028, amount: "200", note: "early" },
      ],
    });
    serve(projectOf(plan, scenario("Plan B")));
    start(`${A}/assessments`);
    const table = await screen.findByRole("table", { name: "Special assessments" });
    await sortBy(table, "Year");
    const notes = within(table).getAllByRole("textbox", { name: /^Note for assessment/ });
    expect((notes[0] as HTMLInputElement).value).toBe("early");
    await userEvent.click(
      within(table).getAllByRole("button", { name: /^Remove assessment/ })[0] as HTMLElement,
    );
    await waitFor(() => expect(savedScenario("Plan A")?.assessments).toHaveLength(1), SLOW);
    expect(savedScenario("Plan A")?.assessments[0]?.note).toBe("late");
  });

  it("fill a pasted column down the years in the order shown", async () => {
    start(`${A}/ffb`);
    const table = await screen.findByRole("table", { name: "Fully Funded Balance by year" });
    await sortBy(table, "Start of year");
    await sortBy(table, "Start of year"); // descending – 2032 at the top
    const top = within(table).getByRole("textbox", {
      name: "Fully Funded Balance at the start of 2031",
    });
    fireEvent.focus(top);
    fireEvent.paste(top, { clipboardData: { getData: () => ["7", "8"].join("\n") } });
    await waitFor(() => expect(savedScenario("Plan A")?.facts.ffb["2031"]).toBe("7"), SLOW);
    expect(savedScenario("Plan A")?.facts.ffb["2030"]).toBe("8"); // the row shown below 2031
    expect(savedScenario("Plan A")?.facts.ffb["2032"]).toBe("203200");
  });
});
