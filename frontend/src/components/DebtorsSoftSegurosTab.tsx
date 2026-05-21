import { useEffect, useMemo, useRef, useState } from 'react';
import {
  useSoftSegurosDebtors,
  type SoftSegurosDebtor,
  type SoftSegurosSyncStatus,
} from '../hooks/useSoftSegurosDebtors';
import {
  useSoftSegurosDebtorsView,
  type DebtorStatus,
  type SortField,
} from '../hooks/useSoftSegurosDebtorsView';
import { SoftSegurosSetup } from './SoftSegurosSetup';

// Shared visual tokens (mirrors CobranzaTab / ClientDashboard).
const C = {
  bg: '#0d0d18', s0: '#12121d', s1: '#1b1a26', s2: '#22212e', s3: '#2c2b3a',
  text: '#e3e0f1', muted: '#8a8a9a', faint: 'rgba(227,224,241,0.3)',
  cyan: '#78dce8', cyanBg: 'rgba(120,220,232,0.08)', cyanBdr: 'rgba(120,220,232,0.22)',
  green: '#a9dc76', greenBg: 'rgba(169,220,118,0.08)',
  pink: '#ff6188', pinkBg: 'rgba(255,97,136,0.1)',
  orange: '#fc9867', orangeBg: 'rgba(252,152,103,0.08)',
  yellow: '#ffd866', yellowBg: 'rgba(255,216,102,0.08)',
  SG: "'Space Grotesk', system-ui, sans-serif",
  IN: "'Inter', system-ui, sans-serif",
};

const lbl = (color = C.muted, size = 10): React.CSSProperties => ({
  fontFamily: C.SG, fontSize: size, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.14em', color,
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCOP(value: number | null | undefined, opts?: { short?: boolean }): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (opts?.short) {
    if (Math.abs(n) >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
    if (Math.abs(n) >= 1_000_000)     return `$${(n / 1_000_000).toFixed(1)}M`;
    if (Math.abs(n) >= 1_000)         return `$${(n / 1_000).toFixed(0)}k`;
    return `$${Math.round(n)}`;
  }
  try {
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(n);
  } catch {
    return `$${Math.round(n).toLocaleString('es-CO')}`;
  }
}

function formatCount(n: number): string {
  try { return new Intl.NumberFormat('es-CO').format(n); } catch { return String(n); }
}

function debtorName(d: SoftSegurosDebtor): string {
  if (d.nombre && d.nombre.trim()) return d.nombre;
  const composed = [d.cliente_nombres, d.cliente_apellidos].filter(Boolean).join(' ').trim();
  return composed || 'Sin nombre';
}

function dueDateISO(d: SoftSegurosDebtor): string | null {
  return d.fecha_fin ?? d.vencimiento ?? null;
}

function daysFromToday(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(t);
  due.setHours(0, 0, 0, 0);
  return Math.round((today.getTime() - due.getTime()) / (1000 * 60 * 60 * 24)); // positive = overdue
}

type Priority = 'alta' | 'media' | 'baja';

function priorityFor(daysOverdue: number | null, monto: number | null | undefined, monthMonto: number): Priority {
  const days = daysOverdue ?? 0;
  const m = Number(monto ?? 0);
  if (days >= 60 || (monthMonto > 0 && m >= monthMonto * 0.75)) return 'alta';
  if (days >= 30 || (monthMonto > 0 && m >= monthMonto * 0.40)) return 'media';
  return 'baja';
}

function priorityStyle(p: Priority): { color: string; bg: string; label: string } {
  if (p === 'alta')  return { color: C.pink,   bg: C.pinkBg,   label: 'ALTA' };
  if (p === 'media') return { color: C.orange, bg: C.orangeBg, label: 'MEDIA' };
  return { color: C.green, bg: C.greenBg, label: 'BAJA' };
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'nunca';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'nunca';
  const secs = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (secs < 60) return 'hace un momento';
  const mins = Math.round(secs / 60);
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `hace ${hrs} h`;
  const days = Math.round(hrs / 24);
  return `hace ${days} día${days === 1 ? '' : 's'}`;
}

// ── Sync status banner / badge ────────────────────────────────────────────────

function SyncStatusLine({ status, totalActive }: { status: SoftSegurosSyncStatus | null; totalActive: number }) {
  if (status?.is_syncing_now) {
    const pct = status.total_count ? Math.round((status.polizas_scanned / status.total_count) * 100) : null;
    return (
      <span style={{ fontFamily: C.SG, fontSize: 11.5, color: C.cyan }}>
        Sincronizando{pct !== null ? ` · ${pct}%` : '…'}
      </span>
    );
  }
  const failed = status?.last_sync_status === 'failed';
  const cancelled = status?.last_sync_status === 'cancelled';
  return (
    <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted }}>
      Última sincronización: {relativeTime(status?.last_sync_at ?? null)}
      {failed && <span style={{ color: C.pink }}> · falló</span>}
      {cancelled && <span style={{ color: C.orange }}> · cancelada</span>}
      {' · '}
      <span style={{ color: C.text }}>{formatCount(totalActive)} deudores activos</span>
    </span>
  );
}

