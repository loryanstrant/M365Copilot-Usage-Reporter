import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [entraEnabled, setEntraEnabled] = useState(false);

  // Show the Microsoft sign-in button only when Azure Easy Auth is configured
  // (the platform /.auth/me endpoint responds). In local/dev it 404s and the
  // button stays hidden.
  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch("/.auth/me", { headers: { Accept: "application/json" } });
        if (resp.ok) setEntraEnabled(true);
      } catch {
        /* not on Azure / Easy Auth off */
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
    <div className="flex h-full items-center justify-center px-4">
      <div className="card w-full max-w-sm p-8">
        <div className="mb-6 text-center">
          <div className="text-sm font-semibold text-brand-600 dark:text-brand-500">M365 Copilot</div>
          <h1 className="text-xl font-bold">Usage Reporter</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Sign in to continue</p>
        </div>

        {entraEnabled && (
          <>
            <a
              href="/.auth/login/aad?post_login_redirect_uri=%2F"
              className="btn-primary flex w-full items-center justify-center gap-2"
            >
              <span aria-hidden>🔐</span> Sign in with Microsoft
            </a>
            <div className="my-5 flex items-center gap-3 text-xs text-slate-400">
              <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
              or admin sign-in
              <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
            </div>
          </>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Username
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              className="input"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
            />
          </div>
          {error && (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={busy}
            className="btn-primary w-full"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
