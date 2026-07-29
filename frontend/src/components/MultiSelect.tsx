import { useEffect, useRef, useState } from "react";

export interface Option {
  value: string;
  label: string;
}

/**
 * Multi-select checklist dropdown.
 *
 * Semantics match a Power BI slicer: an empty `selected` array means "All"
 * (every option is shown as checked). Unchecking one item switches to an
 * explicit include-list of the remaining options, so every chart updates to
 * exclude it. Re-checking everything collapses back to "All".
 */
export default function MultiSelect({
  label,
  options,
  selected,
  onChange,
  allLabel = "All",
}: {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (values: string[]) => void;
  allLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const allValues = options.map((o) => o.value);
  const isAll = selected.length === 0;
  const isChecked = (v: string) => isAll || selected.includes(v);

  function toggle(v: string) {
    let next: string[];
    if (isAll) {
      // Currently "all" -> unchecking one means "all except this".
      next = allValues.filter((x) => x !== v);
    } else if (selected.includes(v)) {
      next = selected.filter((x) => x !== v);
    } else {
      next = [...selected, v];
    }
    // If everything is selected again, collapse to "All" (empty).
    if (next.length === allValues.length) next = [];
    onChange(next);
  }

  const summary = isAll
    ? allLabel
    : selected.length === 1
      ? options.find((o) => o.value === selected[0])?.label ?? "1 selected"
      : `${selected.length} selected`;

  return (
    <div className="relative" ref={ref}>
      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
        {label}
      </label>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="input flex h-[38px] w-44 items-center justify-between text-left"
      >
        <span className={`truncate ${isAll ? "text-slate-400" : ""}`}>{summary}</span>
        <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="ml-1 shrink-0 text-slate-400">
          <path d="M6 8l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 w-56 overflow-auto rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
          <button
            type="button"
            onClick={() => onChange([])}
            className="mb-1 w-full rounded-md px-2 py-1.5 text-left text-xs font-medium text-brand-600 hover:bg-slate-50 dark:text-brand-400 dark:hover:bg-slate-700"
          >
            Select all
          </button>
          {options.length === 0 && (
            <div className="px-2 py-1.5 text-xs text-slate-400">No options</div>
          )}
          {options.map((o) => (
            <label
              key={o.value}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <input
                type="checkbox"
                checked={isChecked(o.value)}
                onChange={() => toggle(o.value)}
                className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              />
              <span className="truncate">{o.label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
