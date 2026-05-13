import { useEffect, useMemo, useState } from 'react';
import { useSoftSegurosDebtors, type SoftSegurosDebtor, type SoftSegurosSyncStatus } from '../hooks/useSoftSegurosDebtors';
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

const lbl = (color = C.muted, size = 9): React.CSSProperties => ({
  fontFamily: C.SG, fontSize: size, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.14em', color,
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatCOP(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  try {
    return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(Number(value));
  } catch {
    return `$${Math.round(Number(value)).toLocaleString('es-CO')}`;
  }
}

function debtorName(d: SoftSegurosDebtor): string {
  if (d.nombre && d.nombre.trim()) return d.nombre;
  const composed = [d.cliente_nombres, d.cliente_apellidos].filter(Boolean).join(' ').trim();
  return composed || 'Sin nombre';
}

function dueDate(d: SoftSegurosDebtor): string | null {
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
  return Math.round((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

function dueLabel(iso: string | null): { text: string; color: string } {
  const days = daysFromToday(iso);
  if (days === null) return { text: 'Sin fecha', color: C.muted };
  if (days < 0) return { text: `Vencido hace ${Math.abs(days)} día${Math.abs(days) === 1 ? '' : 's'}`, color: C.pink };
  if (days === 0) return { text: 'Vence hoy', color: C.orange };
  return { text: `Vence en ${days} día${days === 1 ? '' : 's'}`, color: days <= 7 ? C.yellow : C.cyan };
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

// ── Sub-components ─────────────────────────────────────────────────────────────

function SyncStatusBadge({ status }: { status: SoftSegurosSyncStatus | null }) {
  if (status?.is_syncing_now) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: C.SG, fontSize: 11, color: C.cyan }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.cyan, animation: 'cobr-pulse 1.2s ease-in-out infinite' }} />
        Sincronizando…
      </span>
    );
  }
  return (
    <span style={{ fontFamily: C.SG, fontSize: 11, color: C.muted }}>
      Última sync: {relativeTime(status?.last_sync_at ?? null)}
      {status?.last_sync_status === 'failed' && <span style={{ color: C.pink }}> · falló</span>}
    </span>
  );
}

function DebtorCard({ d }: { d: SoftSegurosDebtor }) {
  const due = dueDate(d);
  const dl = dueLabel(due);
  const tel = d.cliente_celular ?? d.telefono ?? null;
  const total = d.total ?? d.monto ?? null;
  return (
    <div style={{
      background: C.s2, border: `1px solid rgba(255,255,255,0.06)`,
      padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.text }}>{debtorName(d)}</span>
        <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13, color: C.green, whiteSpace: 'nowrap' }}>{formatCOP(total)}</span>
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontFamily: C.IN, fontSize: 12 }}>
        {tel && <a href={`tel:${tel}`} style={{ color: C.cyan, textDecoration: 'none' }}>{tel}</a>}
        {d.cliente_email && <a href={`mailto:${d.cliente_email}`} style={{ color: C.cyan, textDecoration: 'none' }}>{d.cliente_email}</a>}
      </div>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontFamily: C.IN, fontSize: 12, color: dl.color }}>{dl.text}</span>
        {due && <span style={{ fontFamily: C.IN, fontSize: 11, color: C.faint }}>{due}</span>}
        {d.numero_poliza && <span style={{ fontFamily: C.IN, fontSize: 11, color: C.faint }}>Póliza {d.numero_poliza}</span>}
        {d.ramo_nombre && <span style={{ fontFamily: C.IN, fontSize: 11, color: C.faint }}>{d.ramo_nombre}</span>}
        {d.estado_poliza_nombre && <span style={{ fontFamily: C.IN, fontSize: 11, color: C.faint }}>{d.estado_poliza_nombre}</span>}
      </div>
    </div>
  );
}

