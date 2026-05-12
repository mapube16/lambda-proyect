import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../lib/apiFetch';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SoftSegurosDebtor {
  _id: string;
  nombre?: string;
  cliente_nombres?: string;
  cliente_apellidos?: string;
  cliente_celular?: string | null;
  cliente_email?: string | null;
  telefono?: string;
  total?: number | null;
  monto?: number | null;
  fecha_fin?: string | null;
  vencimiento?: string | null;
  numero_poliza?: string | null;
  ramo_nombre?: string | null;
  estado_poliza_nombre?: string | null;
  estado_cartera?: string | null;
  status_softseguros?: 'ya_vencidos' | 'proximos_a_vencer' | 'pagado' | 'eliminado';
  last_synced?: string | null;
  is_active?: boolean;
}

export interface SoftSegurosSetupState {
  configured: boolean;
  configuredAt: string | null;
}

export interface SoftSegurosSyncStatus {
  last_sync_at: string | null;
  last_sync_mode: string | null;
  last_sync_status: string | null;
  debtors_created: number;
  debtors_updated: number;
  next_sync_at: string | null;
  is_syncing_now: boolean;
}

export interface SoftSegurosError {
  message: string;
  code?: 'rate_limited' | 'bad_credentials' | 'provider_down' | 'unknown';
  retryAfter?: number;
}

export interface UseSoftSegurosDebtorsResult {
  setup: SoftSegurosSetupState;
  debtors: { proximosAVencer: SoftSegurosDebtor[]; yaVencidos: SoftSegurosDebtor[] };
  syncStatus: SoftSegurosSyncStatus | null;
  loading: boolean;
  error: SoftSegurosError | null;
  configure: (username: string, password: string) => Promise<boolean>;
  triggerSync: () => Promise<void>;
  refetch: () => Promise<void>;
}

const POLL_MS = 3000;

export function useSoftSegurosDebtors(): UseSoftSegurosDebtorsResult {
  const [setup, setSetup] = useState<SoftSegurosSetupState>({ configured: false, configuredAt: null });
  const [proximosAVencer, setProximosAVencer] = useState<SoftSegurosDebtor[]>([]);
  const [yaVencidos, setYaVencidos] = useState<SoftSegurosDebtor[]>([]);
  const [syncStatus, setSyncStatus] = useState<SoftSegurosSyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<SoftSegurosError | null>(null);

  const pollRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, []);

  const fetchSetup = useCallback(async (): Promise<SoftSegurosSetupState> => {
    try {
      const r = await apiFetch('/api/debtors/configure-softseguros');
      if (!r.ok) return { configured: false, configuredAt: null };
      const d = await r.json();
      const s = { configured: !!d.configured, configuredAt: d.configured_at ?? null };
      if (mountedRef.current) setSetup(s);
      return s;
    } catch {
      return { configured: false, configuredAt: null };
    }
  }, []);

  const fetchSyncStatus = useCallback(async (): Promise<SoftSegurosSyncStatus | null> => {
    try {
      const r = await apiFetch('/api/debtors/sync-status');
      if (!r.ok) return null;
      const d = (await r.json()) as SoftSegurosSyncStatus;
      if (mountedRef.current) setSyncStatus(d);
      return d;
    } catch {
      return null;
    }
  }, []);

  const fetchDebtorsList = useCallback(async () => {
    try {
      const [pr, yr] = await Promise.all([
        apiFetch('/api/debtors?status=proximos_a_vencer&page=1&page_size=200'),
        apiFetch('/api/debtors?status=ya_vencidos&page=1&page_size=200'),
      ]);
      if (pr.ok) {
        const d = await pr.json();
        if (mountedRef.current) setProximosAVencer(Array.isArray(d.items) ? d.items : []);
      }
      if (yr.ok) {
        const d = await yr.json();
        if (mountedRef.current) setYaVencidos(Array.isArray(d.items) ? d.items : []);
      }
    } catch {
      // leave existing lists
    }
  }, []);

  const refetch = useCallback(async () => {
    setLoading(true);
    const s = await fetchSetup();
    await fetchSyncStatus();
    if (s.configured) await fetchDebtorsList();
    if (mountedRef.current) setLoading(false);
  }, [fetchSetup, fetchSyncStatus, fetchDebtorsList]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  // Poll sync-status until no sync is running; refetch lists + setup on completion.
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = window.setInterval(async () => {
      const st = await fetchSyncStatus();
      if (st && !st.is_syncing_now) {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        await fetchSetup();
        await fetchDebtorsList();
      }
    }, POLL_MS);
  }, [fetchSyncStatus, fetchSetup, fetchDebtorsList]);

  const configure = useCallback(async (username: string, password: string): Promise<boolean> => {
    setError(null);
    try {
      const r = await apiFetch('/api/debtors/configure-softseguros', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (r.status === 400) {
        const d = await r.json().catch(() => ({}));
        setError({ message: (d as { detail?: string }).detail || 'Credenciales inválidas', code: 'bad_credentials' });
        return false;
      }
      if (r.status === 502) {
        const d = await r.json().catch(() => ({}));
        setError({ message: (d as { detail?: string }).detail || 'No se pudo contactar a SOFTSEGUROS', code: 'provider_down' });
        return false;
      }
      if (!r.ok) {
        setError({ message: `Error ${r.status}`, code: 'unknown' });
        return false;
      }
      // success — onboarding sync started in background.
      await fetchSetup();
      await fetchSyncStatus();
      startPolling();
      return true;
    } catch {
      setError({ message: 'Error de conexión', code: 'unknown' });
      return false;
    }
  }, [fetchSetup, fetchSyncStatus, startPolling]);

  const triggerSync = useCallback(async () => {
    setError(null);
    try {
      const r = await apiFetch('/api/debtors/sync-now', { method: 'POST' });
      if (r.status === 429) {
        const ra = parseInt(r.headers.get('Retry-After') || '0', 10);
        const d = await r.json().catch(() => ({}));
        setError({
          message: (d as { detail?: string }).detail || 'Sincronización demasiado frecuente',
          code: 'rate_limited',
          retryAfter: Number.isFinite(ra) && ra > 0 ? ra : 300,
        });
        return;
      }
      if (!r.ok) {
        setError({ message: `Error ${r.status}`, code: 'unknown' });
        return;
      }
      await fetchSyncStatus();
      startPolling();
    } catch {
      setError({ message: 'Error de conexión', code: 'unknown' });
    }
  }, [fetchSyncStatus, startPolling]);

  return {
    setup,
    debtors: { proximosAVencer, yaVencidos },
    syncStatus,
    loading,
    error,
    configure,
    triggerSync,
    refetch,
  };
}

export default useSoftSegurosDebtors;
