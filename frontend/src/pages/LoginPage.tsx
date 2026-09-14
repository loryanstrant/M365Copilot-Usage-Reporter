import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError, api } from "../api/client";

export default function LoginPage() {
  const { login, ssoError } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [entraEnabled, setEntraEnabled] = useState(false);

  // Show the Microsoft sign-in button only once an Entra app registration has
  // been saved in Settings. This works on any host — it asks our own API, not
  // an Azure-specific platform endpoint.
  useEffect(() => {
    (async () => {
      try {
        const cfg = await api<{ entra_enabled: boolean }>("/auth/config");
        setEntraEnabled(cfg.entra_enabled);
      } catch {
        /* API unreachable — leave the button hidden */
      }
    })();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full w-full">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-brand-500 p-12 text-white lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, white 0, transparent 40%), radial-gradient(circle at 80% 60%, white 0, transparent 35%)",
          }}
        />
        <div className="relative flex items-center gap-3">
          <img
            src="/app-logo.png"
            alt="Microsoft 365 Copilot"
            className="h-11 w-11 drop-shadow"
          />
          <span className="text-lg font-semibold">M365 Copilot Usage Reporter</span>
        </div>
        <div className="relative max-w-md">
          <h1 className="text-3xl font-semibold leading-tight">
            See who is really using Microsoft 365 Copilot
          </h1>
          <p className="mt-4 text-brand-100">
            Adoption, leaderboards, laggards and coaching pairs across your tenant — with
            no Power BI licence, no Power Platform, and no data leaving your subscription.
          </p>
        </div>
        <div className="relative text-sm text-brand-100/80">
          Community project · MIT-licensed
        </div>
      </div>

      {/* Sign-in panel */}
      <div className="flex w-full items-center justify-center px-6 lg:w-1/2">
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center text-center lg:hidden">
            <img
              src="/app-logo.png"
              alt="Microsoft 365 Copilot"
              className="h-14 w-14 object-contain"
            />
            <div className="mt-3 text-lg font-semibold text-brand-600 dark:text-brand-500">
              M365 Copilot Usage Reporter
            </div>
          </div>

          <h2 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
            Welcome back
          </h2>
          <p className="mb-6 mt-1 text-sm text-slate-500 dark:text-slate-400">
            Sign in to continue.
          </p>

          {ssoError && (
            <div
              role="alert"
              className="mb-5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/60 dark:bg-amber-900/30 dark:text-amber-200"
            >
              {ssoError}
            </div>
          )}

          {entraEnabled && (
            <>
              <a
                href="/auth/oidc/start"
                className="btn-primary flex w-full items-center justify-center gap-2"
              >
                Sign in with Microsoft
              </a>
              <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
                <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
                or admin sign-in
                <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
              </div>
            </>
          )}

          <label
            htmlFor="username"
            className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            Username
          </label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            className="input mb-4"
          />

          <label
            htmlFor="password"
            className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="input mb-6"
          />

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </div>
          )}

          <button type="submit" disabled={busy} className="btn-primary w-full">
            {busy ? "Signing in…" : "Sign in"}
          </button>

          <p className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500">
            Protected by your admin password · Entra SSO optional
          </p>
        </form>
      </div>
    </div>
  );
}
