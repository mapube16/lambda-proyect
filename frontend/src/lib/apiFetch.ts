/**
 * ngrok-skip-browser-warning bypasses the ngrok interstitial page for
 * programmatic fetch calls when accessing the app through an ngrok tunnel.
 * Harmless when running locally.
 */
export const NGROK_BYPASS = { 'ngrok-skip-browser-warning': 'true' } as const;

export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const existing = (init.headers ?? {}) as Record<string, string>;
  return fetch(url, {
    ...init,
    credentials: 'include',
    headers: { ...NGROK_BYPASS, ...existing },
  });
}
