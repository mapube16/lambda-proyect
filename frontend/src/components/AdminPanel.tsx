import React, { useState, useEffect, useCallback } from 'react';
import * as api from '../api';

// ════════════════════════════════════════════════════════════════════
// AdminPanel — Landa staff/admin console.
// Based on the "Landa Admin.html" design prototype, wired to the real
// /api/staff endpoints for Dashboard, Clientes, Operaciones and Servicios.
// Briefs and Facturación have NO backend yet → they stay on demo data and
// are clearly labelled "Demo" in the UI.
//
// Connection legend used in this file:
//   🟢 REAL  → reads/writes the backend
//   🟡 DEMO  → hardcoded mock data (no backend exists)
// ════════════════════════════════════════════════════════════════════

/* ─── ICONS ─── */
function Icon({ name, size = 18, stroke = 1.6, style }: { name: string; size?: number; stroke?: number; style?: React.CSSProperties }) {
  const icons: Record<string, string> = {
    home: 'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25',
    users: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z',
    activity: 'M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z',
    brief: 'M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z',
    billing: 'M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z',
    search: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z',
    bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0',
    plus: 'M12 4.5v15m7.5-7.5h-15',
    arrow: 'M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3',
    check: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    eye: 'M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178zm7.964 0a3 3 0 100-6 3 3 0 000 6z',
    send: 'M6 12L3.269 3.125A59.769 59.769 0 0121.485 12 59.77 59.77 0 013.27 20.875L5.999 12zm0 0h7.5',
    gear: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28zM15 12a3 3 0 11-6 0 3 3 0 016 0z',
    building: 'M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z',
    spark: 'M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z',
    phone: 'M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z',
    chat: 'M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z',
    globe: 'M12 21a9 9 0 100-18 9 9 0 000 18zm0 0c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3M3.6 9h16.8M3.6 15h16.8',
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style}>
      <path d={icons[name] || ''} />
    </svg>
  );
}

/* ─── TYPES ─── */
interface ClientRow {
  id: string; email: string; role: string; created_at?: string; phone?: string;
  // enriched from /stats per_client
  total_leads?: number; approved_leads?: number; total_runs?: number;
  active_runs?: number; last_run_status?: string;
}

/* ─── CONFIG / PALETTE ─── */
const SB_BG = '#1A1A2E';
const SB_ACTIVE = 'rgba(59,170,152,0.18)';
const SB_ACTIVE_C = '#3BAA98';
const SB_TEXT = 'rgba(255,255,255,0.50)';
const SB_BORDER = 'rgba(255,255,255,0.07)';

const ESTADO_CFG: Record<string, { color: string; bg: string; label: string }> = {
  activo: { color: '#15A56A', bg: '#E6F6EE', label: 'Activo' },
  inactivo: { color: '#6B6B7A', bg: '#F2F2F8', label: 'Sin actividad' },
  corriendo: { color: '#0EA5E9', bg: '#E8F6FD', label: 'Corriendo' },
  error: { color: '#E03E4C', bg: '#FCE9EA', label: 'Error' },
};
const ROLE_CFG: Record<string, { name: string; color: string; soft: string; tasks: string[] }> = {
  buscador: { name: 'Buscador', color: '#6366F1', soft: '#EEF0FE', tasks: ['Rastreando SECOP II…', 'Buscando en Bogotá…', 'Explorando directorios…'] },
  scraper: { name: 'Scraper', color: '#0EA5E9', soft: '#E8F6FD', tasks: ['Leyendo web de empresa…', 'Extrayendo contactos…', 'Analizando descripción…'] },
  analista: { name: 'Analista', color: '#10B981', soft: '#E6F8F1', tasks: ['Calculando score…', 'Evaluando activos…', 'Verificando decisor…'] },
  redactor: { name: 'Redactor', color: '#F59E0B', soft: '#FEF4E3', tasks: ['Personalizando apertura…', 'Ajustando tono…', 'Finalizando redacción…'] },
};

/* ─── HELPERS ─── */
function shortName(email: string) {
  return (email || '').split('@')[0].replace(/[._-]/g, ' ').trim() || email || '—';
}
// Derive a coarse status from real run data.
function clientEstado(c: ClientRow): string {
  if (c.active_runs && c.active_runs > 0) return 'corriendo';
  if (c.last_run_status === 'error') return 'error';
  if ((c.total_runs ?? 0) > 0) return 'activo';
  return 'inactivo';
}

function Badge({ label, color, bg }: { label?: string; color?: string; bg?: string }) {
  return <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color, background: bg, padding: '3px 9px', borderRadius: 999 }}>{label}</span>;
}

// Small "Demo" pill, used to flag views/data that are NOT backed by the API.
function DemoTag({ note }: { note?: string }) {
  return (
    <span title={note || 'Datos de demostración — sin backend conectado'} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#D97A06', background: '#FCF1E0', border: '1px solid #D97A0633', padding: '3px 9px', borderRadius: 999 }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#D97A06' }} /> Demo
    </span>
  );
}

function Toggle({ on, onChange, disabled }: { on: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button onClick={disabled ? undefined : onChange} role="switch" aria-checked={on} disabled={disabled} style={{ width: 40, height: 23, borderRadius: 999, border: 'none', cursor: disabled ? 'default' : 'pointer', padding: 2, background: on ? '#3BAA98' : '#D6D6E0', transition: 'background .2s', display: 'flex', alignItems: 'center', flexShrink: 0, opacity: disabled ? 0.5 : 1 }}>
      <span style={{ width: 19, height: 19, borderRadius: '50%', background: '#fff', boxShadow: '0 1px 2px rgba(20,20,40,.25)', transform: on ? 'translateX(17px)' : 'translateX(0)', transition: 'transform .2s' }} />
    </button>
  );
}

function Card({ style, children, onClick }: { style?: React.CSSProperties; children: React.ReactNode; onClick?: (e: React.MouseEvent) => void }) {
  return <div onClick={onClick} style={{ background: '#fff', border: '1px solid #ECECF3', borderRadius: 16, boxShadow: '0 1px 3px rgba(20,20,40,.05)', ...style }}>{children}</div>;
}

