import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { PlanTable } from "./components/PlanTable";
import { ScenarioPicker } from "./components/ScenarioPicker";
import { DecimalInput, ErrorBanner, YearInput, useInvalidFields } from "./components/ui";
import type { ScenarioResult, YearResult } from "./types";

function year(y: number, change: Partial<YearResult> = {}): YearResult {
  return {
    year: y,
    dues: "650",
    assessment_per_unit: "0",
    total_dues: "187200",
    operating: "150000",
    contribution: "37200",
    assessment: "0",
    total_from_owners: "187200",
    interest: "2775",
    expenses: "14000",
    expense_lines: [
      {
        id: "roof",
        frequency: "once",
        description: "Roof",
        source: "Study",
        nominal: true,
        amount: "14000",
      },
    ],
    operating_lines: [
      {
        id: "water",
        frequency: "monthly",
        description: "Water",
        source: "",
        nominal: false,
        amount: "150000",
      },
    ],
    starting_balance: "185000",
    ending_balance: "210975",
    ffb_next: "634000",
    percent_funded: "0.3328",
    target: "0.6",
    low_flag: false,
    target_met: false,
    needs_vote: true,
    operating_shortfall: false,
    owner_dues_year: "7800",
    owner_cost_year: "7800",
    dues_increase_vs_current: "1080",
    extra_vs_current: "1080",
    cumulative_owner_cost: "7800",
    cumulative_extra: "1080",
    ...change,
  };
}

const result = {
  years: [year(2027), year(2028, { low_flag: true, ending_balance: "-45222.23" })],
  summary: {},
} as ScenarioResult;

describe("the plan table", () => {
  it("lays out the spec's rows with years as columns", () => {
    render(<PlanTable result={result} caption="Dues only – year by year" filename="t.csv" />);
    const table = screen.getByRole("table", { name: "Dues only – year by year" });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(["Year", "2027", "2028"]);
    const rows = within(table)
      .getAllByRole("rowheader")
      .map((h) => h.textContent);
    expect(rows[0]).toBe("Dues per unit per month");
    expect(rows.at(-1)).toBe("Percent-funded target");
    expect(rows).toHaveLength(23);
  });

  it("shows flags as words, marks warnings, and keeps exact values for CSV", () => {
    render(<PlanTable result={result} caption="t" filename="t.csv" />);
    const low = screen.getByRole("row", { name: /Below cushion/ });
    const cells = within(low).getAllByRole("cell");
    expect(cells.map((c) => c.textContent)).toEqual(["ok", "LOW"]);
    expect(cells[1]?.className).toContain("flag-warn");
    const ending = within(screen.getByRole("row", { name: /Ending reserve balance/ })).getAllByRole(
      "cell",
    );
    expect(ending[1]?.textContent).toBe("-$45,222");
    expect(ending[1]?.dataset.csv).toBe("-45222.23");
  });

  it("lists a year's expense lines on request", async () => {
    render(<PlanTable result={result} caption="t" filename="t.csv" />);
    const [first] = screen.getAllByRole("button", { name: "$14,000" });
    if (!first) throw new Error("no expense button");
    await userEvent.click(first);
    expect(screen.getByRole("heading", { name: /Reserve expenses in/ })).toBeTruthy();
    expect(screen.getByText(/Roof/)).toBeTruthy();
    expect(screen.getByText(/Source – Study/)).toBeTruthy();
    expect(first.title).toBe("$14,000 – Roof"); // hover shows amounts too
  });

  it("lists a year's operating lines from the operating row", async () => {
    render(<PlanTable result={result} caption="t" filename="t.csv" />);
    const [first] = screen.getAllByRole("button", { name: "$150,000" });
    if (!first) throw new Error("no operating button");
    await userEvent.click(first);
    expect(screen.getByRole("heading", { name: /Operating expenses in/ })).toBeTruthy();
    expect(screen.getByText(/Water \(monthly/)).toBeTruthy();
  });
});

describe("the scenario picker", () => {
  function Harness() {
    const [selected, setSelected] = useState(["A", "B", "C"]);
    return (
      <>
        <ScenarioPicker names={["A", "B", "C"]} selected={selected} onChange={setSelected} />
        <output>{selected.join(",")}</output>
      </>
    );
  }

  it("defaults to all and keeps the project's order", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: /All scenarios/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: "A" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "A" }));
    expect(screen.getByText("A,B,C")).toBeTruthy(); // ticked off and on again – order kept
    await userEvent.click(screen.getByRole("button", { name: "None" }));
    expect(screen.getByRole("button", { name: /No scenarios/ })).toBeTruthy();
  });
});

