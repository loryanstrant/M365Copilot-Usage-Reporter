import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { StatusResult } from "../api/types";

interface SetupStatus {
  /** True once a working connection has been configured. */
  configured: boolean;
  /** False until the status call has resolved, so callers don't redirect prematurely. */
  checked: boolean;
}

/**
 * Reads first-run configuration status. Used to send an admin straight to
 * Settings (where the setup wizard opens itself) instead of an empty dashboard.
 *
 * `checked` stays false until the request settles — redirecting before then
 * would bounce users away from the dashboard on every page load.
 */
export function useSetupStatus(enabled: boolean): SetupStatus {
  const [configured, setConfigured] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      try {
        const status = await api<StatusResult>("/admin/status");
        if (!cancelled) setConfigured(Boolean(status?.configured));
      } catch {
        // Non-admins get a 403 here — treat as "nothing to do" rather than
        // trapping them in a redirect loop.
        if (!cancelled) setConfigured(true);
      } finally {
        if (!cancelled) setChecked(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);

  return { configured, checked };
}
