import type { RefObject } from "react";

import { saveFile } from "../api";
import { tableRows, toCsv } from "../csv";
import { DownloadIcon } from "./ui";

/** Download a table on screen as CSV (spec 7.6) – exact values, formula-safe text. Given
 * several tables that share their header row, one file holds them all, the header once. */
export function CsvButton({
  table,
  filename,
  order,
}: {
  table: RefObject<HTMLTableElement | null> | RefObject<HTMLTableElement | null>[];
  filename: string;
  /** the row labels in the order the file should have them, when it differs from the screen */
  order?: string[];
}) {
  const rows = () => {
    const tables = (Array.isArray(table) ? table : [table]).flatMap((t) =>
      t.current ? [tableRows(t.current)] : [],
    );
    const [head = [], ...body] = tables.flatMap((r, i) => (i === 0 ? r : r.slice(1)));
    if (order) body.sort((a, b) => order.indexOf(a[0] ?? "") - order.indexOf(b[0] ?? ""));
    return tables.length ? [head, ...body] : [];
  };
  return (
    <button
      type="button"
      className="action no-print"
      onClick={() => {
        const all = rows();
        if (all.length) saveFile(new Blob([toCsv(all)], { type: "text/csv" }), filename);
      }}
    >
      Download CSV <DownloadIcon />
    </button>
  );
}