function SyncRunningBanner({ status }: { status: SoftSegurosSyncStatus }) {
  const scanned = status.polizas_scanned ?? 0;
  const total = status.total_count ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((scanned / total) * 100)) : 0;
  const found = status.debtors_created ?? 0;
  return (
    <div role="status" aria-live="polite" style={{
      padding: '12px 16px', background: C.cyanBg, border: `1px solid ${C.cyanBdr}`,
      marginBottom: 14, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
    }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: C.cyan,
        animation: 'cobr-pulse 1.2s ease-in-out infinite', flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontFamily: C.SG, fontSize: 13, color: C.cyan, marginBottom: 4 }}>
          Importando cartera desde SOFTSEGUROS · {pct}%
        </div>
        <div style={{ height: 4, background: C.s3, borderRadius: 2, overflow: 'hidden', marginBottom: 6 }}>
          <div style={{ width: `${pct}%`, height: '100%', background: `linear-gradient(90deg, ${C.cyan}, ${C.green})`, transition: 'width 0.4s ease' }} />
        </div>
        <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted }}>
          {formatCount(scanned)} de {formatCount(total)} pólizas escaneadas
          {' · '}<span style={{ color: C.green }}>{formatCount(found)} deudores encontrados</span>
        </div>
      </div>
    </div>
  );
}

function SyncFailedBanner({ status, onRetry }: { status: SoftSegurosSyncStatus; onRetry: () => void }) {
  return (
    <div role="alert" style={{
      padding: '12px 16px', background: C.pinkBg, border: `1px solid rgba(255,97,136,0.3)`,
      marginBottom: 14,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13, color: C.pink, marginBottom: 4 }}>
            La última importación falló
          </div>
          <div style={{ fontFamily: C.IN, fontSize: 12, color: C.text, lineHeight: 1.5 }}>
            {status.error_message || 'No hay detalles disponibles.'}
          </div>
        </div>
        <button onClick={onRetry} style={{
          height: 30, padding: '0 14px', border: `1px solid ${C.cyanBdr}`,
          background: C.cyanBg, color: C.cyan, cursor: 'pointer',
          fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
        }}>
          Reintentar
        </button>
      </div>
    </div>
  );
}

// ── KPI strip (aging buckets, clickeables) ────────────────────────────────────

interface KPIProps {
  active: boolean;
  label: string;
  count: number;
  monto: number;
  icon?: string;
  variant?: 'danger' | 'warning' | 'info' | 'neutral';
  onClick: () => void;
}

function KPICard({ active, label, count, monto, icon, variant = 'neutral', onClick }: KPIProps) {
  const palette = {
    danger:  { color: C.pink,   bg: 'rgba(255,97,136,0.12)',  bdr: 'rgba(255,97,136,0.35)' },
    warning: { color: C.orange, bg: 'rgba(252,152,103,0.12)', bdr: 'rgba(252,152,103,0.35)' },
    info:    { color: C.yellow, bg: 'rgba(255,216,102,0.12)', bdr: 'rgba(255,216,102,0.30)' },
    neutral: { color: C.cyan,   bg: C.cyanBg,                  bdr: C.cyanBdr },
  }[variant];
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        flex: '1 1 0', minWidth: 130, textAlign: 'left',
        padding: '12px 14px',
        background: active ? palette.bg : C.s1,
        border: `1px solid ${active ? palette.color : 'rgba(255,255,255,0.06)'}`,
        cursor: 'pointer',
        transition: 'all 0.15s ease',
      }}
    >
      <div style={{ ...lbl(active ? palette.color : C.muted, 9.5), marginBottom: 4 }}>
        {icon && <span style={{ marginRight: 4 }}>{icon}</span>}{label}
      </div>
      <div style={{
        fontFamily: C.SG, fontWeight: 700, fontSize: 24, color: active ? palette.color : C.text,
        lineHeight: 1.05, marginBottom: 4,
      }}>
        {formatCount(count)}
      </div>
      <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted }}>
        {formatCOP(monto, { short: true })}
      </div>
    </button>
  );
}

// ── Active filter chips ───────────────────────────────────────────────────────

function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '4px 8px 4px 10px', background: C.cyanBg, border: `1px solid ${C.cyanBdr}`,
      fontFamily: C.SG, fontSize: 11, color: C.cyan, letterSpacing: '0.03em',
    }}>
      {label}
      <button
        onClick={onRemove}
        aria-label={`Quitar filtro ${label}`}
        style={{
          width: 16, height: 16, lineHeight: '14px', textAlign: 'center',
          background: 'transparent', border: 'none', color: C.cyan,
          cursor: 'pointer', fontSize: 14, padding: 0,
        }}
      >×</button>
    </span>
  );
}

