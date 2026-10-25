import { describe, expect, it } from "vitest";

import { linesFromPaste, newLineId, withFrequency } from "./components/tables";
import { csvCell, parsePasted, toCsv } from "./csv";
import { fromPercent, num, parseDecimal, roundCents, shift, toPercent } from "./decimal";
import { dues, money, percent, span } from "./format";
import { sharedDomain, sharedGrid } from "./scale";
import {
  applyChanges,
  blankScenario,
  horizonOf,
  noChanges,
  plausibleHorizon,
  reshapeHorizon,
  reshapeScenario,
  startFrom,
} from "./template";
import type { Baseline, Scenario } from "./types";

describe("exact decimals", () => {
  it.each([
    ["1,234.50", "1234.5"],
    ["$800", "800"],
    ["  0.0300 ", "0.03"],
    ["-0", "0"],
    ["007", "7"],
    ["-12.10", "-12.1"],
  ])("tidies %s to %s", (typed, exact) => expect(parseDecimal(typed)).toBe(exact));

  it.each(["", "abc", "1.2.3", "1e5", "12%", "--1"])("refuses %s", (typed) =>
    expect(parseDecimal(typed)).toBeNull(),
  );

  it("moves the decimal point without floating point", () => {
    expect(shift("3.5", -2)).toBe("0.035");
    expect(shift("0.035", 2)).toBe("3.5");
    expect(shift("7", -3)).toBe("0.007");
    expect(shift("0.1", 3)).toBe("100");
    expect(shift("-4.2", -1)).toBe("-0.42");
    // the classic float trap – 0.07 * 100 is 7.000000000000001 in floating point
    expect(toPercent("0.07")).toBe("7");
    expect(fromPercent("7")).toBe("0.07");
  });

  it("takes percentages with or without the sign", () => {
    expect(fromPercent("20%")).toBe("0.2");
    expect(fromPercent("abc")).toBeNull();
  });

  it("converts to numbers only for display", () => {
    expect(num("12.5")).toBe(12.5);
    expect(num(null)).toBeNaN();
    expect(num(undefined)).toBeNaN();
  });
});

describe("US formatting", () => {
  it("formats money, dues and percentages", () => {
    expect(money("1234567.891")).toBe("$1,234,568");
    expect(money("-45222.23")).toBe("-$45,222");
    expect(money("1234.5", true)).toBe("$1,234.50");
    expect(dues("800")).toBe("$800");
    expect(dues("712.5")).toBe("$712.50");
    expect(percent("0.7075")).toBe("70.8%");
    expect(span(2027, 2041)).toBe("2027–2041");
  });

  it("shows a dash for missing values", () => {
    expect(money(null)).toBe("–");
    expect(dues(undefined)).toBe("–");
    expect(percent("x")).toBe("–");
  });
});

