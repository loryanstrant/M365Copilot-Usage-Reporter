// Minimal fetch wrapper that attaches the bearer token and normalises errors.
const TOKEN_KEY = "cur_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(path, { ...options, headers });

  if (resp.status === 401) {
    setToken(null);
    if (!path.startsWith("/auth/login") && !path.startsWith("/auth/config")) {
      // Force re-auth on expired/invalid token.
      window.dispatchEvent(new Event("cur:unauthorized"));
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

/**
 * Multipart upload (currently only the branding logo).
 *
 * Deliberately does NOT set Content-Type: the browser has to generate the
 * multipart boundary itself, and setting the header by hand produces a body
 * the server cannot parse. Everything else matches `api` above.
 */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(path, { method: "POST", body: form, headers });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }

  return (await resp.json()) as T;
}

/** Multipart PATCH. Same reasoning as `upload` above — the browser must set the
 *  multipart boundary itself. Used for small field updates that FastAPI reads
 *  as Form(...) rather than a JSON body. */
export async function patch<T>(path: string, form: FormData): Promise<T> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(path, { method: "PATCH", body: form, headers });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }

  return (await resp.json()) as T;
}
