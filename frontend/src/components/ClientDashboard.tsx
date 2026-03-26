import { useState, useEffect, useCallback, useRef } from 'react';
import { useOfficeStore } from '../store/officeStore';
import { LeadDossierModal } from './LeadDossierModal';

const API = '';

// Inject keyframes once
if (typeof document !== 'undefined' && !document.getElementById('cd-styles')) {
  const s = document.createElement('style');
  s.id = 'cd-styles';
  s.textContent = `@keyframes pulse { 0%,100%{opacity:1;box-shadow:0 0 6px #78dce8} 50%{opacity:0.4;box-shadow:0 0 2px #78dce8} }`;
  document.head.appendChild(s);
}

type HitlStatus = 'pending' | 'approved' | 'rejected';

interface ApiLead {
  _id: string;
  company_name: string;
  url: string;
  score: number | null;
  email: string | null;
  city: string | null;
  hitl_status: HitlStatus;
  expediente_json: Record<string, unknown> | null;
  created_at: string | null;
}

interface ToastItem {
  id: string;
  message: string;
  type: 'approve' | 'reject';
  undoFn?: () => void;
}

// ─── Tokens ────────────────────────────────────────────────────────────────────
const C = {
  bg:        '#0d0d18',
  s0:        '#12121d',
  s1:        '#1b1a26',
  s2:        '#22212e',
  s3:        '#2c2b3a',
  s4:        '#343440',
  text:      '#e3e0f1',
  muted:     '#8a8a9a',
  faint:     'rgba(227,224,241,0.3)',
  cyan:      '#78dce8',
  cyanBg:    'rgba(120,220,232,0.08)',
  cyanBdr:   'rgba(120,220,232,0.2)',
  purple:    '#ab9df2',
  purpleBg:  'rgba(171,157,242,0.08)',
  green:     '#a9dc76',
  greenBg:   'rgba(169,220,118,0.08)',
  pink:      '#ff6188',
  pinkBg:    'rgba(255,97,136,0.08)',
  grad:      'linear-gradient(135deg,#7c3aed 0%,#06b6d4 100%)',
  SG:        "'Space Grotesk', system-ui, sans-serif",
  IN:        "'Inter', system-ui, sans-serif",
};

// ─── Helpers ───────────────────────────────────────────────────────────────────
const lbl = (color = C.muted, size = 10): React.CSSProperties => ({
  fontFamily: C.SG, fontSize: size, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.12em', color,
});

const card = (extra: React.CSSProperties = {}): React.CSSProperties => ({
  background: C.s1, borderRadius: 10, ...extra,
});

function relativeDate(iso: string | null): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'ahora';
  if (mins < 60) return `hace ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs}h`;
  return `hace ${Math.floor(hrs / 24)}d`;
}

// ─── Badge ─────────────────────────────────────────────────────────────────────
function Badge({ score, status }: { score: number | null; status: HitlStatus }) {
  const cfg =
    status === 'approved'  ? { text: 'Aprobado',         bg: C.greenBg,  color: C.green  } :
    status === 'rejected'  ? { text: 'Descartado',        bg: C.pinkBg,   color: C.pink   } :
    (score ?? 0) >= 85     ? { text: 'Alta intención',    bg: C.greenBg,  color: C.green  } :
    (score ?? 0) >= 70     ? { text: 'Interés creciente', bg: C.purpleBg, color: C.purple } :
                             { text: 'En revisión',       bg: C.cyanBg,   color: C.cyan   };
  return (
    <span style={{ ...lbl(cfg.color, 9), background: cfg.bg, padding: '3px 9px', borderRadius: 4 }}>
      {cfg.text}
    </span>
  );
}

