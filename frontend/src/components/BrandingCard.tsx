import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, patch, upload } from "../api/client";
import type { BrandingAdmin, RampPreview } from "../api/types";
import { useBranding } from "../branding/BrandingContext";
import { looksDark } from "../branding/logoLuminance";

// Settings -> "Your organisation's branding". Extracted rather than added to
// the settings page, which is already ~580 lines, following the existing
// DemoDataCard / SetupWizard pattern.
//
// `Field` and `bannerClass` are re-declared here rather than imported from the
// settings page. They match that page's markup exactly, but this file is
// committed byte-identical to all four sibling solutions and their settings
// pages differ — Agent Quality's is AdminPage.tsx and its `Field` renders its
// own input, so an import would only work in three of the four. A component
// importing from a page is the wrong direction anyway.

const MAX_BYTES = 1024 * 1024;
const MAX_PIXELS = 4000;
const ACCEPT = "image/png,image/jpeg,image/svg+xml";
const HEX = /^#?[0-9a-fA-F]{6}$/;

/** Same markup as the settings page's own label/hint pair. */
function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{hint}</p>}
    </div>
  );
}

/** Same three banner treatments the settings page uses. */
function bannerClass(kind: "ok" | "error" | "info"): string {
  return {
    ok: "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
    error: "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400",
    info: "bg-brand-50 text-brand-700 dark:bg-brand-900/20 dark:text-brand-400",
  }[kind];
}

type Slot = "light" | "dark";

function prettyBytes(n: number): string {
  return n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
}

/** Catch the common mistakes before spending a round trip on them. The server
 *  repeats the type and size checks independently; this is a courtesy, not the
 *  enforcement. */
async function preValidate(file: File): Promise<string | null> {
  const name = file.name.toLowerCase();
  const ok =
    ACCEPT.split(",").includes(file.type) ||
    /\.(png|jpe?g|svg)$/.test(name);
  if (!ok) {
    const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "that file";
    return `That's ${ext === "that file" ? "not an image we recognise" : `a ${ext} file`}. Please choose a PNG, JPEG or SVG.`;
  }
  if (file.size > MAX_BYTES) {
    return `That file is ${prettyBytes(file.size)}. Please choose one under 1 MB.`;
  }
  if (file.type !== "image/svg+xml") {
    const size = await new Promise<{ w: number; h: number } | null>((resolve) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        resolve({ w: img.naturalWidth, h: img.naturalHeight });
        URL.revokeObjectURL(url);
      };
      img.onerror = () => {
        resolve(null);
        URL.revokeObjectURL(url);
      };
      img.src = url;
    });
    if (size && (size.w > MAX_PIXELS || size.h > MAX_PIXELS)) {
      return `That image is ${size.w} by ${size.h} pixels. Please resize it to under ${MAX_PIXELS} pixels.`;
    }
  }
  return null;
}

/** Turn a ramp of hexes into scoped CSS variables, so a preview can show the
 *  PENDING colour while the rest of the page keeps the saved one. Works
 *  because the brand scale resolves through these variables (see index.css). */
function previewVars(ramp: Record<string, string>): React.CSSProperties {
  const vars: Record<string, string> = {};
  for (const [stop, hex] of Object.entries(ramp ?? {})) {
    const h = hex.replace("#", "");
    vars[`--brand-${stop}`] = `${parseInt(h.slice(0, 2), 16)} ${parseInt(h.slice(2, 4), 16)} ${parseInt(h.slice(4, 6), 16)}`;
  }
  // Custom properties are not part of the CSSProperties type.
  return vars as React.CSSProperties;
}

