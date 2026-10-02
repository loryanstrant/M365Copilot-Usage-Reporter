import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "../api/client";
import type { Branding } from "../api/types";
import { applyRampCss, cacheBranding, rampCss, setTitle } from "./applyBranding";

// Customer branding, fetched once at start-up from a PUBLIC endpoint so the
// sign-in screen is branded too. Mounted inside ThemeProvider but OUTSIDE
// AuthProvider, because there is no user yet when the sign-in screen renders.
//
// This provider deliberately does NOT import useTheme. The injected stylesheet
// carries both a :root and a .dark block, so a theme switch needs no reaction
// from JavaScript — see applyBranding.ts.

export const PRODUCT_NAME = "M365 Copilot Usage Reporter";

const EMPTY: Branding = {
  org_display_name: null,
  brand_primary_hex: null,
  ramp_light: {},
  ramp_dark: {},
  dark_accent_lifted: false,
  dark_accent_contrast: null,
  gradient_needs_deepening: false,
  has_logo_light: false,
  has_logo_dark: false,
  logo_light_url: null,
  logo_dark_url: null,
  logo_light_needs_plate: false,
};

interface BrandingCtx {
  branding: Branding;
  /** Re-read after an admin saves, so the change shows without a reload. */
  refresh: () => Promise<void>;
}

const Ctx = createContext<BrandingCtx | null>(null);

export function BrandingProvider({ children }: { children: ReactNode }) {
  const [branding, setBranding] = useState<Branding>(EMPTY);

  const refresh = useCallback(async () => {
    try {
      const next = await api<Branding>("/auth/branding");
      setBranding(next);
      const css = rampCss(next.ramp_light, next.ramp_dark);
      applyRampCss(css);
      setTitle(PRODUCT_NAME, next.org_display_name);
      // Cache so the NEXT first paint is already branded.
      cacheBranding(css, next.org_display_name);
    } catch {
      // Branding is decoration. If this endpoint is unreachable the app must
      // still render — in the product's own colours, which is exactly what
      // leaving the index.css defaults alone gives us.
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return <Ctx.Provider value={{ branding, refresh }}>{children}</Ctx.Provider>;
}

export function useBranding(): BrandingCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useBranding must be used within BrandingProvider");
  return ctx;
}