// ─── Toast ─────────────────────────────────────────────────────────────────────
function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const isReject = toast.type === 'reject';
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '12px 16px', minWidth: 268,
      background: C.s3,
      border: `1px solid ${isReject ? 'rgba(62,73,74,0.5)' : 'rgba(169,220,118,0.25)'}`,
      borderRadius: 8, boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
      pointerEvents: 'all',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateX(0)' : 'translateX(12px)',
      transition: 'opacity 0.2s, transform 0.2s',
    }}>
      <span style={{ fontSize: 13, color: isReject ? C.muted : C.green, flexShrink: 0 }}>
        {isReject ? '✕' : '✓'}
      </span>
      <span style={{ fontFamily: C.SG, fontSize: 12, color: C.text, flex: 1 }}>
        {toast.message}
      </span>
      {toast.undoFn && (
        <button
          onClick={() => { toast.undoFn!(); onDismiss(toast.id); }}
          style={{
            padding: '4px 10px', border: '1px solid rgba(120,220,232,0.35)',
            borderRadius: 4, background: 'transparent', color: C.cyan,
            ...lbl(C.cyan, 10), cursor: 'pointer', flexShrink: 0,
          }}
        >
          Deshacer
        </button>
      )}
      <button
        onClick={() => onDismiss(toast.id)}
        aria-label="Cerrar notificación"
        style={{
          width: 20, height: 20, border: 'none', background: 'transparent',
          color: C.muted, cursor: 'pointer', fontSize: 14,
          display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 3,
          flexShrink: 0,
        }}
      >✕</button>
    </div>
  );
}

function ToastStack({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 300,
      display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none',
    }}>
      {toasts.map(t => <ToastCard key={t.id} toast={t} onDismiss={onDismiss} />)}
    </div>
  );
}

// ─── Lead card ─────────────────────────────────────────────────────────────────
function LeadCard({ lead, onApplyStatus, onOpenDossier }: {
  lead: ApiLead;
  onApplyStatus: (id: string, status: HitlStatus) => void;
  onOpenDossier: () => void;
}) {
  const [hover, setHover] = useState(false);

  const json    = lead.expediente_json as Record<string, unknown> | null;
  const decisor = json?.decisor as Record<string, unknown> | null;
  const resumen = (json?.resumen_empresa as string) || (json?.resumen as string) || '';
  const emailStr = (decisor?.email as string) || lead.email || '';
  const city    = (json?.ciudad as string) || lead.city || '';
  const domain  = lead.url.replace(/^https?:\/\//, '').split('/')[0];
  const initial = (lead.company_name || domain || '?')[0].toUpperCase();
  const date    = relativeDate(lead.created_at);

  const accent = lead.hitl_status === 'approved' ? C.green
    : lead.hitl_status === 'rejected' ? C.pink
    : (lead.score ?? 0) >= 85 ? C.green : C.cyan;

  const act = (type: 'a' | 'r', e: React.MouseEvent) => {
    e.stopPropagation();
    onApplyStatus(lead._id, type === 'a' ? 'approved' : 'rejected');
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpenDossier}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenDossier(); } }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        ...card({ padding: '18px 22px' }),
        borderLeft: `2px solid ${hover ? accent : 'transparent'}`,
        background: hover ? C.s2 : C.s1,
        transition: 'background 0.15s, border-color 0.15s',
        cursor: 'pointer', outline: 'none',
      }}
    >
      {/* Top row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', minWidth: 0, flex: 1 }}>
          <div style={{
            width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
            background: `linear-gradient(135deg,${C.s3},${C.s4})`,
            border: `1px solid ${accent}30`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: C.SG, fontWeight: 700, fontSize: 15, color: accent,
          }}>
            {initial}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {lead.company_name || domain}
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 11, color: C.muted, marginTop: 1 }}>{domain}</div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
          <Badge score={lead.score} status={lead.hitl_status} />
          {lead.score !== null && (
            <span style={lbl(C.faint, 9)}>Score {lead.score}</span>
          )}
        </div>
      </div>

      {resumen && (
        <p style={{
          fontFamily: C.IN, fontSize: 12, color: 'rgba(227,224,241,0.6)',
          lineHeight: 1.6, marginTop: 12,
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {resumen}
        </p>
      )}

      {/* Footer */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginTop: 14, paddingTop: 12,
        borderTop: '1px solid rgba(255,255,255,0.035)',
        flexWrap: 'wrap', gap: 8,
      }}>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          {emailStr && (
            <span style={{ fontFamily: C.SG, fontSize: 10, color: C.cyan }}>
              @ {emailStr.slice(0, 24)}
            </span>
          )}
          {city && (
            <span style={{ fontFamily: C.SG, fontSize: 10, color: C.muted }}>◎ {city}</span>
          )}
          {date && (
            <span style={{ fontFamily: C.SG, fontSize: 10, color: C.faint }}>{date}</span>
          )}
          {/* Affordance: always visible, brightens on hover */}
          <span style={{
            fontFamily: C.SG, fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase',
            color: hover ? C.cyan : 'rgba(120,220,232,0.25)',
            transition: 'color 0.15s',
          }}>
            Ver expediente →
          </span>
        </div>

        {lead.hitl_status === 'pending' && (
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={e => act('r', e)} style={{
              padding: '5px 12px', cursor: 'pointer',
              border: `1px solid ${C.pink}40`, borderRadius: 4, background: 'transparent',
              ...lbl(C.pink, 10), transition: 'background 0.15s',
            }}>
              Descartar
            </button>
            <button onClick={e => act('a', e)} style={{
              padding: '5px 16px', cursor: 'pointer',
              border: 'none', borderRadius: 4, background: C.grad,
              ...lbl('#fff', 10),
              boxShadow: hover ? '0 0 12px rgba(6,182,212,0.3)' : 'none',
              transition: 'box-shadow 0.15s',
            }}>
              Aprobar →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Nav item ──────────────────────────────────────────────────────────────────
function NavItem({ emoji, text, active, count, onClick }: {
  emoji: string; text: string; active: boolean; count?: number; onClick: () => void;
}) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, width: '100%',
        padding: '11px 20px', border: 'none', cursor: 'pointer', textAlign: 'left',
        background: active ? C.cyanBg : hov ? 'rgba(255,255,255,0.03)' : 'transparent',
        borderRight: `2px solid ${active ? C.cyan : 'transparent'}`,
        transition: 'all 0.15s',
      }}
    >
      <span style={{ fontSize: 15, width: 20, textAlign: 'center' }}>{emoji}</span>
      <span style={{ ...lbl(active ? C.cyan : hov ? C.text : C.muted, 11), flex: 1 }}>{text}</span>
      {count !== undefined && count > 0 && (
        <span style={{
          background: active ? C.cyan : C.s3,
          color: active ? '#000' : C.muted,
          borderRadius: 10, padding: '1px 7px',
          fontSize: 10, fontFamily: C.SG, fontWeight: 700,
        }}>
          {count}
        </span>
      )}
    </button>
  );
}


