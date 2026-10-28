import { useState, type ReactNode } from "react";

export type SortValue = string | number | null | undefined;
type Direction = "ascending" | "descending";
type Key = string | number;

/** The order to show a table's rows in when its headers sort it – the positions of `items`,
 * so editable rows keep their own keys and handlers. Sorting only changes what is shown: a
 * first click sorts by that column, a second reverses it, a third puts the rows back. Blank
 * values go last either way.
 *
 * Given `keyOf` (an editable table), the order is fixed when a header is clicked – a row being
 * typed in never jumps away – and only the next click sorts again; rows added since come
 * last, rows removed drop out. Without it (a table that only shows figures) the order follows
 * the figures as they change. */
export function useSort<T>(
  items: T[],
  columns: Record<string, (item: T) => SortValue>,
  keyOf?: (item: T, i: number) => Key,
) {
  const [sort, setSort] = useState<{ key: string; direction: Direction; fixed: Key[] } | null>(
    null,
  );

  function sorted(key: string, direction: Direction): number[] {
    const order = items.map((_, i) => i);
    const value = columns[key];
    if (!value) return order;
    const sign = direction === "ascending" ? 1 : -1;
    return order.sort((a, b) => {
      const x = value(items[a] as T);
      const y = value(items[b] as T);
      const blankX = x === null || x === undefined || x === "";
      const blankY = y === null || y === undefined || y === "";
      if (blankX || blankY) return Number(blankX) - Number(blankY) || a - b;
      const byValue =
        typeof x === "number" && typeof y === "number"
          ? x - y
          : String(x).localeCompare(String(y), "en-US", { numeric: true, sensitivity: "base" });
      return byValue * sign || a - b;
    });
  }

  let order = items.map((_, i) => i);
  if (sort && keyOf) {
    const at = new Map(items.map((item, i) => [keyOf(item, i), i]));
    const kept = sort.fixed.flatMap((k) => (at.has(k) ? [at.get(k) as number] : []));
    const placed = new Set(kept);
    order = [...kept, ...order.filter((i) => !placed.has(i))];
  } else if (sort) {
    order = sorted(sort.key, sort.direction);
  }

  function toggle(key: string) {
    const direction: Direction | null =
      sort?.key !== key ? "ascending" : sort.direction === "ascending" ? "descending" : null;
    if (!direction) {
      setSort(null);
      return;
    }
    const fixed = keyOf ? sorted(key, direction).map((i) => keyOf(items[i] as T, i)) : [];
    setSort({ key, direction, fixed });
  }

  /** A header cell that sorts by `by` – aria-sort on the column sorted by. A render function,
   * not a component, so a click never remounts the button under the focus. */
  function header(
    by: string,
    label: ReactNode,
    props: { className?: string; title?: string } = {},
  ) {
    const direction = sort?.key === by ? sort.direction : undefined;
    return (
      <th scope="col" className={props.className} aria-sort={direction}>
        <button type="button" className="sort" title={props.title} onClick={() => toggle(by)}>
          {label}
          <span className="sort-mark" aria-hidden="true">
            {direction === "ascending" ? " ▲" : direction === "descending" ? " ▼" : " ↕"}
          </span>
        </button>
      </th>
    );
  }

  return { order, header, sorted: sort !== null };
}

/** A decimal string or number as a number to sort by – null when there is none. */
export const numberOf = (value: SortValue): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isNaN(n) ? null : n;
};
