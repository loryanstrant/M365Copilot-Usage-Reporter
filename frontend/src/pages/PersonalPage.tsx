import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ChartCard from "../components/ChartCard";
import KpiCard from "../components/KpiCard";

interface Summary {
  prompts: number;
  conversations: number;
  active_days?: number;
  apps?: number;
}
interface AppRow {
  app_name: string | null;
  prompts: number;
}
interface Comparison {
  my_prompts: number;
  org_median_prompts: number;
  people_counted: number;
  above_median: boolean;
}

/**
 * The landing page for anyone signed in with a work account: their own Copilot
 * activity, and nobody else's. The server derives "me" from the token, so there
 * is no user to pass in from here.
 */
export default function PersonalPage() {
  const { user } = useAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [s, a, c] = await Promise.all([
          api<Summary>("/metrics/me/summary"),
          api<AppRow[]>("/metrics/me/by-app"),
          api<Comparison>("/metrics/me/comparison"),
        ]);
        if (!active) return;
        setSummary(s);
        setApps(a);
        setComparison(c);
      } catch {
        if (active) setError("We couldn't load your activity just now.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;
  }

  const hasData = !!summary && summary.prompts > 0;

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
        Your Copilot usage
      </h1>
      <p className="mb-5 mt-1 text-sm text-slate-500 dark:text-slate-400">
        How you've been using Copilot. Only you and your administrators can see this.
      </p>

      <OrgViewBanner canViewOrg={user?.can_view_org ?? false} />

      {error && (
        <div className="card mb-5 text-sm text-amber-700 dark:text-amber-300">{error}</div>
      )}

      {!hasData && !error ? (
        <ChartCard title="Your activity">
          <div className="py-12 text-center">
            <h2 className="mb-2 text-lg font-semibold text-slate-900 dark:text-slate-100">
              Nothing to show yet
            </h2>
            <p className="mx-auto max-w-md text-sm text-slate-500 dark:text-slate-400">
              We can't find any Copilot activity for your account. That usually means you
              don't have a licence yet, or you haven't used Copilot since reporting
              started.
            </p>
          </div>
        </ChartCard>
      ) : (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Prompts sent" value={summary?.prompts ?? 0} />
            <KpiCard label="Conversations" value={summary?.conversations ?? 0} />
            <KpiCard label="Apps used" value={apps.length} />
            <KpiCard
              label="Organisation median"
              value={comparison?.org_median_prompts ?? 0}
              hint={
                comparison
                  ? comparison.above_median
                    ? "You're above average"
                    : "You're below average"
                  : undefined
              }
            />
          </div>

          <ChartCard title="Where you use Copilot">
            {apps.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No app breakdown available yet.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th className="px-3 py-2 text-left font-medium text-slate-500 dark:text-slate-400">
                      App
                    </th>
                    <th className="px-3 py-2 text-right font-medium text-slate-500 dark:text-slate-400">
                      Prompts
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {apps.map((a) => (
                    <tr
                      key={a.app_name ?? "unknown"}
                      className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                    >
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                        {a.app_name ?? "Unknown"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-900 dark:text-slate-100">
                        {a.prompts}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </ChartCard>
        </>
      )}
    </div>
  );
}

/**
 * The way through to organisation-wide reporting. When the user isn't allowed,
 * this is shown locked rather than hidden — otherwise people assume the feature
 * is broken and raise a ticket, instead of knowing to ask for access.
 */
function OrgViewBanner({ canViewOrg }: { canViewOrg: boolean }) {
  return (
    <div className="card mb-5 flex flex-wrap items-center justify-between gap-4">
      {canViewOrg ? (
        <>
          <div>
            <div className="font-medium text-slate-900 dark:text-slate-100">
              Looking for everyone else?
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              You have access to organisation-wide reporting.
            </div>
          </div>
          <Link to="/overview" className="btn-primary whitespace-nowrap">
            View organisation data →
          </Link>
        </>
      ) : (
        <>
          <div>
            <div className="font-medium text-slate-900 dark:text-slate-100">
              Organisation view
            </div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              🔒 Organisation-wide reporting is limited to an approved group. Ask your
              administrator if you need access.
            </div>
          </div>
          <button className="btn-secondary whitespace-nowrap" disabled>
            Not available
          </button>
        </>
      )}
    </div>
  );
}
