import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Briefing, BriefingApp, DailyPoint } from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import { appLogoSrc } from "../components/AppLabel";
import { gradId } from "../components/chartTheme";

type Tone = "positive" | "negative" | "neutral";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

// Fractional change cur vs prev. null = no prior baseline (treat as "new").
function delta(cur: number, prev: number): number | null {
  if (prev === 0) return cur > 0 ? null : 0;
  return (cur - prev) / prev;
}

function appDelta(a: BriefingApp): number | null {
  return delta(a.prompts, a.prev_prompts);
}

// "up 18%" / "down 9%" / "flat"
function movement(d: number): string {
  if (Math.abs(d) < 0.005) return "flat";
  return `${d > 0 ? "up" : "down"} ${Math.round(Math.abs(d) * 100)}%`;
}

// "+18%" / "−9%" / "flat" / "new"
function chip(d: number | null): string {
  if (d === null) return "new";
  if (Math.abs(d) < 0.005) return "flat";
  return `${d > 0 ? "+" : "−"}${Math.round(Math.abs(d) * 100)}%`;
}

function toneOf(d: number | null): Tone {
  if (d === null) return "positive";
  if (d > 0.005) return "positive";
  if (d < -0.005) return "negative";
  return "neutral";
}

function buildNarrative(b: Briefing): { tone: Tone; text: string }[] {
  const w = b.window_days;
  const end = fmtDate(b.period_end);
  const dP = delta(b.current.prompts, b.previous.prompts);
  const dA = delta(b.current.active_users, b.previous.active_users);
  const out: { tone: Tone; text: string }[] = [];

  const trend =
    dP === null
      ? `, with no comparable activity in the prior ${w} days`
      : Math.abs(dP) < 0.005
        ? ", holding roughly flat against the previous period"
        : `, ${movement(dP)} versus the previous ${w} days`;
  out.push({
    tone: toneOf(dP),
    text: `In the ${w} days to ${end}, the organisation ran ${b.current.prompts.toLocaleString()} Copilot prompts across ${b.current.conversations.toLocaleString()} conversations${trend}.`,
  });

  const activeMove =
    dA === null || Math.abs(dA ?? 0) < 0.005
      ? ""
      : ` (${movement(dA as number)} on active users)`;
  out.push({
    tone: b.adoption_rate >= 0.4 ? "positive" : "neutral",
    text: `${b.active_users.toLocaleString()} of ${b.licensed_users.toLocaleString()} licensed users (${pct(
      b.adoption_rate,
    )}) were active this period${activeMove}.`,
  });

  const top = b.top_apps[0];
  if (top) {
    const growing = b.top_apps
      .map((a) => ({ a, d: appDelta(a) }))
      .filter((x) => x.d !== null && (x.d as number) > 0.05)
      .sort((a, b2) => (b2.d as number) - (a.d as number))[0];
    const grownText = growing
      ? ` ${growing.a.name} is accelerating (${movement(growing.d as number)}).`
      : "";
    out.push({
      tone: "positive",
      text: `${top.name} led usage with ${top.prompts.toLocaleString()} prompts.${grownText}`,
    });
  }

  if (b.inactive_users > 0) {
    const share = b.licensed_users
      ? ` — ${pct(b.inactive_users / b.licensed_users)} of licences`
      : "";
    out.push({
      tone: "negative",
      text: `${b.inactive_users.toLocaleString()} licensed users have not used Copilot in the last ${w} days${share}.`,
    });
  }

  return out;
}

function buildHighlights(b: Briefing): string[] {
  const items: string[] = [];
  const dP = delta(b.current.prompts, b.previous.prompts);
  if (dP !== null && dP > 0.005)
    items.push(`Prompt volume ${movement(dP)} period-on-period.`);
  const top = b.top_apps[0];
  if (top) items.push(`${top.name} leads with ${top.prompts.toLocaleString()} prompts.`);
  const growing = b.top_apps
    .map((a) => ({ a, d: appDelta(a) }))
    .filter((x) => x.d !== null && (x.d as number) > 0.05)
    .sort((a, c) => (c.d as number) - (a.d as number))[0];
  if (growing) items.push(`${growing.a.name} is accelerating (${chip(growing.d)}).`);
  const dept = b.top_departments[0];
  if (dept) items.push(`${dept.name} is the most active team (${dept.prompts.toLocaleString()} prompts).`);
  if (b.adoption_rate >= 0.5) items.push(`Healthy adoption at ${pct(b.adoption_rate)} of licences.`);
  if (b.copilot_score >= 40) items.push(`Copilot score of ${b.copilot_score}/100.`);
  return items.slice(0, 5);
}

