// Injects the customer's brand ramp as one <style> element in <head>.
//
// Why a stylesheet and not inline styles on <html>: we need two sets of values
// — one for light, one under `.dark` — and an inline style on <html> cannot be
// made conditional on <html>'s own class. The element carries a :root block and
// a .dark block, exactly mirroring index.css, so switching theme needs no
// JavaScript at all. The cascade does it.
//
// That is deliberate rather than incidental: it is what keeps the theme-desync
// bug documented in ThemeContext.tsx impossible to reintroduce here. Nothing in
// the branding path reads, writes or subscribes to theme state.

const STYLE_ID = "cur-brand-ramp";
const CSS_CACHE_KEY = "cur_brand_css";
const TITLE_CACHE_KEY = "cur_brand_title";

/** "#2f5ae0" -> "47 90 224". The variables hold channels so Tailwind's
 *  <alpha-value> slot can emit rgb(... / 0.2); a hex there is invalid CSS. */
function toChannels(hex: string): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `${r} ${g} ${b}`;
}

function block(selector: string, ramp: Record<string, string>): string {
  const lines = Object.entries(ramp)
    .map(([stop, hex]) => `  --brand-${stop}: ${toChannels(hex)};`)
    .join("\n");
  return `${selector} {\n${lines}\n}`;
}

/** Build the override stylesheet. Empty string when nothing is branded, which
 *  leaves index.css's defaults untouched. */
export function rampCss(
  light: Record<string, string>,
  dark: Record<string, string>,
): string {
  if (!light || Object.keys(light).length === 0) return "";
  return `${block(":root", light)}\n${block(".dark", dark ?? light)}\n`;
}

/** Replace the override stylesheet wholesale. Appended to <head>, so it always
 *  follows Tailwind's output and wins at equal specificity. */
export function applyRampCss(css: string): void {
  let el = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!css) {
    el?.remove();
    return;
  }
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = css;
}

export function setTitle(product: string, org: string | null): void {
  document.title = org ? `${product} — ${org}` : product;
}

/**
 * Apply the last known branding synchronously, before React mounts.
 *
 * Without this, every page load paints the product's blue and then repaints in
 * the customer's colour one round trip later. Mirrors how ThemeContext reads
 * its own localStorage key for the same reason. A first-ever visit still shows
 * one unbranded frame; that is unavoidable without server-rendering the
 * stylesheet into index.html, which the baked-bundle deployment rules out.
 */
export function applyCachedBranding(product: string): void {
  try {
    const css = localStorage.getItem(CSS_CACHE_KEY);
    if (css) applyRampCss(css);
    const org = localStorage.getItem(TITLE_CACHE_KEY);
    if (org) setTitle(product, org);
  } catch {
    /* private browsing can make localStorage throw; branding is not worth a
       blank page, so fall through to the product defaults. */
  }
}

export function cacheBranding(css: string, org: string | null): void {
  try {
    if (css) localStorage.setItem(CSS_CACHE_KEY, css);
    else localStorage.removeItem(CSS_CACHE_KEY);
    if (org) localStorage.setItem(TITLE_CACHE_KEY, org);
    else localStorage.removeItem(TITLE_CACHE_KEY);
  } catch {
    /* see above */
  }
}
