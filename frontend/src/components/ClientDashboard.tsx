import React, { useState, useEffect, useRef, useMemo, lazy, Suspense } from 'react';
import { useDebounce } from 'use-debounce';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useOfficeStore } from '../store/officeStore';
import { apiFetch } from '../lib/apiFetch';

const LeadDossierModal = lazy(() => import('./LeadDossierModal').then(m => ({ default: m.LeadDossierModal })));
const CobranzaTab = lazy(() => import('./CobranzaTab').then(m => ({ default: m.CobranzaTab })));

const API = '';

// Inject keyframes once
if (typeof document !== 'undefined' && !document.getElementById('cd-styles')) {
  const s = document.createElement('style');
  s.id = 'cd-styles';
  s.textContent = `
    @keyframes pulse { 0%,100%{opacity:1;box-shadow:0 0 6px #78dce8} 50%{opacity:0.4;box-shadow:0 0 2px #78dce8} }
    @keyframes fadeUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes shimmer { 0% { background-position: -1000px 0; } 100% { background-position: 1000px 0; } }
  `;
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

// ─── Tokens (Antigravity Design) ────────────────────────────────────────────────
const C = {
  bg:        'linear-gradient(135deg, #0a0a14 0%, #0d0d18 50%, #0a0a14 100%)',
  bgSolid:   '#0a0a14',
  s0:        'rgba(18,18,29,0.85)',
  s0Blur:    'blur(20px)',
  s1:        'rgba(27,26,38,0.7)',
  s1Blur:    'blur(12px)',
  s2:        'rgba(34,33,46,0.6)',
  s3:        'rgba(44,43,58,0.5)',
  s4:        '#343440',
  text:      '#f0eff8',
  textMid:   '#d8d6e6',
  muted:     '#9b9aaa',
  faint:     'rgba(227,224,241,0.25)',
  cyan:      '#5dd9f5',
  cyanGlow:  'rgba(93,217,245,0.12)',
  cyanBg:    'rgba(93,217,245,0.08)',
  cyanBdr:   'rgba(93,217,245,0.2)',
  purple:    '#b4a1ff',
  purpleBg:  'rgba(180,161,255,0.08)',
  green:     '#7ee8a3',
  greenBg:   'rgba(126,232,163,0.08)',
  pink:      '#ff7a9f',
  pinkBg:    'rgba(255,122,159,0.08)',
  grad:      'linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)',
  SG:        "'Space Grotesk', system-ui, sans-serif",
  IN:        "'Inter', system-ui, sans-serif",
  shadow1:   '0 4px 20px rgba(0,0,0,0.3)',
  shadow2:   '0 8px 32px rgba(0,0,0,0.4)',
  shadowGlow: 'inset 0 0 0 1px rgba(93,217,245,0.1)',
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

// ─── SVG Icons ─────────────────────────────────────────────────────────────────
const SearchIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>;
const CheckIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>;
const MailIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>;
const LogOutIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>;
const RefreshIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36M20.49 15a9 9 0 0 1-14.85 3.36"/></svg>;
const XIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
const HomeIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
const PencilIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>;
const SaveIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>;
const BeakerIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4.5 3h15v7c0 1-1 2-2 2H6.5c-1 0-2-1-2-2V3z"/><path d="M7 14h10"/><path d="M6 21h12M8 21c0-1 1-2 2-2h4c1 0 2 1 2 2"/></svg>;
const ChatIcon = () => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>;
// const DotIcon = ({ animated }: { animated?: boolean }) => <svg width="8" height="8" viewBox="0 0 16 16" fill="currentColor" style={{ animation: animated ? 'pulse 2s infinite' : undefined }}><circle cx="8" cy="8" r="3"/></svg>;

// ─── Badge ─────────────────────────────────────────────────────────────────────
const Badge = React.memo(function Badge({ score, status }: { score: number | null; status: HitlStatus }) {
  const cfg = useMemo(() =>
    status === 'approved'  ? { text: 'Aprobado',         bg: C.greenBg,  color: C.green  } :
    status === 'rejected'  ? { text: 'Descartado',        bg: C.pinkBg,   color: C.pink   } :
    (score ?? 0) >= 85     ? { text: 'Alta intención',    bg: C.greenBg,  color: C.green  } :
    (score ?? 0) >= 70     ? { text: 'Interés creciente', bg: C.purpleBg, color: C.purple } :
                             { text: 'En revisión',       bg: C.cyanGlow, color: C.cyan   },
    [score, status]
  );
  return (
    <span style={{ ...lbl(cfg.color, 9), background: cfg.bg, padding: '4px 10px', borderRadius: 6, border: `1px solid ${cfg.color}25`, backdropFilter: 'blur(4px)' }}>
      {cfg.text}
    </span>
  );
});

// ─── Toast ─────────────────────────────────────────────────────────────────────
const ToastCard = React.memo(function ToastCard({ toast, onDismiss }: { toast: ToastItem; onDismiss: (id: string) => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const isReject = toast.type === 'reject';
  const accentColor = isReject ? C.pink : C.green;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '14px 18px', minWidth: 300,
      background: C.s1,
      backdropFilter: C.s1Blur,
      border: `1px solid ${accentColor}20`,
      borderRadius: 10, boxShadow: C.shadow2,
      pointerEvents: 'all',
      opacity: visible ? 1 : 0,
      transform: visible ? 'translateX(0)' : 'translateX(16px)',
      transition: 'opacity 0.3s ease-out, transform 0.3s ease-out',
    }}>
      <div style={{ color: accentColor, fontSize: 14, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16 }}>
        {isReject ? <XIcon /> : <CheckIcon />}
      </div>
      <span style={{ fontFamily: C.IN, fontSize: 13, color: C.text, flex: 1, lineHeight: 1.5 }}>
        {toast.message}
      </span>
      {toast.undoFn && (
        <button
          onClick={() => { toast.undoFn!(); onDismiss(toast.id); }}
          style={{
            padding: '6px 12px', border: `1px solid ${C.cyan}30`,
            borderRadius: 6, background: 'rgba(93,217,245,0.05)', color: C.cyan,
            ...lbl(C.cyan, 10), cursor: 'pointer', flexShrink: 0,
            transition: 'all 0.2s ease-out',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(93,217,245,0.12)'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(93,217,245,0.05)'; }}
        >
          Deshacer
        </button>
      )}
      <button
        onClick={() => onDismiss(toast.id)}
        aria-label="Cerrar notificación"
        style={{
          width: 20, height: 20, border: 'none', background: 'transparent',
          color: C.muted, cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 4,
          flexShrink: 0, transition: 'color 0.2s',
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = C.text; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = C.muted; }}
      >
        <XIcon />
      </button>
    </div>
  );
});

