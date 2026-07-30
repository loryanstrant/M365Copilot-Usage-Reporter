import MultiSelect from "./MultiSelect";
import { useFilters } from "../filters/FiltersContext";

interface Props {
  showApp?: boolean;
  showChatType?: boolean;
  showUserSearch?: boolean;
}

// Global slicer bar shown on report pages. Drives every metrics query.
export default function FilterBar({
  showApp = true,
  showChatType = true,
  showUserSearch = true,
}: Props) {
  const f = useFilters();
  const o = f.options;

  return (
    <div className="card space-y-4 p-4">
      {/* Top row: dates, quick ranges, user search, and clear-all. */}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="From">
          <input
            type="date"
            value={f.dateFrom}
            onChange={(e) => f.set({ dateFrom: e.target.value })}
            className="input h-[38px] w-40"
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            value={f.dateTo}
            onChange={(e) => f.set({ dateTo: e.target.value })}
            className="input h-[38px] w-40"
          />
        </Field>
        <Field label="Quick range">
          <div className="flex h-[38px] items-center gap-1">
            {[
              { label: "7d", days: 7 },
              { label: "30d", days: 30 },
              { label: "90d", days: 90 },
              { label: "1y", days: 365 },
            ].map((r) => (
              <button
                key={r.days}
                onClick={() => f.setRelative(r.days)}
                className="h-[38px] rounded-lg border border-slate-200 px-3 text-xs font-medium text-slate-600 transition-colors hover:border-brand-400 hover:bg-brand-50 hover:text-brand-700 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-white"
              >
                {r.label}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Measure">
          <div className="flex h-[38px] items-center gap-1 rounded-lg border border-slate-200 p-1 dark:border-slate-600">
            {(
              [
                { value: "prompts", label: "Prompts" },
                { value: "conversations", label: "Conversations" },
              ] as const
            ).map((m) => (
              <button
                key={m.value}
                onClick={() => f.setMetric(m.value)}
                aria-pressed={f.metric === m.value}
                className={`h-[30px] rounded-md px-3 text-xs font-medium transition-colors ${
                  f.metric === m.value
                    ? "bg-brand-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </Field>
        {showUserSearch && (
          <Field label="Search user">
            <input
              type="text"
              value={f.userSearch}
              onChange={(e) => f.set({ userSearch: e.target.value })}
              placeholder="name or email"
              className="input h-[38px] w-56"
            />
          </Field>
        )}
        {f.activeCount > 0 && (
          <button onClick={f.reset} className="btn-secondary ml-auto h-[38px]">
            Clear all ({f.activeCount})
          </button>
        )}
      </div>

      {/* Second row: categorical multi-select slicers. */}
      <div className="flex flex-wrap items-end gap-3">
        {showApp && (
          <MultiSelect
            label="App"
            allLabel="All apps"
            options={(o?.apps ?? []).map((a) => ({ value: a, label: a }))}
            selected={f.apps}
            onChange={(v) => f.set({ apps: v })}
          />
        )}
        <MultiSelect
          label="Department"
          allLabel="All departments"
          options={(o?.departments ?? []).map((d) => ({ value: d, label: d }))}
          selected={f.departments}
          onChange={(v) => f.set({ departments: v })}
        />
        <MultiSelect
          label="Office"
          allLabel="All offices"
          options={(o?.offices ?? []).map((d) => ({ value: d, label: d }))}
          selected={f.offices}
          onChange={(v) => f.set({ offices: v })}
        />
        <MultiSelect
          label="Manager"
          allLabel="All managers"
          options={(o?.managers ?? []).map((m) => ({ value: m.id, label: m.name }))}
          selected={f.managerIds}
          onChange={(v) => f.set({ managerIds: v })}
        />
        {showChatType && (
          <MultiSelect
            label="Chat type"
            allLabel="All chat types"
            options={(o?.chat_types ?? []).map((c) => ({ value: c, label: c }))}
            selected={f.chatTypes}
            onChange={(v) => f.set({ chatTypes: v })}
          />
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
        {label}
      </label>
      {children}
    </div>
  );
}
