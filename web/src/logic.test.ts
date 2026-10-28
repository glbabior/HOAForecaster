import { describe, expect, it, vi } from "vitest";

import { reloadWhenFresh, tokenIn } from "./api";
import { linesFromPaste, newLineId, withFrequency } from "./components/tables";
import { csvCell, parsePasted, toCsv } from "./csv";
import { fromPercent, grouped, num, parseDecimal, roundCents, shift, toPercent } from "./decimal";
import { dues, money, percent, span } from "./format";
import { sharedDomain, sharedGrid } from "./scale";
import {
  copyFact,
  copyFfb,
  copyLine,
  horizonOf,
  plausibleHorizon,
  startFrom,
  withHorizon,
} from "./template";
import type { ExpenseLine, Facts, Scenario } from "./types";

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

  it.each([
    ["1250000", "1,250,000"],
    ["1234.5", "1,234.5"],
    ["-98765.4321", "-98,765.4321"],
    ["999", "999"],
    ["0.25", "0.25"],
  ])("groups %s as %s, keeping every digit", (exact, shown) => {
    expect(grouped(exact)).toBe(shown);
    expect(parseDecimal(shown)).toBe(exact);
  });

  it("groups a figure the server wrote with an exponent", () => {
    expect(grouped("1E+3")).toBe("1,000");
    expect(grouped("1.5E+7")).toBe("15,000,000");
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
    // a default interval never becomes a useful life nobody typed
    expect(withFrequency(withFrequency(once, "every", 2027), "once", 2027)).toEqual({
      ...once,
      useful_life: null,
    });
    // a typed useful life becomes the interval
    expect(withFrequency({ ...once, useful_life: 12 }, "every", 2027).interval).toBe(12);
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

const line = (id: string, year: number, amount = "1"): ExpenseLine => ({
  id,
  frequency: "once",
  year,
  amount,
  description: id,
  source: "",
  nominal: false,
});

const facts = (change: Partial<Facts> = {}): Facts => ({
  start_year: 2027,
  end_year: 2031,
  starting_balance: "100000",
  expense_lines: [line("roof", 2028), line("gate", 2029)],
  expense_inflation: "0.03",
  expense_base_year: 2026,
  ffb: { "2027": "1", "2028": "2", "2029": "3", "2030": "4", "2031": "5", "2032": "6" },
  operating_inflation: "0.03",
  interest_rate: "0.02",
  units: 10,
  current_dues: "500",
  cushion: "0",
  target: "0.7",
  max_dues_increase: "0.2",
  max_assessment_share: "0.05",
  sources: { interest_rate: "Bank" },
  ffb_from_lines: false,
  ...change,
});

const scenario = (name: string, change: Partial<Scenario> = {}): Scenario => ({
  name,
  description: "",
  facts: facts(),
  dues: {
    mode: "rate",
    first_value: "500",
    increases: [{ first_year: null, last_year: null, rate: "0.03" }],
    overrides: {},
  },
  assessments: [],
  rounding: "dollar",
  ...change,
});

describe("starting a scenario from another", () => {
  const adopted = scenario("Adopted", {
    description: "As voted",
    dues: { mode: "explicit", explicit: { "2027": "500", "2028": "510" } },
    assessments: [{ year: 2029, amount: "100", note: "" }],
    rounding: "none",
    adoption: { date: "2026-11-03", note: "", sequence: 1 },
  });

  it("copies every input but not its name or adoption", () => {
    const seeded = startFrom(adopted, "New scenario");
    expect(seeded.adoption).toBeNull();
    expect([seeded.name, seeded.description, seeded.rounding]).toEqual([
      "New scenario",
      "As voted",
      "none",
    ]);
    expect(seeded.facts).toEqual(adopted.facts);
    expect(seeded.dues).toEqual(adopted.dues);
    seeded.assessments.push({ year: 2030, amount: "1", note: "" });
    seeded.facts.expense_lines.push(line("pool", 2030));
    // a copy, not the source's own lists
    expect(adopted.assessments).toHaveLength(1);
    expect(adopted.facts.expense_lines).toHaveLength(2);
  });
});

describe("copying into other scenarios", () => {
  it("copies a figure with its source note, or clears the target's note", () => {
    const from = facts({ interest_rate: "0.05", sources: { interest_rate: "New bank" } });
    const target = scenario("T", {
      facts: facts({ sources: { interest_rate: "Old", units: "Deed" } }),
    });
    const copied = copyFact(target, from, "interest_rate");
    expect(copied.facts.interest_rate).toBe("0.05");
    expect(copied.facts.sources).toEqual({ interest_rate: "New bank", units: "Deed" });
    const noNote = copyFact(target, facts({ interest_rate: "0.01", sources: {} }), "interest_rate");
    expect(noNote.facts.sources).toEqual({ units: "Deed" });
    expect(target.facts.interest_rate).toBe("0.02"); // the target itself is left alone
  });

  it("reshapes the target's tables when a horizon year is copied", () => {
    const typed = scenario("T", { dues: { mode: "explicit", explicit: { "2027": "500" } } });
    const longer = copyFact(typed, facts({ end_year: 2033 }), "end_year");
    expect(longer.facts.end_year).toBe(2033);
    expect(longer.facts.ffb["2034"]).toBe("0");
    expect(longer.dues).toMatchObject({ explicit: { "2033": "500" } });
  });

  it("replaces the line with the same id, or adds it last", () => {
    const target = scenario("T");
    const changed = copyLine(target, line("gate", 2035, "9000"));
    expect(changed.facts.expense_lines.map((l) => `${l.id} ${l.year} ${l.amount}`)).toEqual([
      "roof 2028 1",
      "gate 2035 9000",
    ]);
    const added = copyLine(target, line("pool", 2030));
    expect(added.facts.expense_lines.map((l) => l.id)).toEqual(["roof", "gate", "pool"]);
  });

  it("copies the Fully Funded Balance over the target's years, keeping years only it has", () => {
    const target = scenario("T", {
      facts: facts({ ffb: { "2027": "1", "2040": "40" }, sources: { ffb: "Old study" } }),
    });
    const copied = copyFfb(target, facts({ ffb: { "2027": "7", "2028": "8" }, sources: {} }));
    expect(copied.facts.ffb).toEqual({ "2027": "7", "2028": "8", "2040": "40" });
    expect(copied.facts.sources.ffb).toBeUndefined();
  });
});

describe("horizon changes", () => {
  it("keep every Fully Funded Balance and add zeros for new years", () => {
    const s = scenario("S", { facts: facts({ ffb: { "2027": "1", "2032": "6" } }) });
    const longer = withHorizon(s, 2027, 2033);
    expect(longer.facts.ffb).toEqual({
      "2027": "1",
      "2028": "0",
      "2029": "0",
      "2030": "0",
      "2031": "0",
      "2032": "6",
      "2033": "0",
      "2034": "0",
    });
    const shorter = withHorizon(longer, 2029, 2033);
    expect(shorter.facts.ffb["2027"]).toBe("1"); // shortening never discards an entry
  });

  it("act only on a horizon that makes sense", () => {
    expect(plausibleHorizon(2027, 2031)).toBe(true);
    expect(plausibleHorizon(2027, 2030)).toBe(false); // four years
    expect(plausibleHorizon(2027, 2057)).toBe(false); // thirty-one
    expect(plausibleHorizon(2027, 2)).toBe(false); // an end year half typed
    const typing = withHorizon(scenario("S"), 2027, 2);
    expect(typing.facts.end_year).toBe(2);
    expect(typing.facts.ffb).toEqual(scenario("S").facts.ffb);
    expect(horizonOf(typing)).toEqual([]);
    expect(horizonOf(scenario("S"))).toEqual([2027, 2028, 2029, 2030, 2031]);
  });

  it("carry typed dues into new years and leave grown dues alone", () => {
    const typed = scenario("T", {
      dues: { mode: "explicit", explicit: { "2027": "500", "2028": "520" } },
    });
    const reshaped = withHorizon(typed, 2027, 2031);
    expect(reshaped.dues).toEqual({
      mode: "explicit",
      explicit: { "2027": "500", "2028": "520", "2029": "520", "2030": "520", "2031": "520" },
    });
    const earlier = withHorizon(reshaped, 2025, 2029);
    expect(earlier.dues).toMatchObject({ explicit: { "2025": "500", "2026": "500" } });
    const grown = scenario("G");
    expect(withHorizon(grown, 2027, 2033).dues).toBe(grown.dues);
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

describe("reloading after a restart", () => {
  const page = (t: string) => `<html><head><meta name="hoa-token" content="${t}" /></head></html>`;

  it("waits through the old server and the gap, and reloads only for a fresh one", async () => {
    document.head.innerHTML = '<meta name="hoa-token" content="old" />';
    const answers: (() => Promise<Response>)[] = [
      async () => new Response(page("old")), // the old server, still stopping
      async () => {
        throw new TypeError("connection refused"); // nothing listening yet
      },
      async () => new Response(page("new")),
    ];
    const fetchMock = vi.fn(() => {
      const next = answers.shift();
      if (!next) throw new Error("asked once too often");
      return next();
    });
    vi.stubGlobal("fetch", fetchMock);
    const reload = vi.fn();
    expect(await reloadWhenFresh(10_000, async () => undefined, reload)).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(reload).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("gives up when no fresh server answers in time", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 503 })),
    );
    const reload = vi.fn();
    expect(await reloadWhenFresh(0, async () => undefined, reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("reads the token a page carries", () => {
    expect(tokenIn(page("abc"))).toBe("abc");
    expect(tokenIn("<html></html>")).toBe("");
  });
});
