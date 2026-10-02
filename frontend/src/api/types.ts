export interface AppConfig {
  tenant_id: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  copilot_sku_ids: string[];
  report_access_group_id: string | null;
  /** Members may see organisation-wide data. Null = open to all signed-in users. */
  org_view_group_id: string | null;
  /** Members get admin on Entra sign-in. Null = nobody does (fails closed). */
  admin_group_id: string | null;
  backfill_days: number;
  schedule_cron: string | null;
  schedule_interval_hours: number;
  configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

/** A tenant subscription, and whether it grants Copilot. */
export interface CopilotSku {
  sku_id: string;
  name: string;
  grants_copilot: boolean;
  seats: number;
  assigned: number;
}

export interface TestConnectionResult {
  ok: boolean;
  token_acquired: boolean;
  subscribed_skus: boolean;
  copilot_skus?: CopilotSku[];
  directory_read: boolean;
  copilot_licensed_users: number | null;
  detail: string | null;
}

export interface JobRun {
  id: number;
  job_name: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
}

export interface StatusResult {
  configured: boolean;
  last_run: JobRun | null;
  prompts: number;
  conversations: number;
  licensed_users: number;
  entra_users: number;
}

export interface IngestRunResult {
  status: string;
  detail: string;
}

export interface BackfillProgress {
  status: string; // idle | running | completed | cancelled | failed
  users_total: number;
  users_done: number;
  prompts: number;
  lookback_days: number;
  started_at: string | null;
  updated_at: string | null;
  detail: string | null;
}

// --- metrics ------------------------------------------------------------
export interface MetricsSummary {
  prompts: number;
  conversations: number;
  avg_prompts_per_conversation: number;
  active_users: number;
  licensed_users: number;
  directory_users: number;
  adoption_rate: number;
  copilot_score: number;
  license_enabled: number;
  license_allocated: number;
  license_available: number;
}

export interface DailyPoint {
  date: string;
  prompts: number;
  conversations: number;
}

export interface AppDailyPoint {
  app_name: string | null;
  date: string;
  prompts: number;
  conversations: number;
}

export interface AppRow {
  app_name: string | null;
  prompts: number;
  conversations: number;
  avg_prompts_per_conversation: number;
  users: number;
  first_use: string | null;
  last_use: string | null;
  days_since_last: number | null;
}

export interface UserRow {
  user_id: string;
  display_name: string | null;
  department: string | null;
  office_location: string | null;
  manager_id: string | null;
  has_copilot_license: boolean;
  prompts: number;
  conversations: number;
  avg_prompts_per_conversation: number;
  first_use: string | null;
  last_use: string | null;
  days_since_last: number | null;
}

export interface CategoryRow {
  category: string;
  users: number;
}

export interface ActiveInactive {
  active: number;
  inactive: number;
  licensed: number;
}

export interface BriefingPeriod {
  prompts: number;
  conversations: number;
  active_users: number;
}

export interface BriefingApp {
  name: string | null;
  prompts: number;
  prev_prompts: number;
}

export interface BriefingDept {
  name: string | null;
  prompts: number;
}

export interface Briefing {
  window_days: number;
  period_start: string;
  period_end: string;
  previous_period_start: string;
  current: BriefingPeriod;
  previous: BriefingPeriod;
  licensed_users: number;
  active_users: number;
  adoption_rate: number;
  inactive_users: number;
  copilot_score: number;
  total_prompts: number;
  top_apps: BriefingApp[];
  top_departments: BriefingDept[];
}

export interface LicensePoint {
  date: string;
  enabled: number;
  allocated: number;
  available: number;
}

export interface Freshness {  last_run: {
    job_name: string;
    status: string;
    started_at: string | null;
    finished_at: string | null;
  } | null;
  prompts: number;
  conversations: number;
  licensed_users: number;
  directory_users: number;
  earliest_prompt: string | null;
  latest_prompt: string | null;
}

// --- Phase 9 additions --------------------------------------------------
export interface ManagerOption {
  id: string;
  name: string;
}

export interface FilterOptions {
  apps: string[];
  departments: string[];
  offices: string[];
  companies: string[];
  job_titles: string[];
  chat_types: string[];
  conversation_locations: string[];
  managers: ManagerOption[];
}

export interface NamedCount {
  name: string | null;
  prompts: number;
  conversations: number;
}

export interface DailyChatType {
  date: string;
  chat_type: string;
  prompts: number;
  conversations: number;
}

export interface LocationsData {
  chat_types: NamedCount[];
  conversation_locations: NamedCount[];
  teams_locations: NamedCount[];
  file_locations: NamedCount[];
  daily_by_chat_type: DailyChatType[];
}

export interface RollupRow {
  name: string | null;
  manager_id?: string | null;
  prompts: number;
  conversations: number;
}

export interface LeaderboardRollups {
  users: UserRow[];
  departments: NamedCount[];
  offices: NamedCount[];
  managers: RollupRow[];
}

export interface LaggardRow {
  user_id: string;
  display_name: string;
  department: string | null;
  office_location: string | null;
  prompts_30d: number;
  last_use: string | null;
  days_since_last: number | null;
  inactive: boolean;
}

export interface LaggardTop {
  name: string;
  inactive_users: number;
}

export interface LaggardsData {
  users: LaggardRow[];
  top_departments: LaggardTop[];
  top_offices: LaggardTop[];
}

export interface CopilotScore {
  prompts: number;
  score: number;
}

// --- coaching pairs page ------------------------------------------------
export type PeerGroupBy = "department" | "office_location" | "manager";

export interface PeerMember {
  user_id: string;
  display_name: string;
  job_title: string | null;
  department: string | null;
  office_location: string | null;
  prompts: number;
  conversations: number;
  last_use: string | null;
  days_since_last: number | null;
}

export interface CoachingPair {
  leader: PeerMember;
  laggard: PeerMember;
  gap: number;
}

export interface PeerGroup {
  key: string;
  name: string;
  licensed: number;
  active: number;
  inactive: number;
  adoption_rate: number;
  total: number;
  avg: number;
  leaders: PeerMember[];
  laggards: PeerMember[];
  pairs: CoachingPair[];
}

export interface CoachingPairsData {
  group_by: PeerGroupBy;
  group_label: string;
  metric: "prompts" | "conversations";
  groups: PeerGroup[];
  totals: {
    groups: number;
    groups_with_pairs: number;
    pairs: number;
    leaders: number;
    laggards: number;
  };
}

export interface BreakdownRow {
  d1: string | null;
  d2: string | null;
  prompts: number;
  conversations: number;
}

// --- backfill page ------------------------------------------------------
export interface BackfillRun {
  id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
}

export interface BackfillCoverage {
  earliest_covered: string | null;
  earliest_prompt: string | null;
  lookback_days: number | null;
  total_prompts: number;
  has_run: boolean;
  last_run_at: string | null;
}

export interface UserSyncStatus {
  status: string; // idle | running | completed | failed
  running: boolean;
  licensed_users: number;
  directory_users: number;
  detail: string | null;
  updated_at: string | null;
}


/** One row of the tenant users listing (GET /metrics/users). */
export interface DirectoryUser {
  user_id: string;
  user_principal_name: string | null;
  display_name: string | null;
  job_title: string | null;
  department: string | null;
  company_name: string | null;
  office_location: string | null;
  country: string | null;
  manager_name: string | null;
  user_type: string | null;
  has_copilot_license: boolean;
  prompts: number;
}

/** Customer branding (docs/specs/customer-branding.md).
 *
 *  Ramps are keyed by stop number AS A STRING. JSON object keys are strings;
 *  `Record<number, string>` type-checks here and then indexes wrong at runtime. */
export interface Branding {
  org_display_name: string | null;
  brand_primary_hex: string | null;
  ramp_light: Record<string, string>;
  ramp_dark: Record<string, string>;
  /** True when we brightened the dark accent to reach 4.5:1. Told to the admin. */
  dark_accent_lifted: boolean;
  dark_accent_contrast: number | null;
  /** White text on the sign-in gradient would fail AA, so use deeper stops. */
  gradient_needs_deepening: boolean;
  has_logo_light: boolean;
  has_logo_dark: boolean;
  logo_light_url: string | null;
  logo_dark_url: string | null;
  /** Render the light logo on a white panel when it sits on a dark surface. */
  logo_light_needs_plate: boolean;
}

export interface BrandingAdmin extends Branding {
  logo_light_bytes: number | null;
  logo_dark_bytes: number | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface RampPreview {
  ramp_light: Record<string, string>;
  ramp_dark: Record<string, string>;
  light_accent_contrast: number;
  dark_accent_contrast: number;
  dark_accent_lifted: boolean;
  gradient_needs_deepening: boolean;
}
