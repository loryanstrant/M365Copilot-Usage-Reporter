// Product logos for Copilot app surfaces. Icons are bundled locally in
// /public/logos and sourced from github.com/loryanstrant/MicrosoftCloudLogos.
// Names are normalised (lower-case, alphanumerics only) before lookup so minor
// variations ("Microsoft Teams", "Copilot Chat") still resolve.

const LOGO_FILE: Record<string, string> = {
  copilot: "copilot",
  copilotchat: "copilot",
  copilotsearch: "copilot",
  m365copilot: "copilot",
  microsoft365copilot: "copilot",
  bizchat: "copilot",
  word: "word",
  excel: "excel",
  powerpoint: "powerpoint",
  outlook: "outlook",
  onenote: "onenote",
  teams: "teams",
  microsoftteams: "teams",
  loop: "loop",
  whiteboard: "whiteboard",
  vivaengage: "vivaengage",
  stream: "stream",
  sharepoint: "sharepoint",
  forms: "forms",
  onedrive: "onedrive",
  planner: "planner",
};

function normalise(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Resolve an app display name to a bundled logo URL, or null when unknown. */
export function appLogoSrc(name: string | null | undefined): string | null {
  if (!name) return null;
  const file = LOGO_FILE[normalise(name)];
  return file ? `/logos/${file}.png` : null;
}

/** An app name rendered with its product logo (blank spacer keeps text aligned). */
export default function AppLabel({
  name,
  className = "",
}: {
  name: string | null | undefined;
  className?: string;
}) {
  const label = name ?? "—";
  const src = appLogoSrc(name);
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      {src ? (
        <img
          src={src}
          alt=""
          aria-hidden="true"
          className="h-4 w-4 shrink-0 object-contain"
          loading="lazy"
        />
      ) : (
        <span className="h-4 w-4 shrink-0" aria-hidden="true" />
      )}
      <span className="truncate">{label}</span>
    </span>
  );
}

interface TickProps {
  x?: number;
  y?: number;
  payload?: { value?: string | number };
}

/**
 * A Recharts X-axis tick that draws each category's product logo. Apps with a
 * known logo show the icon (the full name is still available on hover via the
 * chart tooltip); unknown apps fall back to a short truncated text label.
 */
export function AppAxisTick({ x = 0, y = 0, payload }: TickProps) {
  const name = String(payload?.value ?? "");
  const src = appLogoSrc(name);
  const size = 22;
  if (src) {
    return (
      <g transform={`translate(${x},${y})`}>
        <image href={src} x={-size / 2} y={6} width={size} height={size} />
      </g>
    );
  }
  const short = name.length > 11 ? `${name.slice(0, 10)}…` : name;
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={16} textAnchor="middle" fontSize={9} fill="#94a3b8">
        {short}
      </text>
    </g>
  );
}