describe("CSV", () => {
  it("guards text that a spreadsheet would run as a formula", () => {
    expect(csvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(csvCell("+1 call")).toBe("'+1 call");
    expect(csvCell("@SUM")).toBe("'@SUM");
    expect(csvCell("-45222.23")).toBe("-45222.23"); // a number is left a number
    expect(csvCell(-5)).toBe("-5");
  });

  it("quotes commas, quotes and line breaks", () => {
    expect(csvCell('Say "hi", then')).toBe('"Say ""hi"", then"');
    expect(
      toCsv([
        ["a", 1],
        [null, "b\nc"],
      ]),
    ).toBe('a,1\r\n,"b\nc"\r\n');
  });

  it("splits pasted spreadsheet cells", () => {
    expect(parsePasted("2027\t100\r\n\r\n2028\t200\n")).toEqual([
      ["2027", "100"],
      ["2028", "200"],
    ]);
  });

  it("turns pasted rows into expense lines and counts the rest", () => {
    const { lines, skipped } = linesFromPaste(
      "Year\tAmount\n2030\t$1,000\tRoof\tyes\tStudy\n2031\t500\tGate",
      ["line-1"],
    );
    expect(skipped).toBe(1); // the header row
    expect(lines).toEqual([
      {
        id: "line-2",
        frequency: "once",
        year: 2030,
        amount: "1000",
        description: "Roof",
        nominal: true,
        source: "Study",
      },
      {
        id: "line-3",
        frequency: "once",
        year: 2031,
        amount: "500",
        description: "Gate",
        nominal: false,
        source: "",
      },
    ]);
  });
});

describe("expense frequencies", () => {
  const once = {
    id: "roof",
    frequency: "once" as const,
    year: 2030,
    amount: "100",
    description: "Roof",
    source: "Study",
    nominal: true,
  };

  it("keeps a line's words and years and only the fields its new frequency uses", () => {
    const monthly = withFrequency(once, "monthly", 2027);
    expect(monthly).toEqual({
      id: "roof",
      frequency: "monthly",
      year: 2030,
      end_year: null,
      inflation: null,
      amount: "100",
      description: "Roof",
      source: "Study",
    });
    expect(withFrequency({ ...monthly, year: null }, "every", 2027)).toEqual({
      ...once,
      frequency: "every",
      year: 2027,
      interval: 5,
      end_year: null,
      nominal: false,
    });
    expect(withFrequency(withFrequency(once, "every", 2027), "once", 2027)).toEqual(once);
  });

  it("gives new lines an identifier no other line has", () => {
    expect(newLineId([])).toBe("line-1");
    expect(newLineId(["line-1", "line-3"])).toBe("line-2");
  });
});

describe("shared chart scale", () => {
  it("matches the workbook's grid", () => {
    expect(sharedDomain(-45222, 806568)).toEqual([-200000, 1000000]);
    expect(sharedDomain(0, 1040000)).toEqual([0, 1250000]);
    expect(sharedDomain(0, 0)).toEqual([0, 5]);
  });
});

describe("a scenario's changes to the baseline", () => {
  const line = (id: string, year: number) => ({
    id,
    frequency: "once" as const,
    year,
    amount: "1",
    description: id,
    source: "",
    nominal: false,
  });
  const baseline = {
    start_year: 2027,
    end_year: 2031,
    interest_rate: "0.02",
    expense_lines: [line("roof", 2028), line("gate", 2029), line("paint", 2030)],
    ffb: { "2027": "1" },
    sources: { interest_rate: "Bank" },
  } as unknown as Baseline;

  it("changes, leaves out and adds lines where the server does", () => {
    const strip = (l: ReturnType<typeof line>) =>
      Object.fromEntries(Object.entries(l).filter(([k]) => k !== "id")) as Omit<typeof l, "id">;
    const [later, pool] = [strip(line("roof", 2031)), strip(line("pool", 2030))];
    const own = applyChanges(baseline, {
      values: { interest_rate: "0.05", end_year: 2033 },
      sources: { interest_rate: "Board" },
      expense_lines: { roof: later, gate: null, pool, gone: null },
      ffb: { "2032": "9" },
    });
    expect(own.expense_lines.map((l) => `${l.id} ${l.year}`)).toEqual([
      "roof 2031",
      "paint 2030",
      "pool 2030",
    ]);
    expect([own.interest_rate, own.end_year, own.sources.interest_rate]).toEqual([
      "0.05",
      2033,
      "Board",
    ]);
    expect(own.ffb).toEqual({ "2027": "1", "2032": "9" });
  });

  it("runs over its own horizon, or none while that is not a usable one", () => {
    const s = blankScenario("S", baseline);
    expect(horizonOf(baseline, s)).toEqual([2027, 2028, 2029, 2030, 2031]);
    const typing = { ...s, changes: { ...noChanges(), values: { end_year: 2 } } };
    expect(horizonOf(baseline, typing)).toEqual([]);
  });
});

describe("starting a scenario from another", () => {
  const baseline = {
    start_year: 2028,
    end_year: 2032,
    ffb: {},
    expense_lines: [],
  } as unknown as Baseline;
  const typed: Scenario = {
    name: "Adopted",
    description: "As voted",
    dues: { mode: "explicit", explicit: { "2027": "500", "2028": "510" } },
    assessments: [{ year: 2029, amount: "100", note: "" }],
    rounding: "none",
    changes: { values: { interest_rate: "0.04" }, sources: {}, expense_lines: {}, ffb: {} },
    adoption: { date: "2026-11-03", note: "", sequence: 1, baseline },
  };

  it("copies its inputs and changes but not its adoption, on today's years", () => {
    const seeded = startFrom(typed, "New scenario", baseline);
    expect(seeded.adoption).toBeNull();
    expect([seeded.name, seeded.description, seeded.rounding]).toEqual([
      "New scenario",
      "As voted",
      "none",
    ]);
    expect(seeded.changes.values).toEqual({ interest_rate: "0.04" });
    expect(seeded.dues).toEqual({
      mode: "explicit",
      explicit: {
        "2027": "500",
        "2028": "510",
        "2029": "510",
        "2030": "510",
        "2031": "510",
        "2032": "510",
      },
    });
    seeded.assessments.push({ year: 2030, amount: "1", note: "" });
    expect(typed.assessments).toHaveLength(1); // a copy, not the source's own lists
  });

  it("keeps assessments and pinned years outside today's years, for the editor to list", () => {
    const early = {
      ...typed,
      dues: {
        mode: "rate" as const,
        first_value: "500",
        annual_increase: "0.03",
        overrides: { "2027": "480" },
      },
      assessments: [{ year: 2027, amount: "100", note: "" }],
    };
    const seeded = startFrom(early, "New scenario", baseline);
    // nothing is dropped silently – the server names each one as a problem to fix
    expect(seeded.assessments.map((a) => a.year)).toEqual([2027]);
    expect(seeded.dues).toMatchObject({ overrides: { "2027": "480" } });
  });
});

describe("horizon changes", () => {
  const baseline = {
    start_year: 2027,
    end_year: 2031,
    ffb: { "2027": "1", "2032": "6" },
  } as unknown as Baseline;

  it("keeps every Fully Funded Balance it had and adds zeros for new years", () => {
    const longer = reshapeHorizon(baseline, 2027, 2033);
    expect(longer.ffb).toEqual({
      "2027": "1",
      "2028": "0",
      "2029": "0",
      "2030": "0",
      "2031": "0",
      "2032": "6",
      "2033": "0",
      "2034": "0",
    });
    const shorter = reshapeHorizon(longer, 2029, 2033);
    expect(shorter.ffb["2027"]).toBe("1"); // shortening never discards an entry
  });

  it("acts only on a horizon that makes sense", () => {
    expect(plausibleHorizon(2027, 2031)).toBe(true);
    expect(plausibleHorizon(2027, 2030)).toBe(false); // four years
    expect(plausibleHorizon(2027, 2057)).toBe(false); // thirty-one
    expect(plausibleHorizon(2027, 2)).toBe(false); // an end year half typed
  });

  it("carries typed dues into new years and leaves grown dues alone", () => {
    const typed: Scenario = {
      ...blankScenario("T", { current_dues: "500" } as Baseline),
      dues: { mode: "explicit", explicit: { "2027": "500", "2028": "520" } },
    };
    const reshaped = reshapeScenario(typed, 2027, 2030);
    expect(reshaped.dues).toEqual({
      mode: "explicit",
      explicit: { "2027": "500", "2028": "520", "2029": "520", "2030": "520" },
    });
    const earlier = reshapeScenario(reshaped, 2025, 2028);
    expect(earlier.dues).toEqual({
      mode: "explicit",
      explicit: {
        "2025": "500",
        "2026": "500",
        "2027": "500",
        "2028": "520",
        "2029": "520",
        "2030": "520",
      },
    });
    const grown = blankScenario("G", { current_dues: "500" } as Baseline);
    expect(reshapeScenario(grown, 2027, 2030)).toBe(grown);
  });
});

describe("the shared grid's ticks", () => {
  it("line both axes up step for step, zero with zero", () => {
    const g = sharedGrid(-45222, 806568);
    expect(g.dollarTicks).toEqual([-200000, 0, 200000, 400000, 600000, 800000, 1000000]);
    expect(g.percentTicks).toEqual([-0.2, 0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(g.percentDomain).toEqual([-0.2, 1]);
    expect(sharedGrid(0, 1040000).percentDomain).toEqual([0, 1]);
  });
});

describe("exact rounding to cents", () => {
  it.each([
    ["724.4999999", "724.5"],
    ["724.005", "724.01"],
    ["724.004", "724"],
    ["-0.005", "-0.01"],
    ["800", "800"],
    ["1E-7", "0"],
    ["1.2345E+3", "1234.5"],
  ])("rounds %s to %s", (value, cents) => expect(roundCents(value)).toBe(cents));

  it("reads exponent-form decimals the server may send", () => {
    expect(toPercent("5E-7")).toBe("0.00005");
    expect(shift("2.5E+2", 0)).toBe("250");
  });
});
