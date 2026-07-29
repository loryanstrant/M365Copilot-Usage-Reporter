import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { FilterOptions } from "../api/types";

// Categorical filters are multi-select: [] means "All".
interface FilterState {
  dateFrom: string;
  dateTo: string;
  apps: string[];
  departments: string[];
  offices: string[];
  managerIds: string[];
  chatTypes: string[];
  conversationLocations: string[];
  userSearch: string;
}

export interface Filters extends FilterState {
  options: FilterOptions | null;
  set: (patch: Partial<FilterState>) => void;
  setRelative: (days: number) => void;
  reset: () => void;
  activeCount: number;
}

const EMPTY: FilterState = {
  dateFrom: "",
  dateTo: "",
  apps: [],
  departments: [],
  offices: [],
  managerIds: [],
  chatTypes: [],
  conversationLocations: [],
  userSearch: "",
};

const FiltersContext = createContext<Filters | null>(null);

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function FiltersProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<FilterState>(EMPTY);
  const [options, setOptions] = useState<FilterOptions | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setOptions(await api<FilterOptions>("/metrics/filters"));
      } catch {
        /* ignore */
      }
    })();
  }, []);

  const value = useMemo<Filters>(() => {
    const set = (patch: Partial<FilterState>) => setState((s) => ({ ...s, ...patch }));
    const setRelative = (days: number) =>
      setState((s) => ({ ...s, dateFrom: isoDaysAgo(days), dateTo: "" }));
    const reset = () => setState(EMPTY);
    const activeCount =
      (state.dateFrom ? 1 : 0) +
      (state.dateTo ? 1 : 0) +
      (state.userSearch ? 1 : 0) +
      state.apps.length +
      state.departments.length +
      state.offices.length +
      state.managerIds.length +
      state.chatTypes.length +
      state.conversationLocations.length;
    return { ...state, options, set, setRelative, reset, activeCount };
  }, [state, options]);

  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>;
}

export function useFilters(): Filters {
  const ctx = useContext(FiltersContext);
  if (!ctx) throw new Error("useFilters must be used within FiltersProvider");
  return ctx;
}

/** Serialise all active filters into a metrics query string (repeated params). */
export function metricsQuery(f: Filters): string {
  const p = new URLSearchParams();
  if (f.dateFrom) p.set("date_from", f.dateFrom);
  if (f.dateTo) p.set("date_to", f.dateTo);
  f.apps.forEach((v) => p.append("app", v));
  f.departments.forEach((v) => p.append("department", v));
  f.offices.forEach((v) => p.append("office_location", v));
  f.managerIds.forEach((v) => p.append("manager_id", v));
  f.chatTypes.forEach((v) => p.append("chat_type", v));
  f.conversationLocations.forEach((v) => p.append("conversation_location", v));
  if (f.userSearch) p.set("user_search", f.userSearch);
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** A dependency key so effects re-run when any filter changes. */
export function filterDeps(f: Filters): string {
  return metricsQuery(f);
}