function Spinner({ size = 18, color = '#4F46E5' }: { size?: number; color?: string }) {
  return <span style={{ width: size, height: size, border: `2px solid ${color}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'admSpin .7s linear infinite', display: 'inline-block' }} />;
}

/* ─── SERVICIOS CATALOG ───────────────────────────────────────────────
   Only `cobranza_voz` maps to a REAL backend toggle (cobranza/enable).
   The rest have no per-client backend toggle yet → marked demo. */
const SERVICIOS_CATALOGO = [
  { id: 'cobranza_voz', nombre: 'Cobranza de Voz', desc: 'Agente de voz IA llama a deudores y registra promesas automáticamente', icon: 'phone', color: '#3BAA98', bg: '#E4F6F3', real: true },
  { id: 'prospeccion', nombre: 'Prospección IA', desc: 'Buscador + Scraper + Analista + Redactor en serie', icon: 'spark', color: '#4F46E5', bg: '#EEEDFC', real: false },
  { id: 'email_masivo', nombre: 'Email masivo', desc: 'Envío personalizado con analytics de apertura y clicks', icon: 'send', color: '#0EA5E9', bg: '#E8F6FD', real: false },
  { id: 'whatsapp', nombre: 'WhatsApp automatizado', desc: 'Mensajes y seguimiento vía WhatsApp Business API', icon: 'chat', color: '#15A56A', bg: '#E6F6EE', real: false },
  { id: 'landing', nombre: 'Landing page IA', desc: 'Brief → landing generada por agente, publicada en horas', icon: 'brief', color: '#D97A06', bg: '#FCF1E0', real: false },
  { id: 'analytics', nombre: 'Analítica avanzada', desc: 'Dashboard de apertura, clicks, respuestas y funnel completo', icon: 'activity', color: '#6366F1', bg: '#EEF0FE', real: false },
];

// Real backend discovery sources (VALID_SOURCES in routers/staff.py).
const FUENTES = [
  { id: 'google_maps', label: 'Google Maps', desc: 'Empresas por búsqueda en Maps', color: '#4F46E5' },
  { id: 'secop_adjudicados', label: 'SECOP — Adjudicados', desc: 'Contratos públicos adjudicados', color: '#D97A06' },
  { id: 'secop_licitaciones', label: 'SECOP — Licitaciones', desc: 'Procesos de contratación abiertos', color: '#0EA5E9' },
];

const NAV = [
  { id: 'dashboard', icon: 'home', label: 'Dashboard' },
  { id: 'clientes', icon: 'users', label: 'Clientes' },
  { id: 'operaciones', icon: 'activity', label: 'Operaciones' },
  { id: 'servicios', icon: 'gear', label: 'Servicios' },
  { id: 'briefs', icon: 'brief', label: 'Briefs recibidos' },
  { id: 'facturacion', icon: 'billing', label: 'Facturación' },
];

/* ─── SHARED DATA HOOK ─── */
// Loads clients + global stats once and merges per_client metrics into rows.
function useStaffData() {
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [rawClients, rawStats] = await Promise.all([
        api.staffGetClients(),
        api.staffGetStats().catch(() => null),
      ]);
      const perClient: Record<string, any> = {};
      (rawStats?.per_client || []).forEach((p: any) => { perClient[p.client_id] = p; });
      const merged: ClientRow[] = (rawClients || []).map((c: any) => ({
        ...c,
        ...(perClient[c.id] || {}),
      }));
      setClients(merged);
      setStats(rawStats);
    } catch (e: any) {
      setError(e?.message || 'No se pudieron cargar los datos de staff.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  return { clients, stats, loading, error, reload: load, setClients };
}

/* ─── SIDEBAR ─── */
function AdminSidebar({ view, setView, collapsed, onLogout, leadsHoy }: { view: string; setView: (v: string) => void; collapsed: boolean; onLogout?: () => void; leadsHoy: number }) {
  return (
    <div style={{ width: collapsed ? 60 : 224, background: SB_BG, display: 'flex', flexDirection: 'column', height: '100vh', flexShrink: 0, borderRight: `1px solid ${SB_BORDER}`, transition: 'width .22s cubic-bezier(.4,0,.2,1)', overflow: 'hidden' }}>
      <div style={{ padding: collapsed ? '14px 12px' : '22px 18px 18px', borderBottom: `1px solid ${SB_BORDER}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 11, justifyContent: collapsed ? 'center' : 'flex-start' }}>
          <svg width="34" height="32" viewBox="0 0 52 50" fill="none">
            <path d="M37 18 h5.5 a6.5 6.5 0 0 1 6.5 6.5 v2 a6.5 6.5 0 0 1 -6.5 6.5 h-5.5" stroke="#3BAA98" strokeWidth="3.2" strokeLinecap="round" />
            <rect x="6" y="9" width="31" height="33" rx="4.5" fill={SB_BG} stroke="#3BAA98" strokeWidth="3.2" />
            <ellipse cx="21.5" cy="10.5" rx="14" ry="3" fill={SB_BG} stroke="#3BAA98" strokeWidth="2.4" />
            <line x1="11.5" y1="17" x2="11.5" y2="34" stroke="#2FC7A8" strokeWidth="1.8" strokeLinecap="round" />
            <g stroke="#2FC7A8" strokeWidth="3.4" strokeLinecap="square" fill="none">
              <path d="M20 18 L29 35" /><path d="M23.5 25 L17 35" /><path d="M16.5 18 L21 18" />
            </g>
          </svg>
          {!collapsed && <div>
            <div style={{ color: '#fff', fontWeight: 800, fontSize: 18, letterSpacing: '-0.01em', lineHeight: 1 }}>Land<span style={{ color: '#3BAA98' }}>λ</span></div>
            <div style={{ color: 'rgba(255,255,255,0.32)', fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', marginTop: 3 }}>Panel Admin</div>
          </div>}
        </div>
      </div>

      <div style={{ flex: 1, padding: '10px 8px', display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto' }}>
        {NAV.map(n => {
          const active = view === n.id;
          const isDemo = n.id === 'briefs' || n.id === 'facturacion';
          return (
            <button key={n.id} onClick={() => setView(n.id)} title={collapsed ? n.label : undefined}
              style={{ display: 'flex', alignItems: 'center', gap: collapsed ? 0 : 11, padding: collapsed ? '10px 0' : '10px 12px', justifyContent: collapsed ? 'center' : 'flex-start', borderRadius: 10, border: 'none', cursor: 'pointer', background: active ? SB_ACTIVE : 'transparent', color: active ? SB_ACTIVE_C : SB_TEXT, fontFamily: 'inherit', fontWeight: active ? 700 : 500, fontSize: 14, width: '100%', textAlign: 'left', transition: 'all .12s' }}>
              <Icon name={n.icon} size={17} stroke={active ? 2 : 1.6} />
              {!collapsed && <span style={{ flex: 1 }}>{n.label}</span>}
              {!collapsed && isDemo && <span style={{ fontSize: 8.5, fontWeight: 700, letterSpacing: '0.06em', color: '#D97A06', background: 'rgba(217,122,6,0.16)', padding: '2px 5px', borderRadius: 5 }}>DEMO</span>}
            </button>
          );
        })}

        <div style={{ marginTop: 16, padding: '2px 0 8px', borderTop: `1px solid ${SB_BORDER}` }} />

        {!collapsed && <div style={{ padding: '12px 13px', borderRadius: 10, background: 'rgba(255,255,255,0.05)', border: `1px solid ${SB_BORDER}` }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'rgba(255,255,255,0.28)', marginBottom: 10 }}>Agentes IA</div>
          {Object.entries(ROLE_CFG).map(([key, r]) => (
            <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 7 }}>
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)' }}>{r.name}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: SB_ACTIVE_C, animation: 'admPulse 2s infinite', color: SB_ACTIVE_C }} />
                <span style={{ fontSize: 10.5, color: SB_ACTIVE_C, fontWeight: 700 }}>ON</span>
              </div>
            </div>
          ))}
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${SB_BORDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.32)' }}>Leads totales</span>
            <span style={{ fontSize: 16, fontWeight: 800, color: '#fff' }}>{leadsHoy}</span>
          </div>
        </div>}
      </div>

      <div style={{ padding: collapsed ? '14px 8px' : '14px 16px', borderTop: `1px solid ${SB_BORDER}`, display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'flex-start', gap: 10 }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, background: 'linear-gradient(135deg,#3BAA98,#4F46E5)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 13, flex: 'none' }}>LA</div>
        {!collapsed && <><div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: '#fff', fontSize: 13, fontWeight: 700 }}>Landa Admin</div>
          <div style={{ color: 'rgba(255,255,255,0.32)', fontSize: 11, marginTop: 1 }}>LATAM · HQ</div>
        </div>
          <button onClick={onLogout} title="Cerrar sesión" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.35)', padding: 4 }}><Icon name="gear" size={15} /></button></>}
      </div>
    </div>
  );
}