export default function BrandingCard() {
  const { refresh } = useBranding();
  const [cfg, setCfg] = useState<BrandingAdmin | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState<Slot | null>(null);
  const [banner, setBanner] = useState<{ kind: "ok" | "error" | "info"; text: string } | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const [orgName, setOrgName] = useState("");
  const [hex, setHex] = useState("#2f5ae0");
  const [plate, setPlate] = useState(false);
  const [plateAuto, setPlateAuto] = useState(false);
  const [preview, setPreview] = useState<RampPreview | null>(null);

  const lightInput = useRef<HTMLInputElement>(null);
  const darkInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<BrandingAdmin>("/admin/branding");
      setCfg(data);
      setOrgName(data.org_display_name ?? "");
      setHex(data.brand_primary_hex ?? "#2f5ae0");
      setPlate(data.logo_light_needs_plate);
    } catch (err) {
      setBanner({ kind: "error", text: err instanceof ApiError ? err.message : "Could not load branding." });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Derive on the server, debounced. Keeping the colour maths in one
  // implementation is the point: a second copy in the browser would drift, and
  // the symptom would be the preview disagreeing with the saved result.
  useEffect(() => {
    if (!HEX.test(hex)) return;
    // `cancelled` guards against an out-of-order response: debouncing stops us
    // firing on every keystroke, but two requests can still be in flight and
    // the slower one must not paint the preview the wrong colour.
    let cancelled = false;
    const id = window.setTimeout(async () => {
      try {
        const next = await api<RampPreview>("/admin/branding/preview", {
          method: "POST",
          body: JSON.stringify({ brand_primary_hex: hex }),
        });
        if (!cancelled) setPreview(next);
      } catch {
        /* keep the last good preview */
      }
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [hex]);

  async function onSave() {
    setSaving(true);
    setBanner(null);
    try {
      const saved = await api<BrandingAdmin>("/admin/branding", {
        method: "PUT",
        body: JSON.stringify({
          org_display_name: orgName,
          brand_primary_hex: HEX.test(hex) ? hex : "",
        }),
      });
      setCfg(saved);
      await refresh();
      setBanner({ kind: "ok", text: "Branding saved." });
    } catch (err) {
      setBanner({ kind: "error", text: err instanceof ApiError ? err.message : "Could not save branding." });
    } finally {
      setSaving(false);
    }
  }

  async function onPickFile(slot: Slot, file: File | undefined) {
    if (!file) return;
    setBanner(null);
    const problem = await preValidate(file);
    if (problem) {
      setBanner({ kind: "error", text: problem });
      return;
    }

    let wantsPlate = plate;
    if (slot === "light") {
      const dark = await looksDark(file);
      if (dark !== null) {
        wantsPlate = dark;
        setPlate(dark);
        setPlateAuto(dark);
      }
    }

    setUploading(slot);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("variant", slot);
      form.append("needs_light_plate", String(wantsPlate));
      const saved = await upload<BrandingAdmin>("/admin/branding/logo", form);
      setCfg(saved);
      await refresh();
      setBanner({ kind: "ok", text: "Logo saved." });
    } catch (err) {
      setBanner({ kind: "error", text: err instanceof ApiError ? err.message : "Could not upload that logo." });
    } finally {
      setUploading(null);
      if (lightInput.current) lightInput.current.value = "";
      if (darkInput.current) darkInput.current.value = "";
    }
  }

  async function onRemoveLogo(slot: Slot) {
    try {
      setCfg(await api<BrandingAdmin>(`/admin/branding/logo/${slot}`, { method: "DELETE" }));
      await refresh();
    } catch (err) {
      setBanner({ kind: "error", text: err instanceof ApiError ? err.message : "Could not remove that logo." });
    }
  }

  async function onTogglePlate(next: boolean) {
    setPlate(next);
    setPlateAuto(false);
    if (!cfg?.has_logo_light) return;
    // One boolean, one small request. This used to re-fetch the stored logo and
    // POST it back, which sent a megabyte to change a checkbox and re-ran
    // validation on bytes whose filename had lost its extension.
    try {
      const form = new FormData();
      form.append("needs_light_plate", String(next));
      setCfg(await patch<BrandingAdmin>("/admin/branding/logo/light/plate", form));
      await refresh();
    } catch (err) {
      setBanner({
        kind: "error",
        text:
          err instanceof ApiError
            ? err.message
            : "Could not change the white panel setting.",
      });
      setPlate(!next); // put the checkbox back where it was
    }
  }

  async function onReset() {
    try {
      const cleared = await api<BrandingAdmin>("/admin/branding", { method: "DELETE" });
      setCfg(cleared);
      setOrgName("");
      setHex("#2f5ae0");
      setPlate(false);
      setConfirmReset(false);
      await refresh();
      setBanner({ kind: "ok", text: "Branding removed. The app is back to its own look." });
    } catch (err) {
      setBanner({ kind: "error", text: err instanceof ApiError ? err.message : "Could not reset branding." });
    }
  }

  const hexValid = HEX.test(hex);
  const swatch = hexValid ? (hex.startsWith("#") ? hex : `#${hex}`) : "#2f5ae0";

  return (
    <div className="card p-6">
      <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Your organisation's branding
      </h3>
      <p className="mb-5 text-xs text-slate-400 dark:text-slate-500">
        Add your logo and a colour so the app looks like it belongs to your organisation. Your
        logo appears at the top of the sidebar and on the sign-in screen, alongside the
        product's own. Chart colours and the status colours are never changed, so nothing you
        already read means something different afterwards.
      </p>

      {loading ? (
        <div className="muted text-sm">Loading branding…</div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* ---- controls ---- */}
          <div className="space-y-4">
            <Field
              label="Organisation name"
              hint="Shown next to your logo, read out by screen readers in place of it, and added to the browser tab. Leave blank to show nothing."
            >
              <input
                className="input"
                maxLength={80}
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Avanoso"
              />
            </Field>

            <Field
              label="Logo"
              hint="PNG, JPEG or SVG, up to 1 MB. Wide logos look best — yours is shown about 200 pixels wide and 28 pixels tall."
            >
              <LogoRow
                slot="light"
                inputRef={lightInput}
                uploading={uploading === "light"}
                has={cfg?.has_logo_light ?? false}
                bytes={cfg?.logo_light_bytes ?? null}
                url={cfg?.logo_light_url ?? null}
                onPick={onPickFile}
                onRemove={onRemoveLogo}
              />
            </Field>

            <Field
              label="Logo for dark backgrounds (optional)"
              hint="If your logo is dark, upload a lighter version for dark mode. Leave this empty and we'll put a white panel behind your main logo instead."
            >
              <LogoRow
                slot="dark"
                inputRef={darkInput}
                uploading={uploading === "dark"}
                has={cfg?.has_logo_dark ?? false}
                bytes={cfg?.logo_dark_bytes ?? null}
                url={cfg?.logo_dark_url ?? null}
                onPick={onPickFile}
                onRemove={onRemoveLogo}
                dark
              />
            </Field>

            {cfg?.has_logo_light && !cfg?.has_logo_dark && (
              <div>
                <label className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={plate}
                    onChange={(e) => void onTogglePlate(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    Show my logo on a white panel in dark mode
                  </span>
                </label>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  {plateAuto
                    ? "We had a look at your logo and it's quite dark, so we've switched this on. Untick it if you'd rather not have the panel."
                    : "Turn this on if your logo disappears against the dark sidebar."}
                </p>
              </div>
            )}

            <Field
              label="Accent colour"
              hint="One colour. We work out the lighter and darker shades for you, and nudge the dark-mode shade brighter if it would be hard to read. We keep your colour's hue but set its brightness to match the app's design, so text on buttons stays legible — the preview shows exactly what you'll get."
            >
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  aria-label="Pick an accent colour"
                  value={swatch}
                  onChange={(e) => setHex(e.target.value)}
                  className="h-9 w-12 shrink-0 cursor-pointer rounded border border-slate-300 bg-white p-0.5 dark:border-slate-600 dark:bg-slate-900"
                />
                <input
                  className="input font-mono"
                  value={hex}
                  onChange={(e) => setHex(e.target.value)}
                  placeholder="#2f5ae0"
                  aria-label="Accent colour as a hex value"
                />
              </div>
              {!hexValid && hex.trim() !== "" && (
                <p className="mt-1 text-xs font-medium text-red-600 dark:text-red-400">
                  That isn't a colour code. Use a six-digit hex value like #2f5ae0.
                </p>
              )}
            </Field>

            <ul className="space-y-2 text-sm">
              <CheckRow ok={cfg?.has_logo_light ?? false} label="Logo uploaded" />
              <CheckRow ok={cfg?.has_logo_dark ?? false} label="Dark-background logo uploaded" />
            </ul>
          </div>

          {/* ---- preview + actions ---- */}
          <div>
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
              Preview
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <PreviewPane
                mode="light"
                vars={previewVars(preview?.ramp_light ?? {})}
                logo={cfg?.logo_light_url ?? null}
                name={orgName}
              />
              <PreviewPane
                mode="dark"
                vars={previewVars(preview?.ramp_dark ?? {})}
                logo={cfg?.logo_dark_url ?? cfg?.logo_light_url ?? null}
                plated={!cfg?.has_logo_dark && plate}
                name={orgName}
              />
            </div>

            {preview?.dark_accent_lifted && (
              <div className={`mt-4 rounded-lg px-4 py-3 text-sm ${bannerClass("info")}`}>
                We brightened your colour a little for dark mode so text on it stays readable
                (contrast is now {preview.dark_accent_contrast.toFixed(1)} to 1). Light mode
                uses your colour as chosen.
              </div>
            )}

            {banner && (
              <div className={`mt-4 rounded-lg px-4 py-3 text-sm ${bannerClass(banner.kind)}`}>
                {banner.text}
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-3">
              <button className="btn-primary" onClick={() => void onSave()} disabled={saving}>
                {saving ? "Saving…" : "Save branding"}
              </button>
              {confirmReset ? (
                <>
                  <span className="self-center text-sm text-slate-600 dark:text-slate-300">
                    Remove your logo and colour?
                  </span>
                  <button className="btn-primary" onClick={() => void onReset()}>
                    Yes, reset
                  </button>
                  <button className="btn-secondary" onClick={() => setConfirmReset(false)}>
                    Cancel
                  </button>
                </>
              ) : (
                <button className="btn-secondary" onClick={() => setConfirmReset(true)}>
                  Reset to the product's branding
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className={ok ? "text-green-600" : "text-slate-300"}>{ok ? "✓" : "○"}</span>
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
    </li>
  );
}

function LogoRow({
  slot,
  inputRef,
  uploading,
  has,
  bytes,
  url,
  onPick,
  onRemove,
  dark = false,
}: {
  slot: Slot;
  inputRef: React.RefObject<HTMLInputElement>;
  uploading: boolean;
  has: boolean;
  bytes: number | null;
  url: string | null;
  onPick: (slot: Slot, file: File | undefined) => Promise<void>;
  onRemove: (slot: Slot) => Promise<void>;
  dark?: boolean;
}) {
  if (!has && !uploading) {
    return (
      <div className="space-y-2">
        <div
          className={`flex h-16 items-center justify-center rounded-lg border border-dashed text-xs ${
            dark
              ? "border-slate-300 bg-slate-800 text-slate-400 dark:border-slate-600"
              : "border-slate-300 text-slate-400 dark:border-slate-600 dark:text-slate-500"
          }`}
        >
          No logo uploaded
        </div>
        <FilePicker slot={slot} inputRef={inputRef} onPick={onPick} label="Choose a file" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        className={`flex h-16 items-center justify-center rounded-lg border px-3 ${
          dark
            ? "border-slate-700 bg-slate-800"
            : "border-slate-200 bg-white dark:border-slate-700"
        }`}
      >
        {url && <img src={url} alt="" className="max-h-10 max-w-full object-contain" />}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <FilePicker slot={slot} inputRef={inputRef} onPick={onPick} label={uploading ? "Uploading…" : "Replace"} disabled={uploading} />
        <button className="text-xs font-medium text-slate-500 underline dark:text-slate-400" onClick={() => void onRemove(slot)}>
          Remove
        </button>
        {bytes != null && (
          <span className="text-xs text-slate-400 dark:text-slate-500">{prettyBytes(bytes)}</span>
        )}
      </div>
    </div>
  );
}

function FilePicker({
  slot,
  inputRef,
  onPick,
  label,
  disabled = false,
}: {
  slot: Slot;
  inputRef: React.RefObject<HTMLInputElement>;
  onPick: (slot: Slot, file: File | undefined) => Promise<void>;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label className={`btn-secondary inline-block ${disabled ? "opacity-60" : "cursor-pointer"}`}>
      {label}
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept={ACCEPT}
        disabled={disabled}
        onChange={(e) => void onPick(slot, e.target.files?.[0])}
      />
    </label>
  );
}

/** One mock of the app in the pending colour. The dark one is wrapped in
 *  `.dark`, which Tailwind matches on any ancestor — so a forced-dark preview
 *  needs no config change and never touches the real theme. */
function PreviewPane({
  mode,
  vars,
  logo,
  plated = false,
  name,
}: {
  mode: "light" | "dark";
  vars: React.CSSProperties;
  logo: string | null;
  plated?: boolean;
  name: string;
}) {
  const dark = mode === "dark";
  return (
    <div
      style={vars}
      className={`${dark ? "dark " : ""}rounded-lg border p-3 ${
        dark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-slate-50"
      }`}
    >
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {dark ? "Dark mode" : "Light mode"}
      </div>
      <div className={`space-y-2 rounded-md p-3 ${dark ? "bg-slate-800" : "bg-white"}`}>
        <div className={`flex items-center border-b pb-2 ${dark ? "border-slate-700" : "border-slate-200"}`}>
          {logo ? (
            plated ? (
              <span className="inline-flex items-center rounded-md bg-white/95 px-2 py-1">
                <img src={logo} alt="" className="h-4 max-w-[112px] object-contain" />
              </span>
            ) : (
              <img src={logo} alt="" className="h-5 max-w-[120px] object-contain object-left" />
            )
          ) : (
            <span className="truncate text-[10px] font-semibold uppercase tracking-wide text-slate-400">
              {name || "Your logo"}
            </span>
          )}
        </div>
        <div className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-medium text-white">Adoption</div>
        <button className="btn-primary w-full !py-1.5 !text-xs" type="button">Save</button>
        <div className="text-xs">
          <span className={`font-medium underline ${dark ? "text-brand-500" : "text-brand-600"}`}>A text link</span>
        </div>
        <input className="input !py-1 !text-xs" placeholder="Click to see the focus ring" />
      </div>
    </div>
  );
}