function buildWatchouts(b: Briefing): string[] {
  const items: string[] = [];
  const dP = delta(b.current.prompts, b.previous.prompts);
  if (dP !== null && dP < -0.005)
    items.push(`Usage ${movement(dP)} versus the previous period.`);
  if (b.inactive_users > 0)
    items.push(`${b.inactive_users.toLocaleString()} licence holders inactive for 30+ days.`);
  if (b.adoption_rate < 0.5)
    items.push(`Adoption at ${pct(b.adoption_rate)} — significant headroom remains.`);
  const declining = b.top_apps
    .map((a) => ({ a, d: appDelta(a) }))
    .filter((x) => x.d !== null && (x.d as number) < -0.1)
    .sort((a, c) => (a.d as number) - (c.d as number))[0];
  if (declining) items.push(`${declining.a.name} usage fell ${chip(declining.d)}.`);
  return items.slice(0, 5);
}

function buildActions(b: Briefing): string[] {
  const items: string[] = [];
  if (b.inactive_users > 0)
    items.push(`Target the ${b.inactive_users.toLocaleString()} inactive licence holders with enablement — start from the Laggards page.`);
  const growing = b.top_apps
    .map((a) => ({ a, d: appDelta(a) }))
    .filter((x) => x.d !== null && (x.d as number) > 0.05)
    .sort((a, c) => (c.d as number) - (a.d as number))[0];
  if (growing)
    items.push(`Amplify ${growing.a.name} — share the wins behind its ${chip(growing.d)} growth.`);
  const dept = b.top_departments[0];
  if (dept) items.push(`Ask ${dept.name} to share their playbook with other teams.`);
  if (b.adoption_rate < 0.6)
    items.push(`Stand up a champions programme to lift adoption beyond ${pct(b.adoption_rate)}.`);
  items.push("Dig into the detail on the Usage and Leaderboards pages.");
  return items.slice(0, 5);
}

export default function BriefingPage() {
  const [b, setB] = useState<Briefing | null>(null);
  const [daily, setDaily] = useState<DailyPoint[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [brief, d] = await Promise.all([
          api<Briefing>("/metrics/briefing"),
          api<DailyPoint[]>("/metrics/daily"),
        ]);
        setB(brief);
        setDaily(d);
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
  }, []);

  const narrative = useMemo(() => (b ? buildNarrative(b) : []), [b]);
  const highlights = useMemo(() => (b ? buildHighlights(b) : []), [b]);
  const watchouts = useMemo(() => (b ? buildWatchouts(b) : []), [b]);
  const actions = useMemo(() => (b ? buildActions(b) : []), [b]);
  const spark = useMemo(() => daily.slice(-60), [daily]);
  const generatedAt = useMemo(
    () => new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }),
    [],
  );

  if (loaded && (!b || b.total_prompts === 0)) {
    return (
      <div className="space-y-6">
        <Header period="" generatedAt={generatedAt} />
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
          No usage data yet. Configure Microsoft Graph in Settings and run an ingest to
          generate your first briefing.
        </div>
      </div>
    );
  }

  if (!b) {
    return (
      <div className="space-y-6">
        <Header period="" generatedAt={generatedAt} />
        <div className="text-sm text-slate-500 dark:text-slate-400">Preparing briefing…</div>
      </div>
    );
  }

  const period = `${b.window_days} days to ${fmtDate(b.period_end)}`;
  const dPrompts = delta(b.current.prompts, b.previous.prompts);
  const dConv = delta(b.current.conversations, b.previous.conversations);
  const dActive = delta(b.current.active_users, b.previous.active_users);

  return (
    <div className="space-y-8">
      <Header period={period} generatedAt={generatedAt} />

      {/* Narrative commentary — the heart of the briefing. */}
      <div className="card border-l-4 border-l-brand-500 p-6">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
          <span>Summary</span>
          <span className="text-slate-300 dark:text-slate-600">•</span>
          <span className="font-normal normal-case text-slate-400">Auto-generated from your data</span>
        </div>
        <div className="space-y-2.5">
          {narrative.map((p, i) => (
            <p key={i} className="flex gap-2 text-[15px] leading-relaxed text-slate-700 dark:text-slate-200">
              <span aria-hidden className={`mt-1 text-xs ${toneColor(p.tone)}`}>
                {p.tone === "positive" ? "▲" : p.tone === "negative" ? "▼" : "■"}
              </span>
              <span>{p.text}</span>
            </p>
          ))}
        </div>
      </div>

      {/* Headline movement vs the previous period. */}
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <DeltaStat label="Prompts" value={b.current.prompts} d={dPrompts} />
        <DeltaStat label="Conversations" value={b.current.conversations} d={dConv} />
        <DeltaStat label="Active users" value={b.current.active_users} d={dActive} />
        <DeltaStat
          label="Adoption"
          value={pct(b.adoption_rate)}
          d={null}
          hint={`${b.active_users} of ${b.licensed_users} licensed`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard
          title="Momentum"
          subtitle="Daily prompt volume, last 60 days"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={spark} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={8} minTickGap={24} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="prompts"
                name="Prompts"
                stroke="#3b6ef5"
                strokeWidth={2.5}
                fill={`url(#${gradId(0)})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <div className="card flex flex-col items-center justify-center gap-3 p-6 text-center">
          <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Copilot score
          </div>
          <ScoreRing score={b.copilot_score} />
          <div className="text-xs text-slate-400 dark:text-slate-500">
            {b.total_prompts.toLocaleString()} prompts all-time
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ListCard title="Highlights" tone="positive" items={highlights} empty="Nothing notable this period." />
        <ListCard title="Watch-outs" tone="negative" items={watchouts} empty="No concerns flagged — nice." />
      </div>

      <div className="card p-6">
        <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Leading surfaces
        </h3>
        {b.top_apps.length === 0 ? (
          <div className="text-sm text-slate-400">No app usage this period.</div>
        ) : (
          <div className="space-y-3">
            {b.top_apps.map((a) => {
              const d = appDelta(a);
              const max = b.top_apps[0].prompts || 1;
              const src = appLogoSrc(a.name);
              return (
                <div key={a.name ?? "—"} className="flex items-center gap-3">
                  {src ? (
                    <img src={src} alt="" aria-hidden className="h-5 w-5 shrink-0 object-contain" />
                  ) : (
                    <span className="h-5 w-5 shrink-0" aria-hidden />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                        {a.name ?? "—"}
                      </span>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="tabular-nums text-sm text-slate-500 dark:text-slate-400">
                          {a.prompts.toLocaleString()}
                        </span>
                        <DeltaChip d={d} />
                      </div>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                      <div
                        className="h-full rounded-full bg-brand-500"
                        style={{ width: `${(a.prompts / max) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <ListCard title="Suggested actions" tone="neutral" items={actions} empty="" numbered />
    </div>
  );
}

function Header({ period, generatedAt }: { period: string; generatedAt: string }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">Executive briefing</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {period ? `A plain-English snapshot for the ${period}.` : "Copilot at a glance."}
        </p>
      </div>
      <div className="text-right text-xs text-slate-400 dark:text-slate-500">
        Generated {generatedAt}
      </div>
    </div>
  );
}

function toneColor(tone: Tone): string {
  return tone === "positive"
    ? "text-emerald-500"
    : tone === "negative"
      ? "text-rose-500"
      : "text-slate-400";
}

function DeltaChip({ d }: { d: number | null }) {
  const tone = toneOf(d);
  const cls =
    tone === "positive"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
      : tone === "negative"
        ? "bg-rose-50 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400"
        : "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${cls}`}>
      {chip(d)}
    </span>
  );
}

