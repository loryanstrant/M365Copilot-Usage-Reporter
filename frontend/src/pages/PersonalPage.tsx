import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AppBars, {
  AppBarSortToggle,
  type AppBarSort,
  sortAppBars,
} from "../components/AppBars";
import ActivityTimeline, { type TimelinePoint } from "../components/ActivityTimeline";
import ChartCard from "../components/ChartCard";
import PeerComparison, { type PeerComparisonData } from "../components/PeerComparison";
import KpiCard from "../components/KpiCard";

interface Summary {
  prompts: number;
  conversations: number;
  active_days: number;
  avg_prompts_per_conversation?: number;
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
  const [appSort, setAppSort] = useState<AppBarSort>("value");
  const [peers, setPeers] = useState<PeerComparisonData | null>(null);
  const [daily, setDaily] = useState<TimelinePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [s, a, c, p, d] = await Promise.all([
          api<Summary>("/metrics/me/summary"),
          api<AppRow[]>("/metrics/me/by-app"),
          api<Comparison>("/metrics/me/comparison"),
          api<PeerComparisonData>("/metrics/me/peers"),
          api<TimelinePoint[]>("/metrics/me/daily"),
        ]);
        if (!active) return;
        setSummary(s);
        setApps(a);
        setComparison(c);
        setPeers(p);
        setDaily(d);
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
  const activeDays = summary?.active_days ?? 0;
  const perConversation =
    summary && summary.conversations > 0
      ? (summary.prompts / summary.conversations).toFixed(1)
      : null;
  const topApp =
    [...apps].sort((a, b) => b.prompts - a.prompts)[0]?.app_name ?? null;
  const appBars = sortAppBars(
    apps.map((a) => ({ name: a.app_name, value: a.prompts })),
    appSort,
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        Your usage
      </h1>
      <p className="mb-5 mt-1 text-sm text-slate-500 dark:text-slate-400">
        How you've been using Copilot. Only you and your administrators can see this.
      </p>

      <OrgViewBanner canViewOrg={user?.can_view_org ?? false} />

      {error && (
        <div className="card mb-5 p-5 text-sm text-amber-700 dark:text-amber-300">
          {error}
        </div>
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
            <KpiCard
              label="Prompts sent"
              value={summary?.prompts ?? 0}
              hint={
                activeDays
                  ? `Over ${activeDays} active ${activeDays === 1 ? "day" : "days"}`
                  : "No activity recorded yet"
              }
            />
            <KpiCard
              label="Conversations"
              value={summary?.conversations ?? 0}
              hint={
                perConversation
                  ? `${perConversation} prompts each on average`
                  : "Distinct Copilot threads"
              }
            />
            <KpiCard
              label="Apps used"
              value={apps.length}
              hint={topApp ? `Most in ${topApp}` : "Where you've used Copilot"}
            />
            <KpiCard
              label="Organisation median"
              value={comparison?.org_median_prompts ?? 0}
              hint={
                comparison
                  ? `${comparison.above_median ? "●" : "○"} You're ${
                      comparison.above_median ? "above" : "below"
                    } average of ${comparison.people_counted} people`
                  : "Not enough data to compare"
              }
            />
          </div>

          <ChartCard
            title="Your activity over time"
            subtitle="Prompts and conversations per day · line is a 7-day average"
            className="mb-5"
          >
            <ActivityTimeline
              points={daily}
              series={[
                { key: "prompts", label: "Prompts" },
                { key: "conversations", label: "Conversations" },
              ]}
            />
          </ChartCard>

          {peers && (
            <div className="mb-5">
              <PeerComparison
                data={peers}
                measures={[
                  { key: "prompts", label: "Prompts" },
                  { key: "conversations", label: "Conversations" },
                  { key: "apps", label: "Apps used" },
                ]}
              />
            </div>
          )}

          <ChartCard
            title="Where you use Copilot"
            subtitle="Prompts by app"
            action={
              apps.length > 1 ? (
                <AppBarSortToggle sort={appSort} onChange={setAppSort} />
              ) : undefined
            }
          >
            <AppBars
              rows={appBars}
              emptyMessage="No app breakdown available yet."
            />
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
    <div className="card mb-5 flex flex-wrap items-center justify-between gap-4 p-5">
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
