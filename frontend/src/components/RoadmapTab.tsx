import React, { useEffect, useState } from 'react';
import { apiFetch } from '../lib/apiFetch';
import { useOfficeStore } from '../store/officeStore';

// ── Design tokens (dark theme, matches StaffDashboard) ─────────────────
const bg    = '#0d0d18';
const s0    = '#12121f';
const s1    = '#1a1a2e';
const s2    = '#22223a';
const text  = '#e8e8f0';
const muted = '#8b8ba8';
const faint = '#4a4a6a';
const cyan  = '#78dce8';
const green = '#a9dc76';
const pink  = '#ff6188';
const amber = '#ffd866';
const purple= '#ab9df2';
const SG    = "'Space Grotesk', 'Segoe UI', sans-serif";
const IN    = "'Inter', 'Segoe UI', sans-serif";

// ── Data ────────────────────────────────────────────────────────────────
const CHECKLISTS = {
  current: [
    { id: 'cur1',  label: 'Constituir SAS',                                        tag: 'urgent'   },
    { id: 'cur2',  label: 'Comprar dominio',                                        tag: null       },
    { id: 'cur3',  label: 'Ciberseguridad del desarrollo',                          tag: null       },
    { id: 'cur4',  label: 'Definir pricing beta',                                   tag: 'urgent'   },
    { id: 'cur5',  label: 'Actualizar landing page con lógica real del negocio',    tag: null       },
    { id: 'cur6',  label: 'Mejorar UI del desarrollo',                              tag: null       },
    { id: 'cur7',  label: 'Estrategia de propuesta a clientes prospectos',          tag: null       },
    { id: 'cur8',  label: 'Agente SECOP listo para despliegue',                     tag: null       },
    { id: 'cur9',  label: 'NDA socios estratégicos',                                tag: 'prelabel' },
    { id: 'cur10', label: 'NDA freelancers y consultores',                          tag: 'prelabel' },
    { id: 'cur11', label: 'NDA mutuo entre cofundadores',                           tag: 'prelabel' },
  ],
  f1: [
    { id: 'f1-1', label: 'Cliente 1 activo con ingreso recurrente',                tag: null       },
    { id: 'f1-2', label: 'Cliente 2 activo con ingreso recurrente',                tag: null       },
    { id: 'f1-3', label: 'Cliente 3 activo con ingreso recurrente',                tag: null       },
    { id: 'f1-4', label: 'Cliente 4 activo con ingreso recurrente',                tag: 'signal'   },
    { id: 'f1-5', label: 'Segundo vertical validado con cliente real',             tag: null       },
    { id: 'f1-6', label: 'Pricing definitivo por vertical documentado',            tag: null       },
    { id: 'f1-7', label: 'LLC en US constituida y operativa',                      tag: null       },
    { id: 'f1-8', label: 'Estructura legal CO–US definida',                        tag: null       },
  ],
  f2: [
    { id: 'f2-1', label: 'Agentes multi-canal operativos — WhatsApp, email, CRM', tag: null },
    { id: 'f2-2', label: 'Onboarding automatizado sin intervención constante',     tag: null },
    { id: 'f2-3', label: 'Primer cliente activo en US',                            tag: null },
    { id: 'f2-4', label: 'Catálogo ampliado: RUES, Cámara de Comercio, DIAN',     tag: null },
  ],
  f3: [
    { id: 'f3-1', label: 'Marketplace abierto a terceros',                         tag: null },
    { id: 'f3-2', label: 'Primer agente externo publicado en marketplace',         tag: null },
    { id: 'f3-3', label: 'Modelo self-serve sin intervención de LANDA',            tag: null },
    { id: 'f3-4', label: 'Interfaz unificada — sin panel lateral separado',        tag: null },
  ],
};