function DeltaStat({
  label,
  value,
  d,
  hint,
}: {
  label: string;
  value: string | number;
  d: number | null;
  hint?: string;
}) {
  const showDelta = d !== null;
  const tone = toneOf(d);
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm dark:border-slate-700 dark:from-slate-800 dark:to-slate-900/60">
      <div className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-brand-500/10 blur-2xl" />
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-500 dark:text-slate-400">{label}</span>
        {showDelta && <DeltaChip d={d} />}
      </div>
      <div className="mt-2 bg-gradient-to-br from-slate-900 to-slate-500 bg-clip-text text-3xl font-bold tabular-nums text-transparent dark:from-white dark:to-slate-400">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
        {hint ?? (showDelta ? `vs previous period` : "")}
        {showDelta && !hint && tone !== "neutral" ? ` · ${movement(d as number)}` : ""}
      </div>
    </div>
  );
}

function ListCard({
  title,
  tone,
  items,
  empty,
  numbered = false,
}: {
  title: string;
  tone: Tone;
  items: string[];
  empty: string;
  numbered?: boolean;
}) {
  const dot =
    tone === "positive"
      ? "text-emerald-500"
      : tone === "negative"
        ? "text-amber-500"
        : "text-brand-500";
  return (
    <div className="card p-6">
      <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h3>
      {items.length === 0 ? (
        <div className="text-sm text-slate-400">{empty}</div>
      ) : (
        <ul className="space-y-2.5">
          {items.map((it, i) => (
            <li key={i} className="flex gap-2.5 text-sm text-slate-600 dark:text-slate-300">
              <span className={`shrink-0 font-semibold ${dot}`}>
                {numbered ? `${i + 1}.` : "•"}
              </span>
              <span>{it}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ScoreRing({ score }: { score: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(100, score)) / 100;
  return (
    <svg width={96} height={96} viewBox="0 0 88 88" role="img" aria-label={`Copilot score ${score} of 100`}>
      <circle
        cx={44}
        cy={44}
        r={r}
        fill="none"
        strokeWidth={8}
        className="stroke-slate-200 dark:stroke-slate-700"
      />
      <circle
        cx={44}
        cy={44}
        r={r}
        fill="none"
        stroke="#3b6ef5"
        strokeWidth={8}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - frac)}
        transform="rotate(-90 44 44)"
      />
      <text x={44} y={42} textAnchor="middle" className="fill-slate-900 dark:fill-white" fontSize={22} fontWeight={700}>
        {score}
      </text>
      <text x={44} y={58} textAnchor="middle" className="fill-slate-400" fontSize={10}>
        / 100
      </text>
    </svg>
  );
}
