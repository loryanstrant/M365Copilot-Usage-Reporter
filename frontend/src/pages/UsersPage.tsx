import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { DirectoryUser } from "../api/types";
import ChartCard from "../components/ChartCard";
import DataTable, { type Column } from "../components/DataTable";

/**
 * The imported tenant directory.
 *
 * Deliberately the whole list in one fetch, filtered in the browser: the
 * question people bring here is "who has a licence and never touches it",
 * which means scanning and filtering rather than paging.
 */
export default function UsersPage() {
  const [users, setUsers] = useState<DirectoryUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [licensedOnly, setLicensedOnly] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const rows = await api<DirectoryUser[]>("/metrics/users");
        if (active) setUsers(rows);
      } catch {
        if (active) setError("We couldn't load the tenant users just now.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const rows = useMemo(
    () => (licensedOnly ? users.filter((u) => u.has_copilot_license) : users),
    [users, licensedOnly],
  );

  const licensed = useMemo(
    () => users.filter((u) => u.has_copilot_license).length,
    [users],
  );

  // Memoised: DataTable's filter and sort both key off this array, so a fresh
  // literal each render would defeat their memoisation on every keystroke.
  const columns: Column<DirectoryUser>[] = useMemo(() => [
    {
      key: "display_name",
      header: "Name",
      accessor: (u) => u.display_name,
    },
    {
      key: "user_principal_name",
      header: "UPN",
      accessor: (u) => u.user_principal_name,
    },
    // Company is deliberately not shown. In a single-tenant directory it is the
    // same value on every row, and the ten columns overflowed the card at 1600px
    // wide — pushing Prompts, the column people come here for, off the edge. The
    // API still returns it.
    { key: "job_title", header: "Job title", accessor: (u) => u.job_title },
    { key: "department", header: "Department", accessor: (u) => u.department },
    {
      key: "office_location",
      header: "Office",
      accessor: (u) => u.office_location,
    },
    { key: "country", header: "Country", accessor: (u) => u.country },
    { key: "manager_name", header: "Manager", accessor: (u) => u.manager_name },
    {
      key: "has_copilot_license",
      header: "Licence",
      accessor: (u) => (u.has_copilot_license ? "Licensed" : "Not licensed"),
      // Shape and word, never colour alone.
      render: (u) => (
        <span className="whitespace-nowrap">
          <span aria-hidden>{u.has_copilot_license ? "● " : "○ "}</span>
          {u.has_copilot_license ? "Licensed" : "Not licensed"}
        </span>
      ),
    },
    {
      key: "prompts",
      header: "Prompts",
      type: "number",
      align: "right",
      accessor: (u) => u.prompts,
      // A free-text filter on a count helps nobody.
      filterable: false,
    },
  ], []);

  if (loading) {
    return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        Tenant users
      </h1>
      <p className="mb-5 mt-1 text-sm text-slate-500 dark:text-slate-400">
        Everyone imported from your directory, with how much Copilot each person
        has used. Filter any column to narrow the list.
      </p>

      {error && (
        <div className="card mb-5 p-5 text-sm text-amber-700 dark:text-amber-300">
          {error}
        </div>
      )}

      <ChartCard
        title={`${rows.length.toLocaleString()} users`}
        subtitle={`${licensed.toLocaleString()} with a Copilot licence`}
        action={
          <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-600 dark:text-slate-300">
            <input
              type="checkbox"
              checked={licensedOnly}
              onChange={(e) => setLicensedOnly(e.target.checked)}
              className="rounded border-slate-300 dark:border-slate-600"
            />
            Licensed only
          </label>
        }
        className="px-0"
      >
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(u) => u.user_id}
          initialSort={{ key: "display_name", dir: "asc" }}
          filterable
          // A tenant directory is thousands of rows; without this the column
          // headers and their filter boxes scroll out of reach on the way down.
          maxBodyHeight="calc(100vh - 20rem)"
          emptyMessage="No users imported yet. Configure the app registration in Settings, then run a collection."
        />
      </ChartCard>
    </div>
  );
}