const HITOS = [
  { id: 'h1', label: 'Constituir SAS',               desc: 'desbloqueador para inversión, contratos grandes y vinculaciones', badge: 'urg',  badgeText: 'Urgente'    },
  { id: 'h2', label: 'Pricing beta definido',         desc: '',                                                                 badge: 'urg',  badgeText: 'Urgente'    },
  { id: 'h3', label: 'Constituir LLC en US',          desc: '',                                                                 badge: 'wip',  badgeText: 'En proceso' },
  { id: 'h4', label: 'Estructura legal CO–US',        desc: 'definir antes de operar en ambos mercados',                       badge: 'pend', badgeText: 'Pendiente'  },
  { id: 'h5', label: 'Pricing definitivo por vertical', desc: '',                                                               badge: 'pend', badgeText: 'Pendiente'  },
  { id: 'h6', label: 'NDAs completos',                desc: 'socios estratégicos, freelancers y cofundadores',                  badge: 'done', badgeText: '✓ Listo'    },
];

const PHASES = [
  { key: 'current' as const, label: 'Ahora mismo',  title: 'Estado actual',                       accent: amber,  accentBg: `${amber}10`, accentBorder: `${amber}30` },
  { key: 'f1'      as const, label: 'Fase 1',        title: 'Oficina Funcional',                   accent: green,  accentBg: `${green}10`, accentBorder: `${green}30` },
  { key: 'f2'      as const, label: 'Fase 2',        title: 'Oficina Conectada',                   accent: purple, accentBg: `${purple}10`, accentBorder: `${purple}30` },
  { key: 'f3'      as const, label: 'Fase 3',        title: 'Oficina con Presencia + Marketplace', accent: cyan,   accentBg: `${cyan}10`, accentBorder: `${cyan}30` },
];

// ── Subcomponents ───────────────────────────────────────────────────────
function ProgressBar({ done, total, accent }: { done: number; total: number; accent: string }) {
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
      <div style={{ flex: 1, height: 4, background: s2, borderRadius: 999, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: accent, borderRadius: 999, transition: 'width 0.3s ease' }} />
      </div>
      <span style={{ fontSize: 11, color: muted, fontFamily: SG, minWidth: 48, textAlign: 'right' }}>
        {done}/{total}
      </span>
    </div>
  );
}

