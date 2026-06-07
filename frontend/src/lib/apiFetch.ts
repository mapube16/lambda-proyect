/**
 * ngrok-skip-browser-warning bypasses the ngrok interstitial page for
 * programmatic fetch calls when accessing the app through an ngrok tunnel.
 * Harmless when running locally.
 */
import { API_BASE, getToken } from '../api';

export const NGROK_BYPASS = { 'ngrok-skip-browser-warning': 'true' } as const;

/**
 * Shared fetch wrapper. Resolves relative `/api/...` paths against the same
 * API_BASE the rest of the app uses, and attaches the Bearer token from the
 * shared auth state (same token api.ts manages). This unifies cobranza/legacy
 * components with the new Landa auth — without it, cobranza endpoints (which
 * require get_current_user / Bearer) return 401.
 */
export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const existing = (init.headers ?? {}) as Record<string, string>;
  const resolved = url.startsWith('/') ? `${API_BASE}${url}` : url;
  const token = getToken();
  const auth: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  return fetch(resolved, {
    ...init,
    credentials: 'include',
    headers: { ...NGROK_BYPASS, ...auth, ...existing },
  });
}
