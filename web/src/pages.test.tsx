import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { tableRows } from "./csv";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { routes } from "./App";
import { ApiError, api } from "./api";
import { savedTheme } from "./theme";
import { expensesOf } from "./template";
import type { ExpenseLine, ExpenseSet, Facts, Project, Scenario, StoredProject } from "./types";

vi.mock("./api", async (importOriginal) => {
  const real = await importOriginal<typeof import("./api")>();
  return {
    ...real,
    api: {
      about: vi.fn(),
      listProjects: vi.fn(),
      getProject: vi.fn(),
      saveProject: vi.fn(),
      blankScenario: vi.fn(),
      run: vi.fn(),
      runProject: vi.fn(),
      dismissNotes: vi.fn(),
      adopt: vi.fn(),
      unadopt: vi.fn(),
      results: vi.fn(),
      deleteProject: vi.fn(),
    },
  };
});

type Mock = ReturnType<typeof vi.fn>;
const mocked = api as unknown as {
  about: Mock;
  listProjects: Mock;
  getProject: Mock;
  saveProject: Mock;
  blankScenario: Mock;
  run: Mock;
  runProject: Mock;
  dismissNotes: Mock;
  adopt: Mock;
  unadopt: Mock;
  results: Mock;
  deleteProject: Mock;
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
  facts: null, // the project's
  dues: {
    mode: "rate",
    first_value: "600",
    increases: [{ first_year: null, last_year: null, rate: "0.03" }],
    overrides: {},
  },
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
    set_times: {},
    upgrade_notes: [],
    project,
  };
}

const projectOf = (...scenarios: Scenario[]): Project => ({
  schema_version: 4,
  name: "Demo",
  notes: "",
  facts: structuredClone(facts),
  expense_sets: [],
  expenses_from: null,
  expenses_edited: false,
  scenarios,
});
/** An adopted plan, keeping the facts it was adopted with. */
const frozen = (s: Scenario, sequence = 1, change: Partial<Facts> = {}): Scenario => ({
  ...s,
  facts: { ...structuredClone(facts), ...change },
  adoption: { date: "2026-11-03", note: "", sequence, ...(s.adoption ?? {}) },
});

let current: StoredProject;

function serve(project: Project) {
  current = stored(project);
}

/** Two scenarios on a project whose expenses are `lines`. */
function serveLines(lines: ExpenseLine[]) {
  const project = projectOf(scenario("Plan A"), scenario("Plan B"));
  project.facts.expense_lines = lines;
  serve(project);
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
const P = "/projects/abcdefabcdef";
const A = `${P}/scenarios/Plan%20A`;
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
  mocked.runProject.mockResolvedValue({ scenarios: {}, problems: [], ffb: {} });
});

afterEach(() => vi.clearAllMocks());

describe("the screens' theme", () => {
  afterEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("is light until the switch turns dark screens on, and stays as chosen", async () => {
    const { unmount } = render(
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: [A] })} />,
    );
    const dark = await screen.findByRole("switch", { name: "Dark screens" });
    expect(dark.getAttribute("aria-checked")).toBe("false");
    await userEvent.click(dark);
    expect(dark.getAttribute("aria-checked")).toBe("true");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(savedTheme()).toBe("dark"); // what the next visit opens with
    unmount();
    start(A);
    const again = await screen.findByRole("switch", { name: "Dark screens" });
    expect(again.getAttribute("aria-checked")).toBe("true");
    await userEvent.click(again);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(savedTheme()).toBe("light");
  });

  it("still opens light and switches when the browser keeps nothing", async () => {
    const refuse = () => {
      throw new DOMException("refused", "SecurityError");
    };
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(refuse);
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(refuse);
    try {
      expect(savedTheme()).toBe("light");
      start(A);
      const dark = await screen.findByRole("switch", { name: "Dark screens" });
      await userEvent.click(dark);
      expect(dark.getAttribute("aria-checked")).toBe("true");
      expect(document.documentElement.dataset.theme).toBe("dark");
    } finally {
      get.mockRestore();
      set.mockRestore();
    }
  });
});

describe("the project list", () => {
  afterEach(() => mocked.listProjects.mockReset());

  it("shows a card per project, the last saved first unless another order is chosen", async () => {
    const summary = (id: string, name: string, scenarios: number, modified: string) => ({
      id,
      name,
      scenarios,
      modified,
    });
    mocked.listProjects.mockResolvedValue({
      projects: [
        summary("aaaaaaaaaaaa", "Alder House", 3, "2026-10-01T10:00:00+00:00"),
        summary("bbbbbbbbbbbb", "Beech Court", 1, "2026-10-30T10:00:00+00:00"),
        summary("cccccccccccc", "Cedar Hall", 2, "2026-10-15T10:00:00+00:00"),
      ],
      unreadable: [],
    });
    start("/");
    const cards = await screen.findByRole("list", { name: "Saved projects" });
    const titles = () =>
      within(cards)
        .getAllByRole("link")
        .map((a) => a.textContent);
    expect(titles()).toEqual(["Beech Court", "Cedar Hall", "Alder House"]);
    expect(within(cards).getByText(/^1 scenario · saved/)).toBeTruthy();
    expect(within(cards).getByRole("link", { name: "Alder House" }).getAttribute("href")).toBe(
      "/projects/aaaaaaaaaaaa",
    );
    const sort = screen.getByRole("combobox", { name: "Sort" });
    await userEvent.selectOptions(sort, "Name (A–Z)");
    expect(titles()).toEqual(["Alder House", "Beech Court", "Cedar Hall"]);
    await userEvent.selectOptions(sort, "Scenarios (most first)");
    expect(titles()).toEqual(["Alder House", "Cedar Hall", "Beech Court"]);
  });
});

