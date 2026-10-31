import { useRef, useState, type ReactNode } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { saveFile } from "../api";
import { num } from "../decimal";
import { money, percent } from "../format";
import type { Grid } from "../scale";
import type { ScenarioResult } from "../types";
import { DownloadIcon } from "./ui";

// Colours chosen for contrast in both light and dark themes; percent lines are dotted or
// dashed as well as coloured, so they are told apart without colour too.
const COLOURS = {
  expenses: "#3b6fb6",
  owners: "#b64a47",
  assessment: "#c98a1e",
  balance: "#5d8c32",
  pf: "#7d5fa6",
  target: "#808080",
};

export interface LegendEntry {
  name: string;
  colour: string;
  dash?: string;
}

export const BALANCE_LEGEND: LegendEntry[] = [
  { name: "Reserve expenses", colour: COLOURS.expenses },
  { name: "Dues + assessments collected", colour: COLOURS.owners },
  { name: "Year-end reserve balance", colour: COLOURS.balance },
  { name: "Percent funded", colour: COLOURS.pf, dash: "2 3" },
  { name: "Percent-funded target", colour: COLOURS.target, dash: "8 5" },
];

export const OWNER_LEGEND: LegendEntry[] = [
  { name: "Dues per unit per year", colour: COLOURS.owners },
  { name: "Special assessment per unit", colour: COLOURS.assessment },
  { name: "Percent funded", colour: COLOURS.pf, dash: "2 3" },
  { name: "Percent-funded target", colour: COLOURS.target, dash: "8 5" },
];

/** −$200k, $0, $250k, $1.2M – US style, minus sign before the dollar sign. */
export function moneyTick(v: number): string {
  const sign = v < 0 ? "−" : "";
  const a = Math.abs(v);
  if (a >= 1_000_000)
    return `${sign}$${(a / 1_000_000).toFixed(a % 1_000_000 ? 2 : 1).replace(/\.?0+$/, "")}M`;
  if (a >= 1000) return `${sign}$${Math.round(a / 1000)}k`;
  return `${sign}$${Math.round(a)}`;
}
const pctTick = (v: number) => `${Math.round(v * 100)}%`;

function tooltipValue(value: unknown, name: unknown): [string, string] {
  const label = String(name);
  const n = Number(value);
  return [label.startsWith("Percent") ? percent(String(n)) : money(String(n)), label];
}