function DebtorList({ debtors, emptyText }: { debtors: SoftSegurosDebtor[]; emptyText: string }) {
  if (debtors.length === 0) {
    return (
      <div style={{ padding: '24px 14px', textAlign: 'center', fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
        {emptyText}
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {debtors.map(d => <DebtorCard key={d._id} d={d} />)}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

type TabKey = 'proximos' | 'vencidos';

export function DebtorsSoftSegurosTab() {
  const hook = useSoftSegurosDebtors();
  const { setup, debtors, syncStatus, loading, error, triggerSync, reimport, refetch } = hook;
  const [tab, setTab] = useState<TabKey>('proximos');
  const [now, setNow] = useState(Date.now());
  // Re-import panel state
  const [showReimport, setShowReimport] = useState(false);
  const [riVencidos, setRiVencidos] = useState(true);
  const [riProximos, setRiProximos] = useState(true);
  const [riSubmitting, setRiSubmitting] = useState(false);

  // Re-render every second while rate-limited so the countdown updates.
  useEffect(() => {
    if (error?.code !== 'rate_limited') return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [error]);

  // Refetch when the window/tab regains focus.
  useEffect(() => {
    const onFocus = () => { void refetch(); };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [refetch]);

  // Open the re-import panel pre-filled with the current filters.
  useEffect(() => {
    if (showReimport) {
      setRiVencidos(setup.importFilters.include_vencidos);
      setRiProximos(setup.importFilters.include_proximos);
    }
  }, [showReimport, setup.importFilters]);

  // Track when the rate-limit error first appeared to compute the countdown.
  const [rateLimitStart, setRateLimitStart] = useState<number | null>(null);
  useEffect(() => {
    if (error?.code === 'rate_limited') {
      setRateLimitStart(prev => prev ?? Date.now());
    } else {
      setRateLimitStart(null);
    }
  }, [error]);
  const countdown = useMemo(() => {
    if (!rateLimitStart || error?.code !== 'rate_limited' || !error.retryAfter) return 0;
    const elapsed = Math.floor((now - rateLimitStart) / 1000);
    return Math.max(0, error.retryAfter - elapsed);
  }, [rateLimitStart, error, now]);

  // Service not authorized by Landa for this account.
  if (setup.authorized === false) {
    return (
      <div style={{ background: C.s1, border: `1px solid ${C.faint}`, padding: '20px 22px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <span style={lbl(C.muted, 9)}>SOFTSEGUROS</span>
          <span style={{ fontFamily: C.SG, fontSize: 11, color: C.muted }}>No habilitado</span>
        </div>
        <p style={{ fontFamily: C.IN, fontSize: 13, color: C.text, margin: '0 0 4px' }}>
          La integración con SOFTSEGUROS no está habilitada para esta cuenta.
        </p>
        <p style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, margin: 0 }}>
          Contacta a Landa para activar este servicio.
        </p>
      </div>
    );
  }

  // Still checking authorization / setup.
  if (setup.authorized === null && loading) {
    return (
      <div style={{ background: C.s1, border: `1px solid ${C.faint}`, padding: '20px 22px', fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
        Cargando…
      </div>
    );
  }

  if (!setup.configured) {
    return <SoftSegurosSetup hook={hook} onComplete={() => { void refetch(); }} />;
  }

  const syncing = !!syncStatus?.is_syncing_now;
  const syncDisabled = syncing || countdown > 0;
  const { include_vencidos: hasVencidos, include_proximos: hasProximos } = setup.importFilters;
  const riNoneSelected = !riVencidos && !riProximos;

  const allTabs: { key: TabKey; label: string; list: SoftSegurosDebtor[]; empty: string; imported: boolean }[] = [
    { key: 'proximos', label: `Próximos a vencer (${debtors.proximosAVencer.length})`, list: debtors.proximosAVencer, empty: 'No hay deudores próximos a vencer.', imported: hasProximos },
    { key: 'vencidos', label: `Ya vencidos (${debtors.yaVencidos.length})`, list: debtors.yaVencidos, empty: 'No hay deudores vencidos.', imported: hasVencidos },
  ];
  const tabs = allTabs.filter(t => t.imported);
  // If the currently-selected tab isn't imported, fall back to the first imported one.
  const active = tabs.find(t => t.key === tab) ?? tabs[0] ?? allTabs[0];

  const doReimport = async () => {
    if (riNoneSelected) return;
    setRiSubmitting(true);
    const ok = await reimport({ include_vencidos: riVencidos, include_proximos: riProximos });
    setRiSubmitting(false);
    if (ok) setShowReimport(false);
  };

  return (
    <div style={{ background: C.s1, border: `1px solid ${C.cyanBdr}`, padding: '16px 18px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={lbl(C.cyan, 9)}>SOFTSEGUROS</span>
          <SyncStatusBadge status={syncStatus} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {error && error.code !== 'rate_limited' && (
            <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.pink }}>{error.message}</span>
          )}
          <button
            onClick={() => setShowReimport(v => !v)}
            disabled={syncing}
            title="Re-importar la cartera con otros filtros"
            style={{
              height: 30, padding: '0 14px', border: `1px solid rgba(255,255,255,0.1)`,
              background: 'transparent', color: syncing ? C.muted : C.muted,
              cursor: syncing ? 'not-allowed' : 'pointer',
              fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
            }}
          >
            Re-importar…
          </button>
          <button
            onClick={() => { void triggerSync(); }}
            disabled={syncDisabled}
            title={countdown > 0 ? `Espera ${countdown}s` : syncing ? 'Sincronizando…' : 'Actualizar deudores desde SOFTSEGUROS'}
            style={{
              height: 30, padding: '0 14px', border: `1px solid ${C.cyanBdr}`,
              background: syncDisabled ? C.s3 : C.cyanBg, color: syncDisabled ? C.muted : C.cyan,
              cursor: syncDisabled ? 'not-allowed' : 'pointer',
              fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, letterSpacing: '0.05em',
            }}
          >
            {countdown > 0 ? `Espera ${countdown}s` : 'Actualizar ahora'}
          </button>
        </div>
      </div>

      {/* Re-import panel */}
      {showReimport && (
        <div style={{ background: C.s2, border: `1px solid ${C.cyanBdr}`, padding: '14px 16px', marginBottom: 14 }}>
          <div style={{ ...lbl(C.muted, 9), marginBottom: 8 }}>RE-IMPORTAR CON OTROS FILTROS</div>
          <p style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, margin: '0 0 10px' }}>
            Vuelve a escanear toda la cartera (puede tardar varios minutos). El historial de
            llamadas de los deudores actuales se conserva — los que ya no coincidan con los
            filtros se ocultan pero no se borran.
          </p>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: C.IN, fontSize: 12.5, color: C.text, cursor: 'pointer', marginBottom: 6 }}>
            <input type="checkbox" checked={riVencidos} disabled={riSubmitting} onChange={e => setRiVencidos(e.target.checked)} />
            Ya vencidos (deuda en mora)
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: C.IN, fontSize: 12.5, color: C.text, cursor: 'pointer', marginBottom: 10 }}>
            <input type="checkbox" checked={riProximos} disabled={riSubmitting} onChange={e => setRiProximos(e.target.checked)} />
            Próximos a vencer (próximos 30 días)
          </label>
          {riNoneSelected && (
            <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.orange, marginBottom: 8 }}>
              Selecciona al menos un tipo de deudor.
            </div>
          )}
          {error?.code === 'rate_limited' && (
            <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.orange, marginBottom: 8 }}>
              {countdown > 0 ? `Espera ${countdown}s antes de re-importar.` : error.message}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={() => { void doReimport(); }}
              disabled={riSubmitting || riNoneSelected || countdown > 0}
              style={{
                height: 30, padding: '0 16px', border: 'none',
                background: riSubmitting || riNoneSelected || countdown > 0 ? C.s3 : C.cyan,
                color: C.bg, fontFamily: C.SG, fontWeight: 700, fontSize: 11.5, letterSpacing: '0.05em',
                cursor: riSubmitting || riNoneSelected || countdown > 0 ? 'not-allowed' : 'pointer',
              }}
            >
              {riSubmitting ? 'Iniciando…' : 'Re-importar ahora'}
            </button>
            <button
              onClick={() => setShowReimport(false)}
              disabled={riSubmitting}
              style={{
                height: 30, padding: '0 14px', border: `1px solid rgba(255,255,255,0.1)`,
                background: 'transparent', color: C.muted, fontFamily: C.SG, fontWeight: 600, fontSize: 11.5,
                cursor: riSubmitting ? 'not-allowed' : 'pointer',
              }}
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      {tabs.length > 1 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                padding: '7px 14px', border: `1px solid ${t.key === active.key ? C.cyanBdr : 'rgba(255,255,255,0.06)'}`,
                background: t.key === active.key ? C.cyanBg : 'transparent',
                color: t.key === active.key ? C.cyan : C.muted,
                fontFamily: C.SG, fontWeight: 600, fontSize: 11.5, cursor: 'pointer',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}
      {tabs.length === 1 && (
        <div style={{ ...lbl(C.muted, 9), marginBottom: 10 }}>{active.label}</div>
      )}

      {/* List */}
      {loading
        ? <div style={{ padding: '24px 14px', textAlign: 'center', fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>Cargando…</div>
        : <DebtorList debtors={active.list} emptyText={active.empty} />}
    </div>
  );
}

export default DebtorsSoftSegurosTab;
