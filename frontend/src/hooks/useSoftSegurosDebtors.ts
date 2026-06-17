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
  cliente_documento?: string | null;
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

export type CarteraState = 'Pendiente por pagar' | 'Sin pagos Asignados';

export interface SoftSegurosImportFilters {
  include_vencidos: boolean;
  include_proximos: boolean;
  /** Which estado_cartera values count as cobrable. Default: ["Pendiente por pagar"]. */
  cartera_states?: CarteraState[];
  /** Max age (months) of fecha_fin to import. null = no limit. Default: 12. */
  max_age_months?: number | null;
  /** Include cancelled / not-renewed pólizas. Default: false (only active). */
  include_cancelled?: boolean;
}

export interface SoftSegurosSetupState {
  /** Whether Landa has authorized the SOFTSEGUROS integration for this account.
   *  null = not yet known. false = 403 from the gate (service not enabled). */
  authorized: boolean | null;
  configured: boolean;
  configuredAt: string | null;
  /** The import filters in effect (what kinds of debtor were imported). */
  importFilters: SoftSegurosImportFilters;
}

export interface SoftSegurosSyncStatus {
  last_sync_at: string | null;
  last_sync_mode: string | null;
  last_sync_status: string | null;
  started_at: string | null;
  polizas_scanned: number;
  total_count: number;
  debtors_created: number;
  debtors_updated: number;
  debtors_marked_paid?: number;
  debtors_marked_deleted?: number;
  debtors_excluded_by_filter?: number;
  error_message: string | null;
  next_sync_at: string | null;
  is_syncing_now: boolean;
}

export interface SoftSegurosError {
  message: string;
  code?: 'rate_limited' | 'bad_credentials' | 'provider_down' | 'unknown';
  retryAfter?: number;
}

export interface SoftSegurosDisconnectImpact {
  debtors_to_delete: number;
  call_history_to_delete: number;
}

export interface UseSoftSegurosDebtorsResult {
  setup: SoftSegurosSetupState;
  debtors: { proximosAVencer: SoftSegurosDebtor[]; yaVencidos: SoftSegurosDebtor[] };
  syncStatus: SoftSegurosSyncStatus | null;
  loading: boolean;
  error: SoftSegurosError | null;
  configure: (username: string, password: string, filters?: SoftSegurosImportFilters) => Promise<boolean>;
  triggerSync: () => Promise<void>;
  reimport: (filters: SoftSegurosImportFilters) => Promise<boolean>;
  cancelSync: () => Promise<boolean>;
  fetchDisconnectImpact: () => Promise<SoftSegurosDisconnectImpact | null>;
  disconnect: (confirmWord: string) => Promise<boolean>;
  refetch: () => Promise<void>;
}

const DEFAULT_FILTERS: SoftSegurosImportFilters = {
  include_vencidos: true,
  include_proximos: true,
  cartera_states: ['Pendiente por pagar'],
  max_age_months: 12,
  include_cancelled: false,
};

const POLL_MS = 3000;
const MAX_CONSECUTIVE_ERRORS = 3;   // ~9s of failures → stop the zombie poll
const MAX_POLL_MS = 10 * 60 * 1000; // 10 min hard ceiling for a single sync

