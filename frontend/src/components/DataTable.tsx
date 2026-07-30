import { useMemo, useState, type ReactNode } from "react";

// A reusable, type-aware sortable table. Every column can be sorted in both
// directions according to its type: text sorts alphabetically, number sorts
// numerically, and date sorts chronologically (newest/oldest). Empty values
// (null / undefined / "") always sort to the bottom regardless of direction.

export type ColumnType = "text" | "number" | "date";
export type SortDir = "asc" | "desc";

export interface Column<Row> {
  key: string;
  header: string;
  /** Value type — drives the sort comparator. Defaults to "text". */
  type?: ColumnType;
  /** Raw value used for sorting. Omit to make the column non-sortable. */
  accessor?: (row: Row) => string | number | null | undefined;
  /** Custom cell content. Defaults to the accessor value ("—" when empty). */
  render?: (row: Row) => ReactNode;
  align?: "left" | "right" | "center";
  /** Force-disable sorting even when an accessor is present. */
  sortable?: boolean;
  /** Extra classes for the body cell. */
  className?: string;
}

export interface SortState {
  key: string;
  dir: SortDir;
}

interface Props<Row> {
  columns: Column<Row>[];
  rows: Row[];
  getRowKey: (row: Row, index: number) => string | number;
  initialSort?: SortState;
  emptyMessage?: string;
  rowClassName?: (row: Row) => string;
}

function isEmpty(v: string | number | null | undefined): boolean {
  return v === null || v === undefined || v === "";
}

function compareValues(
  a: string | number,
  b: string | number,
  type: ColumnType,
): number {
  if (type === "number") return Number(a) - Number(b);
  if (type === "date") return Date.parse(String(a)) - Date.parse(String(b));
  return String(a).localeCompare(String(b), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

// New columns start in the most useful direction: text A→Z, numbers/dates
// high→low (largest / newest first).
function defaultDir(type: ColumnType): SortDir {
  return type === "text" ? "asc" : "desc";
}

function defaultDisplay(v: string | number | null | undefined): ReactNode {
  return isEmpty(v) ? "—" : v;
}

export default function DataTable<Row>({
  columns,
  rows,
  getRowKey,
  initialSort,
  emptyMessage = "No data yet.",
  rowClassName,
}: Props<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col || !col.accessor) return rows;
    const accessor = col.accessor;
    const type = col.type ?? "text";
    const dir = sort.dir;
    return [...rows].sort((ra, rb) => {
      const va = accessor(ra);
      const vb = accessor(rb);
      const ea = isEmpty(va);
      const eb = isEmpty(vb);
      if (ea && eb) return 0;
      if (ea) return 1; // empties always last
      if (eb) return -1;
      const cmp = compareValues(va as string | number, vb as string | number, type);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [rows, sort, columns]);

  function toggle(col: Column<Row>) {
    const type = col.type ?? "text";
    setSort((prev) =>
      prev && prev.key === col.key
        ? { key: col.key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key: col.key, dir: defaultDir(type) },
    );
  }

  const alignClass = (a?: Column<Row>["align"]) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-slate-400">
            {columns.map((col) => {
              const canSort = col.sortable !== false && !!col.accessor;
              const active = sort?.key === col.key;
              const state: "asc" | "desc" | "none" = active ? sort!.dir : "none";
              return (
                <th
                  key={col.key}
                  aria-sort={
                    active ? (sort!.dir === "asc" ? "ascending" : "descending") : "none"
                  }
                  className={`px-5 py-3 font-medium ${alignClass(col.align)}`}
                >
                  {canSort ? (
                    <button
                      type="button"
                      onClick={() => toggle(col)}
                      className={`group inline-flex items-center gap-1 uppercase tracking-wide transition-colors hover:text-slate-600 dark:hover:text-slate-300 ${
                        col.align === "right" ? "flex-row-reverse" : ""
                      } ${active ? "text-slate-600 dark:text-slate-300" : ""}`}
                    >
                      <span>{col.header}</span>
                      <SortIcon state={state} />
                    </button>
                  ) : (
                    <span>{col.header}</span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-5 py-6 text-center text-slate-400"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sortedRows.map((row, i) => (
              <tr
                key={getRowKey(row, i)}
                className={`border-t border-slate-100 dark:border-slate-700 ${
                  rowClassName?.(row) ?? ""
                }`}
              >
                {columns.map((col, j) => {
                  const numeric = col.type === "number" || col.type === "date";
                  const base =
                    j === 0
                      ? "font-medium text-slate-800 dark:text-slate-100"
                      : "text-slate-600 dark:text-slate-300";
                  return (
                    <td
                      key={col.key}
                      className={`px-5 py-3 ${base} ${numeric ? "tabular-nums" : ""} ${alignClass(
                        col.align,
                      )} ${col.className ?? ""}`}
                    >
                      {col.render ? col.render(row) : defaultDisplay(col.accessor?.(row))}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function SortIcon({ state }: { state: "asc" | "desc" | "none" }) {
  const activeCls = "text-brand-600 dark:text-brand-400";
  const idleCls = "text-slate-300 dark:text-slate-600";
  return (
    <span className="inline-flex flex-col text-[8px] leading-[8px]">
      <span className={state === "asc" ? activeCls : idleCls}>▲</span>
      <span className={state === "desc" ? activeCls : idleCls}>▼</span>
    </span>
  );
}
