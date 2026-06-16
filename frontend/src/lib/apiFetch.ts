/**
 * ngrok-skip-browser-warning bypasses the ngrok interstitial page for
 * programmatic fetch calls when accessing the app through an ngrok tunnel.
 * Harmless when running locally.
 */
import { API_BASE, getToken } from '../api';

export const NGROK_BYPASS = { 'ngrok-skip-browser-warning': 'true' } as const;

// ── Dev-only request logger ────────────────────────────────────────────────────
// Toggle from the browser console with:  __apiDebug(true)  /  __apiDebug(false)
// Or persist across reloads:  localStorage.setItem('apiDebug','1')
// Shows every apiFetch call with method, path, status, duration, and a per-endpoint
// call counter. Flags suspected render-loops (same endpoint hit many times in a
// short window) in red so you can see what's hammering the backend.

interface EndpointStat {
  count: number;
  windowStart: number;
  windowCount: number;
}

const _stats = new Map<string, EndpointStat>();
const LOOP_WINDOW_MS = 3000;
const LOOP_THRESHOLD = 5; // >5 calls to the same endpoint within the window = suspicious

function _debugEnabled(): boolean {
  try {
    if (typeof window === 'undefined') return false;
    const w = window as unknown as { __API_DEBUG__?: boolean };
    if (w.__API_DEBUG__ !== undefined) return w.__API_DEBUG__;
    return localStorage.getItem('apiDebug') === '1';
  } catch {
    return false;
  }
}

// Normalize a URL to a stable key (strip query string + origin) so the same
// endpoint with different params still groups together for loop detection.
function _endpointKey(url: string): string {
  try {
    const u = url.startsWith('http') ? new URL(url) : new URL(url, window.location.origin);
    return u.pathname;
  } catch {
    return url.split('?')[0];
  }
}

function _track(method: string, url: string, status: number | 'ERR', ms: number): void {
  if (!_debugEnabled()) return;
  const key = `${method} ${_endpointKey(url)}`;
  const now = performance.now();
  const s = _stats.get(key) ?? { count: 0, windowStart: now, windowCount: 0 };
  s.count += 1;
  if (now - s.windowStart > LOOP_WINDOW_MS) {
    s.windowStart = now;
    s.windowCount = 1;
  } else {
    s.windowCount += 1;
  }
  _stats.set(key, s);

  const looping = s.windowCount > LOOP_THRESHOLD;
  const color = looping ? '#ff6188' : status === 'ERR' ? '#fc9867' : '#a9dc76';
  const tag = looping ? ' 🔁 LOOP?' : '';
  // eslint-disable-next-line no-console
  console.log(
    `%c[api] ${method} ${_endpointKey(url)} → ${status} · ${ms.toFixed(0)}ms · #${s.count} (${s.windowCount}/${(LOOP_WINDOW_MS / 1000)}s)${tag}`,
    `color:${color}`,
  );
}

// Expose a console helper + a summary printer.
if (typeof window !== 'undefined') {
  const w = window as unknown as {
    __apiDebug?: (on?: boolean) => void;
    __apiStats?: () => void;
    __API_DEBUG__?: boolean;
  };
  w.__apiDebug = (on = true) => {
    w.__API_DEBUG__ = on;
    try { localStorage.setItem('apiDebug', on ? '1' : '0'); } catch { /* ignore */ }
    // eslint-disable-next-line no-console
    console.log(`%c[api] debug ${on ? 'ON' : 'OFF'}`, 'color:#78dce8;font-weight:bold');
  };
  w.__apiStats = () => {
    const rows = [...(_stats.entries())]
      .map(([k, v]) => ({ endpoint: k, total: v.count }))
      .sort((a, b) => b.total - a.total);
    // eslint-disable-next-line no-console
    console.table(rows);
  };
}

// Default per-request timeout. Without this, a hung connection occupies one of
// the browser's ~6 connections-per-host slots indefinitely, so subsequent
// requests queue behind it (this is what produced the 100s "latencies" — the
// server answered in 0.5s but the request waited in the browser's queue).
const DEFAULT_TIMEOUT_MS = 20_000;

/**
 * Shared fetch wrapper. Resuelve rutas relativas `/api/...` contra API_BASE,
 * adjunta el Bearer token (mismo que api.ts), y añade timeout + logging de debug.
 * Sin el Bearer, los endpoints de cobranza/legacy (get_current_user) dan 401.
 */
export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const existing = (init.headers ?? {}) as Record<string, string>;
  const method = (init.method ?? 'GET').toUpperCase();
  const t0 = performance.now();

  const resolved = url.startsWith('/') ? `${API_BASE}${url}` : url;
  const token = getToken();
  const auth: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  // Wire up an abort timeout unless the caller already passed a signal.
  const controller = init.signal ? null : new AbortController();
  const timeoutId = controller
    ? window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
    : null;

  return fetch(resolved, {
    ...init,
    credentials: 'include',
    headers: { ...NGROK_BYPASS, ...auth, ...existing },
    signal: init.signal ?? controller?.signal,
  })
    .then((res) => {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      _track(method, resolved, res.status, performance.now() - t0);
      return res;
    })
    .catch((err) => {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      _track(method, resolved, 'ERR', performance.now() - t0);
      throw err;
    });
}