describe("decimal inputs", () => {
  function Harness({ percent }: { percent?: boolean }) {
    const [value, setValue] = useState<string | null>(percent ? "0.03" : "800");
    return (
      <>
        <DecimalInput
          label="Amount"
          name="Amount"
          value={value}
          percent={percent}
          onChange={setValue}
        />
        <output>{String(value)}</output>
      </>
    );
  }

  it("hands back exact decimal strings and flags text that is not a number", async () => {
    render(<Harness />);
    const input = screen.getByRole("textbox", { name: "Amount" });
    await userEvent.clear(input);
    await userEvent.type(input, "1,250.5");
    expect(screen.getByText("1250.5")).toBeTruthy();
    await userEvent.type(input, "x");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("1250.5")).toBeTruthy(); // the last good value is kept
  });

  it("shows amounts with commas, and puts them back after typing", async () => {
    function Big() {
      const [value, setValue] = useState<string | null>("1250000");
      return <DecimalInput label="Amount" name="Amount" value={value} onChange={setValue} />;
    }
    render(<Big />);
    const input = screen.getByRole("textbox", { name: "Amount" }) as HTMLInputElement;
    expect(input.value).toBe("1,250,000");
    await userEvent.clear(input);
    await userEvent.type(input, "98765.5");
    expect(input.value).toBe("98765.5"); // left as typed while typing
    await userEvent.tab();
    expect(input.value).toBe("98,765.5");
  });

  it("leaves text that is not a number as typed when leaving the field", async () => {
    render(<Harness />);
    const input = screen.getByRole("textbox", { name: "Amount" }) as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "12x34");
    await userEvent.tab();
    expect(input.value).toBe("12x34");
  });

  it("shows percentages and stores fractions", async () => {
    render(<Harness percent />);
    const input = screen.getByRole("textbox", { name: "Amount" });
    expect((input as HTMLInputElement).value).toBe("3");
    await userEvent.clear(input);
    await userEvent.type(input, "4.5");
    expect(screen.getByText("0.045")).toBeTruthy();
  });
});

describe("errors", () => {
  it("are shown even with no list of problems", () => {
    render(<ErrorBanner error={new Error("the project was saved elsewhere")} />);
    expect(screen.getByRole("alert").textContent).toBe("The project was saved elsewhere");
  });
});

describe("the plan table matches the workbook", () => {
  it("shows the increase in dues alone, as the workbook's row of that name does", () => {
    const withAssessment = {
      years: [year(2027, { dues_increase_vs_current: "1080", extra_vs_current: "6080" })],
      summary: {},
    } as ScenarioResult;
    render(<PlanTable result={withAssessment} caption="t" filename="t.csv" />);
    const row = screen.getByRole("row", { name: /Increase vs current dues/ });
    expect(within(row).getAllByRole("cell")[0]?.textContent).toBe("$1,080");
  });
});

describe("entries that are not usable", () => {
  function Form() {
    const { invalid, Provider } = useInvalidFields();
    const [value, setValue] = useState<string | null>("1");
    const [year, setYear] = useState(2030);
    return (
      <Provider>
        <DecimalInput label="Cushion" name="Minimum cushion" value={value} onChange={setValue} />
        <YearInput label="Year" name="Start year" value={year} onChange={setYear} />
        <output>{invalid.join("|") || "all good"}</output>
      </Provider>
    );
  }

  it("are named to the form until fixed, and never become year 0", async () => {
    render(<Form />);
    await userEvent.type(screen.getByRole("textbox", { name: "Cushion" }), "x");
    const year = screen.getByRole("textbox", { name: "Year" });
    await userEvent.clear(year);
    expect(screen.getByText("Minimum cushion|Start year")).toBeTruthy();
    await userEvent.type(year, "2031");
    await userEvent.clear(screen.getByRole("textbox", { name: "Cushion" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Cushion" }), "5");
    expect(screen.getByText("all good")).toBeTruthy();
  });
});