// ─── Main ──────────────────────────────────────────────────────────────────────
type Tab = 'pending' | 'approved' | 'rejected';

const TAB_META: Record<Tab, { title: string; sub: string; emoji: string }> = {
  pending:  { title: 'Leads Pendientes',   sub: 'Prospectos identificados por los agentes en espera de revisión.', emoji: '🔍' },
  approved: { title: 'Leads Aprobados',    sub: 'Prospectos con intención verificada, listos para outreach.', emoji: '✅' },
  rejected: { title: 'Leads Descartados',  sub: 'Prospectos que no cumplen con los criterios del pipeline.', emoji: '✕' },
};

export function ClientDashboard({ onBack }: { onBack?: () => void }) {
  const { authToken, userEmail, clearAuth } = useOfficeStore();
  const token = authToken || sessionStorage.getItem('hive_token') || '';

  const [leads, setLeads]      = useState<ApiLead[]>([]);
  const [loading, setLoading]  = useState(true);
  const [tab, setTab]          = useState<Tab>('pending');
  const [tick, setTick]        = useState(0);
  const [selectedLead, setSelectedLead] = useState<ApiLead | null>(null);
  const [toasts, setToasts]    = useState<ToastItem[]>([]);
  const [query, setQuery]      = useState('');

  // tracks pending reject timeouts — keyed by lead id
  const pendingRejects = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // ── Data fetching ────────────────────────────────────────────────────────────
  const fetchLeads = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const r = await fetch(`${API}/api/leads`, { headers: { Authorization: `Bearer ${token}` } });
      const d = await r.json();
      setLeads(Array.isArray(d) ? d : []);
    } catch { if (!silent) setLeads([]); }
    finally   { if (!silent) setLoading(false); }
  }, [token]);

  useEffect(() => { fetchLeads(tick > 0); }, [fetchLeads, tick]);

  const refresh = () => setTick(t => t + 1);

  // ── Toast helpers ────────────────────────────────────────────────────────────
  const dismissToast = (id: string) =>
    setToasts(prev => prev.filter(t => t.id !== id));

  const addToast = (toast: ToastItem, duration = 3500) => {
    setToasts(prev => [...prev.filter(t => t.id !== toast.id), toast]);
    setTimeout(() => dismissToast(toast.id), duration);
  };

  // ── Undo reject ─────────────────────────────────────────────────────────────
  const undoReject = (id: string) => {
    const tid = pendingRejects.current.get(id);
    if (tid !== undefined) { clearTimeout(tid); pendingRejects.current.delete(id); }
    setLeads(prev => prev.map(l => l._id === id ? { ...l, hitl_status: 'pending' } : l));
    setSelectedLead(prev => prev?._id === id ? { ...prev, hitl_status: 'pending' } : prev);
  };

  // ── Central action handler (owns all PATCHes) ────────────────────────────────
  const applyStatus = (id: string, status: HitlStatus) => {
    // 1. Optimistic local update
    setLeads(prev => prev.map(l => l._id === id ? { ...l, hitl_status: status } : l));
    setSelectedLead(prev => prev?._id === id ? { ...prev, hitl_status: status } : prev);

    if (status === 'approved') {
      // Fire immediately
      fetch(`${API}/api/leads/${id}/approve`, {
        method: 'PATCH', headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
      setTick(t => t + 1);
      addToast({ id: `ok-${id}`, message: '✓ Lead aprobado', type: 'approve' });

    } else if (status === 'rejected') {
      // Delay 5s so user can undo
      const tid = setTimeout(() => {
        pendingRejects.current.delete(id);
        fetch(`${API}/api/leads/${id}/reject`, {
          method: 'PATCH',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ motivo: 'manual_reject' }),
        }).catch(() => {});
        setTick(t => t + 1);
      }, 5000);
      pendingRejects.current.set(id, tid);
      addToast(
        { id: `rej-${id}`, message: 'Lead descartado', type: 'reject', undoFn: () => undoReject(id) },
        5500, // auto-dismiss slightly after PATCH fires
      );
    }
  };

  // ── Derived state ────────────────────────────────────────────────────────────
  const pending  = leads.filter(l => l.hitl_status === 'pending');
  const approved = leads.filter(l => l.hitl_status === 'approved');
  const rejected = leads.filter(l => l.hitl_status === 'rejected');

  const tabLeads = tab === 'pending' ? pending : tab === 'approved' ? approved : rejected;
  const visible  = query
    ? tabLeads.filter(l => {
        const q = query.toLowerCase();
        return (l.company_name || '').toLowerCase().includes(q)
            || l.url.toLowerCase().includes(q)
            || (l.city || '').toLowerCase().includes(q);
      })
    : tabLeads;

  const convRate = leads.length > 0 ? Math.round((approved.length / leads.length) * 100) : 0;
  const avgScore = (() => {
    const sc = leads.filter(l => l.score !== null);
    return sc.length > 0 ? Math.round(sc.reduce((s, l) => s + (l.score ?? 0), 0) / sc.length) : null;
  })();

  const meta = TAB_META[tab];

  return (
    <div style={{ display: 'flex', height: '100vh', background: C.bg, color: C.text, fontFamily: C.IN, overflow: 'hidden' }}>

      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <aside style={{
        width: 236, flexShrink: 0,
        display: 'flex', flexDirection: 'column',
        background: C.s0,
        boxShadow: '6px 0 24px rgba(0,0,0,0.3)',
      }}>
        {/* Logo */}
        <div style={{ padding: '26px 20px 18px' }}>
          <div style={{ fontFamily: C.SG, fontWeight: 900, fontSize: 21, color: C.purple, fontStyle: 'italic', letterSpacing: '-0.03em' }}>
            LANDA
          </div>
          <div style={lbl(C.cyan, 9)}>SYSTEM_READY</div>
        </div>

        {/* Navigation — single source of truth for tab */}
        <nav style={{ flex: 1, paddingTop: 4 }}>
          <NavItem emoji="🔍" text="Pipeline"    active={tab === 'pending'}  count={pending.length}  onClick={() => setTab('pending')}  />
          <NavItem emoji="✅" text="Aprobados"   active={tab === 'approved'} count={approved.length} onClick={() => setTab('approved')} />
          <NavItem emoji="✕"  text="Descartados" active={tab === 'rejected'} count={rejected.length} onClick={() => setTab('rejected')} />

          {onBack && (
            <>
              <div style={{ height: 1, background: `linear-gradient(to right, transparent, ${C.cyanBdr}, transparent)`, margin: '8px 0' }} />
              <NavItem emoji="🏢" text="Ir a la Oficina" active={false} onClick={onBack} />
            </>
          )}
        </nav>

        {/* Footer */}
        <div style={{ padding: '8px 0 14px' }}>
          <div style={{ height: 1, background: `linear-gradient(to right, transparent, ${C.cyanBdr}, transparent)`, margin: '0 0 6px' }} />
          <button onClick={clearAuth} style={{
            display: 'flex', alignItems: 'center', gap: 10, width: '100%',
            padding: '10px 20px', border: 'none', background: 'transparent',
            cursor: 'pointer', ...lbl(C.muted, 10),
          }}>
            ⎋ Cerrar sesión
          </button>
        </div>
      </aside>

      {/* ── Content ─────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* Top bar */}
        <header style={{
          height: 54, flexShrink: 0, display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', padding: '0 28px',
          background: C.s0, position: 'relative',
        }}>
          {/* Search — actually filters leads */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.s1, borderRadius: 20, padding: '6px 16px', cursor: 'text' }}>
            <span style={{ color: C.cyan, fontSize: 13 }}>⌕</span>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Buscar leads..."
              aria-label="Buscar leads"
              style={{
                background: 'transparent', border: 'none', outline: 'none',
                color: C.text, fontSize: 12, fontFamily: C.IN, width: 140,
              }}
            />
            {query && (
              <button onClick={() => setQuery('')} style={{
                background: 'transparent', border: 'none', color: C.muted,
                cursor: 'pointer', fontSize: 12, lineHeight: 1, padding: 0,
              }}>✕</button>
            )}
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: C.SG, fontSize: 11, color: C.muted }}>{userEmail}</span>
          </div>
          {/* gradient separator */}
          <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 1, background: 'linear-gradient(to right, transparent, rgba(120,220,232,0.12), transparent)', pointerEvents: 'none' }} />
        </header>

        {/* Scrollable body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px' }}>

          {/* Page heading — reflects active tab */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 22 }}>
            <div>
              <h1 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 28, letterSpacing: '-0.03em', color: C.text }}>
                {meta.title}
              </h1>
              <p style={{ fontFamily: C.IN, fontSize: 13, color: C.muted, marginTop: 5 }}>
                {meta.sub}
              </p>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, ...lbl(C.green, 10), background: C.greenBg, padding: '5px 14px', borderRadius: 20 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.green, display: 'inline-block' }} />
              Sistema Activo
            </div>
          </div>

          {/* Pipeline funnel */}
          <div style={{ ...card({ padding: '18px 24px', marginBottom: 26, position: 'relative', overflow: 'hidden' }) }}>
            {/* subtle radial glow in corner */}
            <div style={{ position: 'absolute', top: 0, left: 0, width: 200, height: 120, background: 'radial-gradient(ellipse at 0% 0%, rgba(120,220,232,0.06) 0%, transparent 70%)', pointerEvents: 'none' }} />
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14 }}>
              <span style={lbl(C.muted)}>Pipeline de Leads</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
              {[
                { label: 'Total', value: leads.length, color: C.cyan, active: false },
                { label: 'Pendientes', value: pending.length, color: C.purple, active: tab === 'pending' },
                { label: 'Aprobados', value: approved.length, color: C.green, active: tab === 'approved' },
                { label: 'Descartados', value: rejected.length, color: C.pink, active: tab === 'rejected' },
              ].map((stage, i) => (
                <div key={stage.label} style={{ display: 'flex', alignItems: 'center', flex: i === 0 ? '1.4' : '1' }}>
                  <div
                    onClick={i === 1 ? () => setTab('pending') : i === 2 ? () => setTab('approved') : i === 3 ? () => setTab('rejected') : undefined}
                    style={{
                      flex: 1, padding: '12px 16px', borderRadius: 8, position: 'relative',
                      background: stage.active ? `${stage.color}10` : 'transparent',
                      border: stage.active ? `1px solid ${stage.color}30` : '1px solid transparent',
                      cursor: i > 0 ? 'pointer' : 'default',
                      transition: 'all 0.15s',
                      boxShadow: stage.active ? `0 0 16px ${stage.color}15` : 'none',
                    }}
                  >
                    <div style={{ fontFamily: C.SG, fontWeight: 900, fontSize: 30, color: stage.active ? stage.color : C.text, lineHeight: 1 }}>
                      {stage.value}
                    </div>
                    <div style={lbl(stage.active ? stage.color : C.muted, 9)}>{stage.label}</div>
                    {i > 0 && leads.length > 0 && (
                      <div style={{
                        position: 'absolute', top: 6, right: 8,
                        fontFamily: C.SG, fontSize: 9, color: stage.color, opacity: 0.6,
                      }}>
                        {Math.round((stage.value / leads.length) * 100)}%
                      </div>
                    )}
                  </div>
                  {i < 3 && (
                    <div style={{ color: 'rgba(227,224,241,0.15)', fontSize: 16, padding: '0 4px', flexShrink: 0 }}>›</div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Two-column body */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 272px', gap: 20, alignItems: 'start' }}>

            {/* Lead stream */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <h2 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 16, letterSpacing: '-0.02em' }}>
                  {meta.emoji} {tabLeads.length} {tab === 'pending' ? 'pendientes' : tab === 'approved' ? 'aprobados' : 'descartados'}
                  {query && (
                    <span style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, fontWeight: 400, marginLeft: 8 }}>
                      · {visible.length} resultado{visible.length !== 1 ? 's' : ''} para "{query}"
                    </span>
                  )}
                </h2>
                <button onClick={refresh} title="Actualizar" aria-label="Actualizar lista" style={{
                  width: 30, height: 30, border: 'none', borderRadius: 5,
                  background: C.s1, color: C.muted, cursor: 'pointer', fontSize: 14,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'background 0.15s',
                }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.s3; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = C.s1; }}
                >↺</button>
              </div>

              {loading ? (
                /* Skeleton loaders */
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {[1,2,3].map(i => (
                    <div key={i} style={{ ...card({ padding: '20px 22px' }), opacity: 0.5 }}>
                      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        <div style={{ width: 40, height: 40, borderRadius: '50%', background: C.s3 }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ height: 12, background: C.s3, borderRadius: 4, width: '45%', marginBottom: 6 }} />
                          <div style={{ height: 10, background: C.s2, borderRadius: 4, width: '30%' }} />
                        </div>
                      </div>
                      <div style={{ height: 10, background: C.s2, borderRadius: 4, width: '80%', marginTop: 14 }} />
                      <div style={{ height: 10, background: C.s2, borderRadius: 4, width: '60%', marginTop: 6 }} />
                    </div>
                  ))}
                </div>
              ) : visible.length === 0 ? (
                <div style={{ ...card({ padding: '52px 28px', textAlign: 'center', position: 'relative', overflow: 'hidden' }) }}>
                  <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 0%, rgba(171,157,242,0.04) 0%, transparent 60%)', pointerEvents: 'none' }} />
                  <div style={{ fontSize: 36, marginBottom: 12 }}>{meta.emoji}</div>
                  <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 15, color: C.text, marginBottom: 6 }}>
                    {query ? `Sin resultados para "${query}"` :
                     tab === 'pending' ? 'Sin leads pendientes' :
                     tab === 'approved' ? 'Aún no hay aprobados' : 'Sin leads descartados'}
                  </div>
                  <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, lineHeight: 1.6, maxWidth: 280, margin: '0 auto' }}>
                    {query ? 'Intenta con otro término de búsqueda.' :
                     tab === 'pending' ? 'Los agentes están buscando prospectos. Los leads aparecerán aquí para tu revisión.' :
                     tab === 'approved' ? 'Revisa los leads pendientes y aprueba los que cumplan tu perfil ideal.' : 'Ningún lead ha sido descartado aún.'}
                  </div>
                  {tab === 'pending' && !query && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 18 }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.cyan, boxShadow: `0 0 8px ${C.cyan}`, display: 'inline-block', animation: 'pulse 2s infinite' }} />
                      <span style={lbl(C.cyan, 10)}>Agentes activos buscando...</span>
                    </div>
                  )}
                  {tab === 'approved' && !query && pending.length > 0 && (
                    <button
                      onClick={() => setTab('pending')}
                      style={{
                        marginTop: 18, padding: '8px 20px', border: 'none', borderRadius: 4,
                        background: C.grad, color: '#fff', cursor: 'pointer',
                        fontFamily: C.SG, fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
                      }}
                    >
                      Ver {pending.length} pendiente{pending.length !== 1 ? 's' : ''} →
                    </button>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {visible.map(l => (
                    <LeadCard key={l._id} lead={l} onApplyStatus={applyStatus} onOpenDossier={() => setSelectedLead(l)} />
                  ))}
                </div>
              )}
            </div>

            {/* Right sidebar */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

              {/* Conversion card — accent changes with tab */}
              <div style={card({ padding: '18px', position: 'relative', overflow: 'hidden' })}>
                <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(ellipse at 100% 0%, ${tab === 'approved' ? 'rgba(169,220,118,0.06)' : tab === 'rejected' ? 'rgba(255,97,136,0.05)' : 'rgba(120,220,232,0.05)'} 0%, transparent 65%)`, pointerEvents: 'none' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <span style={lbl(tab === 'approved' ? C.green : tab === 'rejected' ? C.pink : C.cyan)}>
                    {tab === 'pending' ? 'Pendientes' : tab === 'approved' ? 'Aprobados' : 'Descartados'}
                  </span>
                  <span style={{ ...lbl(C.cyan, 8), background: C.cyanBg, padding: '2px 8px', borderRadius: 10 }}>En vivo</span>
                </div>
                <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 34, color: tab === 'approved' ? C.green : tab === 'rejected' ? C.pink : C.purple }}>
                  {tab === 'pending' ? pending.length : tab === 'approved' ? approved.length : rejected.length}
                </div>
                <div style={{ fontFamily: C.IN, fontSize: 11, color: C.muted, marginTop: 5 }}>
                  {tab === 'approved' && `${convRate}% conversión total`}
                  {tab === 'pending' && `de ${leads.length} leads totales`}
                  {tab === 'rejected' && (leads.length > 0 ? `${Math.round((rejected.length / leads.length) * 100)}% tasa de descarte` : 'sin leads aún')}
                </div>
              </div>

              {/* Contextual analysis */}
              <div style={card({ padding: '18px' })}>
                <span style={lbl(C.purple, 9)}>Análisis del Pipeline</span>
                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 0 }}>
                  {[
                    { k: 'Score promedio', v: avgScore ?? '—' },
                    { k: 'Alta intención',  v: leads.filter(l => (l.score ?? 0) >= 85).length },
                    { k: 'Con contacto',    v: leads.filter(l => !!l.email || !!(l.expediente_json as Record<string,unknown>|null)?.decisor).length },
                    { k: 'Tasa aprobación', v: leads.length > 0 ? `${convRate}%` : '—' },
                  ].map((row, i) => (
                    <div key={row.k} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '9px 0',
                      marginBottom: i < 3 ? 0 : undefined,
                    }}>
                      <span style={{ fontFamily: C.IN, fontSize: 12, color: C.muted }}>{row.k}</span>
                      <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.text }}>{row.v}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Quick action hint for pending tab */}
              {tab === 'pending' && pending.length > 0 && (
                <div style={{ ...card({ padding: '16px 18px' }), background: 'rgba(171,157,242,0.06)', border: '1px solid rgba(171,157,242,0.15)' }}>
                  <div style={lbl(C.purple, 9)}>Acción rápida</div>
                  <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, marginTop: 8, lineHeight: 1.6 }}>
                    Haz clic en cualquier lead para ver el expediente completo y tomar una decisión.
                  </div>
                </div>
              )}

            </div>
          </div>
        </div>
      </div>

      {/* ── Dossier modal ───────────────────────────────────────────────────── */}
      {selectedLead && (
        <LeadDossierModal
          lead={selectedLead}
          token={token}
          onClose={() => setSelectedLead(null)}
          onAction={refresh}
          onApplyStatus={applyStatus}
        />
      )}

      {/* ── Toast stack ─────────────────────────────────────────────────────── */}
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