// ── Dense table row ───────────────────────────────────────────────────────────

interface RowProps {
  d: SoftSegurosDebtor;
  monthMonto: number;
  density: 'table' | 'cards';
}

function DebtorRow({ d, monthMonto, density }: RowProps) {
  const due = dueDateISO(d);
  const days = daysFromToday(due);
  const overdue = days !== null && days > 0;
  const monto = (d as { monto?: number; total?: number }).monto ?? d.total ?? 0;
  const prio = priorityFor(days, monto, monthMonto);
  const pStyle = priorityStyle(prio);
  const tel = d.cliente_celular ?? d.telefono ?? null;
  const stripeColor =
    overdue && days! >= 90 ? C.pink
    : overdue && days! >= 60 ? C.orange
    : 'transparent';

  if (density === 'cards') {
    return (
      <div style={{
        background: C.s2, borderLeft: `3px solid ${stripeColor}`,
        padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              fontFamily: C.SG, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.08em',
              color: pStyle.color, background: pStyle.bg,
              padding: '2px 6px', border: `1px solid ${pStyle.color}33`,
            }}>{pStyle.label}</span>
            <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.text }}>{debtorName(d)}</span>
          </div>
          <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.green, whiteSpace: 'nowrap' }}>
            {formatCOP(monto)}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontFamily: C.IN, fontSize: 12 }}>
          {tel && <a href={`tel:${tel}`} style={{ color: C.cyan, textDecoration: 'none' }}>{tel}</a>}
          {d.cliente_email && <a href={`mailto:${d.cliente_email}`} style={{ color: C.cyan, textDecoration: 'none' }}>{d.cliente_email}</a>}
          {d.numero_poliza && <span style={{ color: C.faint }}>Póliza {d.numero_poliza}</span>}
          {d.ramo_nombre && <span style={{ color: C.faint }}>{d.ramo_nombre}</span>}
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
          {overdue && (
            <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13, color: days! >= 60 ? C.pink : C.orange }}>
              Vencido hace {days} día{days === 1 ? '' : 's'}
            </span>
          )}
          {due && <span style={{ fontFamily: C.IN, fontSize: 11, color: C.faint }}>{due}</span>}
        </div>
      </div>
    );
  }

  // Dense table row
  return (
    <tr style={{ borderTop: `1px solid rgba(255,255,255,0.04)`, borderLeft: `3px solid ${stripeColor}` }}>
      <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        <span style={{
          fontFamily: C.SG, fontSize: 9.5, fontWeight: 700, letterSpacing: '0.08em',
          color: pStyle.color, background: pStyle.bg,
          padding: '2px 6px', border: `1px solid ${pStyle.color}33`, display: 'inline-block',
        }}
          title={
            prio === 'alta'
              ? `Alta: ${overdue ? `${days} días vencido` : 'monto alto'}`
              : prio === 'media'
              ? 'Media: días moderados o monto medio'
              : 'Baja: deuda reciente y de menor monto'
          }
        >{pStyle.label}</span>
      </td>
      <td style={{ padding: '9px 12px', fontFamily: C.SG, fontWeight: 600, fontSize: 13, color: C.text }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span>{debtorName(d)}</span>
          {(d.numero_poliza || d.ramo_nombre) && (
            <span style={{ fontFamily: C.IN, fontSize: 11, color: C.faint, fontWeight: 400 }}>
              {d.numero_poliza ? `#${d.numero_poliza}` : ''}{d.numero_poliza && d.ramo_nombre ? ' · ' : ''}{d.ramo_nombre ?? ''}
            </span>
          )}
        </div>
      </td>
      <td style={{ padding: '9px 12px', fontFamily: C.IN, fontSize: 12 }}>
        {tel ? <a href={`tel:${tel}`} style={{ color: C.cyan, textDecoration: 'none' }}>{tel}</a> : <span style={{ color: C.faint }}>—</span>}
      </td>
      <td style={{ padding: '9px 12px', textAlign: 'right', fontFamily: C.SG, fontWeight: 700, fontSize: 13, color: C.green, whiteSpace: 'nowrap' }}>
        {formatCOP(monto)}
      </td>
      <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        {overdue ? (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13, color: days! >= 60 ? C.pink : C.orange }}>
              {days} día{days === 1 ? '' : 's'}
            </span>
            {due && <span style={{ fontFamily: C.IN, fontSize: 10.5, color: C.faint }}>desde {due}</span>}
          </div>
        ) : (
          <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted }}>{due ?? '—'}</span>
        )}
      </td>
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function DebtorsSoftSegurosTab() {
  const hook = useSoftSegurosDebtors();
  const { setup, syncStatus, loading: loadingSetup, error, triggerSync, reimport, refetch, fetchDisconnectImpact, disconnect } = hook;
  const [statusTab, setStatusTab] = useState<DebtorStatus>('ya_vencidos');
  const view = useSoftSegurosDebtorsView({ status: statusTab });
  const [density, setDensity] = useState<'table' | 'cards'>('table');

  // Keep view.filters.status in sync with the tab.
  useEffect(() => { view.setFilters({ status: statusTab }); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [statusTab]);

  // Re-import panel
  const [showReimport, setShowReimport] = useState(false);
  const [riVencidos, setRiVencidos] = useState(true);
  const [riProximos, setRiProximos] = useState(true);
  const [riSubmitting, setRiSubmitting] = useState(false);
  useEffect(() => {
    if (showReimport) {
      setRiVencidos(setup.importFilters.include_vencidos);
      setRiProximos(setup.importFilters.include_proximos);
    }
  }, [showReimport, setup.importFilters]);

  // Disconnect modal
  const [showDisconnect, setShowDisconnect] = useState(false);
  const [discConfirm, setDiscConfirm] = useState('');
  const [discImpact, setDiscImpact] = useState<{ debtors_to_delete: number; call_history_to_delete: number } | null>(null);
  const [discSubmitting, setDiscSubmitting] = useState(false);
  const [discError, setDiscError] = useState<string | null>(null);
  useEffect(() => {
    if (!showDisconnect) return;
    setDiscConfirm(''); setDiscError(null); setDiscImpact(null);
    let alive = true;
    fetchDisconnectImpact().then(d => { if (alive && d) setDiscImpact({ debtors_to_delete: d.debtors_to_delete, call_history_to_delete: d.call_history_to_delete }); });
    return () => { alive = false; };
  }, [showDisconnect, fetchDisconnectImpact]);

  // Refetch view when the window regains focus. We keep the latest refetch fns
  // in a ref so the listener is attached ONCE (not re-subscribed every render —
  // `view` and `refetch` change identity on each render and would otherwise
  // churn the event listener and risk refetch storms).
  const refetchRef = useRef<() => void>(() => {});
  refetchRef.current = () => { void view.refetch(); void refetch(); };
  useEffect(() => {
    const onFocus = () => refetchRef.current();
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  // All useMemo / derived state MUST live above the early returns below — React
  // requires the same hook order on every render. Earlier versions of this
  // component crashed with "Rendered more hooks than during the previous render"
  // because monthMonto's useMemo ran only when the guards passed.
  const monthMonto = useMemo(() => {
    let max = 0;
    for (const d of view.list.items) {
      const m = (d as { monto?: number; total?: number }).monto ?? d.total ?? 0;
      if (Number(m) > max) max = Number(m);
    }
    return max;
  }, [view.list.items]);

  // ── Guards ──────────────────────────────────────────────────────────────────
  if (setup.authorized === false) {
    return (
      <div style={{ background: C.s1, border: `1px solid ${C.faint}`, padding: '20px 22px' }}>
        <div style={lbl(C.muted, 9.5)}>SOFTSEGUROS · No habilitado</div>
        <p style={{ fontFamily: C.IN, fontSize: 13, color: C.text, margin: '6px 0 4px' }}>
          La integración con SOFTSEGUROS no está habilitada para esta cuenta.
        </p>
        <p style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, margin: 0 }}>
          Contacta a Landa para activar este servicio.
        </p>
      </div>
    );
  }
  if (setup.authorized === null && loadingSetup) {
    return (
      <div style={{ background: C.s1, border: `1px solid ${C.faint}`, padding: '20px 22px', fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
        Cargando…
      </div>
    );
  }
  if (!setup.configured) {
    return <SoftSegurosSetup hook={hook} onComplete={() => { void refetch(); void view.refetch(); }} />;
  }

  // ── Derived view-state ──────────────────────────────────────────────────────
  const aging = view.aging;
  const totalActive = aging?.total.count ?? 0;
  const buckets = aging?.buckets;
  const ramoOptions = aging?.ramos ?? [];

  const showFailedBanner = !syncStatus?.is_syncing_now
    && syncStatus?.last_sync_status === 'failed'
    && !!syncStatus.error_message;

  const activeFilters = view.filters;
  const totalPages = Math.max(1, Math.ceil(view.list.total / view.filters.pageSize));

  return (
    <div style={{ background: C.s1, border: `1px solid ${C.cyanBdr}`, padding: '20px 22px' }}>
      {/* Top banner */}
      {syncStatus?.is_syncing_now && <SyncRunningBanner status={syncStatus} />}
      {showFailedBanner && syncStatus && (
        <SyncFailedBanner status={syncStatus} onRetry={() => { void triggerSync(); }} />
      )}

      {/* Header: title + sync line + actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <div>
          <div style={lbl(C.cyan, 9.5)}>SOFTSEGUROS</div>
          <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 20, color: C.text, marginTop: 2, marginBottom: 4 }}>
            Cartera por antigüedad
          </div>
          <SyncStatusLine status={syncStatus} totalActive={totalActive} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {error && error.code !== 'rate_limited' && (
            <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.pink }}>{error.message}</span>
          )}
          <button
            onClick={() => setShowDisconnect(true)}
            disabled={!!syncStatus?.is_syncing_now}
            title="Desconectar SOFTSEGUROS y borrar la cartera importada"
            style={btn('ghost-danger', !!syncStatus?.is_syncing_now)}
          >Desconectar</button>
          <button
            onClick={() => setShowReimport(v => !v)}
            disabled={!!syncStatus?.is_syncing_now}
            title="Re-importar la cartera con otros filtros"
            style={btn('ghost', !!syncStatus?.is_syncing_now)}
          >Re-importar…</button>
          <button
            onClick={() => { void triggerSync(); void view.refetch(); }}
            disabled={!!syncStatus?.is_syncing_now}
            title="Actualizar desde SOFTSEGUROS"
            style={btn('primary', !!syncStatus?.is_syncing_now)}
          >Actualizar</button>
        </div>
      </div>

      {/* KPI strip — aging buckets */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        <KPICard
          active={activeFilters.bucket === '90+'}
          label="+ 90 días"
          icon="🚩"
          variant="danger"
          count={buckets?.['90+'].count ?? 0}
          monto={buckets?.['90+'].total_monto ?? 0}
          onClick={() => view.setFilters({ bucket: activeFilters.bucket === '90+' ? null : '90+' })}
        />
        <KPICard
          active={activeFilters.bucket === '61-90'}
          label="61 – 90 días"
          icon="⚠"
          variant="warning"
          count={buckets?.['61-90'].count ?? 0}
          monto={buckets?.['61-90'].total_monto ?? 0}
          onClick={() => view.setFilters({ bucket: activeFilters.bucket === '61-90' ? null : '61-90' })}
        />
        <KPICard
          active={activeFilters.bucket === '31-60'}
          label="31 – 60 días"
          variant="info"
          count={buckets?.['31-60'].count ?? 0}
          monto={buckets?.['31-60'].total_monto ?? 0}
          onClick={() => view.setFilters({ bucket: activeFilters.bucket === '31-60' ? null : '31-60' })}
        />
        <KPICard
          active={activeFilters.bucket === '1-30'}
          label="1 – 30 días"
          variant="neutral"
          count={buckets?.['1-30'].count ?? 0}
          monto={buckets?.['1-30'].total_monto ?? 0}
          onClick={() => view.setFilters({ bucket: activeFilters.bucket === '1-30' ? null : '1-30' })}
        />
        <KPICard
          active={activeFilters.bucket === null}
          label="Total"
          variant="neutral"
          count={aging?.total.count ?? 0}
          monto={aging?.total.total_monto ?? 0}
          onClick={() => view.setFilters({ bucket: null })}
        />
      </div>

      {/* Status sub-tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14, borderBottom: `1px solid rgba(255,255,255,0.06)` }}>
        {(['ya_vencidos', 'proximos_a_vencer'] as DebtorStatus[]).map(s => (
          <button
            key={s}
            onClick={() => setStatusTab(s)}
            aria-pressed={statusTab === s}
            style={{
              padding: '8px 16px', border: 'none', background: 'transparent',
              borderBottom: `2px solid ${statusTab === s ? C.cyan : 'transparent'}`,
              color: statusTab === s ? C.cyan : C.muted,
              fontFamily: C.SG, fontWeight: 600, fontSize: 12.5, letterSpacing: '0.03em',
              cursor: 'pointer', marginBottom: -1,
            }}
          >
            {s === 'ya_vencidos' ? 'Ya vencidos' : 'Próximos a vencer'}
          </button>
        ))}
      </div>

      {/* Toolbar: search + monto + ramo + view density */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
        <input
          type="search"
          placeholder="Buscar nombre, póliza, documento…"
          value={view.searchText}
          onChange={e => view.setSearchText(e.target.value)}
          aria-label="Buscar deudores"
          style={{
            flex: '2 1 280px', minWidth: 240, height: 34, padding: '0 12px',
            background: C.s2, border: `1px solid rgba(255,255,255,0.1)`, color: C.text,
            fontFamily: C.IN, fontSize: 13, outline: 'none',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="number"
            placeholder="Monto mín"
            value={activeFilters.minMonto ?? ''}
            onChange={e => view.setFilters({ minMonto: e.target.value ? Number(e.target.value) : null })}
            aria-label="Monto mínimo"
            style={inputCompact}
          />
          <span style={{ color: C.faint, fontFamily: C.IN, fontSize: 12 }}>–</span>
          <input
            type="number"
            placeholder="Monto máx"
            value={activeFilters.maxMonto ?? ''}
            onChange={e => view.setFilters({ maxMonto: e.target.value ? Number(e.target.value) : null })}
            aria-label="Monto máximo"
            style={inputCompact}
          />
        </div>
        {ramoOptions.length > 0 && (
          <select
            multiple={false}
            value={activeFilters.ramos[0] ?? ''}
            onChange={e => view.setFilters({ ramos: e.target.value ? [e.target.value] : [] })}
            aria-label="Filtrar por ramo"
            style={{
              height: 34, padding: '0 10px', background: C.s2,
              border: `1px solid rgba(255,255,255,0.1)`, color: C.text,
              fontFamily: C.IN, fontSize: 12.5, outline: 'none', minWidth: 160,
            }}
          >
            <option value="">Todos los ramos</option>
            {ramoOptions.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        )}
        <div style={{ display: 'flex', border: `1px solid rgba(255,255,255,0.1)`, marginLeft: 'auto' }}>
          <button
            onClick={() => setDensity('table')}
            aria-pressed={density === 'table'}
            title="Vista tabla densa"
            style={densityBtn(density === 'table')}
          >Tabla</button>
          <button
            onClick={() => setDensity('cards')}
            aria-pressed={density === 'cards'}
            title="Vista expandida en tarjetas"
            style={densityBtn(density === 'cards')}
          >Cards</button>
        </div>
      </div>

      {/* Active filter chips */}
      {(activeFilters.bucket || activeFilters.minMonto !== null || activeFilters.maxMonto !== null || activeFilters.ramos.length > 0 || view.searchText) && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10, alignItems: 'center' }}>
          <span style={{ ...lbl(C.muted, 9), marginRight: 4 }}>Filtros:</span>
          {activeFilters.bucket && (
            <FilterChip label={`${activeFilters.bucket} días`} onRemove={() => view.setFilters({ bucket: null })} />
          )}
          {activeFilters.minMonto !== null && (
            <FilterChip label={`mín ${formatCOP(activeFilters.minMonto, { short: true })}`} onRemove={() => view.setFilters({ minMonto: null })} />
          )}
          {activeFilters.maxMonto !== null && (
            <FilterChip label={`máx ${formatCOP(activeFilters.maxMonto, { short: true })}`} onRemove={() => view.setFilters({ maxMonto: null })} />
          )}
          {activeFilters.ramos.map(r => (
            <FilterChip key={r} label={r} onRemove={() => view.setFilters({ ramos: activeFilters.ramos.filter(x => x !== r) })} />
          ))}
          {view.searchText && (
            <FilterChip label={`"${view.searchText}"`} onRemove={() => view.setSearchText('')} />
          )}
          <button
            onClick={() => { view.resetFilters(); }}
            style={{
              background: 'transparent', border: 'none', color: C.muted,
              fontFamily: C.IN, fontSize: 11.5, cursor: 'pointer', textDecoration: 'underline',
              padding: '2px 6px',
            }}
          >Limpiar todo</button>
        </div>
      )}

      {/* List */}
      {view.loading && view.list.items.length === 0 ? (
        <div style={{ padding: '40px 14px', textAlign: 'center', fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
          Cargando…
        </div>
      ) : view.visibleItems.length === 0 ? (
        <div style={{ padding: '40px 14px', textAlign: 'center', fontFamily: C.IN, fontSize: 13, color: C.muted, background: C.s2 }}>
          {view.list.total === 0
            ? 'No hay deudores en esta categoría.'
            : 'Ningún deudor coincide con los filtros aplicados.'}
        </div>
      ) : density === 'table' ? (
        <div style={{ overflow: 'auto', background: C.s2 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: C.IN }}>
            <thead>
              <tr style={{ background: C.s0 }}>
                <Th>Prioridad</Th>
                <Th sortable sort="nombre" current={view.filters.sort} dir={view.filters.direction} onSort={k => view.setFilters({ sort: k, direction: view.filters.sort === k && view.filters.direction === 'asc' ? 'desc' : 'asc' })}>Deudor</Th>
                <Th>Teléfono</Th>
                <Th sortable sort="monto" current={view.filters.sort} dir={view.filters.direction} onSort={k => view.setFilters({ sort: k, direction: view.filters.sort === k && view.filters.direction === 'desc' ? 'asc' : 'desc' })} align="right">Monto</Th>
                <Th sortable sort="vencimiento" current={view.filters.sort} dir={view.filters.direction} onSort={k => view.setFilters({ sort: k, direction: view.filters.sort === k && view.filters.direction === 'asc' ? 'desc' : 'asc' })}>Vencido</Th>
              </tr>
            </thead>
            <tbody>
              {view.visibleItems.map(d => (
                <DebtorRow key={d._id} d={d} monthMonto={monthMonto} density="table" />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {view.visibleItems.map(d => <DebtorRow key={d._id} d={d} monthMonto={monthMonto} density="cards" />)}
        </div>
      )}

      {/* Pagination */}
      {view.list.total > view.filters.pageSize && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14, fontFamily: C.IN, fontSize: 12, color: C.muted, gap: 12, flexWrap: 'wrap' }}>
          <div>
            Mostrando {(view.filters.page - 1) * view.filters.pageSize + 1}
            {' – '}{Math.min(view.filters.page * view.filters.pageSize, view.list.total)}
            {' de '}{formatCount(view.list.total)}
            {view.searchText && <span> · {view.visibleItems.length} coinciden con "{view.searchText}"</span>}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => view.setFilters({ page: Math.max(1, view.filters.page - 1) })}
              disabled={view.filters.page === 1}
              style={pagerBtn(view.filters.page === 1)}
            >← Anterior</button>
            <span style={{ padding: '6px 12px', fontFamily: C.SG, fontSize: 12, color: C.text }}>
              {view.filters.page} / {totalPages}
            </span>
            <button
              onClick={() => view.setFilters({ page: Math.min(totalPages, view.filters.page + 1) })}
              disabled={view.filters.page >= totalPages}
              style={pagerBtn(view.filters.page >= totalPages)}
            >Siguiente →</button>
          </div>
        </div>
      )}

      {/* Re-import panel */}
      {showReimport && (
        <div style={{ background: C.s2, border: `1px solid ${C.cyanBdr}`, padding: '14px 16px', marginTop: 16 }}>
          <div style={{ ...lbl(C.muted, 9), marginBottom: 8 }}>RE-IMPORTAR CON OTROS FILTROS</div>
          <p style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, margin: '0 0 10px' }}>
            Vuelve a escanear toda la cartera. El historial de llamadas se conserva.
          </p>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: C.IN, fontSize: 12.5, color: C.text, cursor: 'pointer', marginBottom: 6 }}>
            <input type="checkbox" checked={riVencidos} disabled={riSubmitting} onChange={e => setRiVencidos(e.target.checked)} />
            Ya vencidos (deuda en mora)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: C.IN, fontSize: 12.5, color: C.text, cursor: 'pointer', marginBottom: 10 }}>
            <input type="checkbox" checked={riProximos} disabled={riSubmitting} onChange={e => setRiProximos(e.target.checked)} />
            Próximos a vencer (próximos 30 días)
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={async () => {
                if (!riVencidos && !riProximos) return;
                setRiSubmitting(true);
                const ok = await reimport({
                  ...setup.importFilters,
                  include_vencidos: riVencidos,
                  include_proximos: riProximos,
                });
                setRiSubmitting(false);
                if (ok) setShowReimport(false);
              }}
              disabled={riSubmitting || (!riVencidos && !riProximos)}
              style={btn('primary', riSubmitting || (!riVencidos && !riProximos))}
            >{riSubmitting ? 'Iniciando…' : 'Re-importar ahora'}</button>
            <button onClick={() => setShowReimport(false)} disabled={riSubmitting} style={btn('ghost', riSubmitting)}>Cancelar</button>
          </div>
        </div>
      )}

      {/* Disconnect modal */}
      {showDisconnect && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="ss-disconnect-title"
          onClick={() => !discSubmitting && setShowDisconnect(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: C.s1, border: `1px solid rgba(255,97,136,0.35)`, padding: '24px 26px', maxWidth: 520, width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.6)' }}>
            <div style={lbl(C.pink, 9)}>ACCIÓN IRREVERSIBLE</div>
            <h3 id="ss-disconnect-title" style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 18, color: C.text, margin: '6px 0 10px' }}>
              Desconectar SOFTSEGUROS
            </h3>
            <p style={{ fontFamily: C.IN, fontSize: 13, color: C.text, lineHeight: 1.55, margin: '0 0 12px' }}>
              Vamos a borrar permanentemente:
            </p>
            <ul style={{ fontFamily: C.IN, fontSize: 12.5, color: C.muted, lineHeight: 1.65, paddingLeft: 20, margin: '0 0 14px' }}>
              <li>Tus credenciales SOFTSEGUROS guardadas.</li>
              <li><strong style={{ color: C.text }}>{discImpact ? formatCount(discImpact.debtors_to_delete) : '…'} deudores</strong> importados.</li>
              <li><strong style={{ color: C.text }}>{discImpact ? formatCount(discImpact.call_history_to_delete) : '…'} registros</strong> de historial de llamadas.</li>
            </ul>
            <p style={{ fontFamily: C.IN, fontSize: 12.5, color: C.text, margin: '0 0 6px' }}>
              Para confirmar, escribí <strong style={{ color: C.pink, fontFamily: C.SG, letterSpacing: '0.06em' }}>BORRAR</strong> abajo:
            </p>
            <input
              type="text"
              value={discConfirm}
              onChange={e => { setDiscConfirm(e.target.value); setDiscError(null); }}
              disabled={discSubmitting}
              autoFocus
              placeholder="BORRAR"
              aria-label="Confirmación de borrado"
              style={{ width: '100%', boxSizing: 'border-box', background: C.s2, border: `1px solid rgba(255,97,136,0.3)`, color: C.text, fontFamily: C.IN, fontSize: 14, padding: '10px 12px', outline: 'none', letterSpacing: '0.04em' }}
            />
            {discError && (
              <div role="alert" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.orange, marginTop: 8 }}>{discError}</div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
              <button onClick={() => setShowDisconnect(false)} disabled={discSubmitting} style={btn('ghost', discSubmitting)}>Cancelar</button>
              <button
                onClick={async () => {
                  if (discConfirm !== 'BORRAR') { setDiscError('Escribí exactamente BORRAR.'); return; }
                  setDiscSubmitting(true); setDiscError(null);
                  const ok = await disconnect('BORRAR');
                  setDiscSubmitting(false);
                  if (ok) setShowDisconnect(false);
                  else setDiscError(error?.message || 'No se pudo desconectar.');
                }}
                disabled={discSubmitting || discConfirm !== 'BORRAR'}
                style={{
                  height: 34, padding: '0 18px', border: 'none',
                  background: discSubmitting || discConfirm !== 'BORRAR' ? C.s3 : C.pink,
                  color: discSubmitting || discConfirm !== 'BORRAR' ? C.muted : '#fff',
                  fontFamily: C.SG, fontWeight: 700, fontSize: 12, letterSpacing: '0.05em',
                  cursor: discSubmitting || discConfirm !== 'BORRAR' ? 'not-allowed' : 'pointer',
                }}
              >{discSubmitting ? 'Desconectando…' : 'Desconectar y borrar'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub: table header cell with optional sort indicator ───────────────────────

function Th({
  children, align = 'left', sortable, sort, current, dir, onSort,
}: {
  children: React.ReactNode;
  align?: 'left' | 'right';
  sortable?: boolean;
  sort?: SortField;
  current?: SortField;
  dir?: 'asc' | 'desc';
  onSort?: (k: SortField) => void;
}) {
  const isActive = sortable && sort === current;
  return (
    <th
      style={{
        textAlign: align,
        padding: '10px 12px',
        ...lbl(isActive ? C.cyan : C.muted, 9.5),
        cursor: sortable ? 'pointer' : 'default',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
      onClick={sortable && sort && onSort ? () => onSort(sort) : undefined}
    >
      {children}
      {sortable && (
        <span style={{ marginLeft: 6, color: isActive ? C.cyan : C.faint, fontSize: 9 }}>
          {isActive ? (dir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      )}
    </th>
  );
}

// ── Style helpers ─────────────────────────────────────────────────────────────

function btn(variant: 'primary' | 'ghost' | 'ghost-danger', disabled: boolean): React.CSSProperties {
  if (variant === 'primary') {
    return {
      height: 30, padding: '0 14px', border: `1px solid ${C.cyanBdr}`,
      background: disabled ? C.s3 : C.cyanBg, color: disabled ? C.muted : C.cyan,
      cursor: disabled ? 'not-allowed' : 'pointer',
      fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
    };
  }
  if (variant === 'ghost-danger') {
    return {
      height: 30, padding: '0 12px', border: `1px solid rgba(255,97,136,0.25)`,
      background: 'transparent', color: disabled ? C.muted : C.pink,
      cursor: disabled ? 'not-allowed' : 'pointer',
      fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
    };
  }
  return {
    height: 30, padding: '0 14px', border: `1px solid rgba(255,255,255,0.1)`,
    background: 'transparent', color: C.muted,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
  };
}

const inputCompact: React.CSSProperties = {
  width: 110, height: 34, padding: '0 8px',
  background: C.s2, border: `1px solid rgba(255,255,255,0.1)`, color: C.text,
  fontFamily: C.IN, fontSize: 12.5, outline: 'none',
};

function densityBtn(active: boolean): React.CSSProperties {
  return {
    height: 34, padding: '0 12px', border: 'none',
    background: active ? C.cyanBg : 'transparent',
    color: active ? C.cyan : C.muted,
    fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
    cursor: 'pointer',
  };
}

function pagerBtn(disabled: boolean): React.CSSProperties {
  return {
    padding: '6px 12px', border: `1px solid rgba(255,255,255,0.1)`,
    background: 'transparent', color: disabled ? C.faint : C.muted,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontFamily: C.SG, fontWeight: 600, fontSize: 11.5,
  };
}

export default DebtorsSoftSegurosTab;
