/**
 * A compact segmented control — the same visual language as the FilterBar's
 * measure toggle, extracted so pages can reuse it for their own local options
 * (chart sort order, group-by, etc.) without duplicating the styling.
 */
export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="flex items-center gap-1 rounded-lg border border-slate-200 p-1 dark:border-slate-600"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`h-[26px] rounded-md px-2.5 text-xs font-medium transition-colors ${
            value === o.value
              ? "bg-brand-600 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
