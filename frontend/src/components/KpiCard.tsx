export default function KpiCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm transition-shadow hover:shadow-md dark:border-slate-700 dark:from-slate-800 dark:to-slate-900/60">
      <div className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-brand-500/10 blur-2xl" />
      <div className="flex min-h-[2.5rem] items-start text-sm font-medium leading-tight text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-2 bg-gradient-to-br from-slate-900 to-slate-500 bg-clip-text text-3xl font-bold tabular-nums text-transparent dark:from-white dark:to-slate-400">
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">{hint}</div>}
    </div>
  );
}