const ToastStack = React.memo(function ToastStack({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 300,
      display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none',
    }}>
      {toasts.map(t => <ToastCard key={t.id} toast={t} onDismiss={onDismiss} />)}
    </div>
  );
});

// ─── Lead card ─────────────────────────────────────────────────────────────────
const LeadCard = React.memo(function LeadCard({ lead, onApplyStatus, onOpenDossier }: {
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
        borderLeft: `3px solid ${hover ? accent : 'transparent'}`,
        background: hover ? C.s2 : C.s1,
        backdropFilter: C.s1Blur,
        border: `1px solid ${hover ? accent + '30' : C.cyanBdr}`,
        transition: 'all 0.25s ease-out',
        cursor: 'pointer', outline: 'none',
        transform: hover ? 'translateY(-2px)' : 'translateY(0)',
        boxShadow: hover ? C.shadow2 : C.shadow1,
      }}
    >
      {/* Top row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', minWidth: 0, flex: 1 }}>
          <div style={{
            width: 44, height: 44, borderRadius: '50%', flexShrink: 0,
            background: `linear-gradient(135deg, ${accent}20, ${accent}05)`,
            border: `1.5px solid ${accent}50`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: C.SG, fontWeight: 700, fontSize: 16, color: accent,
            boxShadow: `inset 0 1px 2px ${accent}20`,
            transition: 'all 0.2s ease-out',
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
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={e => act('r', e)} style={{
              padding: '6px 14px', cursor: 'pointer',
              border: `1.5px solid ${C.pink}40`, borderRadius: 6, background: `${C.pink}08`,
              ...lbl(C.pink, 10), transition: 'all 0.2s ease-out', fontWeight: 600,
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = `${C.pink}15`; (e.currentTarget as HTMLElement).style.borderColor = `${C.pink}70`; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = `${C.pink}08`; (e.currentTarget as HTMLElement).style.borderColor = `${C.pink}40`; }}
            >
              Descartar
            </button>
            <button onClick={e => act('a', e)} style={{
              padding: '6px 16px', cursor: 'pointer',
              border: 'none', borderRadius: 6, background: C.grad,
              ...lbl('#fff', 10), fontWeight: 600,
              boxShadow: hover ? `0 8px 20px ${C.cyan}30` : `0 4px 12px ${C.cyan}20`,
              transition: 'all 0.2s ease-out',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(-1px)'; (e.currentTarget as HTMLElement).style.boxShadow = `0 12px 24px ${C.cyan}40`; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = 'translateY(0)'; (e.currentTarget as HTMLElement).style.boxShadow = hover ? `0 8px 20px ${C.cyan}30` : `0 4px 12px ${C.cyan}20`; }}
            >
              Aprobar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}, (prev, next) => {
  // Custom comparison - solo re-render si lead._id o hitl_status cambian
  return prev.lead._id === next.lead._id && 
         prev.lead.hitl_status === next.lead.hitl_status &&
         prev.lead.score === next.lead.score;
});

// ─── Nav item ──────────────────────────────────────────────────────────────────
const NavItem = React.memo(function NavItem({ emoji, text, active, count, onClick }: {
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
        padding: '12px 20px', border: 'none', cursor: 'pointer', textAlign: 'left',
        background: active ? C.cyanGlow : hov ? `${C.cyan}08` : 'transparent',
        borderRight: `2px solid ${active ? C.cyan : 'transparent'}`,
        transition: 'all 0.2s ease-out',
        borderRadius: '8px 0 0 8px',
      }}
    >
      <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 18, height: 18, color: active ? C.cyan : hov ? C.text : C.muted, transition: 'color 0.2s' }}>
        {emoji === '🔍' ? <SearchIcon /> : emoji === '✅' ? <CheckIcon /> : emoji === '✕' ? <XIcon /> : emoji === '🏢' ? <HomeIcon /> : emoji}
      </span>
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
});

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: C.s1,
      border: `1px solid ${C.s3}`,
      borderRadius: 10,
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 8,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: C.SG }}>
        {value}
      </div>
      <div style={{ fontSize: 10, color: C.muted, fontFamily: C.SG, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {label}
      </div>
    </div>
  );
}

const MemoStatCard = React.memo(StatCard);

// ─── Main ──────────────────────────────────────────────────────────────────────
type Tab = 'pending' | 'approved' | 'rejected';

const TAB_META: Record<Tab, { title: string; sub: string; emoji: string }> = {
  pending:  { title: 'Leads Pendientes',   sub: 'Prospectos identificados por los agentes en espera de revisión.', emoji: '🔍' }, // Kept for backward compatibility, not displayed
  approved: { title: 'Leads Aprobados',    sub: 'Prospectos con intención verificada, listos para outreach.', emoji: '✅' },
  rejected: { title: 'Leads Descartados',  sub: 'Prospectos que no cumplen con los criterios del pipeline.', emoji: '✕' },
};

export function ClientDashboard({ onBack }: { onBack?: () => void }) {
  const { authToken, userEmail, clearAuth } = useOfficeStore();
  const token = authToken || sessionStorage.getItem('hive_token') || '';
  const queryClient = useQueryClient();

  // ── State ──────────────────────────────────────────────────────────────────────
  const [section, setSection]  = useState<'leads' | 'cobranza' | 'email' | 'canales'>('leads');
  const [tab, setTab]          = useState<Tab>('pending');
  const [selectedLead, setSelectedLead] = useState<ApiLead | null>(null);
  const [toasts, setToasts]    = useState<ToastItem[]>([]);
  const [query, setQuery]      = useState('');
  const [showTemplateEditor, setShowTemplateEditor] = useState(false);
  const [testEmailLoading, setTestEmailLoading] = useState(false);
  const [debouncedQuery] = useDebounce(query, 300);
  const pendingRejects = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // ── React Query: Fetch leads with caching ──────────────────────────────────────
  const { data: leads = [], isLoading, refetch: refetchLeads } = useQuery({
    queryKey: ['leads', token],
    queryFn: async () => {
      const r = await apiFetch(`${API}/api/leads`, { headers: { Authorization: `Bearer ${token}` } });
      return r.ok ? await r.json() : [];
    },
    staleTime: 30000, // cachear por 30 segundos
    enabled: !!token,
  });

  // ── React Query: Cobranza status ───────────────────────────────────────────────
  const { data: cobranzaData } = useQuery({
    queryKey: ['cobranza-status', token],
    queryFn: async () => {
      const r = await apiFetch(`${API}/api/cobranza/status`, { headers: { Authorization: `Bearer ${token}` } });
      return r.ok ? await r.json() : null;
    },
    enabled: !!token,
    refetchInterval: 5000, // Auto-refresh every 5 seconds
  });

  const cobranzaEnabled = cobranzaData?.enabled ?? false;

  // ── React Query: Email status ──────────────────────────────────────────────────
  const { data: emailData } = useQuery({
    queryKey: ['email-status', token],
    queryFn: async () => {
      const r = await apiFetch(`${API}/api/me/email-status`, { headers: { Authorization: `Bearer ${token}` } });
      return r.ok ? await r.json() : null;
    },
    enabled: !!token,
    refetchInterval: 5000, // Auto-refresh every 5 seconds
  });

  const emailConnected = emailData?.connected ?? false;
  const emailAddress = emailData?.email ?? '';

  // ── Mutation: Approve lead ─────────────────────────────────────────────────────
  const approveMutation = useMutation({
    mutationFn: (id: string) => 
      apiFetch(`${API}/api/leads/${id}/approve`, { 
        method: 'PATCH', 
        headers: { Authorization: `Bearer ${token}` }
      }),
    onSuccess: (_, id) => {
      // Soft update de cache
      queryClient.setQueryData(['leads', token], (prev: ApiLead[]) =>
        (prev || []).map(l => l._id === id ? { ...l, hitl_status: 'approved' as HitlStatus } : l)
      );
    },
  });

  // ── Mutation: Reject lead ──────────────────────────────────────────────────────
  const rejectMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`${API}/api/leads/${id}/reject`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo: 'manual_reject' }),
      }),
    onSuccess: (_, id) => {
      // Soft update de cache
      queryClient.setQueryData(['leads', token], (prev: ApiLead[]) =>
        (prev || []).map(l => l._id === id ? { ...l, hitl_status: 'rejected' as HitlStatus } : l)
      );
    },
  });

  // ── Handle OAuth callback (SECURE) ────────────────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session_id');

    if (sessionId) {
      // ✅ SECURE: Clear URL immediately to remove session_id
      window.history.replaceState({}, document.title, window.location.pathname);
      
      // ✅ SECURE: Confirm session with backend via POST (not GET)
      apiFetch(`${API}/api/auth/oauth-confirm`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ session_id: sessionId })
      })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (d) {
            queryClient.invalidateQueries({ queryKey: ['email-status'] });
            addToast({
              id: Date.now().toString(),
              message: `✅ ${d.provider.charAt(0).toUpperCase() + d.provider.slice(1)} conectado!\nAhora enviarás desde: ${d.email}`,
              type: 'approve'
            });
          }
        })
        .catch(err => {
          console.error('[OAuth] Error confirming session:', err);
          addToast({
            id: Date.now().toString(),
            message: `❌ Error al conectar. Intenta de nuevo.`,
            type: 'reject'
          });
        });
    }
  }, [token]);

  // ── Toast helpers ──────────────────────────────────────────────────────────────
  const dismissToast = (id: string) =>
    setToasts(prev => prev.filter(t => t.id !== id));

  const addToast = (toast: ToastItem, duration = 3500) => {
    setToasts(prev => [...prev.filter(t => t.id !== toast.id), toast]);
    setTimeout(() => dismissToast(toast.id), duration);
  };

  // ── Undo reject ───────────────────────────────────────────────────────────────
  const undoReject = (id: string) => {
    const tid = pendingRejects.current.get(id);
    if (tid !== undefined) { clearTimeout(tid); pendingRejects.current.delete(id); }
    queryClient.setQueryData(['leads', token], (prev: ApiLead[]) =>
      (prev || []).map(l => l._id === id ? { ...l, hitl_status: 'pending' as HitlStatus } : l)
    );
    setSelectedLead(prev => prev?._id === id ? { ...prev, hitl_status: 'pending' } : prev);
  };

  // ── Central action handler (uses React Query mutations) ──────────────────────
  const applyStatus = (id: string, status: HitlStatus) => {
    // 1. Optimistic local update
    queryClient.setQueryData(['leads', token], (prev: ApiLead[]) =>
      (prev || []).map(l => l._id === id ? { ...l, hitl_status: status } : l)
    );
    setSelectedLead(prev => prev?._id === id ? { ...prev, hitl_status: status } : prev);

    if (status === 'approved') {
      approveMutation.mutate(id);
      addToast({ id: `ok-${id}`, message: '✓ Lead aprobado', type: 'approve' });
    } else if (status === 'rejected') {
      const tid = setTimeout(() => {
        pendingRejects.current.delete(id);
        rejectMutation.mutate(id);
      }, 5000);
      pendingRejects.current.set(id, tid);
      addToast(
        { id: `rej-${id}`, message: 'Lead descartado', type: 'reject', undoFn: () => undoReject(id) },
        5500,
      );
    }
  };

  // ── Derived state (memoized to avoid re-calculations) ────────────────────────
  const { pending, approved, rejected, tabLeads, visible, convRate, avgScore } = useMemo(() => {
    const pending  = leads.filter((l: ApiLead) => l.hitl_status === 'pending');
    const approved = leads.filter((l: ApiLead) => l.hitl_status === 'approved');
    const rejected = leads.filter((l: ApiLead) => l.hitl_status === 'rejected');

    const tabLeads = tab === 'pending' ? pending : tab === 'approved' ? approved : rejected;
    
    const visible = debouncedQuery
      ? tabLeads.filter((l: ApiLead) => {
          const q = debouncedQuery.toLowerCase();
          return (l.company_name || '').toLowerCase().includes(q)
              || l.url.toLowerCase().includes(q)
              || (l.city || '').toLowerCase().includes(q);
        })
      : tabLeads;

    const convRate = leads.length > 0 ? Math.round((approved.length / leads.length) * 100) : 0;
    const avgScore = (() => {
      const sc = leads.filter((l: ApiLead) => l.score !== null);
      return sc.length > 0 ? Math.round(sc.reduce((s: number, l: ApiLead) => s + (l.score ?? 0), 0) / sc.length) : null;
    })();

    return { pending, approved, rejected, tabLeads, visible, convRate, avgScore };
  }, [leads, tab, debouncedQuery]); // IMPORTANTE: usa debouncedQuery, no query

  const meta = TAB_META[tab];

  return (
    <div style={{ display: 'flex', height: '100vh', background: C.bg, color: C.text, fontFamily: C.IN, overflow: 'hidden' }}>

      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <aside style={{
        width: 236, flexShrink: 0,
        display: 'flex', flexDirection: 'column',
        background: C.s0,
        backdropFilter: C.s0Blur,
        borderRight: `1px solid ${C.cyanBdr}`,
        boxShadow: C.shadow1,
      }}>
        {/* Logo */}
        <div style={{ padding: '16px 20px 18px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src="/assets/logo.svg" alt="Landa AI" style={{ width: 40, height: 40 }} />
          <div>
            <div style={{ fontFamily: C.SG, fontWeight: 900, fontSize: 21, color: C.purple, fontStyle: 'italic', letterSpacing: '-0.03em' }}>
              LANDA
            </div>
            <div style={lbl(C.cyan, 9)}>SYSTEM_READY</div>
          </div>
        </div>

        {/* Navigation — single source of truth for tab */}
        <nav style={{ flex: 1, paddingTop: 4 }}>
          {/* Section switcher */}
          <div style={{ display: 'flex', margin: '0 12px 8px', gap: 4, flexWrap: 'wrap' }}>
            {(['leads', ...(cobranzaEnabled ? ['cobranza'] : []), 'email', 'canales'] as const).map(s => (
              <button
                key={s}
                onClick={() => setSection(s as 'leads' | 'cobranza' | 'email' | 'canales')}
                style={{
                  flex: s === 'leads' || s === 'cobranza' ? 1 : 'auto',
                  padding: '7px 10px', border: 'none', cursor: 'pointer',
                  background: section === s ? (s === 'cobranza' ? 'rgba(252,152,103,0.1)' : s === 'canales' ? 'rgba(126,232,163,0.1)' : C.cyanGlow) : 'transparent',
                  borderBottom: `2px solid ${section === s ? (s === 'cobranza' ? '#fc9867' : s === 'canales' ? '#7ee8a3' : C.cyan) : 'transparent'}`,
                  fontFamily: C.SG, fontWeight: 600, fontSize: 10, letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: section === s ? (s === 'cobranza' ? '#fc9867' : s === 'canales' ? '#7ee8a3' : C.cyan) : C.muted,
                  transition: 'all 0.2s ease-out',
                  minWidth: s === 'leads' || s === 'cobranza' ? undefined : '60px',
                  whiteSpace: 'nowrap',
                  backdropFilter: 'blur(6px)',
                  borderRadius: '6px 6px 0 0',
                }}
              >
                {s === 'leads' ? 'Leads' : s === 'cobranza' ? 'Cobro' : s === 'email' ? 'Email' : 'Canales'}
              </button>
            ))}
          </div>

          {section === 'leads' && (
            <>
              <NavItem emoji="🔍" text="Pipeline"    active={tab === 'pending'}  count={pending.length}  onClick={() => setTab('pending')}  />
              <NavItem emoji="✅" text="Aprobados"   active={tab === 'approved'} count={approved.length} onClick={() => setTab('approved')} />
              <NavItem emoji="✕"  text="Descartados" active={tab === 'rejected'} count={rejected.length} onClick={() => setTab('rejected')} />
            </>
          )}

          {onBack && (
            <>
              <div style={{ height: 1, background: `linear-gradient(to right, transparent, ${C.cyanBdr}, transparent)`, margin: '8px 0' }} />
              <NavItem emoji="🏢" text="Ir a la Oficina" active={false} onClick={onBack} />
            </>
          )}
        </nav>

        {/* Footer */}
        <div style={{ padding: '12px 0 16px' }}>
          <div style={{ height: 1, background: `linear-gradient(to right, transparent, ${C.cyanBdr}, transparent)`, margin: '0 0 8px' }} />
          <button onClick={clearAuth} style={{
            display: 'flex', alignItems: 'center', gap: 10, width: '100%',
            padding: '10px 20px', border: 'none', background: 'transparent',
            cursor: 'pointer', ...lbl(C.muted, 10),
            transition: 'all 0.2s ease-out',
            borderRadius: 6,
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.s3; (e.currentTarget as HTMLElement).style.color = C.cyan; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; (e.currentTarget as HTMLElement).style.color = C.muted; }}
          >
            <LogOutIcon /> Cerrar sesión
          </button>
        </div>
      </aside>

      {/* ── Content ─────────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

        {/* Top bar */}
        <header style={{
          height: 60, flexShrink: 0, display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', padding: '0 28px',
          background: C.s0,
          backdropFilter: C.s0Blur,
          borderBottom: `1px solid ${C.cyanBdr}`,
          position: 'relative',
        }}>
          {/* Search — actually filters leads */}
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, background: C.s1, backdropFilter: 'blur(8px)', borderRadius: 10, padding: '8px 18px', cursor: 'text', border: `1px solid ${C.cyanBdr}`, transition: 'all 0.2s ease-out', color: C.cyan }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.s2; (e.currentTarget as HTMLElement).style.borderColor = C.cyan + '40'; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = C.s1; (e.currentTarget as HTMLElement).style.borderColor = C.cyanBdr; }}
          >
            <SearchIcon />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Buscar leads..."
              aria-label="Buscar leads"
              style={{
                background: 'transparent', border: 'none', outline: 'none',
                color: C.text, fontSize: 13, fontFamily: C.IN, width: 180,
              }}
            />
            {query && (
              <button onClick={() => setQuery('')} style={{
                background: 'transparent', border: 'none', color: C.muted,
                cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'color 0.2s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = C.cyan; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = C.muted; }}
              >
                <XIcon />
              </button>
            )}
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: C.IN, fontSize: 12, color: C.muted }}>{userEmail}</span>
          </div>
        </header>

        {/* Cobranza section */}
        {section === 'cobranza' && (
          <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center', color: C.muted }}>Cargando cobranza...</div>}>
            <CobranzaTab />
          </Suspense>
        )}

        {/* Email metrics section */}
        {section === 'email' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px' }}>
            <div style={{ marginBottom: 32 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: C.cyan, fontFamily: C.SG, marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24 }}><MailIcon /></span> Estadísticas de Email
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 16 }}>
                <MemoStatCard label="Enviados" value="87" color={C.cyan} />
                <MemoStatCard label="Abiertos" value="42" color="#a9dc76" />
                <MemoStatCard label="% Apertura" value="48%" color="#ffd866" />
                <MemoStatCard label="Clicks" value="23" color="#ff6188" />
              </div>
            </div>

            <div style={{ fontSize: 12, color: C.muted, fontFamily: C.IN }}>
              Los datos de aperturas se actualizan en tiempo real cuando tus clientes abren los correos.
            </div>
          </div>
        )}

        {/* Channels configuration section */}
        {section === 'canales' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px' }}>
            <div style={{ marginBottom: 32 }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: C.green, fontFamily: C.SG, marginBottom: 20 }}>
                Canales de Comunicación
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Email channel */}
                <div style={{
                  background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}`, borderRadius: 12, padding: 20,
                  transition: 'all 0.3s ease-out', boxShadow: '0 4px 12px rgba(0,0,0,0.2)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: C.text, fontFamily: C.SG, display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, color: C.cyan, background: 'rgba(93,217,245,0.1)', borderRadius: 6 }}><MailIcon /></span> Email
                    </div>
                    <div style={{ fontSize: 11, color: emailConnected ? C.green : '#ffd866', background: emailConnected ? C.greenBg : 'rgba(255,216,102,0.1)', padding: '4px 10px', borderRadius: 6, fontWeight: 600, border: `1px solid ${emailConnected ? C.green + '20' : '#ffd866' + '20'}` }}>
                      {emailConnected ? 'Conectado' : 'No configurado'}
                    </div>
                  </div>
                  {emailConnected ? (
                    <>
                      <div style={{ fontSize: 12, color: C.muted, fontFamily: C.IN, marginBottom: 14 }}>
                        {emailAddress}
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button style={{
                          background: C.cyanBg, border: `1px solid ${C.cyanBdr}`, color: C.cyan,
                          padding: '8px 12px', borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: C.SG,
                          display: 'flex', alignItems: 'center', gap: 6,
                          transition: 'all 0.25s ease-out',
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.background = C.cyanGlow;
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.background = C.cyanBg;
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                        }}
                        onClick={() => {
                          setTestEmailLoading(true);
                          apiFetch(`${API}/api/me/email-test`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
                            .then(r => r.ok ? r.json() : null)
                            .then(d => {
                              setTestEmailLoading(false);
                              if (d) addToast({ id: Date.now().toString(), message: `Correo de prueba enviado a ${d.sent_to}`, type: 'approve' });
                            })
                            .catch(() => setTestEmailLoading(false));
                        }} disabled={testEmailLoading}>
                          <BeakerIcon /> {testEmailLoading ? 'Enviando...' : 'Prueba'}
                        </button>
                        <button style={{
                          background: 'rgba(255,216,102,0.08)', border: `1px solid rgba(255,216,102,0.3)`, color: '#ffd866',
                          padding: '8px 12px', borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: C.SG,
                          display: 'flex', alignItems: 'center', gap: 6,
                          transition: 'all 0.25s ease-out',
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.background = 'rgba(255,216,102,0.12)';
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.background = 'rgba(255,216,102,0.08)';
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                        }}
                        onClick={() => setShowTemplateEditor(!showTemplateEditor)}>
                          <PencilIcon /> Template
                        </button>
                        <button style={{
                          background: 'rgba(169,220,118,0.08)', border: `1px solid rgba(169,220,118,0.2)`, color: '#a9dc76',
                          padding: '8px 12px', borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: C.SG,
                          display: 'flex', alignItems: 'center', gap: 6,
                          transition: 'all 0.25s ease-out',
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.background = 'rgba(169,220,118,0.12)';
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.background = 'rgba(169,220,118,0.08)';
                          (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                        }}
                        onClick={() => {
                          apiFetch(`${API}/api/me/email-disconnect`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
                            .then(() => { queryClient.invalidateQueries({ queryKey: ['email-status'] }); })
                            .catch();
                        }}>
                          <XIcon /> Desconectar
                        </button>
                      </div>
                    </>
                  ) : (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button style={{
                        background: C.cyanBg, border: `1px solid ${C.cyanBdr}`, color: C.cyan,
                        padding: '8px 12px', borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: C.SG,
                        display: 'flex', alignItems: 'center', gap: 6,
                        transition: 'all 0.25s ease-out',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.background = C.cyanGlow;
                        (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.background = C.cyanBg;
                        (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                      }}
                      onClick={() => {
                        if (!token) {
                          alert('No authentication token found. Please refresh the page.');
                          return;
                        }
                        // ✅ SECURE: Get redirect URL from backend
                        apiFetch(`${API}/api/email/connect`, {
                          method: 'POST',
                          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
                          body: JSON.stringify({ provider: 'gmail' })
                        })
                          .then(r => r.ok ? r.json() : null)
                          .then(d => {
                            if (d?.redirect_url) window.location.href = d.redirect_url;
                          });
                      }}>
                        <MailIcon /> Gmail
                      </button>
                      <button style={{
                        background: 'rgba(169,220,118,0.08)', border: `1px solid rgba(169,220,118,0.3)`, color: '#a9dc76',
                        padding: '8px 12px', borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: C.SG,
                        display: 'flex', alignItems: 'center', gap: 6,
                        transition: 'all 0.25s ease-out',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.background = 'rgba(169,220,118,0.12)';
                        (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.background = 'rgba(169,220,118,0.08)';
                        (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                      }}
                      onClick={() => {
                        if (!token) {
                          alert('No authentication token found. Please refresh the page.');
                          return;
                        }
                        // ✅ SECURE: Get redirect URL from backend
                        apiFetch(`${API}/api/email/connect`, {
                          method: 'POST',
                          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
                          body: JSON.stringify({ provider: 'outlook' })
                        })
                          .then(r => r.ok ? r.json() : null)
                          .then(d => {
                            if (d?.redirect_url) window.location.href = d.redirect_url;
                          });
                      }}>
                        <MailIcon /> Outlook
                      </button>
                    </div>
                  )}
                </div>

                {/* WhatsApp channel */}
                <div style={{
                  background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}`, borderRadius: 12, padding: 20,
                  transition: 'all 0.3s ease-out', boxShadow: '0 4px 12px rgba(0,0,0,0.2)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: C.text, fontFamily: C.SG, display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, color: '#ffd866', background: 'rgba(255,216,102,0.1)', borderRadius: 6 }}><ChatIcon /></span> WhatsApp
                    </div>
                    <div style={{ fontSize: 11, color: '#ffd866', background: 'rgba(255,216,102,0.1)', padding: '4px 10px', borderRadius: 6, fontWeight: 600, border: `1px solid rgba(255,216,102,0.2)` }}>
                      Pendiente
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: C.muted, fontFamily: C.IN, marginBottom: 16 }}>
                    Configurar WhatsApp Business para enviar mensajes desde tu número.
                  </div>
                  <button style={{
                    background: 'rgba(255,216,102,0.08)', border: `1px solid rgba(255,216,102,0.3)`, color: '#ffd866',
                    padding: '8px 12px', borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: 'pointer', fontFamily: C.SG,
                    transition: 'all 0.25s ease-out',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'rgba(255,216,102,0.12)';
                    (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'rgba(255,216,102,0.08)';
                    (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                  }}>
                    Configurar
                  </button>
                </div>
              </div>
            </div>

            <div style={{ fontSize: 12, color: C.muted, fontFamily: C.IN, marginBottom: 24 }}>
              Cada canal te permite contactar a tus leads desde tu propia cuenta. El proceso de aprobación de WhatsApp puede tomar 2-5 días.
            </div>

            {/* Template Editor */}
            {showTemplateEditor && emailConnected && (
              <div style={{
                background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}`, borderRadius: 12, padding: 20, marginTop: 20,
                transition: 'all 0.3s ease-out', boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                animation: 'fadeUp 0.3s ease-out'
              }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: C.text, fontFamily: C.SG, marginBottom: 18, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, color: '#ffd866', background: 'rgba(255,216,102,0.1)', borderRadius: 6 }}><PencilIcon /></span> Personalizar Template
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div>
                    <label style={{ fontSize: 11, color: C.cyan, fontFamily: C.SG, textTransform: 'uppercase', display: 'block', marginBottom: 8, fontWeight: 600, letterSpacing: '0.08em' }}>
                      Pie de página
                    </label>
                    <textarea style={{
                      width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${C.cyanBdr}`, background: C.s0,
                      color: C.text, fontFamily: C.IN, fontSize: 12, minHeight: 80,
                      transition: 'all 0.25s ease-out',
                      outline: 'none',
                    }}
                    placeholder="Este es un mensaje automático..."
                    onFocus={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = C.cyan;
                      (e.currentTarget as HTMLElement).style.boxShadow = `0 0 12px ${C.cyan}20`;
                    }}
                    onBlur={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = C.cyanBdr;
                      (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                    }}
                    />
                  </div>

                  <div>
                    <label style={{ fontSize: 11, color: C.cyan, fontFamily: C.SG, textTransform: 'uppercase', display: 'block', marginBottom: 8, fontWeight: 600, letterSpacing: '0.08em' }}>
                      Color de marca (hex)
                    </label>
                    <input type="text" placeholder="#78dce8" style={{
                      width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${C.cyanBdr}`, background: C.s0,
                      color: C.text, fontFamily: C.IN, fontSize: 12,
                      transition: 'all 0.25s ease-out',
                      outline: 'none',
                    }}
                    onFocus={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = C.cyan;
                      (e.currentTarget as HTMLElement).style.boxShadow = `0 0 12px ${C.cyan}20`;
                    }}
                    onBlur={(e) => {
                      (e.currentTarget as HTMLElement).style.borderColor = C.cyanBdr;
                      (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                    }}
                    />
                  </div>

                  <button style={{
                    background: C.cyanBg, border: `1px solid ${C.cyanBdr}`, color: C.cyan,
                    padding: '10px 14px', borderRadius: 8, fontSize: 11, cursor: 'pointer', fontFamily: C.SG, fontWeight: 600,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    transition: 'all 0.25s ease-out',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = C.cyanGlow;
                    (e.currentTarget as HTMLElement).style.boxShadow = `0 0 16px ${C.cyan}40, inset 0 1px 0 ${C.cyan}20`;
                    (e.currentTarget as HTMLElement).style.transform = 'scale(1.02)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = C.cyanBg;
                    (e.currentTarget as HTMLElement).style.boxShadow = 'none';
                    (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                  }}>
                    <SaveIcon /> Guardar Template
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Scrollable body — leads section */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px', display: section === 'leads' ? undefined : 'none' }}>

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
          <div style={{ ...card({ padding: '24px 28px', marginBottom: 26, position: 'relative', overflow: 'hidden', background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}`, boxShadow: C.shadow1 }) }}>
            {/* subtle radial glow in corner */}
            <div style={{ position: 'absolute', top: 0, left: 0, width: 300, height: 150, background: 'radial-gradient(ellipse at 0% 0%, rgba(93,217,245,0.08) 0%, transparent 70%)', pointerEvents: 'none' }} />
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
              <span style={lbl(C.cyan, 10)}>Pipeline de Leads</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
              {[
                { label: 'Total', value: leads.length, color: C.cyan, active: false },
                { label: 'Pendientes', value: pending.length, color: C.purple, active: tab === 'pending' },
                { label: 'Aprobados', value: approved.length, color: C.green, active: tab === 'approved' },
                { label: 'Descartados', value: rejected.length, color: C.pink, active: tab === 'rejected' },
              ].map((stage: any, i: number) => (
                <div key={stage.label} style={{ display: 'flex', alignItems: 'center', flex: i === 0 ? '1.4' : '1' }}>
                  <div
                    onClick={i === 1 ? () => setTab('pending') : i === 2 ? () => setTab('approved') : i === 3 ? () => setTab('rejected') : undefined}
                    style={{
                      flex: 1, padding: '16px 18px', borderRadius: 10, position: 'relative',
                      background: stage.active ? `${stage.color}12` : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${stage.active ? stage.color + '40' : stage.color + '15'}`,
                      cursor: i > 0 ? 'pointer' : 'default',
                      transition: 'all 0.25s ease-out',
                      boxShadow: stage.active ? `0 0 20px ${stage.color}20, inset 0 1px 0 ${stage.color}20` : 'none',
                      backdropFilter: 'blur(4px)',
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
                <h2 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 16, letterSpacing: '-0.02em', color: C.text }}>
                  {tabLeads.length} {tab === 'pending' ? 'pendientes' : tab === 'approved' ? 'aprobados' : 'descartados'}
                  {query && (
                    <span style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, fontWeight: 400, marginLeft: 8 }}>
                      · {visible.length} resultado{visible.length !== 1 ? 's' : ''} para "{query}"
                    </span>
                  )}
                </h2>
                <button onClick={() => refetchLeads()} title="Actualizar" aria-label="Actualizar lista" style={{
                  width: 36, height: 36, borderRadius: 8,
                  background: C.s2, color: C.cyan, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.2s ease-out',
                  border: `1px solid ${C.cyanBdr}`,
                }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = `${C.cyan}15`; (e.currentTarget as HTMLElement).style.transform = 'scale(1.05)'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = C.s2; (e.currentTarget as HTMLElement).style.transform = 'scale(1)'; }}
                >
                  <RefreshIcon />
                </button>
              </div>

              {isLoading ? (
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
                <div style={{ ...card({ padding: '52px 28px', textAlign: 'center', position: 'relative', overflow: 'hidden', background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}` }) }}>
                  <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 0%, rgba(93,217,245,0.04) 0%, transparent 60%)', pointerEvents: 'none' }} />
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
                  {visible.map((l: ApiLead) => (
                    <LeadCard key={l._id} lead={l} onApplyStatus={applyStatus} onOpenDossier={() => setSelectedLead(l)} />
                  ))}
                </div>
              )}
            </div>

            {/* Right sidebar */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

              {/* Conversion card — accent changes with tab */}
              <div style={card({ padding: '20px', position: 'relative', overflow: 'hidden', background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}`, boxShadow: C.shadow1 })}>
                <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(ellipse at 100% 0%, ${tab === 'approved' ? 'rgba(126,232,163,0.08)' : tab === 'rejected' ? 'rgba(255,122,159,0.08)' : 'rgba(93,217,245,0.08)'} 0%, transparent 65%)`, pointerEvents: 'none' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                  <span style={lbl(tab === 'approved' ? C.green : tab === 'rejected' ? C.pink : C.cyan, 9)}>
                    {tab === 'pending' ? 'Pendientes' : tab === 'approved' ? 'Aprobados' : 'Descartados'}
                  </span>
                  <span style={{ ...lbl(C.cyan, 8), background: C.cyanGlow, padding: '3px 9px', borderRadius: 12, border: `1px solid ${C.cyan}30` }}>En vivo</span>
                </div>
                <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 38, color: tab === 'approved' ? C.green : tab === 'rejected' ? C.pink : C.purple, lineHeight: 1 }}>
                  {tab === 'pending' ? pending.length : tab === 'approved' ? approved.length : rejected.length}
                </div>
                <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, marginTop: 8 }}>
                  {tab === 'approved' && `${convRate}% conversión total`}
                  {tab === 'pending' && `de ${leads.length} leads totales`}
                  {tab === 'rejected' && (leads.length > 0 ? `${Math.round((rejected.length / leads.length) * 100)}% tasa de descarte` : 'sin leads aún')}
                </div>
              </div>

              {/* Contextual analysis */}
              <div style={card({ padding: '20px', background: C.s1, backdropFilter: C.s1Blur, border: `1px solid ${C.cyanBdr}`, boxShadow: C.shadow1 })}>
                <span style={lbl(C.purple, 9)}>Análisis del Pipeline</span>
                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 0 }}>
                  {[
                    { k: 'Score promedio', v: avgScore ?? '—' },
                    { k: 'Alta intención',  v: leads.filter((l: ApiLead) => (l.score ?? 0) >= 85).length },
                    { k: 'Con contacto',    v: leads.filter((l: ApiLead) => !!l.email || !!(l.expediente_json as Record<string,unknown>|null)?.decisor).length },
                    { k: 'Tasa aprobación', v: leads.length > 0 ? `${convRate}%` : '—' },
                  ].map((row: any, i: number) => (
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
                <div style={{ ...card({ padding: '16px 18px' }), background: C.purpleBg, backdropFilter: 'blur(6px)', border: `1px solid ${C.purple}30`, boxShadow: `0 0 16px ${C.purple}10` }}>
                  <div style={lbl(C.purple, 9)}>💡 Tip rápido</div>
                  <div style={{ fontFamily: C.IN, fontSize: 12, color: C.textMid, marginTop: 8, lineHeight: 1.6 }}>
                    Abre cualquier lead para ver el expediente completo y tomar una decisión inmediata.
                  </div>
                </div>
              )}

            </div>
          </div>
        </div>
      </div>

      {/* ── Dossier modal ───────────────────────────────────────────────────── */}
      {selectedLead && (
        <Suspense fallback={null}>
          <LeadDossierModal
            lead={selectedLead}
            token={token}
            onClose={() => setSelectedLead(null)}
            onAction={() => refetchLeads()}
            onApplyStatus={applyStatus}
          />
        </Suspense>
      )}

      {/* ── Toast stack ─────────────────────────────────────────────────────── */}
      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