export function useSoftSegurosDebtors(): UseSoftSegurosDebtorsResult {
  const [setup, setSetup] = useState<SoftSegurosSetupState>({
    authorized: null, configured: false, configuredAt: null, importFilters: { ...DEFAULT_FILTERS },
  });
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
      if (r.status === 403) {
        const s: SoftSegurosSetupState = { authorized: false, configured: false, configuredAt: null, importFilters: { ...DEFAULT_FILTERS } };
        if (mountedRef.current) setSetup(s);
        return s;
      }
      if (!r.ok) {
        const s: SoftSegurosSetupState = { authorized: true, configured: false, configuredAt: null, importFilters: { ...DEFAULT_FILTERS } };
        if (mountedRef.current) setSetup(s);
        return s;
      }
      const d = await r.json();
      const f = d.import_filters as Partial<SoftSegurosImportFilters> | undefined;
      const s: SoftSegurosSetupState = {
        authorized: true,
        configured: !!d.configured,
        configuredAt: d.configured_at ?? null,
        importFilters: {
          include_vencidos: f?.include_vencidos ?? true,
          include_proximos: f?.include_proximos ?? true,
          cartera_states: f?.cartera_states ?? DEFAULT_FILTERS.cartera_states,
          max_age_months: f?.max_age_months ?? DEFAULT_FILTERS.max_age_months,
          include_cancelled: f?.include_cancelled ?? DEFAULT_FILTERS.include_cancelled,
        },
      };
      if (mountedRef.current) setSetup(s);
      return s;
    } catch {
      return { authorized: null, configured: false, configuredAt: null, importFilters: { ...DEFAULT_FILTERS } };
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

  // Poll sync-status until no sync is running; refetch setup on completion.
  // NOTE: debtor LISTS are owned by useSoftSegurosDebtorsView now — this hook
  // only tracks setup + sync status, so we no longer fetch lists here (that was
  // a redundant 2×200-row fetch on every poll tick).
  //
  // Safety stops so the interval can never become a zombie poller (which is what
  // saturated the network tab with sync-status calls in idle):
  //   • stop after MAX_CONSECUTIVE_ERRORS failed/null responses in a row
  //   • stop after MAX_POLL_MS wall-clock (a real sync never runs this long)
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    const startedAt = Date.now();
    let consecutiveErrors = 0;
    const stop = () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
    pollRef.current = window.setInterval(async () => {
      const st = await fetchSyncStatus();
      if (st === null) {
        // Transient network error — give up after a few tries instead of
        // polling forever.
        if (++consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) stop();
        return;
      }
      consecutiveErrors = 0;
      if (!st.is_syncing_now || Date.now() - startedAt > MAX_POLL_MS) {
        stop();
        await fetchSetup();
      }
    }, POLL_MS);
  }, [fetchSyncStatus, fetchSetup]);

  const refetch = useCallback(async () => {
    setLoading(true);
    const s = await fetchSetup();
    if (s.authorized === false) {
      // Service not enabled by Landa — nothing else to fetch.
      if (mountedRef.current) setLoading(false);
      return;
    }
    const st = await fetchSyncStatus();
    if (mountedRef.current) setLoading(false);
    // If a sync is already running on the server (e.g., user closed and came
    // back), resume polling so the UI keeps updating live.
    if (st?.is_syncing_now) startPolling();
  }, [fetchSetup, fetchSyncStatus, startPolling]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const configure = useCallback(async (username: string, password: string, filters?: SoftSegurosImportFilters): Promise<boolean> => {
    setError(null);
    try {
      const body: Record<string, unknown> = { username, password };
      if (filters) body.import_filters = filters;
      const r = await apiFetch('/api/debtors/configure-softseguros', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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

  const reimport = useCallback(async (filters: SoftSegurosImportFilters): Promise<boolean> => {
    setError(null);
    try {
      const r = await apiFetch('/api/debtors/reimport', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ import_filters: filters }),
      });
      if (r.status === 429) {
        const ra = parseInt(r.headers.get('Retry-After') || '0', 10);
        const d = await r.json().catch(() => ({}));
        setError({
          message: (d as { detail?: string }).detail || 'Re-importación demasiado frecuente',
          code: 'rate_limited',
          retryAfter: Number.isFinite(ra) && ra > 0 ? ra : 300,
        });
        return false;
      }
      if (r.status === 400) {
        const d = await r.json().catch(() => ({}));
        setError({ message: (d as { detail?: string }).detail || 'SOFTSEGUROS no configurado', code: 'unknown' });
        return false;
      }
      if (!r.ok) {
        setError({ message: `Error ${r.status}`, code: 'unknown' });
        return false;
      }
      // Optimistically reflect the new filters; the poll will refetch real state.
      if (mountedRef.current) setSetup(prev => ({ ...prev, importFilters: { ...filters } }));
      await fetchSyncStatus();
      startPolling();
      return true;
    } catch {
      setError({ message: 'Error de conexión', code: 'unknown' });
      return false;
    }
  }, [fetchSyncStatus, startPolling]);

  const fetchDisconnectImpact = useCallback(async (): Promise<SoftSegurosDisconnectImpact | null> => {
    try {
      const r = await apiFetch('/api/debtors/disconnect-softseguros/impact');
      if (!r.ok) return null;
      return (await r.json()) as SoftSegurosDisconnectImpact;
    } catch {
      return null;
    }
  }, []);

  const disconnect = useCallback(async (confirmWord: string): Promise<boolean> => {
    setError(null);
    try {
      const r = await apiFetch('/api/debtors/disconnect-softseguros', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: confirmWord }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError({ message: (d as { detail?: string }).detail || `Error ${r.status}`, code: 'unknown' });
        return false;
      }
      // Wipe local state. The component will re-render and fall back to the setup form
      // (setup.configured=false). fetchSetup also re-runs via the refetch wrapper below.
      if (mountedRef.current) {
        setProximosAVencer([]);
        setYaVencidos([]);
        setSyncStatus(null);
        setSetup(prev => ({ ...prev, configured: false, configuredAt: null }));
      }
      void fetchSetup();
      return true;
    } catch {
      setError({ message: 'Error de conexión', code: 'unknown' });
      return false;
    }
  }, [fetchSetup]);

  const cancelSync = useCallback(async (): Promise<boolean> => {
    try {
      const r = await apiFetch('/api/debtors/sync-cancel', { method: 'POST' });
      if (!r.ok) {
        setError({ message: `Error ${r.status} al cancelar`, code: 'unknown' });
        return false;
      }
      await fetchSyncStatus();
      return true;
    } catch {
      setError({ message: 'Error de conexión', code: 'unknown' });
      return false;
    }
  }, [fetchSyncStatus]);

  return {
    setup,
    debtors: { proximosAVencer, yaVencidos },
    syncStatus,
    loading,
    error,
    configure,
    triggerSync,
    reimport,
    cancelSync,
    fetchDisconnectImpact,
    disconnect,
    refetch,
  };
}

export default useSoftSegurosDebtors;
