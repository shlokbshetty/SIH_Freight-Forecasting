// ─── Backend client ───────────────────────────────────────────────────────────
//
// Every call is allowed to fail. The dashboard shipped as a fully static app and
// must keep working that way: if the FastAPI service is not running, each screen
// falls back to the bundled data and says so, rather than showing an error page.
//
// That mirrors the backend's own rule. A dead source degrades to cached values
// with a visible staleness flag; a dead backend degrades to bundled values with
// a visible offline flag. Nothing silently pretends to be live.

const DEFAULT_BASE = 'http://localhost:8000';

export const API_BASE: string =
  (import.meta.env?.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? DEFAULT_BASE;

/** Abandon a request after this long. A slow backend must not hang a screen. */
const TIMEOUT_MS = 8000;

export class ApiError extends Error {
  // A declared field rather than a constructor parameter property: the project
  // builds with erasableSyntaxOnly, which forbids the shorthand.
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      throw new ApiError(`${path} returned ${res.status}`, res.status);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    const reason = err instanceof Error && err.name === 'AbortError'
      ? `timed out after ${TIMEOUT_MS / 1000}s`
      : err instanceof Error ? err.message : 'unreachable';
    throw new ApiError(`${path}: ${reason}`);
  } finally {
    clearTimeout(timer);
  }
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}
