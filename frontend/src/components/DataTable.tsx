import { useMemo, useState, type ReactNode } from "react";

// A reusable, type-aware sortable table. Every column can be sorted in both
// directions according to its type: text sorts alphabetically, number sorts
// numerically, and date sorts chronologically (newest/oldest). Empty values
// (null / undefined / "") always sort to the bottom regardless of direction.
//
// Tables of people or other long lists can also opt into a row of per-column
// filter boxes by passing `filterable`. It is opt-in rather than automatic
// because most tables here are short summaries where a filter row is noise —
// but a directory of a few thousand users is unusable without one.

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
  /** Exclude this column from the filter row (only relevant when the table
   *  is filterable). Defaults to filterable when the column has an accessor. */
  filterable?: boolean;
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
  onRowClick?: (row: Row) => void;
  /** When set, the table body scrolls within this pixel height and the header
   * sticks to the top — keeps long tables from pushing the page scrollbar away. */
  maxBodyHeight?: number;
  /** Show a per-column filter row, and a "N of M rows" count beneath. */
  filterable?: boolean;
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
  onRowClick,
  maxBodyHeight,
  filterable = false,
}: Props<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);
  const [filters, setFilters] = useState<Record<string, string>>({});

  // Case-insensitive substring per column, ANDed across columns — the same
  // behaviour people expect from a spreadsheet filter.
  const filteredRows = useMemo(() => {
    if (!filterable) return rows;
    const active = Object.entries(filters).filter(([, term]) => term.trim());
    if (active.length === 0) return rows;
    return rows.filter((row) =>
      active.every(([key, term]) => {
        const col = columns.find((c) => c.key === key);
        if (!col?.accessor) return true;
        return String(col.accessor(row) ?? "")
          .toLowerCase()
          .includes(term.trim().toLowerCase());
      }),
    );
  }, [rows, columns, filters, filterable]);

  const sortedRows = useMemo(() => {
    const rows = filteredRows;
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
  }, [filteredRows, sort, columns]);

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
    <>
    <div
      className="overflow-auto"
      style={maxBodyHeight ? { maxHeight: `${maxBodyHeight}px` } : undefined}
    >
      <table className="w-full text-sm">
        <thead className={maxBodyHeight ? "sticky top-0 z-10" : undefined}>
          <tr className="bg-white text-xs uppercase tracking-wide text-slate-400 dark:bg-slate-800">
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
          {filterable && (
            <tr className="bg-white dark:bg-slate-800">
              {columns.map((col) => {
                const canFilter = col.filterable !== false && !!col.accessor;
                return (
                  <th key={col.key} className="px-5 pb-3">
                    {canFilter && (
                      <input
                        value={filters[col.key] ?? ""}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, [col.key]: e.target.value }))
                        }
                        placeholder="Filter…"
                        aria-label={`Filter by ${col.header}`}
                        className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs font-normal normal-case tracking-normal text-slate-700 outline-none focus:border-brand-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                      />
                    )}
                  </th>
                );
              })}
            </tr>
          )}
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
                onClick={onRowClick ? () => onRowClick(row) : undefined}
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
    {filterable && rows.length > 0 && (
      <div className="px-5 py-3 text-xs text-slate-400 dark:text-slate-500">
        {sortedRows.length === rows.length
          ? `${rows.length.toLocaleString()} rows`
          : `${sortedRows.length.toLocaleString()} of ${rows.length.toLocaleString()} rows`}
      </div>
    )}
    </>
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
