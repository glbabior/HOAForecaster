import type { RefObject } from "react";

import { saveFile } from "../api";
import { tableRows, toCsv } from "../csv";

/** Download a table on screen as CSV (spec 7.6) – exact values, formula-safe text. */
export function CsvButton({
  table,
  filename,
}: {
  table: RefObject<HTMLTableElement | null>;
  filename: string;
}) {
  return (
    <button
      type="button"
      className="small no-print"
      onClick={() =>
        table.current &&
        saveFile(new Blob([toCsv(tableRows(table.current))], { type: "text/csv" }), filename)
      }
    >
      Download CSV
    </button>
  );
}