/* ─── TOPBAR ─── */
function AdminTopbar({ view, collapsed, setCollapsed, onLogout, onRefresh, refreshing }: { view: string; collapsed: boolean; setCollapsed: (fn: (c: boolean) => boolean) => void; onLogout?: () => void; onRefresh?: () => void; refreshing?: boolean }) {
  const titles: Record<string, string> = { dashboard: 'Dashboard', clientes: 'Clientes', operaciones: 'Operaciones en vivo', servicios: 'Servicios', briefs: 'Briefs recibidos', facturacion: 'Facturación' };
  return (
    <div style={{ height: 58, borderBottom: '1px solid #ECECF3', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', background: '#fff', flexShrink: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button onClick={() => setCollapsed(c => !c)} title={collapsed ? 'Expandir sidebar' : 'Colapsar sidebar'}
          style={{ width: 32, height: 32, border: '1px solid #ECECF3', borderRadius: 8, background: '#F6F6FB', cursor: 'pointer', display: 'grid', placeItems: 'center', color: '#6B6B7A', flexShrink: 0 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#9696A6' }}>Admin</span>
        <span style={{ color: '#D1D1DC' }}>/</span>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#16161D' }}>{titles[view]}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {onRefresh && (
          <button onClick={onRefresh} disabled={refreshing} title="Recargar datos" style={{ height: 36, padding: '0 12px', border: '1px solid #ECECF3', borderRadius: 9, background: '#F6F6FB', cursor: refreshing ? 'default' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: 7, color: '#6B6B7A', fontFamily: 'inherit', fontSize: 12.5, fontWeight: 600 }}>
            {refreshing ? <Spinner size={14} color="#6B6B7A" /> : <Icon name="activity" size={14} />} Actualizar
          </button>
        )}
        <button style={{ width: 36, height: 36, border: '1px solid #ECECF3', borderRadius: 9, background: '#F6F6FB', cursor: 'pointer', display: 'grid', placeItems: 'center', color: '#6B6B7A', position: 'relative' }}>
          <Icon name="bell" size={16} />
          <span style={{ position: 'absolute', top: 7, right: 7, width: 7, height: 7, borderRadius: '50%', background: '#3BAA98', border: '1.5px solid #fff' }} />
        </button>
        <button onClick={onLogout} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '7px 13px', border: '1px solid #ECECF3', borderRadius: 9, background: '#F6F6FB', color: '#6B6B7A', fontFamily: 'inherit', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>
          <Icon name="eye" size={13} /> Salir
        </button>
      </div>
    </div>
  );
}

/* ══════════════ VIEWS ══════════════ */

/* DASHBOARD — 🟢 REAL (/api/staff/stats) */
function ViewDashboard({ clients, stats, loading, error }: { clients: ClientRow[]; stats: any; loading: boolean; error: string | null }) {
  const g = stats?.global || {};
  const activos = clients.filter(c => clientEstado(c) === 'activo' || clientEstado(c) === 'corriendo').length;
  const approvalRate = g.total_leads ? Math.round((g.total_approved / g.total_leads) * 100) : 0;

  const KPIS = [
    { label: 'Clientes', value: `${activos} / ${g.total_clients ?? clients.length}`, sub: 'con actividad', color: '#4F46E5' },
    { label: 'Leads totales', value: g.total_leads ?? '—', sub: `${g.total_approved ?? 0} aprobados`, color: '#3BAA98' },
    { label: 'Corridas activas', value: g.active_runs ?? 0, sub: `${g.total_runs ?? 0} históricas`, color: '#15A56A' },
    { label: 'Tasa aprobación', value: approvalRate + '%', sub: 'global', color: '#D97A06' },
  ];

  // "Actividad reciente" derived from per-client last_run_status (no activity feed endpoint yet).
  const recent = [...clients]
    .filter(c => c.last_run_status)
    .slice(0, 6)
    .map(c => {
      const st = c.last_run_status;
      const color = st === 'complete' ? '#15A56A' : st === 'error' ? '#E03E4C' : st === 'running' ? '#0EA5E9' : '#9696A6';
      return { text: `${shortName(c.email)} — última corrida: ${st}`, time: `${c.total_leads ?? 0} leads`, c: color };
    });

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, animation: 'admFade .35s ease both' }}>
      <div>
        <h1 style={{ fontSize: 24, margin: 0, marginBottom: 4, fontWeight: 800, letterSpacing: '-0.02em', color: '#16161D' }}>Resumen global</h1>
        <p style={{ margin: 0, fontSize: 14, color: '#6B6B7A' }}>Operación Landa LATAM · datos en vivo</p>
      </div>

      {error && <div style={{ padding: '12px 16px', background: '#FCE9EA', color: '#E03E4C', borderRadius: 12, fontSize: 13.5 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14 }}>
        {KPIS.map(k => (
          <Card key={k.label} style={{ padding: 18 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#9696A6', marginBottom: 12 }}>{k.label}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: '#16161D', letterSpacing: '-0.03em', lineHeight: 1 }}>{loading ? '…' : k.value}</div>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#9696A6', marginTop: 6 }}>{k.sub}</div>
          </Card>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.65fr 1fr', gap: 16 }}>
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #ECECF3', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#16161D' }}>Clientes y actividad</h3>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#9696A6' }}>{clients.length} registros</span>
          </div>
          {loading && <div style={{ padding: 30, textAlign: 'center' }}><Spinner /></div>}
          {!loading && clients.length === 0 && <div style={{ padding: 30, textAlign: 'center', fontSize: 13, color: '#B0B0BE' }}>No hay clientes registrados.</div>}
          {clients.slice(0, 6).map((c, i) => {
            const ec = ESTADO_CFG[clientEstado(c)];
            const ratio = c.total_leads ? Math.round(((c.approved_leads ?? 0) / c.total_leads) * 100) : 0;
            return (
              <div key={c.id} style={{ display: 'flex', alignItems: 'center', padding: '11px 20px', borderBottom: i < Math.min(clients.length, 6) - 1 ? '1px solid #F5F5FA' : 'none', gap: 12 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: '#F2F2F8', display: 'grid', placeItems: 'center', flex: 'none', color: '#9696A6' }}>
                  <Icon name="building" size={18} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 13.5, color: '#16161D', textTransform: 'capitalize', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{shortName(c.email)}</div>
                  <div style={{ fontSize: 11.5, color: '#9696A6', marginTop: 1 }}>{c.total_leads ?? 0} leads · {c.approved_leads ?? 0} aprobados</div>
                </div>
                <div style={{ width: 78, flex: 'none' }}>
                  <div style={{ height: 5, background: '#F2F2F8', borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ width: ratio + '%', height: '100%', background: '#15A56A', borderRadius: 999 }} />
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#15A56A', marginTop: 3, textAlign: 'right' }}>{ratio}%</div>
                </div>
                <Badge label={ec.label} color={ec.color} bg={ec.bg} />
              </div>
            );
          })}
        </Card>
        <Card style={{ padding: 20 }}>
          <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 700, color: '#16161D' }}>Actividad reciente</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
            {recent.length === 0 && <div style={{ fontSize: 13, color: '#B0B0BE' }}>Sin corridas registradas todavía.</div>}
            {recent.map((a, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: a.c, marginTop: 5, flex: 'none' }} />
                <div>
                  <div style={{ fontSize: 12.5, color: '#34343F', lineHeight: 1.4, textTransform: 'capitalize' }}>{a.text}</div>
                  <div style={{ fontSize: 11, color: '#9696A6', marginTop: 2 }}>{a.time}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

/* PROVISION CLIENT MODAL — 🟢 REAL (POST /api/staff/tenants/provision) */
function ProvisionClientModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({
    email: '', password: '', company_name: '', phone: '',
    agent_name: 'ARIA', company_brand: '', tono: 'amable',
    softseguros_username: '', softseguros_password: '',
    enable_cobranza: true,
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const set = (k: string, v: any) => setF(prev => ({ ...prev, [k]: v }));

  const submit = async () => {
    if (!f.email || !f.password) { setMsg('Email y contraseña son obligatorios'); return; }
    setBusy(true); setMsg(null);
    try {
      const payload: api.ProvisionTenantPayload = {
        email: f.email.trim(), password: f.password,
        company_name: f.company_name || undefined,
        phone: f.phone || undefined,
        enable_cobranza: f.enable_cobranza,
        voice_persona: {
          agent_name: f.agent_name || undefined,
          company_name: f.company_name || undefined,
          company_brand: f.company_brand || f.company_name || undefined,
          tono: f.tono || undefined,
        },
        softseguros_username: f.softseguros_username || undefined,
        softseguros_password: f.softseguros_password || undefined,
      };
      const r = await api.staffProvisionTenant(payload);
      setMsg(`✓ Cliente ${r.created ? 'creado' : 'actualizado'} (${r.user_id})`);
      setTimeout(onDone, 900);
    } catch (e: any) {
      setMsg('Error: ' + (e?.message || 'no se pudo crear'));
    } finally {
      setBusy(false);
    }
  };

  const inp: React.CSSProperties = { width: '100%', padding: '9px 11px', border: '1px solid #E3E3EC', borderRadius: 9, fontFamily: 'inherit', fontSize: 13.5, boxSizing: 'border-box' };
  const lbl: React.CSSProperties = { fontSize: 12, fontWeight: 600, color: '#6B6B7A', marginBottom: 4, display: 'block' };
  const Field = ({ label, k, type = 'text', ph }: { label: string; k: string; type?: string; ph?: string }) => (
    <div><label style={lbl}>{label}</label><input style={inp} type={type} placeholder={ph} value={(f as any)[k]} onChange={e => set(k, e.target.value)} /></div>
  );

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(20,20,30,0.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, animation: 'admFade .2s ease both' }}>
      <div onClick={e => e.stopPropagation()} style={{ background: '#fff', borderRadius: 16, padding: 26, width: 560, maxWidth: '92vw', maxHeight: '88vh', overflowY: 'auto', boxShadow: '0 24px 64px rgba(0,0,0,0.22)' }}>
        <h2 style={{ margin: 0, marginBottom: 4, fontSize: 20, fontWeight: 800, color: '#16161D' }}>Nuevo cliente</h2>
        <p style={{ margin: 0, marginBottom: 18, fontSize: 13, color: '#9696A6' }}>Crea la cuenta, la voz del asistente y los accesos en un solo paso.</p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <Field label="Email *" k="email" type="email" ph="cliente@empresa.com" />
          <Field label="Contraseña *" k="password" type="password" />
          <Field label="Empresa" k="company_name" ph="DPG Seguros" />
          <Field label="Teléfono" k="phone" ph="+57..." />
        </div>

        <div style={{ fontSize: 12, fontWeight: 700, color: '#4F46E5', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '6px 0 10px' }}>Voz del asistente</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <Field label="Nombre del asistente" k="agent_name" ph="ARIA" />
          <Field label="Marca (cómo se nombra)" k="company_brand" ph="DPG Seguros" />
          <Field label="Tono" k="tono" ph="amable" />
        </div>

        <div style={{ fontSize: 12, fontWeight: 700, color: '#4F46E5', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '6px 0 10px' }}>SoftSeguros (opcional)</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <Field label="Usuario SoftSeguros" k="softseguros_username" />
          <Field label="Contraseña SoftSeguros" k="softseguros_password" type="password" />
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13.5, color: '#16161D', marginBottom: 18, cursor: 'pointer' }}>
          <input type="checkbox" checked={f.enable_cobranza} onChange={e => set('enable_cobranza', e.target.checked)} />
          Habilitar cobranza por voz
        </label>

        {msg && <div style={{ padding: '10px 14px', borderRadius: 10, marginBottom: 14, fontSize: 13, background: msg.startsWith('✓') ? '#E7F6EF' : '#FCE9EA', color: msg.startsWith('✓') ? '#13875B' : '#E03E4C' }}>{msg}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button onClick={onClose} disabled={busy} style={{ padding: '9px 18px', border: '1px solid #E3E3EC', borderRadius: 10, background: '#fff', color: '#6B6B7A', fontFamily: 'inherit', fontSize: 13.5, fontWeight: 600, cursor: 'pointer' }}>Cancelar</button>
          <button onClick={submit} disabled={busy} style={{ padding: '9px 20px', border: 'none', borderRadius: 10, background: busy ? '#A5A0F0' : '#4F46E5', color: '#fff', fontFamily: 'inherit', fontSize: 13.5, fontWeight: 700, cursor: busy ? 'default' : 'pointer' }}>{busy ? 'Creando…' : 'Crear cliente'}</button>
        </div>
      </div>
    </div>
  );
}

/* CLIENTES — 🟢 REAL (clients + detail + sources + cobranza) */
function ViewClientes({ clients, loading, error, reload }: { clients: ClientRow[]; loading: boolean; error: string | null; reload: () => void }) {
  const [filtro, setFiltro] = useState<string | null>(null);
  const [selected, setSelected] = useState<ClientRow | null>(null);
  const [detailTab, setDetailTab] = useState('info');
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [cobranzaBusy, setCobranzaBusy] = useState(false);
  const [fuentes, setFuentes] = useState<string[]>([]);
  const [fuentesBusy, setFuentesBusy] = useState(false);
  const [fuentesMsg, setFuentesMsg] = useState<string | null>(null);
  const [provisionOpen, setProvisionOpen] = useState(false);

  const openClient = async (c: ClientRow) => {
    setSelected(c); setDetailTab('info'); setDetail(null); setDetailLoading(true); setFuentesMsg(null);
    try {
      const d = await api.staffGetClientDetail(c.id);
      setDetail(d);
      setFuentes(d?.fuentes_habilitadas || []);
    } catch {
      setDetail({ _error: true });
    } finally {
      setDetailLoading(false);
    }
  };

  const toggleCobranza = async () => {
    if (!selected) return;
    setCobranzaBusy(true);
    try {
      const enabled = !!detail?.cobranza_enabled;
      if (enabled) await api.staffDisableCobranza(selected.id);
      else await api.staffEnableCobranza(selected.id);
      setDetail((d: any) => ({ ...d, cobranza_enabled: !enabled }));
    } catch (e: any) {
      alert('No se pudo cambiar cobranza: ' + (e?.message || ''));
    } finally {
      setCobranzaBusy(false);
    }
  };

  const toggleFuente = (id: string) => {
    setFuentes(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };
  const saveFuentes = async () => {
    if (!selected) return;
    setFuentesBusy(true); setFuentesMsg(null);
    try {
      await api.staffUpdateClientSources(selected.id, fuentes);
      setFuentesMsg('Fuentes guardadas ✓');
    } catch (e: any) {
      setFuentesMsg('Error: ' + (e?.message || ''));
    } finally {
      setFuentesBusy(false);
    }
  };

  const filtered = filtro ? clients.filter(c => clientEstado(c) === filtro) : clients;
  const FILTROS: [string | null, string][] = [[null, 'Todos'], ['corriendo', 'Corriendo'], ['activo', 'Con actividad'], ['inactivo', 'Sin actividad'], ['error', 'Con error']];

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, animation: 'admFade .35s ease both' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ fontSize: 24, margin: 0, marginBottom: 4, fontWeight: 800, letterSpacing: '-0.02em', color: '#16161D' }}>Clientes</h1>
          <p style={{ margin: 0, fontSize: 14, color: '#6B6B7A' }}>{clients.length} clientes registrados</p>
        </div>
        <button onClick={() => setProvisionOpen(true)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '9px 16px', border: 'none', borderRadius: 10, background: '#4F46E5', color: '#fff', fontFamily: 'inherit', fontSize: 13.5, fontWeight: 700, cursor: 'pointer' }}>
          <Icon name="plus" size={16} /> Nuevo cliente
        </button>
      </div>
      {provisionOpen && <ProvisionClientModal onClose={() => setProvisionOpen(false)} onDone={() => { setProvisionOpen(false); reload(); }} />}
      <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
        {FILTROS.map(([v, l]) => (
          <button key={l} onClick={() => setFiltro(v === filtro ? null : v)} style={{ padding: '5px 13px', border: '1px solid ' + (filtro === v ? '#4F46E5' : '#E3E3EC'), borderRadius: 999, background: filtro === v ? '#EEEDFC' : '#fff', color: filtro === v ? '#4F46E5' : '#6B6B7A', fontFamily: 'inherit', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' }}>
            {l}{v === null && <span style={{ background: '#4F46E5', color: '#fff', borderRadius: 999, padding: '1px 7px', fontSize: 11, marginLeft: 5 }}>{clients.length}</span>}
          </button>
        ))}
      </div>

      {error && <div style={{ padding: '12px 16px', background: '#FCE9EA', color: '#E03E4C', borderRadius: 12, fontSize: 13.5 }}>{error}</div>}

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#FAFAFC', borderBottom: '1px solid #ECECF3' }}>
                {['Cliente', 'Estado', 'Leads', 'Aprobados', 'Corridas', ''].map(h => (
                  <th key={h} style={{ padding: '10px 18px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: '#9696A6', textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} style={{ padding: 30, textAlign: 'center' }}><Spinner /></td></tr>}
              {!loading && filtered.length === 0 && <tr><td colSpan={6} style={{ padding: 30, textAlign: 'center', fontSize: 13, color: '#B0B0BE' }}>Sin clientes en este filtro.</td></tr>}
              {filtered.map(c => {
                const ec = ESTADO_CFG[clientEstado(c)];
                return (
                  <tr key={c.id} onClick={() => openClient(c)} style={{ borderBottom: '1px solid #F5F5FA', cursor: 'pointer', transition: 'background .1s' }} onMouseEnter={e => e.currentTarget.style.background = '#F9F9FF'} onMouseLeave={e => e.currentTarget.style.background = ''}>
                    <td style={{ padding: '14px 18px' }}>
                      <div style={{ fontWeight: 700, fontSize: 13.5, color: '#16161D', textTransform: 'capitalize' }}>{shortName(c.email)}</div>
                      <div style={{ fontSize: 12, color: '#9696A6', marginTop: 2 }}>{c.email}</div>
                    </td>
                    <td style={{ padding: '14px 18px' }}><Badge label={ec.label} color={ec.color} bg={ec.bg} /></td>
                    <td style={{ padding: '14px 18px', fontSize: 14, fontWeight: 700, color: '#16161D' }}>{c.total_leads ?? 0}</td>
                    <td style={{ padding: '14px 18px', fontSize: 14, fontWeight: 700, color: '#15A56A' }}>{c.approved_leads ?? 0}</td>
                    <td style={{ padding: '14px 18px', fontSize: 13, color: '#6B6B7A' }}>{c.total_runs ?? 0}</td>
                    <td style={{ padding: '14px 18px', color: '#C0C0CC' }}><Icon name="arrow" size={15} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Client detail modal */}
      {selected && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 300, background: 'rgba(20,20,50,.45)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }} onClick={() => { setSelected(null); reload(); }}>
          <div onClick={e => e.stopPropagation()} style={{ background: '#fff', borderRadius: 20, width: '100%', maxWidth: 620, maxHeight: '90vh', overflowY: 'auto', boxShadow: '0 24px 60px -20px rgba(20,20,70,.38)', animation: 'admFade .25s ease both', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '22px 26px', borderBottom: '1px solid #ECECF3', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexShrink: 0 }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: 19, color: '#16161D', letterSpacing: '-0.02em', textTransform: 'capitalize' }}>{shortName(selected.email)}</div>
                <div style={{ fontSize: 13, color: '#9696A6', marginTop: 4 }}>{selected.email}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Badge label={ESTADO_CFG[clientEstado(selected)].label} color={ESTADO_CFG[clientEstado(selected)].color} bg={ESTADO_CFG[clientEstado(selected)].bg} />
                <button onClick={() => { setSelected(null); reload(); }} style={{ width: 32, height: 32, border: '1px solid #ECECF3', borderRadius: 8, background: 'transparent', cursor: 'pointer', display: 'grid', placeItems: 'center', color: '#9696A6' }}>✕</button>
              </div>
            </div>
            <div style={{ display: 'flex', borderBottom: '1px solid #ECECF3', padding: '0 26px', flexShrink: 0 }}>
              {[['info', 'Resumen'], ['fuentes', 'Fuentes'], ['cobranza', 'Cobranza']].map(([id, label]) => (
                <button key={id} onClick={() => setDetailTab(id)} style={{ padding: '12px 16px', border: 'none', borderBottom: detailTab === id ? '2px solid #4F46E5' : '2px solid transparent', background: 'transparent', color: detailTab === id ? '#4F46E5' : '#6B6B7A', fontFamily: 'inherit', fontWeight: detailTab === id ? 700 : 500, fontSize: 13.5, cursor: 'pointer', marginBottom: -1 }}>{label}</button>
              ))}
            </div>
            <div style={{ flex: 1, padding: 26, overflowY: 'auto', minHeight: 200 }}>
              {detailLoading && <div style={{ padding: 30, textAlign: 'center' }}><Spinner /></div>}
              {!detailLoading && detail?._error && <div style={{ padding: 20, background: '#FCE9EA', color: '#E03E4C', borderRadius: 12, fontSize: 13.5 }}>No se pudo cargar el detalle del cliente.</div>}

              {!detailLoading && detail && !detail._error && detailTab === 'info' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
                    {[{ l: 'Leads', v: detail.total_leads ?? 0, c: '#4F46E5' }, { l: 'Aprobados', v: detail.approved_leads ?? 0, c: '#15A56A' }, { l: 'Corridas', v: detail.total_runs ?? 0, c: '#3BAA98' }].map(k => (
                      <div key={k.l} style={{ padding: '14px 16px', background: '#F6F6FB', borderRadius: 12, border: '1px solid #ECECF3' }}>
                        <div style={{ fontSize: 11, color: '#9696A6', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 700 }}>{k.l}</div>
                        <div style={{ fontSize: 22, fontWeight: 800, color: k.c }}>{k.v}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ padding: 16, background: '#F6F6FB', borderRadius: 12, border: '1px solid #ECECF3' }}>
                    <div style={{ fontSize: 11, color: '#9696A6', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 700 }}>Pipeline de agentes</div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {['Buscador', 'Scraper', 'Analista', 'Redactor'].map((ag, i) => (
                        <React.Fragment key={ag}>
                          <div style={{ flex: 1, padding: '10px 8px', background: '#EEEDFC', borderRadius: 9, textAlign: 'center' }}>
                            <div style={{ fontSize: 11.5, fontWeight: 700, color: '#4F46E5' }}>{ag}</div>
                          </div>
                          {i < 3 && <div style={{ display: 'flex', alignItems: 'center', color: '#C0C0CC', fontSize: 16 }}>→</div>}
                        </React.Fragment>
                      ))}
                    </div>
                    <div style={{ fontSize: 12, color: '#9696A6', marginTop: 10 }}>Agentes runtime configurados: <strong style={{ color: '#16161D' }}>{detail.runtime_pipeline_agents ?? 0}</strong></div>
                  </div>
                  {detail.last_run_status && <div style={{ fontSize: 13, color: '#6B6B7A' }}>Última corrida: <strong style={{ color: '#16161D' }}>{detail.last_run_status}</strong></div>}
                </div>
              )}

              {!detailLoading && detail && !detail._error && detailTab === 'fuentes' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <p style={{ margin: 0, fontSize: 13.5, color: '#6B6B7A', lineHeight: 1.6 }}>Activa las fuentes de descubrimiento para este cliente. Afecta qué leads encontrarán sus agentes.</p>
                  {FUENTES.map(f => {
                    const on = fuentes.includes(f.id);
                    return (
                      <div key={f.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 18px', background: '#F6F6FB', borderRadius: 12, border: on ? '1.5px solid ' + f.color + '55' : '1px solid #ECECF3', transition: 'border-color .15s' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <div style={{ width: 40, height: 40, borderRadius: 11, background: on ? f.color + '18' : '#ECECF3', color: on ? f.color : '#B0B0BE', display: 'grid', placeItems: 'center' }}>
                            <Icon name="globe" size={18} />
                          </div>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: 14, color: on ? '#16161D' : '#6B6B7A' }}>{f.label}</div>
                            <div style={{ fontSize: 12, color: '#9696A6', marginTop: 2 }}>{f.desc}</div>
                          </div>
                        </div>
                        <Toggle on={on} onChange={() => toggleFuente(f.id)} />
                      </div>
                    );
                  })}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4 }}>
                    <button onClick={saveFuentes} disabled={fuentesBusy} style={{ padding: '10px 18px', background: '#4F46E5', color: '#fff', border: 'none', borderRadius: 10, fontFamily: 'inherit', fontWeight: 700, fontSize: 13.5, cursor: fuentesBusy ? 'default' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: 8, opacity: fuentesBusy ? 0.7 : 1 }}>
                      {fuentesBusy ? <Spinner size={14} color="#fff" /> : <Icon name="check" size={15} />} Guardar fuentes
                    </button>
                    {fuentesMsg && <span style={{ fontSize: 13, color: fuentesMsg.startsWith('Error') ? '#E03E4C' : '#15A56A', fontWeight: 600 }}>{fuentesMsg}</span>}
                  </div>
                </div>
              )}

              {!detailLoading && detail && !detail._error && detailTab === 'cobranza' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 20px', background: '#F6F6FB', borderRadius: 12, border: '1px solid #ECECF3' }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 15, color: '#16161D', marginBottom: 4 }}>Agente de Cobranza de Voz</div>
                      <div style={{ fontSize: 13, color: '#6B6B7A', lineHeight: 1.5 }}>Habilita llamadas automáticas para deudores de este cliente.</div>
                    </div>
                    {cobranzaBusy ? <Spinner color="#3BAA98" /> : (
                      <div onClick={toggleCobranza} style={{ width: 48, height: 28, borderRadius: 999, background: detail.cobranza_enabled ? '#3BAA98' : '#D1D1DC', cursor: 'pointer', position: 'relative', transition: 'background .2s', flexShrink: 0 }}>
                        <div style={{ width: 22, height: 22, borderRadius: '50%', background: '#fff', position: 'absolute', top: 3, left: detail.cobranza_enabled ? 23 : 3, transition: 'left .2s', boxShadow: '0 1px 3px rgba(0,0,0,.2)' }} />
                      </div>
                    )}
                  </div>
                  {detail.cobranza_enabled && (
                    <div style={{ padding: '16px 18px', background: '#E4F6F3', borderRadius: 12, border: '1px solid #3BAA9844' }}>
                      <div style={{ fontSize: 13, color: '#1A6B5A', lineHeight: 1.6 }}>
                        <strong>Activo</strong> — El agente de voz puede iniciar llamadas a los deudores configurados. Máx. 1 contacto por día (Ley 2300 de 2023).
                      </div>
                    </div>
                  )}
                  <div style={{ padding: '16px 18px', background: '#FCF1E0', borderRadius: 12, border: '1px solid #D97A0633' }}>
                    <div style={{ fontSize: 12.5, color: '#D97A06', lineHeight: 1.5 }}>⚠️ <strong>Ley 2300:</strong> Máximo un contacto por deudor por día. El sistema previene llamadas duplicadas automáticamente.</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* OPERACIONES — 🟢 REAL (/api/staff/agents/active + clients) */
function ViewOperaciones({ clients }: { clients: ClientRow[] }) {
  const [active, setActive] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setActive(await api.staffGetActiveAgents()); }
    catch { setActive({ per_client_active: [] }); }
    finally { setLoading(false); }
  }, []);
  // Poll every 5s for live operations.
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const activeIds = new Set((active?.per_client_active || []).map((p: any) => p.client_id));
  const running = clients.filter(c => activeIds.has(c.id));
  const idle = clients.filter(c => !activeIds.has(c.id));

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, animation: 'admFade .35s ease both' }}>
      <div>
        <h1 style={{ fontSize: 24, margin: 0, marginBottom: 4, fontWeight: 800, letterSpacing: '-0.02em', color: '#16161D' }}>Operaciones en vivo</h1>
        <p style={{ margin: 0, fontSize: 14, color: '#6B6B7A' }}>{running.length} cliente(s) con agentes corriendo ahora · actualiza cada 5s</p>
      </div>

      {/* Agent role status (pipeline registry — always on at the platform level) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14 }}>
        {Object.entries(ROLE_CFG).map(([key, r]) => (
          <Card key={key} style={{ padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ width: 38, height: 38, borderRadius: 11, background: r.soft, color: r.color, display: 'grid', placeItems: 'center' }}>
                <Icon name={key === 'buscador' ? 'search' : key === 'scraper' ? 'arrow' : key === 'analista' ? 'check' : 'send'} size={19} stroke={1.9} />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: running.length ? r.color : '#D1D1DC', animation: running.length ? 'admPulse 2s infinite' : 'none', color: r.color }} />
                <span style={{ fontSize: 11, fontWeight: 700, color: running.length ? r.color : '#9696A6' }}>{running.length ? 'ON' : 'IDLE'}</span>
              </div>
            </div>
            <div style={{ fontWeight: 800, fontSize: 15, color: '#16161D' }}>{r.name}</div>
            <div style={{ fontSize: 12, color: '#9696A6', marginTop: 4, minHeight: 32, lineHeight: 1.4 }}>{running.length ? r.tasks[0] : 'En espera de corridas'}</div>
          </Card>
        ))}
      </div>

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #ECECF3', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#16161D' }}>Agentes corriendo</h3>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#9696A6' }}>En vivo</span>
        </div>
        {loading && <div style={{ padding: 30, textAlign: 'center' }}><Spinner /></div>}
        {!loading && running.length === 0 && <div style={{ padding: 30, textAlign: 'center', fontSize: 13, color: '#B0B0BE' }}>Ningún agente corriendo ahora mismo. {idle.length} cliente(s) en espera.</div>}
        {running.map((c, i) => {
          const roleKeys = Object.keys(ROLE_CFG);
          const activeRole = ROLE_CFG[roleKeys[i % roleKeys.length]];
          return (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', padding: '13px 20px', borderBottom: i < running.length - 1 ? '1px solid #F5F5FA' : 'none', gap: 14 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: '#F2F2F8', display: 'grid', placeItems: 'center', flex: 'none', color: '#9696A6' }}>
                <Icon name="building" size={18} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13.5, color: '#16161D', textTransform: 'capitalize' }}>{shortName(c.email)}</div>
                <div style={{ fontSize: 12, color: activeRole.color, marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: activeRole.color, animation: 'admPulse 1.8s infinite', color: activeRole.color }} />
                  Pipeline activo
                </div>
              </div>
              <div style={{ textAlign: 'right', flex: 'none' }}>
                <div style={{ fontSize: 16, fontWeight: 800, color: '#16161D' }}>{c.total_leads ?? 0}</div>
                <div style={{ fontSize: 11, color: '#9696A6' }}>leads</div>
              </div>
            </div>
          );
        })}
      </Card>
    </div>
  );
}

/* SERVICIOS — 🟢 REAL para Cobranza, 🟡 DEMO para el resto */
function ViewServicios({ clients }: { clients: ClientRow[] }) {
  const [sel, setSel] = useState<string | null>(clients[0]?.id || null);
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  // Demo toggles (no backend) persisted only locally.
  const [demoSvcs, setDemoSvcs] = useState<Record<string, Record<string, boolean>>>(() => {
    try { return JSON.parse(localStorage.getItem('landa_admin_demo_svcs') || '{}'); } catch { return {}; }
  });

  useEffect(() => { if (!sel && clients[0]) setSel(clients[0].id); }, [clients, sel]);

  const loadDetail = useCallback(async (id: string) => {
    setLoading(true); setDetail(null);
    try { setDetail(await api.staffGetClientDetail(id)); }
    catch { setDetail({ _error: true }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (sel) loadDetail(sel); }, [sel, loadDetail]);

  const client = clients.find(c => c.id === sel);

  const toggleReal = async () => {
    if (!sel) return;
    setBusy(true);
    try {
      const enabled = !!detail?.cobranza_enabled;
      if (enabled) await api.staffDisableCobranza(sel); else await api.staffEnableCobranza(sel);
      setDetail((d: any) => ({ ...d, cobranza_enabled: !enabled }));
    } catch (e: any) { alert('Error: ' + (e?.message || '')); }
    finally { setBusy(false); }
  };
  const toggleDemo = (svcId: string) => {
    if (!sel) return;
    setDemoSvcs(prev => {
      const nx = { ...prev, [sel]: { ...(prev[sel] || {}), [svcId]: !(prev[sel]?.[svcId]) } };
      localStorage.setItem('landa_admin_demo_svcs', JSON.stringify(nx));
      return nx;
    });
  };

  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, animation: 'admFade .35s ease both' }}>
      <div>
        <h1 style={{ fontSize: 24, margin: 0, marginBottom: 4, fontWeight: 800, letterSpacing: '-0.02em', color: '#16161D' }}>Servicios</h1>
        <p style={{ margin: 0, fontSize: 14, color: '#6B6B7A' }}>Activa o desactiva módulos por cliente. Solo <strong>Cobranza de Voz</strong> está conectada al backend; el resto son demo.</p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '256px 1fr', gap: 18, alignItems: 'start' }}>
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #ECECF3', fontSize: 10.5, fontWeight: 700, letterSpacing: '0.09em', textTransform: 'uppercase', color: '#9696A6' }}>Cliente</div>
          <div style={{ maxHeight: 460, overflowY: 'auto' }}>
            {clients.length === 0 && <div style={{ padding: 20, fontSize: 13, color: '#B0B0BE' }}>Sin clientes.</div>}
            {clients.map(c => {
              const active = c.id === sel;
              const ec = ESTADO_CFG[clientEstado(c)];
              return (
                <div key={c.id} onClick={() => setSel(c.id)} style={{ padding: '11px 16px', cursor: 'pointer', borderBottom: '1px solid #F5F5FA', background: active ? '#EEEDFC' : 'transparent', borderLeft: active ? '3px solid #4F46E5' : '3px solid transparent', transition: 'all .12s' }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#F6F6FB'; }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: active ? '#4F46E5' : '#16161D', textTransform: 'capitalize' }}>{shortName(c.email)}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                    <Badge label={ec.label} color={ec.color} bg={ec.bg} />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Card style={{ padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: 16, color: '#16161D', textTransform: 'capitalize' }}>{client ? shortName(client.email) : '—'}</div>
                <div style={{ fontSize: 13, color: '#9696A6', marginTop: 2 }}>{client?.email}</div>
              </div>
              {loading && <Spinner />}
            </div>
          </Card>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {SERVICIOS_CATALOGO.map(svc => {
              const on = svc.real ? !!detail?.cobranza_enabled : !!(sel && demoSvcs[sel]?.[svc.id]);
              return (
                <Card key={svc.id} style={{ padding: 20, border: on ? `1.5px solid ${svc.color}55` : '1px solid #ECECF3', transition: 'border-color .2s' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                      <div style={{ width: 44, height: 44, borderRadius: 13, background: on ? svc.bg : '#F2F2F8', display: 'grid', placeItems: 'center', color: on ? svc.color : '#B0B0BE', transition: 'all .2s', flexShrink: 0 }}>
                        <Icon name={svc.icon} size={20} />
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ fontWeight: 700, fontSize: 14, color: on ? '#16161D' : '#6B6B7A' }}>{svc.nombre}</span>
                          {!svc.real && <DemoTag />}
                        </div>
                        <div style={{ fontSize: 11.5, color: '#9696A6', marginTop: 2, lineHeight: 1.4 }}>{svc.desc}</div>
                      </div>
                    </div>
                    {svc.real && busy ? <Spinner color="#3BAA98" /> : <Toggle on={on} onChange={() => svc.real ? toggleReal() : toggleDemo(svc.id)} disabled={svc.real && (loading || !!detail?._error)} />}
                  </div>
                  <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #F5F5FA', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: on ? svc.color : '#9696A6' }}>{on ? 'Activo' : 'Inactivo'}</span>
                    <span style={{ fontSize: 11, color: '#9696A6' }}>{svc.real ? 'Conectado' : 'Demo (local)'}</span>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

/* BRIEFS — 🟡 DEMO (no backend) */
const DEMO_BRIEFS = [
  { id: 1, empresa: 'Laboratorios Vita', contacto: 'Sandra Ruiz', email: 'sruiz@labosvita.co', recibido: 'hace 20 min', etapa: 'nuevo', cta: 'Agendar demo', campos: 34 },
  { id: 2, empresa: 'Import & Export Bogotá', contacto: 'Diego Vargas', email: 'dvargas@iebog.co', recibido: 'hace 2 horas', etapa: 'nuevo', cta: 'Captar registros', campos: 28 },
  { id: 3, empresa: 'Ferretería Central Norte', contacto: 'Jaime Ospina', email: 'jaime@fercentral.co', recibido: 'ayer', etapa: 'revision', cta: 'Captar leads', campos: 36 },
  { id: 4, empresa: 'Clínica Santa Cruz', contacto: 'Patricia Mora', email: 'pmora@clisantacruz.co', recibido: 'hace 3 días', etapa: 'produccion', cta: 'Captar leads', campos: 40 },
  { id: 5, empresa: 'Muebles Horizonte', contacto: 'Luis Torres', email: 'ltorres@muebleshorizonte.co', recibido: 'hace 5 días', etapa: 'publicado', cta: 'Venta online', campos: 38 },
];
const BRIEF_STAGES = [
  { id: 'nuevo', label: 'Nuevo', color: '#0EA5E9', bg: '#E8F6FD' },
  { id: 'revision', label: 'En revisión', color: '#D97A06', bg: '#FCF1E0' },
  { id: 'produccion', label: 'En producción', color: '#4F46E5', bg: '#EEEDFC' },
  { id: 'publicado', label: 'Publicado', color: '#15A56A', bg: '#E6F6EE' },
];

function ViewBriefs() {
  const [stages, setStages] = useState<Record<number, string>>(() => {
    const d: Record<number, string> = {}; DEMO_BRIEFS.forEach(b => { d[b.id] = b.etapa; }); return d;
  });
  const move = (id: number, etapa: string) => setStages(s => ({ ...s, [id]: etapa }));
  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, animation: 'admFade .35s ease both' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <h1 style={{ fontSize: 24, margin: 0, fontWeight: 800, letterSpacing: '-0.02em', color: '#16161D' }}>Briefs recibidos</h1>
            <DemoTag note="No existe backend de briefs todavía — datos de demostración." />
          </div>
          <p style={{ margin: 0, fontSize: 14, color: '#6B6B7A' }}>Formularios de onboarding. <strong>Sin backend conectado</strong> — vista de demostración.</p>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, alignItems: 'start' }}>
        {BRIEF_STAGES.map(st => {
          const cards = DEMO_BRIEFS.filter(b => stages[b.id] === st.id);
          return (
            <div key={st.id} style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: st.color }} />
                  <span style={{ fontWeight: 800, fontSize: 13, color: '#16161D' }}>{st.label}</span>
                </div>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#9696A6' }}>{cards.length}</span>
              </div>
              {cards.length === 0 && <div style={{ border: '1.5px dashed #E3E3EC', borderRadius: 12, padding: '20px 12px', textAlign: 'center', fontSize: 12, color: '#B0B0BE' }}>Sin briefs</div>}
              {cards.map(b => {
                const idx = BRIEF_STAGES.findIndex(s => s.id === stages[b.id]);
                const next = BRIEF_STAGES[idx + 1];
                return (
                  <Card key={b.id} style={{ padding: 15, borderLeft: `3px solid ${st.color}` }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                      <div style={{ fontWeight: 700, fontSize: 13.5, color: '#16161D', lineHeight: 1.3 }}>{b.empresa}</div>
                      <span style={{ fontSize: 10, fontWeight: 700, color: st.color, background: st.bg, borderRadius: 6, padding: '2px 6px', flexShrink: 0, whiteSpace: 'nowrap' }}>{b.campos} campos</span>
                    </div>
                    <div style={{ fontSize: 12, color: '#6B6B7A', marginTop: 4 }}>{b.contacto}</div>
                    <div style={{ fontSize: 11.5, color: '#9696A6', marginTop: 1 }}>{b.email}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 9 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#4F46E5', background: '#EEEDFC', borderRadius: 6, padding: '2px 7px' }}>{b.cta}</span>
                      <span style={{ fontSize: 11, color: '#B0B0BE', marginLeft: 'auto' }}>{b.recibido}</span>
                    </div>
                    {next && (
                      <button onClick={() => move(b.id, next.id)} style={{ marginTop: 11, width: '100%', fontSize: 11.5, fontWeight: 700, color: next.color, background: next.bg, border: 'none', borderRadius: 8, padding: '6px 0', cursor: 'pointer', fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                        Mover a {next.label} <Icon name="arrow" size={13} />
                      </button>
                    )}
                  </Card>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* FACTURACIÓN — 🟡 DEMO (no backend) */
const DEMO_MRR = [
  { mes: 'Ene', val: 18200000 }, { mes: 'Feb', val: 21500000 }, { mes: 'Mar', val: 24100000 },
  { mes: 'Abr', val: 25800000 }, { mes: 'May', val: 27200000 }, { mes: 'Jun', val: 27300000 },
];
const DEMO_INVOICES = [
  { id: 'INV-041', cliente: 'DPG Seguros', monto: 8500000, estado: 'pagado', vence: '2026-06-01' },
  { id: 'INV-040', cliente: 'Constructora Vértice', monto: 4800000, estado: 'pagado', vence: '2026-06-01' },
  { id: 'INV-039', cliente: 'AgroExport Caribe', monto: 4800000, estado: 'pendiente', vence: '2026-06-20' },
  { id: 'INV-037', cliente: 'Distribuidora El Cóndor', monto: 2200000, estado: 'vencido', vence: '2026-05-25' },
];
const INV_ESTADO: Record<string, { color: string; bg: string; label: string }> = { pagado: { color: '#15A56A', bg: '#E6F6EE', label: 'Pagado' }, pendiente: { color: '#D97A06', bg: '#FCF1E0', label: 'Pendiente' }, vencido: { color: '#E03E4C', bg: '#FCE9EA', label: 'Vencido' } };
function fmtCOP(n: number) { if (n === 0) return '—'; if (n >= 1000000) return '$' + (n / 1000000).toFixed(1) + 'M'; return '$' + n.toLocaleString('es-CO'); }

function ViewFacturacion() {
  const max = Math.max(...DEMO_MRR.map(d => d.val));
  return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 20, animation: 'admFade .35s ease both' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <h1 style={{ fontSize: 24, margin: 0, fontWeight: 800, letterSpacing: '-0.02em', color: '#16161D' }}>Facturación</h1>
        <DemoTag note="No existe módulo de facturación en el backend — datos de demostración." />
      </div>
      <p style={{ margin: '-12px 0 0', fontSize: 14, color: '#6B6B7A' }}>Junio 2026 · <strong>Sin backend conectado</strong> — vista de demostración.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14 }}>
        {[
          { label: 'MRR Activo (demo)', value: fmtCOP(DEMO_MRR[DEMO_MRR.length - 1].val), color: '#3BAA98' },
          { label: 'Cobrado (demo)', value: fmtCOP(DEMO_INVOICES.filter(i => i.estado === 'pagado').reduce((s, i) => s + i.monto, 0)), color: '#15A56A' },
          { label: 'Vencidas (demo)', value: DEMO_INVOICES.filter(i => i.estado === 'vencido').length, color: '#E03E4C' },
        ].map(k => (
          <Card key={k.label} style={{ padding: 20 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#9696A6', marginBottom: 10 }}>{k.label}</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: k.color, letterSpacing: '-0.03em' }}>{k.value}</div>
          </Card>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16 }}>
        <Card style={{ padding: 22 }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: '#16161D', margin: '0 0 20px' }}>MRR últimos 6 meses</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', height: 90 }}>
            {DEMO_MRR.map(d => (
              <div key={d.mes} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
                <div style={{ width: '100%', background: '#F2F2F8', borderRadius: '4px 4px 0 0', overflow: 'hidden', height: 52, display: 'flex', alignItems: 'flex-end' }}>
                  <div style={{ width: '100%', height: (d.val / max * 100) + '%', background: d.mes === 'Jun' ? '#3BAA98' : '#D1D1DC', borderRadius: '3px 3px 0 0' }} />
                </div>
                <div style={{ fontSize: 11, fontWeight: 700, color: d.mes === 'Jun' ? '#3BAA98' : '#9696A6' }}>{d.mes}</div>
              </div>
            ))}
          </div>
        </Card>
        <Card style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #ECECF3' }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: '#16161D', margin: 0 }}>Facturas (demo)</h3>
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#FAFAFC', borderBottom: '1px solid #ECECF3' }}>
                {['#', 'Cliente', 'Monto', 'Vence', 'Estado'].map(h => (
                  <th key={h} style={{ padding: '9px 16px', textAlign: 'left', fontSize: 10, fontWeight: 700, letterSpacing: '0.09em', textTransform: 'uppercase', color: '#9696A6' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DEMO_INVOICES.map((inv, i) => {
                const ec = INV_ESTADO[inv.estado];
                return (
                  <tr key={inv.id} style={{ borderBottom: i < DEMO_INVOICES.length - 1 ? '1px solid #F5F5FA' : 'none' }}>
                    <td style={{ padding: '10px 16px', fontSize: 11, color: '#9696A6' }}>{inv.id}</td>
                    <td style={{ padding: '10px 16px', fontWeight: 700, color: '#16161D' }}>{inv.cliente}</td>
                    <td style={{ padding: '10px 16px', fontWeight: 700, color: '#16161D' }}>{fmtCOP(inv.monto)}</td>
                    <td style={{ padding: '10px 16px', color: '#9696A6', fontSize: 12 }}>{inv.vence}</td>
                    <td style={{ padding: '10px 16px' }}><Badge label={ec.label} color={ec.color} bg={ec.bg} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

/* ─── ADMIN APP SHELL ─── */
export function AdminPanel({ onExit }: { onExit?: () => void }) {
  const [view, setView] = useState('dashboard');
  const [collapsed, setCollapsed] = useState(false);
  const handleExit = onExit || (() => { api.logout(); window.location.reload(); });
  const { clients, stats, loading, error, reload } = useStaffData();
  const leadsTotal = stats?.global?.total_leads ?? clients.reduce((s, c) => s + (c.total_leads ?? 0), 0);

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', background: '#F6F6FB', fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif", WebkitFontSmoothing: 'antialiased' }}>
      <style>{`
        @keyframes admPulse { 0%,100%{opacity:1;box-shadow:0 0 0 0 currentColor}70%{box-shadow:0 0 0 5px transparent} }
        @keyframes admFade { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
        @keyframes admSpin { to { transform: rotate(360deg); } }
      `}</style>
      <AdminSidebar view={view} setView={setView} collapsed={collapsed} onLogout={handleExit} leadsHoy={leadsTotal} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <AdminTopbar view={view} collapsed={collapsed} setCollapsed={setCollapsed} onLogout={handleExit} onRefresh={reload} refreshing={loading} />
        <div style={{ flex: 1, overflowY: 'auto', background: '#F6F6FB' }}>
          {view === 'dashboard' && <ViewDashboard clients={clients} stats={stats} loading={loading} error={error} />}
          {view === 'clientes' && <ViewClientes clients={clients} loading={loading} error={error} reload={reload} />}
          {view === 'operaciones' && <ViewOperaciones clients={clients} />}
          {view === 'servicios' && <ViewServicios clients={clients} />}
          {view === 'briefs' && <ViewBriefs />}
          {view === 'facturacion' && <ViewFacturacion />}
        </div>
      </div>
    </div>
  );
}

export default AdminPanel;