describe("a scenario's screens", () => {
  it("are tabs under the scenario's name – its funding only", async () => {
    start(`${A}/dues`);
    const index = await screen.findByRole("list", { name: "Plan A – screens" });
    // the tab names the screen; the heading still does, for printing and screen readers
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Plan A – Dues");
    const bar = screen.getByRole("navigation", { name: "Project screens" }).parentElement;
    expect(
      within(bar as HTMLElement)
        .getByRole("link", { name: "Demo" })
        .getAttribute("href"),
    ).toBe("/projects/abcdefabcdef");
    const links = within(index).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Results", "Dues", "Special assessments"]);
    expect(links[2]?.getAttribute("href")).toBe(`${A}/assessments`);
    expect(within(index).getByRole("link", { name: "Dues" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });

  it("save an edit by themselves once typing stops", async () => {
    start(`${A}/dues`);
    const description = await screen.findByRole("textbox", { name: "Description" });
    await userEvent.type(description, "Steady rises");
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    await waitFor(() => expect(savedScenario("Plan A")?.description).toBe("Steady rises"), SLOW);
    expect(savedScenario("Plan B")?.description).toBe(""); // the others as they were
    expect(lastSaved().facts).toEqual(facts); // the project's facts untouched
    expect(await screen.findByText("All changes saved")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Save/ })).toBeNull(); // no Save button
  });

  it("keep one form across the screens", async () => {
    const router = start(`${A}/dues`);
    const first = await screen.findByRole("textbox", { name: "Dues in 2027" });
    await userEvent.clear(first);
    await userEvent.type(first, "650");
    await userEvent.click(screen.getByRole("link", { name: "Special assessments" }));
    expect(at(router)).toBe(`${A}/assessments`);
    await screen.findByRole("table", { name: "Special assessments" });
    await userEvent.click(screen.getByRole("link", { name: "Dues" }));
    expect(
      ((await screen.findByRole("textbox", { name: "Dues in 2027" })) as HTMLInputElement).value,
    ).toBe("650");
    await waitFor(() => {
      const dues = savedScenario("Plan A")?.dues;
      expect(dues?.mode === "rate" && dues.first_value).toBe("650");
    }, SLOW);
  });

  it("do not save an entry that is not a number, and ask before leaving it", async () => {
    start(`${A}/dues`);
    const first = await screen.findByRole("textbox", { name: "Dues in 2027" });
    await userEvent.type(first, "x");
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent ?? "");
    expect(alerts.some((t) => t.includes("Dues in 2027"))).toBe(true);
    expect(await screen.findByText("Not saved yet – see below", {}, SLOW)).toBeTruthy();
    expect(mocked.saveProject).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("link", { name: "Special assessments" }));
    expect(await screen.findByText("Leave this screen?")).toBeTruthy();
  });

  it("do not save a name another scenario has, and say where to fix it", async () => {
    start(`${A}/dues`);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan B");
    expect(
      await screen.findByText(
        /Another scenario is already called “Plan B” – choose another name on Dues/,
      ),
    ).toBeTruthy();
    await new Promise((r) => setTimeout(r, 900));
    expect(mocked.saveProject).not.toHaveBeenCalled();
  });

  it("rename the scenario, move its address and keep the form", async () => {
    const router = start(`${A}/dues`);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan C");
    await waitFor(
      () => expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/Plan%20C/dues"),
      SLOW,
    );
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan C", "Plan B"]);
    expect(await screen.findByRole("heading", { name: /Plan C/ })).toBeTruthy();
    // the same form – an edit after the rename saves on the renamed scenario
    await userEvent.type(screen.getByRole("textbox", { name: "Description" }), "Renamed");
    await waitFor(() => expect(savedScenario("Plan C")?.description).toBe("Renamed"), SLOW);
    expect(lastSaved().scenarios).toHaveLength(2);
  });

  it("run an ordinary scenario on the project's facts", async () => {
    start(A);
    await waitFor(() => expect(mocked.run).toHaveBeenCalled());
    const [sent, withFacts] = mocked.run.mock.calls.at(-1) ?? [];
    expect((sent as Scenario).name).toBe("Plan A");
    expect((sent as Scenario).facts).toBeNull();
    expect(withFacts).toEqual(facts);
  });

  it("delete the scenario after asking, and go back to the list", async () => {
    const router = start(A);
    await userEvent.click(await screen.findByRole("button", { name: "Delete…" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(at(router)).toBe("/projects/abcdefabcdef/scenarios"));
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan B"]);
  });
});

describe("the project's facts and assumptions", () => {
  it("save an edit by themselves, for every scenario", async () => {
    start(`${P}/facts`);
    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe(
      "Facts and assumptions",
    );
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    await waitFor(() => expect(lastSaved().facts.units).toBe(12), SLOW);
    expect(lastSaved().scenarios.map((s) => s.facts)).toEqual([null, null]); // none of their own
    expect(await screen.findByText("All changes saved")).toBeTruthy();
    // every scenario's results are worked out on the facts as they are typed
    await waitFor(() =>
      expect((mocked.runProject.mock.calls.at(-1)?.[0] as Project).facts.units).toBe(12),
    );
    // and a scenario opened now runs on them
    await userEvent.click(
      within(screen.getByRole("complementary", { name: "Key results" })).getByRole("link", {
        name: "Plan B",
      }),
    );
    await waitFor(() =>
      expect(mocked.run).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Plan B", facts: null }),
        expect.objectContaining({ units: 12 }),
        expect.anything(),
      ),
    );
  });

  it("keep one form across the project's screens", async () => {
    start(`${P}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    await userEvent.clear(units);
    await userEvent.type(units, "14");
    await userEvent.click(screen.getByRole("link", { name: "Expenses" }));
    await screen.findByRole("region", { name: "Expense sets" });
    await userEvent.click(screen.getByRole("link", { name: "Facts and assumptions" }));
    expect(
      ((await screen.findByRole("textbox", { name: "Number of units" })) as HTMLInputElement).value,
    ).toBe("14");
    await waitFor(() => expect(lastSaved().facts.units).toBe(14), SLOW);
  });

  it("do not save an entry that is not a number, and ask before leaving it", async () => {
    start(`${P}/facts`);
    const balance = await screen.findByRole("textbox", { name: "Starting reserve balance" });
    await userEvent.type(balance, "x");
    const alerts = screen.getAllByRole("alert").map((a) => a.textContent ?? "");
    expect(alerts.some((t) => t.includes("Starting reserve balance"))).toBe(true);
    expect(await screen.findByText("Not saved yet – see below", {}, SLOW)).toBeTruthy();
    expect(mocked.saveProject).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("link", { name: "Expenses" }));
    expect(await screen.findByText("Leave this screen?")).toBeTruthy();
  });

  it("stretch the Fully Funded Balance and typed dues when the end year changes", async () => {
    const typed = scenario("Plan B", {
      dues: {
        mode: "explicit",
        explicit: { "2027": "600", "2028": "610", "2029": "620", "2030": "630", "2031": "650" },
      },
    });
    serve(projectOf(scenario("Plan A"), typed, frozen(scenario("Plan C"))));
    start(`${P}/facts`);
    const end = await screen.findByRole("textbox", { name: "End year" });
    await userEvent.clear(end);
    await userEvent.type(end, "2033");
    await waitFor(() => expect(lastSaved().facts.end_year).toBe(2033), SLOW);
    expect(lastSaved().facts.ffb["2034"]).toBe("0");
    expect(lastSaved().facts.ffb["2027"]).toBe("202700");
    const dues = savedScenario("Plan B")?.dues;
    expect(dues?.mode === "explicit" && dues.explicit["2033"]).toBe("650"); // the nearest earlier
    expect(savedScenario("Plan C")?.facts?.end_year).toBe(2031); // an adopted plan keeps its own
  });

  it("list every ordinary scenario's key results beside them, adopted plans apart", async () => {
    const lowA = ok(scenario("Plan A"));
    lowA.result.summary.lowest_balance = "-5000";
    lowA.result.summary.lowest_balance_year = 2029;
    lowA.result.summary.pf_end = "0.25";
    lowA.result.summary.low_years = 3;
    mocked.runProject.mockResolvedValue({
      scenarios: { "Plan A": lowA, "Plan B": { problems: ["the 2029 expense 'Roof' is odd"] } },
      problems: [],
      ffb: {},
    });
    serve(projectOf(scenario("Plan A"), scenario("Plan B"), frozen(scenario("Plan C"))));
    start(`${P}/expenses`);
    const aside = await screen.findByRole("complementary", { name: "Key results" });
    const rows = within(aside).getAllByRole("row").slice(1); // after the header
    expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual([
      "Plan A",
      "Plan B",
    ]);
    await waitFor(() =>
      expect(
        within(rows[0] as HTMLElement)
          .getAllByRole("cell")
          .map((c) => c.textContent),
      ).toEqual(["-$5,000 (2029)", "25.0%", "3"]),
    );
    expect(rows[1]?.textContent).toContain("Has problems");
    expect(within(aside).getByRole("link", { name: "Plan A" }).getAttribute("href")).toBe(A);
    expect(
      within(aside).getByText(/Adopted plans keep the facts they were adopted with/),
    ).toBeTruthy();
    expect(within(aside).getByText(/– Plan C\.$/)).toBeTruthy();
  });
});

describe("expense sets", () => {
  const studyB = (): ExpenseSet => ({
    name: "Study B",
    expense_lines: [
      {
        id: "lift",
        frequency: "once",
        year: 2030,
        amount: "40000",
        description: "Lift",
        source: "",
        nominal: false,
      },
    ],
    expense_base_year: 2025,
    ffb: { "2027": "1", "2033": "9" },
    ffb_from_lines: false,
    sources: { ffb: "Study B, table 3" },
    saved_inflation: "0.05",
  });
  /** The project with its expenses from Study A, which held only the roof. */
  const fromStudyA = (edited: boolean): Project => {
    const p = projectOf(scenario("Plan A"), scenario("Plan B"));
    const roofOnly = {
      ...facts,
      expense_lines: facts.expense_lines.filter((l) => l.id === "roof"),
    };
    p.expense_sets = [expensesOf(roofOnly, "Study A"), studyB()];
    p.expenses_from = "Study A";
    p.expenses_edited = edited;
    return p;
  };
  const panel = () => screen.findByRole("region", { name: "Expense sets" });

  it("save the expenses as a set under a name no other set has", async () => {
    const p = projectOf(scenario("Plan A"), scenario("Plan B"));
    p.expense_sets = [{ ...studyB(), name: "Old study" }];
    serve(p);
    start(`${P}/expenses`);
    const sets = await panel();
    expect(within(sets).getByText("These expenses are not saved as a set.")).toBeTruthy();
    await userEvent.click(within(sets).getByRole("button", { name: "Save as a set…" }));
    const dialog = screen.getByRole("dialog", { name: "Save these expenses as a set" });
    const box = within(dialog).getByRole("textbox", { name: "Name of the set" });
    await userEvent.clear(box);
    await userEvent.type(box, "Old study");
    expect(within(dialog).getByText("There is already a set called “Old study”.")).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(mocked.saveProject).not.toHaveBeenCalled();
    await userEvent.clear(box);
    await userEvent.type(box, "Study 2027");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled());
    const saved = lastSaved();
    expect(saved.expense_sets.map((s) => s.name)).toEqual(["Old study", "Study 2027"]);
    const set = saved.expense_sets[1];
    // an operating line from the start year keeps meaning 2027 whenever the set is loaded
    expect(set?.expense_lines.map((l) => `${l.id} ${l.year}`)).toEqual([
      "operating 2027",
      "roof 2029",
    ]);
    expect(set?.expense_base_year).toBe(2026);
    expect(set?.saved_inflation).toBe("0.03");
    expect([saved.expenses_from, saved.expenses_edited]).toEqual(["Study 2027", false]);
    expect(await within(sets).findByText("From the set “Study 2027”.")).toBeTruthy();
  });

  it("mark the expenses edited since their set was loaded, and save the changes back", async () => {
    const p = projectOf(scenario("Plan A"), scenario("Plan B"));
    p.expense_sets = [expensesOf(facts, "Study A")];
    p.expenses_from = "Study A";
    serve(p);
    start(`${P}/expenses`);
    const sets = await panel();
    expect(within(sets).getByText("From the set “Study A”.")).toBeTruthy();
    expect(within(sets).queryByRole("button", { name: /^Save changes/ })).toBeNull();
    const amount = screen.getByRole("textbox", { name: "Amount of expense 2" });
    await userEvent.clear(amount);
    await userEvent.type(amount, "95000");
    await waitFor(() => expect(lastSaved().expenses_edited).toBe(true), SLOW);
    expect(lastSaved().facts.expense_lines[1]?.amount).toBe("95000");
    expect(lastSaved().expense_sets[0]?.expense_lines[1]?.amount).toBe("80000"); // the set as it was
    expect(
      within(sets).getByText("From the set “Study A” – edited since it was loaded."),
    ).toBeTruthy();
    await userEvent.click(within(sets).getByRole("button", { name: "Save changes to “Study A”" }));
    await waitFor(() => expect(lastSaved().expenses_edited).toBe(false));
    expect(lastSaved().expense_sets[0]?.expense_lines[1]?.amount).toBe("95000");
  });

  it("load a set, first keeping the edited expenses as a new set, and take its rate", async () => {
    serve(fromStudyA(true));
    start(`${P}/expenses`);
    const sets = await panel();
    await userEvent.click(within(sets).getByRole("button", { name: "Load Study B" }));
    const dialog = screen.getByRole("dialog", { name: "Load “Study B”?" });
    const keep = within(dialog).getByRole("group", {
      name: "The expenses have been edited since “Study A” was loaded",
    });
    expect(
      (
        within(keep).getByRole("radio", {
          name: "Save the changes to “Study A”",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    await userEvent.click(within(keep).getByRole("radio", { name: "Save them as a new set" }));
    const name = within(dialog).getByRole("textbox", { name: "Name of the new set" });
    await userEvent.clear(name);
    await userEvent.type(name, "Kept");
    const rate = within(dialog).getByRole("checkbox", {
      name: /This set was saved with 5\.0% reserve inflation – the project uses 3\.0%/,
    });
    expect((rate as HTMLInputElement).checked).toBe(true);
    await userEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study B"));
    const saved = lastSaved();
    expect(saved.expenses_edited).toBe(false);
    expect(saved.expense_sets.map((s) => s.name)).toEqual(["Study A", "Study B", "Kept"]);
    expect(saved.expense_sets[0]?.expense_lines.map((l) => l.id)).toEqual(["roof"]); // untouched
    expect(saved.expense_sets[2]?.expense_lines.map((l) => l.id)).toEqual(["operating", "roof"]);
    expect(saved.facts.expense_lines.map((l) => l.id)).toEqual(["lift"]);
    expect(saved.facts.expense_base_year).toBe(2025);
    expect(saved.facts.expense_inflation).toBe("0.05");
    // the set's years replace the project's; the years it lacks are kept
    expect([saved.facts.ffb["2027"], saved.facts.ffb["2028"], saved.facts.ffb["2033"]]).toEqual([
      "1",
      "202800",
      "9",
    ]);
    expect(saved.facts.sources.ffb).toBe("Study B, table 3");
    // the screen shows the loaded expenses
    expect(
      (
        (await screen.findByRole("textbox", {
          name: "Description of expense 1",
        })) as HTMLInputElement
      ).value,
    ).toBe("Lift");
    expect(await within(sets).findByText("From the set “Study B”.")).toBeTruthy();
  });

  it("load a set, saving the changes to the set they came from and keeping the rate", async () => {
    serve(fromStudyA(true));
    start(`${P}/expenses`);
    await userEvent.click(within(await panel()).getByRole("button", { name: "Load Study B" }));
    const dialog = screen.getByRole("dialog", { name: "Load “Study B”?" });
    await userEvent.click(
      within(dialog).getByRole("checkbox", { name: /This set was saved with/ }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study B"));
    const saved = lastSaved();
    expect(saved.expense_sets.map((s) => s.name)).toEqual(["Study A", "Study B"]);
    expect(saved.expense_sets[0]?.expense_lines.map((l) => l.id)).toEqual(["operating", "roof"]);
    expect(saved.facts.expense_inflation).toBe("0.03");
  });

  it("load a set, discarding the changes", async () => {
    serve(fromStudyA(true));
    start(`${P}/expenses`);
    await userEvent.click(within(await panel()).getByRole("button", { name: "Load Study B" }));
    const dialog = screen.getByRole("dialog", { name: "Load “Study B”?" });
    await userEvent.click(within(dialog).getByRole("radio", { name: "Discard them" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study B"));
    expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Study A", "Study B"]);
    expect(lastSaved().expense_sets[0]?.expense_lines.map((l) => l.id)).toEqual(["roof"]);
    expect(lastSaved().facts.expense_lines.map((l) => l.id)).toEqual(["lift"]);
  });

  it("load a set straight away when the expenses are that set unchanged", async () => {
    const p = fromStudyA(false);
    p.facts.expense_lines = p.facts.expense_lines.filter((l) => l.id === "roof"); // Study A itself
    serve(p);
    start(`${P}/expenses`);
    await userEvent.click(within(await panel()).getByRole("button", { name: "Load Study B" }));
    const dialog = screen.getByRole("dialog", { name: "Load “Study B”?" });
    expect(within(dialog).queryByRole("group")).toBeNull(); // nothing to keep
    await userEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study B"));
    expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Study A", "Study B"]);
  });

  it("offer to save expenses from no set before loading one", async () => {
    const p = projectOf(scenario("Plan A"), scenario("Plan B"));
    p.expense_sets = [studyB()];
    serve(p);
    start(`${P}/expenses`);
    await userEvent.click(within(await panel()).getByRole("button", { name: "Load Study B" }));
    const dialog = screen.getByRole("dialog", { name: "Load “Study B”?" });
    const name = within(dialog).getByRole("textbox", { name: "Name of the set" });
    await userEvent.clear(name);
    await userEvent.type(name, "As they were");
    await userEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study B"));
    expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Study B", "As they were"]);
    expect(lastSaved().expense_sets[1]?.expense_lines.map((l) => l.id)).toEqual([
      "operating",
      "roof",
    ]);
  });

  it("load a set without saving expenses from no set first, when told not to", async () => {
    const p = projectOf(scenario("Plan A"), scenario("Plan B"));
    p.expense_sets = [studyB()];
    serve(p);
    start(`${P}/expenses`);
    await userEvent.click(within(await panel()).getByRole("button", { name: "Load Study B" }));
    const dialog = screen.getByRole("dialog", { name: "Load “Study B”?" });
    await userEvent.click(within(dialog).getByRole("checkbox", { name: /First save the current/ }));
    expect(within(dialog).queryByRole("textbox", { name: "Name of the set" })).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Load" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study B"));
    expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Study B"]);
  });

  it("rename a set, refusing a blank or taken name, and delete one", async () => {
    serve(fromStudyA(false));
    start(`${P}/expenses`);
    const sets = await panel();
    await userEvent.click(within(sets).getByRole("button", { name: "Rename Study A" }));
    const dialog = screen.getByRole("dialog", { name: "Rename the set" });
    const box = within(dialog).getByRole("textbox", { name: "New name" });
    await userEvent.clear(box);
    expect(within(dialog).getByText("A set needs a name.")).toBeTruthy();
    await userEvent.type(box, "Study B");
    expect(within(dialog).getByText("There is already a set called “Study B”.")).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Rename" }));
    expect(mocked.saveProject).not.toHaveBeenCalled();
    await userEvent.clear(box);
    await userEvent.type(box, "Study 2026");
    await userEvent.click(within(dialog).getByRole("button", { name: "Rename" }));
    await waitFor(() => expect(lastSaved().expenses_from).toBe("Study 2026"));
    expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Study 2026", "Study B"]);
    // deleting the set the expenses came from asks first, then leaves them as they are
    await userEvent.click(await within(sets).findByRole("button", { name: "Delete Study 2026" }));
    const asked = screen.getByRole("dialog", { name: "Delete the set “Study 2026”?" });
    expect(within(asked).getByText(/no longer from a saved set/)).toBeTruthy();
    await userEvent.click(within(asked).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Study B"]));
    expect(lastSaved().expenses_from).toBeNull();
    expect(lastSaved().facts.expense_lines.map((l) => l.id)).toEqual(["operating", "roof"]);
    expect(await within(sets).findByText("These expenses are not saved as a set.")).toBeTruthy();
  });
});

describe("adopted plans", () => {
  const adopted = frozen(
    scenario("Plan A", { adoption: { date: "2026-11-03", note: "Board vote", sequence: 1 } }),
    1,
    { units: 8 },
  );

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

  it("open read-only, its frozen facts on tabs of their own, with a way to revise and un-adopt", async () => {
    serve(projectOf(adopted, scenario("Plan B")));
    mocked.unadopt.mockResolvedValue(stored(projectOf(scenario("Plan A"), scenario("Plan B")), 2));
    start(`${A}/facts`);
    expect(await screen.findByText(/adopted November 3, 2026\. Board vote/)).toBeTruthy();
    const tabs = screen.getByRole("list", { name: "Plan A – screens" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual([
      "Results",
      "Facts and assumptions",
      "Expenses",
      "Fully Funded Balance",
      "Dues",
      "Special assessments",
    ]);
    // the facts it was adopted with, not the project's – disabled through its fieldset
    const units = screen.getByRole("textbox", { name: "Number of units" });
    expect((units as HTMLInputElement).value).toBe("8");
    expect(units.matches(":disabled")).toBe(true);
    expect(screen.getByText(/The facts and expenses this plan was adopted with/)).toBeTruthy();
    await userEvent.click(within(tabs).getByRole("link", { name: "Expenses" }));
    const amount = await screen.findByRole("textbox", { name: "Amount of expense 2" });
    expect(amount.matches(":disabled")).toBe(true);
    // its sets panel only saves its frozen expenses as a set – nothing loads into it
    const sets = screen.getByRole("region", { name: "Expense sets" });
    expect(within(sets).queryByRole("button", { name: /^Load/ })).toBeNull();
    expect(
      within(sets).getByRole("button", { name: "Save these expenses as a set…" }),
    ).toBeTruthy();
    await userEvent.click(within(tabs).getByRole("link", { name: "Fully Funded Balance" }));
    const typed = await screen.findByRole("radio", { name: /The reserve study's figures/ });
    expect(typed.matches(":disabled")).toBe(true);
    expect(screen.queryByText("All changes saved")).toBeNull();
    expect(screen.getByRole("link", { name: "Copy as a new scenario" }).getAttribute("href")).toBe(
      "/projects/abcdefabcdef/scenarios/new?from=Plan%20A",
    );
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt" }));
    await waitFor(() => expect(mocked.unadopt).toHaveBeenCalledWith("abcdefabcdef", 1));
    expect(mocked.saveProject).not.toHaveBeenCalled();
  });

  it("run on the facts they were adopted with", async () => {
    serve(projectOf(adopted, scenario("Plan B")));
    start(A);
    await waitFor(() => expect(mocked.run).toHaveBeenCalled());
    const [sent, withFacts] = mocked.run.mock.calls.at(-1) ?? [];
    expect((sent as Scenario).facts?.units).toBe(8);
    expect(withFacts).toBeNull();
  });

  it("offers no un-adopt on an earlier adopted plan", async () => {
    const later = frozen(scenario("Plan B"), 2);
    serve(projectOf(adopted, later));
    start(A);
    expect(await screen.findByText(/An earlier adopted plan/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Un-adopt…" })).toBeNull();
  });
});

describe("a new scenario", () => {
  it("starts blank from the server's defaults and the current dues, and opens on Dues", async () => {
    mocked.blankScenario.mockImplementation(async (name: string) => scenario(name));
    const router = start("/projects/abcdefabcdef/scenarios/new");
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect((name as HTMLInputElement).value).toBe("New scenario");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/New%20scenario/dues"),
    );
    expect(mocked.blankScenario).toHaveBeenCalledWith("New scenario", "500");
    expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan A", "Plan B", "New scenario"]);
  });

  it("copies the funding of the scenario it starts from, but not its facts or adoption", async () => {
    const own = frozen(
      scenario("Plan A", {
        description: "Steady rises",
        assessments: [{ year: 2029, amount: "100", note: "" }],
      }),
      1,
      { interest_rate: "0.04" },
    );
    serve(projectOf(own, scenario("Plan B")));
    const router = start("/projects/abcdefabcdef/scenarios/new?from=Plan%20A");
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect((name as HTMLInputElement).value).toBe("Plan A – copy");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/Plan%20A%20%E2%80%93%20copy"),
    );
    const copy = savedScenario("Plan A – copy");
    expect(copy?.facts).toBeNull(); // the project's, even from an adopted plan
    expect(copy?.dues).toEqual(own.dues);
    expect(copy?.assessments).toEqual(own.assessments);
    expect(copy?.description).toBe("Steady rises");
    expect(copy?.adoption).toBeNull();
    expect(mocked.blankScenario).not.toHaveBeenCalled();
    // the same years – nothing to carry over
    expect(mocked.run).not.toHaveBeenCalledWith(expect.objectContaining({ name: "Plan A" }), null);
  });

  it("carries the dues of an adopted plan of other years into the project's start year", async () => {
    const old = frozen(scenario("Old plan"), 1, { start_year: 2025, end_year: 2029 });
    serve(projectOf(old, scenario("Plan B")));
    mocked.run.mockImplementation(async (s: Scenario) => {
      if (s.name !== "Old plan") throw new ApiError(422, "not under test", ["not under test"]);
      return {
        years: [
          { year: 2025, dues: "600" },
          { year: 2026, dues: "618" },
          { year: 2027, dues: "637" },
        ],
      };
    });
    const router = start("/projects/abcdefabcdef/scenarios/new?from=Old%20plan");
    await userEvent.click(await screen.findByRole("button", { name: "Create" }));
    await waitFor(() =>
      expect(at(router)).toBe("/projects/abcdefabcdef/scenarios/Old%20plan%20%E2%80%93%20copy"),
    );
    expect(mocked.run).toHaveBeenCalledWith(expect.objectContaining({ name: "Old plan" }), null);
    const dues = savedScenario("Old plan – copy")?.dues;
    expect(dues?.mode === "rate" && dues.first_value).toBe("637"); // what it charged in 2027
    expect(dues?.mode === "rate" && dues.increases).toEqual(
      old.dues.mode === "rate" ? old.dues.increases : null,
    );
  });

  it("starts from the card chosen, the suggested name following the choice", async () => {
    serve(
      projectOf(frozen(scenario("Plan A")), scenario("Plan B", { description: "Steady rises" })),
    );
    const router = start("/projects/abcdefabcdef/scenarios/new");
    const choices = await screen.findByRole("group", { name: "Start from" });
    const cards = within(choices).getAllByRole("radio");
    // blank first, then the adopted plan, then the rest in the project's order – each named by
    // its title, the line under it its description
    expect(cards.map((c) => c.getAttribute("aria-labelledby"))).toHaveLength(3);
    const blank = within(choices).getByRole("radio", { name: "A blank scenario" });
    const plan = within(choices).getByRole("radio", { name: "Plan A" });
    const planB = within(choices).getByRole("radio", { name: "Plan B" });
    expect(cards).toEqual([blank, plan, planB]);
    expect(document.getElementById(plan.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "The adopted plan",
    );
    expect(document.getElementById(planB.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Steady rises",
    );
    expect((blank as HTMLInputElement).checked).toBe(true);
    await userEvent.click(planB);
    expect(router.state.location.search).toBe("?from=Plan+B");
    expect((screen.getByRole("textbox", { name: "Name" }) as HTMLInputElement).value).toBe(
      "Plan B – copy",
    );
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
  afterEach(() => mocked.listProjects.mockReset());

  it("open on Scenarios, listed in the project's order", async () => {
    serve(
      projectOf(
        frozen(scenario("Old plan"), 1),
        scenario("Plan A"),
        frozen(scenario("Plan now"), 2),
      ),
    );
    const router = start("/projects/abcdefabcdef");
    const table = await screen.findByRole("table");
    expect(at(router)).toBe("/projects/abcdefabcdef/scenarios");
    const names = within(table)
      .getAllByRole("rowheader")
      .map((th) => within(th).getByRole("link").textContent);
    expect(names).toEqual(["Old plan", "Plan A", "Plan now"]);
    const index = screen.getByRole("navigation", { name: "Project screens" });
    const links = within(index).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual([
      "Scenarios",
      "Facts and assumptions",
      "Expenses",
      "Fully Funded Balance",
      "Compare",
      "Charts",
      "Export",
    ]);
    expect(links[2]?.getAttribute("href")).toBe(`${P}/expenses`);
  });

  it("say what the upgrade changed until it is dismissed", async () => {
    current = {
      ...current,
      upgrade_notes: ["Plan B's expenses differed – they are kept as the set “Plan B expenses”."],
    };
    mocked.dismissNotes.mockImplementation(async (_id: string, revision: number) => {
      current = { ...current, revision: revision + 1, upgrade_notes: [] };
      return current;
    });
    start("/projects/abcdefabcdef/scenarios");
    const notes = await screen.findByRole("region", { name: "What changed in this version" });
    expect(within(notes).getByRole("listitem").textContent).toBe(
      "Plan B's expenses differed – they are kept as the set “Plan B expenses”.",
    );
    await userEvent.click(within(notes).getByRole("button", { name: "Dismiss" }));
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "What changed in this version" })).toBeNull(),
    );
    expect(mocked.dismissNotes).toHaveBeenCalledWith("abcdefabcdef", 1);
  });

  it("delete the project, once asked, and go back to the projects", async () => {
    mocked.deleteProject.mockResolvedValue(undefined);
    mocked.listProjects.mockResolvedValue({ projects: [], unreadable: [] });
    const router = start("/projects/abcdefabcdef/scenarios");
    await userEvent.click(await screen.findByRole("button", { name: "Delete this project…" }));
    const dialog = screen.getByRole("dialog", { name: "Delete Demo?" });
    expect(within(dialog).getByText(/moves to the trash folder/)).toBeTruthy();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mocked.deleteProject).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete this project…" }));
    await userEvent.click(
      within(screen.getByRole("dialog", { name: "Delete Demo?" })).getByRole("button", {
        name: "Delete",
      }),
    );
    await waitFor(() => expect(at(router)).toBe("/"));
    expect(mocked.deleteProject).toHaveBeenCalledWith("abcdefabcdef");
  });

  it("delete the project without asking to keep a name that could not be saved", async () => {
    mocked.deleteProject.mockResolvedValue(undefined);
    mocked.listProjects.mockResolvedValue({ projects: [], unreadable: [] });
    const router = start("/projects/abcdefabcdef/scenarios");
    await userEvent.clear(await screen.findByRole("textbox", { name: "Name" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete this project…" }));
    await userEvent.click(
      within(screen.getByRole("dialog", { name: "Delete Demo?" })).getByRole("button", {
        name: "Delete",
      }),
    );
    await waitFor(() => expect(at(router)).toBe("/"));
    expect(screen.queryByRole("dialog", { name: "Leave this screen?" })).toBeNull();
  });

  it("stay on the project, saying why, when it cannot be deleted", async () => {
    mocked.deleteProject.mockRejectedValue(new ApiError(500, "the project could not be moved"));
    const router = start("/projects/abcdefabcdef/scenarios");
    await userEvent.click(await screen.findByRole("button", { name: "Delete this project…" }));
    await userEvent.click(
      within(screen.getByRole("dialog", { name: "Delete Demo?" })).getByRole("button", {
        name: "Delete",
      }),
    );
    expect(await screen.findByText(/the project could not be moved/i)).toBeTruthy();
    expect(at(router)).toBe("/projects/abcdefabcdef/scenarios");
  });
  it("move a scenario in the project's order, and Compare follows it", async () => {
    serve(projectOf(scenario("Plan A"), scenario("Plan B"), scenario("Plan C")));
    mocked.results.mockResolvedValue({
      scenarios: Object.fromEntries(
        ["Plan A", "Plan B", "Plan C"].map((n) => [n, ok(scenario(n))]),
      ),
    });
    start("/projects/abcdefabcdef/scenarios");
    const down = await screen.findByRole("button", { name: "Move Plan A down" });
    expect(
      (screen.getByRole("button", { name: "Move Plan A up" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await userEvent.click(down);
    await waitFor(() =>
      expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan B", "Plan A", "Plan C"]),
    );
    await userEvent.click(screen.getByRole("link", { name: "Compare" }));
    const table = await screen.findByRole("table", { name: "Summary measures by scenario" });
    const heads = () =>
      within(table)
        .getAllByRole("columnheader")
        .map((th) => th.firstChild?.textContent);
    await waitFor(() => expect(heads()).toEqual(["Measure", "Plan B", "Plan A", "Plan C"]));
    // the first column is the one differences are from
    await userEvent.click(screen.getByRole("button", { name: "Move Plan C left" }));
    await waitFor(() =>
      expect(lastSaved().scenarios.map((s) => s.name)).toEqual(["Plan B", "Plan C", "Plan A"]),
    );
    await waitFor(() => expect(heads()).toEqual(["Measure", "Plan B", "Plan C", "Plan A"]));
    // a sortable header's CSV is its label alone – not its sort mark or its printed copy
    const byYear = screen.getByRole("table", { name: "Year-end reserve balance by year" });
    expect(tableRows(byYear as HTMLTableElement)[0]).toEqual([
      "Year",
      "Plan B",
      "Plan C",
      "Plan A",
    ]);
    expect(screen.getByRole("checkbox", { name: /Show differences from Plan B/ })).toBeTruthy();
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
    serve(projectOf(frozen(scenario("Plan A")), scenario("Plan B")));
    mocked.unadopt.mockImplementation(async () => {
      current = stored(projectOf(scenario("Plan A"), scenario("Plan B")), 2);
      return current;
    });
    start(`${A}/dues`);
    await userEvent.click(await screen.findByRole("button", { name: "Un-adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt" }));
    const description = await screen.findByRole("textbox", { name: "Description" });
    await waitFor(() => expect(description.matches(":disabled")).toBe(false));
    await userEvent.type(description, "Revised");
    await waitFor(() => expect(savedScenario("Plan A")?.description).toBe("Revised"), SLOW);
    expect(savedScenario("Plan A")?.adoption ?? null).toBeNull();
    expect(savedScenario("Plan A")?.facts).toBeNull();
  });

  it("makes a save that another save beat again on the project as it now is", async () => {
    mocked.saveProject.mockRejectedValueOnce(new ApiError(409, "saved elsewhere"));
    start(`${A}/dues`);
    const description = await screen.findByRole("textbox", { name: "Description" });
    current = stored(projectOf(scenario("Plan A"), scenario("Plan B", { description: "New" })), 5);
    await userEvent.type(description, "Mine");
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalledTimes(2), SLOW);
    expect(mocked.saveProject.mock.calls[1]?.[2]).toBe(5);
    expect(savedScenario("Plan A")?.description).toBe("Mine");
    expect(savedScenario("Plan B")?.description).toBe("New"); // the other save is kept
    expect(await screen.findByText("All changes saved")).toBeTruthy();
  });

  it("makes a facts edit that another save beat again on the project as it now is", async () => {
    mocked.saveProject.mockRejectedValueOnce(new ApiError(409, "saved elsewhere"));
    start(`${P}/facts`);
    const units = await screen.findByRole("textbox", { name: "Number of units" });
    current = stored(projectOf(scenario("Plan A"), scenario("Plan B", { description: "New" })), 5);
    await userEvent.clear(units);
    await userEvent.type(units, "12");
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalledTimes(2), SLOW);
    expect(mocked.saveProject.mock.calls[1]?.[2]).toBe(5);
    expect(lastSaved().facts.units).toBe(12);
    expect(savedScenario("Plan B")?.description).toBe("New");
  });

  it("saves the last edit before adopting, so the plan adopted is the one on screen", async () => {
    mocked.adopt.mockImplementation(async () => current);
    start(`${A}/dues`);
    await userEvent.type(await screen.findByRole("textbox", { name: "Description" }), "Pick");
    await userEvent.click(screen.getByRole("button", { name: "Adopt…" }));
    await userEvent.click(screen.getByRole("button", { name: "Adopt" }));
    await waitFor(() => expect(mocked.adopt).toHaveBeenCalled());
    expect(savedScenario("Plan A")?.description).toBe("Pick");
    const saved = mocked.saveProject.mock.invocationCallOrder.at(-1) ?? 0;
    expect(saved).toBeLessThan(mocked.adopt.mock.invocationCallOrder[0] ?? 0);
  });

  it("copies a scenario with an edit made a moment before", async () => {
    const router = start(`${A}/dues`);
    await userEvent.type(await screen.findByRole("textbox", { name: "Description" }), "Fresh");
    await userEvent.click(screen.getByRole("link", { name: "Copy as a new scenario" }));
    await userEvent.click(await screen.findByRole("button", { name: "Create" }));
    await waitFor(() => expect(at(router)).toMatch(/Plan%20A%20%E2%80%93%20copy$/), SLOW);
    expect(savedScenario("Plan A – copy")?.description).toBe("Fresh");
    expect(savedScenario("Plan A")?.description).toBe("Fresh");
  });

  it("gives a new expense an id no adopted plan's expenses use", async () => {
    const plan = frozen(scenario("Plan B"));
    const roof = plan.facts?.expense_lines.find((l) => l.id === "roof");
    if (roof) plan.facts?.expense_lines.push({ ...roof, id: "line-1" });
    serve(projectOf(scenario("Plan A"), plan));
    start(`${P}/expenses`);
    await userEvent.click(await screen.findByRole("button", { name: "Add a one-time cost" }));
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    expect(lastSaved().facts.expense_lines.at(-1)?.id).toBe("line-2");
  });
});

describe("leaving with something unsaved", () => {
  it("asks when the name is another scenario's, since nothing after it is saved", async () => {
    start(`${A}/dues`);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Plan B");
    await userEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(await screen.findByText(/name is blank or another scenario's/)).toBeTruthy();
  });

  it("asks after a save failed, says so, and can try the save again", async () => {
    mocked.saveProject.mockRejectedValueOnce(new ApiError(500, "the data folder is busy"));
    start(`${A}/dues`);
    await userEvent.type(await screen.findByRole("textbox", { name: "Description" }), "Steady");
    expect(await screen.findByText("The data folder is busy", {}, SLOW)).toBeTruthy();
    await userEvent.click(screen.getByRole("link", { name: "Compare" }));
    expect(
      await screen.findByText("The last edit could not be saved – it will be lost."),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Try saving again" }));
    await waitFor(() => expect(savedScenario("Plan A")?.description).toBe("Steady"));
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
    start(`${P}/expenses`);
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
    await waitFor(() => expect(lastSaved().facts.expense_lines[1]?.frequency).toBe("every"), SLOW);
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
    serveLines([]);
    start(`${P}/expenses`);
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
    await waitFor(() => expect(lastSaved().facts.expense_lines).toHaveLength(2), SLOW);
    expect(lastSaved().facts.expense_lines.map((l) => l.year)).toEqual([2030, 2031]);
  });

  it("sort one kind by year within the places it holds, leaving the others where they are", async () => {
    const yearly = { ...(facts.expense_lines[0] as ExpenseLine), id: "y" };
    const every = { ...once("d", 2029), frequency: "every" as const, interval: 5, end_year: null };
    serveLines([once("a", 2030), yearly, once("c", 2027), every, once("e", 2025)]);
    start(`${P}/expenses`);
    await screen.findByText("One-time costs", { selector: ".summary-title" });
    expect(summaryOf("One-time costs").textContent).toBe("One-time costs (3)");
    await userEvent.click(
      within(section("One-time costs")).getByRole("button", { name: "Sort by year" }),
    );
    await waitFor(() => expect(mocked.saveProject).toHaveBeenCalled(), SLOW);
    expect(lastSaved().facts.expense_lines.map((l) => l.id)).toEqual(["e", "y", "c", "d", "a"]);
  });

  it("keep the keyboard on a line's choice after it moves to another table", async () => {
    start(`${P}/expenses`);
    const choice = await screen.findByRole("combobox", { name: "How often expense 2 falls" });
    await userEvent.selectOptions(choice, "every");
    await waitFor(() =>
      expect(document.activeElement?.getAttribute("aria-label")).toBe("How often expense 2 falls"),
    );
    expect(screen.getByText("Expense 2 moved to Every few years.")).toBeTruthy();
  });
});

describe("a worked-out Fully Funded Balance", () => {
  it("is chosen on its screen, shows the project's figures and keeps the typed ones", async () => {
    // the project's own worked-out figures – not a scenario's, which may be an adopted plan's
    const plan = ok(scenario("Plan A"));
    plan.result.ffb = { "2032": "1" };
    mocked.runProject.mockResolvedValue({
      scenarios: { "Plan A": plan },
      problems: [],
      ffb: Object.fromEntries(years(2027, 2032).map((y) => [String(y), String(y * 10)])),
    });
    start(`${P}/ffb`);
    await userEvent.click(
      await screen.findByRole("radio", { name: /Worked out from the expenses/ }),
    );
    const table = await screen.findByRole("table", { name: "Fully Funded Balance, worked out" });
    expect(within(table).getByRole("row", { name: /2032/ }).textContent).toContain("$20,320");
    expect(
      screen.getByText(/0 of 1 reserve expenses count – 1 one-time cost has no useful life yet/),
    ).toBeTruthy();
    await waitFor(() => expect(lastSaved().facts.ffb_from_lines).toBe(true), SLOW);
    expect(lastSaved().facts.ffb["2027"]).toBe("202700"); // kept for switching back
  });

  it("takes a one-time cost's useful life", async () => {
    start(`${P}/expenses`);
    const life = await screen.findByRole("textbox", { name: "Useful life of expense 2 in years" });
    await userEvent.type(life, "30");
    await waitFor(() => expect(lastSaved().facts.expense_lines[1]?.useful_life).toBe(30), SLOW);
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
    serveLines([
      { id: "b", frequency: "yearly", year: null, amount: "900", description: "Big", source: "" },
      { id: "s", frequency: "yearly", year: null, amount: "100", description: "Small", source: "" },
    ]);
    start(`${P}/expenses`);
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
    expect(lastSaved().facts.expense_lines.map((l) => l.description)).toEqual(["Big", "Smaller"]);
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
    start(`${A}/dues`);
    await userEvent.type(await screen.findByRole("textbox", { name: "Dues in 2027" }), "x");
    expect((screen.getByRole("button", { name: "Rename…" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("is not offered on an adopted plan", async () => {
    serve(projectOf(frozen(scenario("Plan A")), scenario("Plan B")));
    start(A);
    await screen.findByText(/The adopted plan/);
    expect(screen.queryByRole("button", { name: "Rename…" })).toBeNull();
  });
});

describe("sorted editable tables", () => {
  const sortBy = async (table: HTMLElement, name: string) =>
    userEvent.click(within(within(table).getByRole("columnheader", { name })).getByRole("button"));

  it("keep a row in place while a figure in it is typed, until the next click", async () => {
    serveLines([
      { id: "b", frequency: "yearly", year: null, amount: "900", description: "Big", source: "" },
      { id: "s", frequency: "yearly", year: null, amount: "100", description: "Small", source: "" },
    ]);
    start(`${P}/expenses`);
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
    await waitFor(() => expect(lastSaved().facts.expense_lines[1]?.amount).toBe("1500"), SLOW);
    await sortBy(yearly, "Amount a year"); // the next click sorts again – descending
    expect(amounts()).toEqual(["1,500", "900"]);
  });

  it("put yearless costs first when sorted by year, as the start year", async () => {
    serveLines([
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
    ]);
    start(`${P}/expenses`);
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
    start(`${P}/ffb`);
    const table = await screen.findByRole("table", { name: "Fully Funded Balance by year" });
    await sortBy(table, "Start of year");
    await sortBy(table, "Start of year"); // descending – 2032 at the top
    const top = within(table).getByRole("textbox", {
      name: "Fully Funded Balance at the start of 2031",
    });
    fireEvent.focus(top);
    fireEvent.paste(top, { clipboardData: { getData: () => ["7", "8"].join("\n") } });
    await waitFor(() => expect(lastSaved().facts.ffb["2031"]).toBe("7"), SLOW);
    expect(lastSaved().facts.ffb["2030"]).toBe("8"); // the row shown below 2031
    expect(lastSaved().facts.ffb["2032"]).toBe("203200");
  });
});

describe("yearly increases by period", () => {
  it("add a stretch after the last, save them, and show what overlaps or is missing", async () => {
    mocked.run.mockRejectedValue(
      new ApiError(422, "the inputs have problems", ["no yearly dues increase covers 2028–2031"]),
    );
    start(`${A}/dues`);
    // the new one starts the year after the last one's to year – and the first is left alone
    const to = await screen.findByRole("textbox", { name: "Last year of yearly increase 1" });
    await userEvent.type(to, "2029");
    await userEvent.click(screen.getByRole("button", { name: "Add yearly % increase" }));
    expect((to as HTMLInputElement).value).toBe("2029");
    const from2 = screen.getByRole("textbox", { name: "First year of yearly increase 2" });
    expect((from2 as HTMLInputElement).value).toBe("2030");
    const rate2 = screen.getByRole("textbox", { name: "Yearly increase 2" });
    await userEvent.clear(rate2);
    await userEvent.type(rate2, "8");
    await waitFor(() => {
      const dues = savedScenario("Plan A")?.dues;
      expect(dues?.mode === "rate" && dues.increases).toEqual([
        { first_year: null, last_year: 2029, rate: "0.03" },
        { first_year: 2030, last_year: null, rate: "0.08" },
      ]);
    }, SLOW);
    const fix = await screen.findByText("Yearly increases to fix");
    expect(fix.closest("[role=alert]")?.textContent).toContain(
      "no yearly dues increase covers 2028–2031",
    );
  });
});

describe("repeats of every-few-years costs", () => {
  it("number each line and show its later years beneath it, following its first year", async () => {
    serveLines([
      {
        id: "p",
        frequency: "every",
        year: 2027,
        interval: 2,
        end_year: null,
        amount: "1000",
        description: "Plumbing",
        source: "",
        nominal: false,
      },
    ]);
    start(`${P}/expenses`);
    const every = await screen.findByRole("table", { name: "Every few years" });
    const repeats = () =>
      Array.from(every.querySelectorAll("tr.repeat")).map(
        (r) => `${r.children[1]?.textContent} ${r.children[5]?.textContent}`,
      );
    // 2027–2031, base year 2026 at 3%: the 2029 and 2031 occurrences
    expect(repeats()).toEqual(["2029 Repeat of #1 – Plumbing", "2031 Repeat of #1 – Plumbing"]);
    expect(every.querySelector("tr.repeat td[title]")?.textContent).toBe("$1,093"); // 1000 × 1.03³
    const first = within(every).getByRole("textbox", { name: "Year of expense 1" });
    await userEvent.clear(first);
    await userEvent.type(first, "2028");
    expect(repeats()).toEqual(["2030 Repeat of #1 – Plumbing"]);
    await userEvent.click(screen.getByRole("checkbox", { name: /Show each one's repeats/ }));
    expect(repeats()).toEqual([]);
  });
});

describe("every-few-years costs in year order", () => {
  it("place each repeat in its own year among the lines", async () => {
    const every = (id: string, year: number, interval: number, description: string) => ({
      id,
      frequency: "every" as const,
      year,
      interval,
      end_year: null,
      amount: "100",
      description,
      source: "",
      nominal: false,
    });
    serveLines([every("p", 2027, 3, "Plumbing"), every("r", 2028, 10, "Roof")]);
    start(`${P}/expenses`);
    const table = await screen.findByRole("table", { name: "Every few years" });
    const rows = Array.from(table.querySelectorAll("tbody tr")).map((r) =>
      r.classList.contains("repeat")
        ? (r.children[5]?.textContent ?? "")
        : ((r.querySelector("input[aria-label^='Description']") as HTMLInputElement).value ?? ""),
    );
    // 2027 plumbing, 2028 roof, then plumbing again in 2030
    expect(rows).toEqual(["Plumbing", "Roof", "Repeat of #1 – Plumbing"]);
  });

  it("keep a line in place while its year is typed, and move it once the box is left", async () => {
    const every = (id: string, year: number, interval: number, description: string) => ({
      id,
      frequency: "every" as const,
      year,
      interval,
      end_year: null,
      amount: "100",
      description,
      source: "",
      nominal: false,
    });
    serveLines([every("p", 2027, 10, "Plumbing"), every("r", 2028, 10, "Roof")]);
    start(`${P}/expenses`);
    const table = await screen.findByRole("table", { name: "Every few years" });
    const order = () =>
      within(table)
        .getAllByRole("textbox", { name: /^Description of expense/ })
        .map((b) => (b as HTMLInputElement).value);
    const year = within(table).getByRole("textbox", { name: "Year of expense 1" });
    await userEvent.clear(year);
    await userEvent.type(year, "2029");
    expect(order()).toEqual(["Plumbing", "Roof"]); // not moved while typed
    expect(table.querySelector("td.line-number")?.textContent).toBe("#1");
    await userEvent.tab(); // the box is left
    expect(order()).toEqual(["Roof", "Plumbing"]);
  });

  it("keep each line's repeats beneath it while a header sorts the table", async () => {
    serveLines([
      {
        id: "p",
        frequency: "every",
        year: 2027,
        interval: 2,
        end_year: null,
        amount: "100",
        description: "Plumbing",
        source: "",
        nominal: false,
      },
      {
        id: "r",
        frequency: "every",
        year: 2028,
        interval: 10,
        end_year: null,
        amount: "900",
        description: "Roof",
        source: "",
        nominal: false,
      },
    ]);
    start(`${P}/expenses`);
    const table = await screen.findByRole("table", { name: "Every few years" });
    await userEvent.click(
      within(within(table).getByRole("columnheader", { name: "Amount" })).getByRole("button"),
    );
    await userEvent.click(
      within(within(table).getByRole("columnheader", { name: "Amount" })).getByRole("button"),
    ); // descending – the roof first
    const rows = Array.from(table.querySelectorAll("tbody tr")).map((r) =>
      r.classList.contains("repeat")
        ? (r.children[5]?.textContent ?? "")
        : ((r.querySelector("input[aria-label^='Description']") as HTMLInputElement).value ?? ""),
    );
    expect(rows).toEqual([
      "Roof",
      "Plumbing",
      "Repeat of #2 – Plumbing",
      "Repeat of #2 – Plumbing",
    ]);
  });
});

describe("the Fully Funded Balance screen", () => {
  it("explains what the figure means", async () => {
    start(`${P}/ffb`);
    const about = await screen.findByRole("region", {
      name: "What the Fully Funded Balance means",
    });
    expect(about.textContent).toContain("what should have been saved by a given year");
    expect(
      within(about)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual([
      "At 100% funded, the fund has kept pace – owners pay only for future wear.",
      "Below 100%, past wear wasn't fully paid for. Owners will make up the difference later, through higher dues or special assessments.",
    ]);
  });
});

/** A scenario's results as the Compare screen reads them. */
const ok = (s: Scenario) => ({
  result: {
    years: [2027, 2028, 2029, 2030, 2031].map((year) => ({
      year,
      ending_balance: "1",
      percent_funded: "0.5",
      low_flag: false,
    })),
    summary: {
      dues_y1: "600",
      dues_y4: "650",
      dues_y9: null,
      dues_end: "675",
      total_assessments: "0",
      lowest_balance: "1",
      lowest_balance_year: 2027,
      low_years: 0,
      balance_y4: "1",
      pf_y4: "0.5",
      balance_y9: null,
      pf_y9: null,
      balance_end: "1",
      pf_end: "0.5",
      first_target_year: null,
      outlay_first5: "1",
      outlay_total: "1",
      extra_first4: "1",
      extra_total: "1",
      avg_owner_cost: "1",
      avg_extra: "1",
      vote_years: 0,
      shortfall_years: 0,
    },
    ffb: {},
  },
  name: s.name,
});

describe("Compare's shared figures – the cushion, the target and the current dues", () => {
  const rowsOf = async () => {
    const table = await screen.findByRole("table", { name: "Summary measures by scenario" });
    return within(table)
      .getAllByRole("rowheader")
      .map((th) => th.textContent);
  };

  it("are named in the labels when every scenario shares them", async () => {
    current.project.expenses_from = "Study A";
    current.project.expenses_edited = true;
    mocked.results.mockResolvedValue({
      scenarios: { "Plan A": ok(scenario("Plan A")), "Plan B": ok(scenario("Plan B")) },
    });
    start("/projects/abcdefabcdef/compare");
    const rows = await rowsOf();
    expect(rows).toContain("Years below the cushion ($10,000)");
    expect(rows).toContain("First year the target (70.0% funded) is met");
    expect(rows).toContain("Dues per unit per month – 2031");
    expect(rows).not.toContain("Minimum cushion");
    expect(
      screen.getByText("Expenses from the set “Study A”, edited since it was loaded."),
    ).toBeTruthy();
  });

  it("get rows of their own, right above, when the scenarios differ", async () => {
    // only an adopted plan has facts of its own
    const b = frozen(scenario("Plan B"), 1, { cushion: "25000", target: "0.6" });
    serve(projectOf(scenario("Plan A"), b));
    mocked.results.mockResolvedValue({
      scenarios: { "Plan A": ok(scenario("Plan A")), "Plan B": ok(b) },
    });
    start("/projects/abcdefabcdef/compare");
    const rows = await rowsOf();
    const at = (label: string) => rows.indexOf(label);
    expect(at("Minimum cushion")).toBe(at("Years below each scenario's cushion") - 1);
    expect(at("Percent-funded target")).toBe(at("First year each scenario's target is met") - 1);
    const table = screen.getByRole("table", { name: "Summary measures by scenario" });
    const cushions = within(
      within(table).getByRole("row", { name: /^Minimum cushion/ }),
    ).getAllByRole("cell");
    expect(cushions.map((c) => c.textContent)).toEqual(["$10,000", "$25,000"]);
    expect(
      screen.getByText(
        "Expenses not from a saved set. Plan B keeps the facts and expenses it was adopted with.",
      ),
    ).toBeTruthy();
  });

  it("names the current dues extra cost is measured against", async () => {
    const b = frozen(scenario("Plan B"), 1, { current_dues: "500.00" }); // the same figure written another way
    serve(projectOf(scenario("Plan A"), b));
    mocked.results.mockResolvedValue({
      scenarios: { "Plan A": ok(scenario("Plan A")), "Plan B": ok(b) },
    });
    start("/projects/abcdefabcdef/compare");
    const rows = await rowsOf();
    // both scenarios' current dues are $500 – the labels say so, the baseline row shows it
    expect(rows).toContain("Extra cost per unit over today's $500 a month, 2027–2030");
    expect(rows).toContain("Extra cost per unit over today's $500 a month, 2027–2031");
    expect(rows).toContain("Average extra cost per unit per year over today's $500 a month");
    const baseline = "Current dues per unit per month – what extra cost is measured against";
    expect(rows.indexOf(baseline)).toBe(
      rows.indexOf("Extra cost per unit over today's $500 a month, 2027–2030") - 1,
    );
    const table = screen.getByRole("table", { name: "Summary measures by scenario" });
    const cells = within(within(table).getByRole("row", { name: /^Current dues/ })).getAllByRole(
      "cell",
    );
    expect(cells.map((c) => c.textContent)).toEqual(["$500", "$500"]);
    expect(
      screen.getByText(/Extra cost is what an owner pays above today's dues held flat/),
    ).toBeTruthy();
  });

  it("says each scenario's current dues when they differ", async () => {
    const b = frozen(scenario("Plan B"), 1, { current_dues: "540" });
    serve(projectOf(scenario("Plan A"), b));
    mocked.results.mockResolvedValue({
      scenarios: { "Plan A": ok(scenario("Plan A")), "Plan B": ok(b) },
    });
    start("/projects/abcdefabcdef/compare");
    const rows = await rowsOf();
    expect(rows).toContain("Extra cost per unit over each scenario's current dues, 2027–2030");
    expect(rows).toContain("Extra cost per unit over each scenario's current dues, 2027–2031");
    expect(rows).toContain(
      "Average extra cost per unit per year over each scenario's current dues",
    );
    expect(rows.filter((r) => r?.includes("today's"))).toEqual([]);
    const table = screen.getByRole("table", { name: "Summary measures by scenario" });
    const row = () =>
      within(within(table).getByRole("row", { name: /^Current dues/ })).getAllByRole("cell");
    expect(row().map((c) => c.textContent)).toEqual(["$500", "$540"]);
    // a difference in a fact is shown plainly – neither better nor worse
    await userEvent.click(screen.getByRole("checkbox", { name: /Show differences/ }));
    const diff = row()[1]?.querySelector(".diff");
    expect(diff?.textContent).toBe(" (+$40)");
    expect(diff?.classList.contains("better") || diff?.classList.contains("worse")).toBe(false);
  });

  it("flags negative figures in the summary and percent funded as a low balance is", async () => {
    const short = ok(scenario("Plan B"));
    short.result.summary.lowest_balance = "-5000";
    short.result.summary.avg_extra = "-200";
    short.result.years[1] = {
      year: 2028,
      ending_balance: "1",
      percent_funded: "-0.1",
      low_flag: false,
    };
    mocked.results.mockResolvedValue({
      scenarios: { "Plan A": ok(scenario("Plan A")), "Plan B": short },
    });
    start("/projects/abcdefabcdef/compare");
    const lowest = within(
      within(await screen.findByRole("table", { name: "Summary measures by scenario" })).getByRole(
        "row",
        { name: /^Lowest year-end balance/ },
      ),
    ).getAllByRole("cell");
    expect(lowest.map((c) => c.classList.contains("flag-warn"))).toEqual([false, true]);
    // a negative extra cost is a saving, not a warning
    const extra = within(
      within(screen.getByRole("table", { name: "Summary measures by scenario" })).getByRole("row", {
        name: /^Average extra cost/,
      }),
    ).getAllByRole("cell");
    expect(extra.map((c) => c.classList.contains("flag-warn"))).toEqual([false, false]);
    const pf = within(
      within(screen.getByRole("table", { name: "Percent funded by year" })).getByRole("row", {
        name: /^2028/,
      }),
    ).getAllByRole("cell");
    expect(pf.map((c) => c.classList.contains("flag-warn"))).toEqual([false, true]);
  });
});

describe("an adopted plan's frozen expenses", () => {
  it("can be saved as an expense set, and un-adopting says they are dropped", async () => {
    const plan = frozen(
      scenario("Plan A", { adoption: { date: "2026-11-03", note: "", sequence: 1 } }),
    );
    serve(projectOf(plan, scenario("Plan B")));
    start("/projects/abcdefabcdef/scenarios/Plan%20A/expenses");
    const save = await screen.findByRole("button", { name: "Save these expenses as a set…" });
    expect((save as HTMLButtonElement).disabled).toBe(false); // the rest of the tab is read-only
    await userEvent.click(save);
    const dialog = screen.getByRole("dialog", {
      name: "Save the adopted plan's expenses as a set",
    });
    const name = within(dialog).getByRole("textbox", { name: "Name of the set" });
    expect((name as HTMLInputElement).value).toBe("Expenses of Plan A");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(lastSaved().expense_sets.map((s) => s.name)).toEqual(["Expenses of Plan A"]),
    );
    expect(lastSaved().scenarios[0]).toEqual(plan); // the plan itself is unchanged
    expect(await screen.findByText("Saved as the set “Expenses of Plan A”.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Un-adopt…" }));
    expect(screen.getByText(/drops the facts and expenses it was adopted with/)).toBeTruthy();
  });
});

describe("the project's facts screens and old scenario addresses", () => {
  it("list the facts' own problems, from the project's live run", async () => {
    mocked.runProject.mockResolvedValue({
      scenarios: {},
      problems: ["the Fully Funded Balance is missing for 2033"],
      ffb: {},
    });
    start(`${P}/facts`);
    const listed = await screen.findByText("the Fully Funded Balance is missing for 2033");
    expect(listed.closest("[role=alert]")?.textContent).toContain("Fix these to see results");
  });

  it("send an ordinary scenario's facts address to the project's screen", async () => {
    const router = start("/projects/abcdefabcdef/scenarios/Plan%20A/expenses");
    await waitFor(() => expect(at(router)).toBe("/projects/abcdefabcdef/expenses"));
    expect(await screen.findByRole("region", { name: "Expense sets" })).toBeTruthy();
  });
});
