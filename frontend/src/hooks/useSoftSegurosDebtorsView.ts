import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../lib/apiFetch';
import type { SoftSegurosDebtor } from './useSoftSegurosDebtors';

// ── Types ─────────────────────────────────────────────────────────────────────

export type AgingBucket = '1-30' | '31-60' | '61-90' | '90+';
export type DebtorStatus = 'ya_vencidos' | 'proximos_a_vencer';
export type SortField = 'vencimiento' | 'monto' | 'nombre' | 'dias_vencidos';
export type SortDirection = 'asc' | 'desc';

export interface DebtorsListFilters {
  status: DebtorStatus;
  bucket: AgingBucket | null;
  minMonto: number | null;
  maxMonto: number | null;
  ramos: string[];
  sort: SortField;
  direction: SortDirection;
  page: number;
  pageSize: number;
}

export interface AgingBucketSummary {
  count: number;
  total_monto: number;
}

export interface AgingSummary {
  buckets: {
    '1-30': AgingBucketSummary;
    '31-60': AgingBucketSummary;
    '61-90': AgingBucketSummary;
    '90+': AgingBucketSummary;
    future: AgingBucketSummary;
    unknown: AgingBucketSummary;
  };
  total: AgingBucketSummary;
  ramos: string[];
}

export interface DebtorsListResult {
  items: SoftSegurosDebtor[];
  total: number;
  page: number;
  pageSize: number;
}

export interface UseDebtorsViewResult {
  filters: DebtorsListFilters;
  setFilters: (patch: Partial<DebtorsListFilters>) => void;
  resetFilters: () => void;
  list: DebtorsListResult;
  aging: AgingSummary | null;
  loading: boolean;
  /** Free-text search applied client-side over the current page (nombre, póliza, documento). */
  searchText: string;
  setSearchText: (s: string) => void;
  /** Items in the current page after searchText is applied. */
  visibleItems: SoftSegurosDebtor[];
  refetch: () => Promise<void>;
}

const DEFAULTS: DebtorsListFilters = {
  status: 'ya_vencidos',
  bucket: null,
  minMonto: null,
  maxMonto: null,
  ramos: [],
  sort: 'vencimiento',
  direction: 'asc',
  page: 1,
  pageSize: 50,
};

// Build the query string for the backend from current filters.
function buildQuery(f: DebtorsListFilters): string {
  const p = new URLSearchParams();
  p.set('status', f.status);
  if (f.bucket) p.set('bucket', f.bucket);
  if (f.minMonto !== null) p.set('min_monto', String(f.minMonto));
  if (f.maxMonto !== null) p.set('max_monto', String(f.maxMonto));
  if (f.ramos.length > 0) p.set('ramo', f.ramos.join(','));
  p.set('sort', f.sort);
  p.set('direction', f.direction);
  p.set('page', String(f.page));
  p.set('page_size', String(f.pageSize));
  return p.toString();
}

function agingQuery(f: DebtorsListFilters): string {
  const p = new URLSearchParams();
  p.set('status', f.status);
  if (f.minMonto !== null) p.set('min_monto', String(f.minMonto));
  if (f.maxMonto !== null) p.set('max_monto', String(f.maxMonto));
  if (f.ramos.length > 0) p.set('ramo', f.ramos.join(','));
  return p.toString();
}

// Client-side text search over the current page. Matches against several
// debtor fields, case-insensitive, accent-insensitive, partial.
function normalize(s: string): string {
  // Strip combining diacritical marks (U+0300–U+036F) so "lópez" matches "lopez".
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function matchesSearch(d: SoftSegurosDebtor, q: string): boolean {
  if (!q) return true;
  const needle = normalize(q.trim());
  if (!needle) return true;
  const haystack = normalize(
    [d.nombre, d.cliente_nombres, d.cliente_apellidos, d.numero_poliza, d.cliente_documento, d.cliente_email, d.telefono, d.cliente_celular]
      .filter(Boolean)
      .join(' '),
  );
  return haystack.includes(needle);
}

export function useSoftSegurosDebtorsView(initial?: Partial<DebtorsListFilters>): UseDebtorsViewResult {
  const [filters, setFiltersState] = useState<DebtorsListFilters>({ ...DEFAULTS, ...(initial ?? {}) });
  const [list, setList] = useState<DebtorsListResult>({ items: [], total: 0, page: 1, pageSize: filters.pageSize });
  const [aging, setAging] = useState<AgingSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const setFilters = useCallback((patch: Partial<DebtorsListFilters>) => {
    setFiltersState(prev => {
      // Any change OTHER than page resets pagination to 1.
      const keys = Object.keys(patch);
      const resetPage = keys.some(k => k !== 'page');
      return { ...prev, ...patch, ...(resetPage && !('page' in patch) ? { page: 1 } : {}) };
    });
  }, []);

  const resetFilters = useCallback(() => {
    setFiltersState(prev => ({ ...DEFAULTS, status: prev.status, pageSize: prev.pageSize }));
    setSearchText('');
  }, []);

  const fetchAll = useCallback(async (current: DebtorsListFilters) => {
    setLoading(true);
    try {
      const [listResp, agingResp] = await Promise.all([
        apiFetch(`/api/debtors?${buildQuery(current)}`),
        apiFetch(`/api/debtors/aging-summary?${agingQuery(current)}`),
      ]);
      if (listResp.ok) {
        const d = await listResp.json();
        if (mountedRef.current) {
          setList({
            items: Array.isArray(d.items) ? d.items : [],
            total: Number(d.total ?? 0),
            page: Number(d.page ?? 1),
            pageSize: Number(d.page_size ?? current.pageSize),
          });
        }
      }
      if (agingResp.ok) {
        const d = (await agingResp.json()) as AgingSummary;
        if (mountedRef.current) setAging(d);
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  // Debounce list refetch on filter changes (300ms — fast enough to feel snappy,
  // slow enough to not spam when the user is typing a min/max).
  useEffect(() => {
    const t = window.setTimeout(() => { void fetchAll(filters); }, 250);
    return () => window.clearTimeout(t);
  }, [filters, fetchAll]);

  const refetch = useCallback(() => fetchAll(filters), [fetchAll, filters]);

  const visibleItems = useMemo(
    () => list.items.filter(d => matchesSearch(d, searchText)),
    [list.items, searchText],
  );

  return { filters, setFilters, resetFilters, list, aging, loading, searchText, setSearchText, visibleItems, refetch };
}

export default useSoftSegurosDebtorsView;