function CheckItem({
  item, done, accent, onToggle,
}: {
  item: { id: string; label: string; tag: string | null };
  done: boolean;
  accent: string;
  onToggle: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  const tagBadge = () => {
    if (done) return null;
    if (item.tag === 'urgent')   return <span style={{ fontSize: 10, background: `${pink}18`, color: pink,   borderRadius: 20, padding: '2px 8px', fontFamily: SG, flexShrink: 0 }}>urgente</span>;
    if (item.tag === 'signal')   return <span style={{ fontSize: 10, background: `${amber}18`, color: amber, borderRadius: 20, padding: '2px 8px', fontFamily: SG, flexShrink: 0 }}>señal de salida</span>;
    if (item.tag === 'prelabel') return <span style={{ fontSize: 10, background: `${muted}18`, color: muted, borderRadius: 20, padding: '2px 8px', fontFamily: SG, flexShrink: 0 }}>prelegal</span>;
    return null;
  };

  return (
    <div
      role="checkbox"
      aria-checked={done}
      tabIndex={0}
      onClick={onToggle}
      onKeyDown={e => (e.key === ' ' || e.key === 'Enter') && onToggle()}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '9px 12px', borderRadius: 8, cursor: 'pointer',
        border: `1px solid ${hovered && !done ? `${accent}40` : done ? `${accent}25` : faint + '55'}`,
        background: done ? `${accent}08` : hovered ? `${accent}06` : s1,
        marginBottom: 6, transition: 'all 0.15s ease',
        outline: 'none',
      }}
    >
      {/* Checkbox */}
      <span style={{
        width: 16, height: 16, flexShrink: 0,
        border: `1.5px solid ${done ? accent : faint}`,
        borderRadius: 4,
        background: done ? accent : 'transparent',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.15s ease',
      }}>
        {done && (
          <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
            <path d="M1 3.5L3.2 5.5L8 1" stroke={bg} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      </span>
      {/* Label */}
      <span style={{
        fontSize: 13, flex: 1, fontFamily: IN,
        color: done ? muted : text,
        textDecoration: done ? 'line-through' : 'none',
        textDecorationColor: faint,
      }}>
        {item.label}
      </span>
      {tagBadge()}
    </div>
  );
}

function PhaseCard({
  phase, items, state, onToggle,
}: {
  phase: typeof PHASES[number];
  items: typeof CHECKLISTS[keyof typeof CHECKLISTS];
  state: Record<string, boolean | string>;
  onToggle: (id: string) => void;
}) {
  const done = items.filter(i => state[i.id]).length;
  const total = items.length;
  const complete = done === total;

  return (
    <div style={{
      background: complete ? `${phase.accent}08` : s0,
      border: `1px solid ${complete ? phase.accent + '40' : faint + '44'}`,
      borderRadius: 12, padding: '20px 22px', marginBottom: 10,
      transition: 'border-color 0.2s ease',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: phase.accent, fontFamily: SG }}>
          {phase.label}
        </span>
        {complete && (
          <span style={{ fontSize: 10, color: phase.accent, fontFamily: SG, fontWeight: 600 }}>✓ Completado</span>
        )}
      </div>
      <h2 style={{ fontSize: 17, fontWeight: 700, color: text, marginBottom: 14, fontFamily: SG, letterSpacing: '-0.02em' }}>
        {phase.title}
      </h2>
      <ProgressBar done={done} total={total} accent={phase.accent} />
      <div>
        {items.map(item => (
          <CheckItem key={item.id} item={item} done={!!state[item.id]} accent={phase.accent} onToggle={() => onToggle(item.id)} />
        ))}
      </div>
    </div>
  );
}

type HitoStatus = 'pend' | 'urg' | 'wip' | 'done';
const HITO_CYCLE: HitoStatus[] = ['pend', 'urg', 'wip', 'done'];
const HITO_LABELS: Record<HitoStatus, string> = { pend: 'Pendiente', urg: 'Urgente', wip: 'En proceso', done: '✓ Listo' };
const HITO_STYLES: Record<HitoStatus, React.CSSProperties> = {
  pend: { background: s2,             color: muted,  border: `1px solid ${faint}44`  },
  urg:  { background: `${pink}18`,    color: pink,   border: `1px solid ${pink}30`   },
  wip:  { background: `${amber}18`,   color: amber,  border: `1px solid ${amber}30`  },
  done: { background: `${green}18`,   color: green,  border: `1px solid ${green}30`  },
};

function HitosCard({ state, onCycle }: { state: Record<string, boolean | string>; onCycle: (id: string, next: HitoStatus) => void }) {
  return (
    <div style={{ background: s0, border: `1px solid ${faint}44`, borderRadius: 12, padding: '20px 22px', marginTop: 10 }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: muted, marginBottom: 4, fontFamily: SG }}>
        Hitos transversales
      </div>
      <div style={{ fontSize: 11, color: faint, fontFamily: IN, marginBottom: 16 }}>
        Clic para avanzar estado
      </div>
      {HITOS.map((h, i) => {
        const raw = state[h.id];
        const current: HitoStatus = (typeof raw === 'string' && raw in HITO_LABELS)
          ? raw as HitoStatus
          : (raw === true ? 'done' : h.badge as HitoStatus);
        const nextIdx = (HITO_CYCLE.indexOf(current) + 1) % HITO_CYCLE.length;
        const next = HITO_CYCLE[nextIdx];
        const isDone = current === 'done';

        return (
          <div
            key={h.id}
            role="button"
            aria-label={`${h.label} — ${HITO_LABELS[current]}. Clic para avanzar a ${HITO_LABELS[next]}`}
            tabIndex={0}
            onClick={() => onCycle(h.id, next)}
            onKeyDown={e => (e.key === ' ' || e.key === 'Enter') && onCycle(h.id, next)}
            style={{
              display: 'flex', alignItems: 'flex-start', gap: 12,
              padding: '11px 0',
              borderBottom: i < HITOS.length - 1 ? `1px solid ${faint}33` : 'none',
              cursor: 'pointer', outline: 'none',
              opacity: isDone ? 0.55 : 1, transition: 'opacity 0.15s',
            }}
          >
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '3px 10px', borderRadius: 20,
              minWidth: 82, textAlign: 'center', fontFamily: SG, flexShrink: 0,
              ...HITO_STYLES[current],
            }}>
              {HITO_LABELS[current]}
            </span>
            <span style={{ fontSize: 13, color: isDone ? muted : text, fontFamily: IN, textDecoration: isDone ? 'line-through' : 'none', textDecorationColor: faint }}>
              <strong style={{ color: isDone ? muted : text }}>{h.label}</strong>
              {h.desc ? <span style={{ color: muted }}> — {h.desc}</span> : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────
export const RoadmapTab: React.FC = () => {
  const { userRole, authToken } = useOfficeStore();
  const [state, setState] = useState<Record<string, boolean | string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authToken) return;
    setLoading(true);
    apiFetch('/api/roadmap-state', { headers: { Authorization: 'Bearer ' + authToken } })
      .then(r => r.json())
      .then(data => { setState(data.state || {}); setLoading(false); })
      .catch(() => { setError('No se pudo cargar el estado'); setLoading(false); });
  }, [authToken]);

  const saveState = (newState: Record<string, boolean | string>) => {
    if (!authToken) return;
    apiFetch('/api/roadmap-state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + authToken },
      body: JSON.stringify({ state: newState }),
    });
  };

  const toggle = (id: string) => {
    const newState = { ...state, [id]: !state[id] };
    setState(newState);
    saveState(newState);
  };

  const cycleHito = (id: string, next: HitoStatus) => {
    const newState = { ...state, [id]: next };
    setState(newState);
    saveState(newState);
  };

  if (userRole !== 'staff') return null;

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: muted, fontFamily: IN, fontSize: 13 }}>
      Cargando roadmap...
    </div>
  );

  if (error) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: pink, fontFamily: IN, fontSize: 13 }}>
      {error}
    </div>
  );

  // Overall progress
  const allItems = Object.values(CHECKLISTS).flat();
  const totalDone = allItems.filter(i => state[i.id]).length;
  const totalAll  = allItems.length;
  const overallPct = Math.round((totalDone / totalAll) * 100);

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '36px 24px 80px', background: bg, minHeight: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: muted, fontFamily: SG }}>LANDA PROJECT · Confidencial</span>
          <span style={{ fontSize: 11, color: muted, fontFamily: SG }}>{overallPct}% completado</span>
        </div>
        <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.03em', color: text, marginBottom: 4, fontFamily: SG }}>
          Roadmap de fases
        </h1>
        <p style={{ fontSize: 13, color: muted, fontFamily: IN }}>Sin fechas — las fases avanzan por señales, no por calendario</p>
        {/* Global progress bar */}
        <div style={{ marginTop: 16, height: 3, background: s2, borderRadius: 999, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${overallPct}%`, background: `linear-gradient(to right, ${cyan}, ${green})`, borderRadius: 999, transition: 'width 0.4s ease' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
          <span style={{ fontSize: 10, color: faint, fontFamily: SG }}>{totalDone} de {totalAll} tareas</span>
          <span style={{ fontSize: 10, color: faint, fontFamily: SG }}>{totalAll - totalDone} pendientes</span>
        </div>
      </div>

      {/* Phase cards */}
      {PHASES.map(phase => (
        <PhaseCard
          key={phase.key}
          phase={phase}
          items={CHECKLISTS[phase.key]}
          state={state}
          onToggle={toggle}
        />
      ))}

      {/* Hitos */}
      <HitosCard state={state} onCycle={cycleHito} />
    </div>
  );
};