/** A figure with a caption, a text alternative and a PNG download (spec 7.5, 10.1). */
export function ChartFrame({
  title,
  summary,
  filename,
  legend,
  children,
}: {
  title: string;
  summary: string;
  filename: string;
  legend: LegendEntry[];
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  return (
    <figure className="chart">
      <figcaption>
        <span>{title}</span>
        <button
          type="button"
          className="action no-print"
          onClick={() => {
            setFailed(false);
            downloadPng(ref.current, title, legend, filename).catch(() => setFailed(true));
          }}
        >
          Download PNG <DownloadIcon />
        </button>
      </figcaption>
      {failed && <p className="warning">The picture could not be made – try again.</p>}
      <div ref={ref} className="chart-area" role="img" aria-label={`${title}. ${summary}`}>
        {children}
      </div>
    </figure>
  );
}

/** Chart 1 – expenses, collections and year-end balance on the left; percent funded and the
 * target on the right, 0–100% unless a shared grid extends it below zero. */
export function BalanceChart({
  result,
  grid,
  years,
}: {
  result: ScenarioResult;
  grid?: Grid;
  /** the shared year axis of stacked charts, when the scenarios cover different years */
  years?: [number, number];
}) {
  const data = result.years.map((y) => ({
    year: y.year,
    expenses: num(y.expenses),
    owners: num(y.total_from_owners),
    balance: num(y.ending_balance),
    pf: num(y.percent_funded),
    target: num(y.target),
  }));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.4} />
        {years ? (
          <XAxis dataKey="year" type="number" domain={years} allowDecimals={false} />
        ) : (
          <XAxis dataKey="year" />
        )}
        <YAxis
          yAxisId="money"
          tickFormatter={moneyTick}
          domain={grid?.domain ?? ["auto", "auto"]}
          ticks={grid?.dollarTicks}
          width={64}
        />
        <YAxis
          yAxisId="pct"
          orientation="right"
          tickFormatter={pctTick}
          domain={grid?.percentDomain ?? [0, 1]}
          ticks={grid?.percentTicks}
          width={48}
        />
        <ReferenceLine yAxisId="money" y={0} stroke="currentColor" strokeOpacity={0.5} />
        <Tooltip formatter={tooltipValue} />
        <Legend />
        {lines(BALANCE_LEGEND, ["expenses", "owners", "balance", "pf", "target"])}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Chart 2 – owner cost per unit per year on the left; percent funded and target on the right. */
export function OwnerCostChart({ result }: { result: ScenarioResult }) {
  const data = result.years.map((y) => ({
    year: y.year,
    dues: num(y.owner_dues_year),
    assessment: num(y.assessment_per_unit),
    pf: num(y.percent_funded),
    target: num(y.target),
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.4} />
        <XAxis dataKey="year" />
        <YAxis yAxisId="money" tickFormatter={moneyTick} width={72} />
        <YAxis
          yAxisId="pct"
          orientation="right"
          tickFormatter={pctTick}
          domain={[0, 1]}
          width={48}
        />
        <Tooltip formatter={tooltipValue} />
        <Legend />
        {lines(OWNER_LEGEND, ["dues", "assessment", "pf", "target"])}
      </LineChart>
    </ResponsiveContainer>
  );
}

function lines(legend: LegendEntry[], keys: string[]) {
  return legend.map((entry, i) => (
    <Line
      key={keys[i]}
      yAxisId={entry.name.startsWith("Percent") ? "pct" : "money"}
      dataKey={keys[i] ?? ""}
      name={entry.name}
      stroke={entry.colour}
      strokeDasharray={entry.dash}
      strokeWidth={entry.dash ? 2 : 2.5}
      dot={false}
      isAnimationActive={false}
    />
  ));
}

/** One sentence that says what chart 1 shows, for screen readers and the printed page. */
export function balanceSummary(result: ScenarioResult): string {
  const s = result.summary;
  const target =
    s.first_target_year === null
      ? "never reaches the percent-funded target"
      : `first reaches the percent-funded target in ${s.first_target_year}`;
  return (
    `The balance is lowest in ${s.lowest_balance_year} at ${money(s.lowest_balance)}, ` +
    `ends at ${money(s.balance_end)} (${percent(s.pf_end)} funded) and ${target}.`
  );
}

/** Draw the chart – the plot itself, a title and a legend – onto a canvas and save a PNG. */
async function downloadPng(
  container: HTMLElement | null,
  title: string,
  legend: LegendEntry[],
  filename: string,
): Promise<void> {
  // the plot surface, not one of the small legend icons Recharts also draws as SVG
  const svg = container?.querySelector<SVGSVGElement>("svg.recharts-surface[role='application']");
  if (!svg) throw new Error("no chart to draw");
  const { width, height } = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("style", "font-family: system-ui, sans-serif; font-size: 12px; color: #333");
  const source = new XMLSerializer().serializeToString(clone);
  const image = new Image();
  const url = URL.createObjectURL(new Blob([source], { type: "image/svg+xml" }));
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("the chart could not be drawn"));
      image.src = url;
    });
    const scale = 2; // a sharper picture for slides and print
    const top = 32;
    const legendHeight = 22 * Math.ceil(legend.length / 3) + 8;
    const canvas = document.createElement("canvas");
    canvas.width = width * scale;
    canvas.height = (top + height + legendHeight) * scale;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("no canvas");
    context.scale(scale, scale);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, top + height + legendHeight);
    context.fillStyle = "#1d1f21";
    context.font = "600 14px system-ui, sans-serif";
    context.fillText(title, 12, 20);
    context.drawImage(image, 0, top, width, height);
    context.font = "12px system-ui, sans-serif";
    const column = width / 3;
    legend.forEach((entry, i) => {
      const x = 12 + (i % 3) * column;
      const y = top + height + 14 + Math.floor(i / 3) * 22;
      context.strokeStyle = entry.colour;
      context.lineWidth = 2.5;
      context.setLineDash(entry.dash ? entry.dash.split(" ").map(Number) : []);
      context.beginPath();
      context.moveTo(x, y);
      context.lineTo(x + 24, y);
      context.stroke();
      context.fillStyle = "#1d1f21";
      context.fillText(entry.name, x + 30, y + 4);
    });
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("no picture");
    saveFile(blob, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}
