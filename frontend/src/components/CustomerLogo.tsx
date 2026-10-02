import { useBranding } from "../branding/BrandingContext";
import { useTheme } from "../theme/ThemeContext";

// The customer's logo, wherever it appears. Always ADDITIONAL to the product's
// own mark, never a substitute for it — the product mark stays exactly where it
// was in every placement below.
//
// This is the only file in the branding path allowed to call useTheme(), and
// only to pick which *image* to show. Colours follow the cascade (see
// applyBranding.ts), so nothing here reacts to a theme change.

export type LogoPlacement = "sidebar" | "login-panel" | "login-narrow";

const SIZES: Record<LogoPlacement, string> = {
  // 28px tall, capped at 200px wide, left-aligned so its left edge lines up
  // with the product mark below it. Wide wordmarks are the common case.
  sidebar: "h-7 max-w-[200px] object-contain object-left",
  "login-panel": "h-8 max-w-[150px] object-contain drop-shadow",
  "login-narrow": "h-8 max-w-[180px] object-contain",
};

// Inside the white plate the logo loses the plate's padding, so shrink it
// slightly to keep the overall block the same height as the bare variant.
const PLATE_SIZES: Record<LogoPlacement, string> = {
  sidebar: "h-5 max-w-[184px] object-contain",
  "login-panel": "h-6 max-w-[134px] object-contain",
  "login-narrow": "h-6 max-w-[164px] object-contain",
};

const TEXT_CLASSES: Record<LogoPlacement, string> = {
  sidebar:
    "truncate text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400",
  "login-panel": "truncate text-sm font-semibold text-white/90",
  "login-narrow":
    "truncate text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400",
};

export default function CustomerLogo({
  placement,
}: {
  placement: LogoPlacement;
}) {
  const { branding } = useBranding();
  const { theme } = useTheme();

  const name = branding.org_display_name;
  // The sign-in brand panel is a dark gradient whatever the theme is, so a
  // dark-ink logo needs the same treatment there even in light mode.
  const onDarkSurface = placement === "login-panel" || theme === "dark";

  if (!branding.has_logo_light && !branding.has_logo_dark) {
    // No logo, but a name is still something to show. An organisation that
    // hasn't got a logo file to hand still gets branding.
    return name ? <span className={TEXT_CLASSES[placement]}>{name}</span> : null;
  }

  const alt = name || "Customer logo";

  if (onDarkSurface && branding.has_logo_dark && branding.logo_dark_url) {
    return (
      <img src={branding.logo_dark_url} alt={alt} className={SIZES[placement]} />
    );
  }

  const src = branding.logo_light_url;
  if (!src) return null;

  // No dark variant supplied and the logo is dark ink: put it on a soft white
  // panel rather than letting it disappear into the background.
  if (onDarkSurface && branding.logo_light_needs_plate) {
    return (
      <span className="inline-flex items-center rounded-md bg-white/95 px-2 py-1">
        <img src={src} alt={alt} className={PLATE_SIZES[placement]} />
      </span>
    );
  }

  return <img src={src} alt={alt} className={SIZES[placement]} />;
}

/** Whether there is anything to draw, so callers can skip their wrapper
 *  (a divider with nothing beside it reads as a rendering bug). */
export function useHasCustomerBranding(): boolean {
  const { branding } = useBranding();
  return Boolean(
    branding.has_logo_light || branding.has_logo_dark || branding.org_display_name,
  );
}
