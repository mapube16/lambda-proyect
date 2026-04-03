import { useState, useEffect } from 'react'; // useState kept for `copied`

const C = {
  bg:      '#0d0d18',
  s0:      '#12121d',
  s1:      '#1b1a26',
  s2:      '#22212e',
  s3:      '#2c2b3a',
  s4:      '#343440',
  text:    '#e3e0f1',
  muted:   'rgba(227,224,241,0.5)',
  faint:   'rgba(227,224,241,0.25)',
  cyan:    '#78dce8',
  cyanDim: 'rgba(120,220,232,0.12)',
  purple:  '#ab9df2',
  green:   '#a9dc76',
  greenDim:'rgba(169,220,118,0.12)',
  pink:    '#ff6188',
  pinkDim: 'rgba(255,97,136,0.12)',
  grad:    'linear-gradient(135deg,#7c3aed 0%,#06b6d4 100%)',
  SG:      "'Space Grotesk',system-ui,sans-serif",
  IN:      "'Inter',system-ui,sans-serif",
  MONO:    "'JetBrains Mono','Fira Code','Courier New',monospace",
};

// ─── Circular score gauge ──────────────────────────────────────────────────────
function ScoreGauge({ score }: { score: number }) {
  const r = 52;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(Math.max(score, 0), 100) / 100;
  const offset = circ * (1 - pct);
  const color = score >= 80 ? C.green : score >= 60 ? C.cyan : C.purple;

  return (
    <div style={{ position: 'relative', width: 120, height: 120, flexShrink: 0 }}>
      <svg width="120" height="120" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="60" cy="60" r={r} fill="transparent" stroke={C.s4} strokeWidth="6" />
        <circle
          cx="60" cy="60" r={r} fill="transparent"
          stroke={color} strokeWidth="6"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontFamily: C.SG, fontWeight: 900, fontSize: 26, color, lineHeight: 1 }}>{score}</span>
        <span style={{ fontFamily: C.SG, fontSize: 8, color: C.faint, textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 3 }}>Match Score</span>
      </div>
      {/* glow */}
      <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: `${color}08`, filter: 'blur(12px)', pointerEvents: 'none' }} />
    </div>
  );
}

// ─── Chip ──────────────────────────────────────────────────────────────────────
function Chip({ text }: { text: string }) {
  return (
    <span style={{
      padding: '3px 10px', background: C.s3,
      color: 'rgba(172,246,255,0.7)',
      fontFamily: C.SG, fontSize: 10, fontWeight: 700,
      textTransform: 'uppercase', letterSpacing: '0.1em', borderRadius: 3,
    }}>
      {text}
    </span>
  );
}

// ─── Section label ─────────────────────────────────────────────────────────────
function SectionLabel({ text }: { text: string }) {
  return (
    <div style={{ fontFamily: C.SG, fontSize: 9, fontWeight: 700, color: C.faint, textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 10 }}>
      {text}
    </div>
  );
}

// ─── Props ─────────────────────────────────────────────────────────────────────
interface DossierProps {
  lead: {
    _id: string;
    company_name: string;
    url: string;
    score: number | null;
    email: string | null;
    city: string | null;
    hitl_status: 'pending' | 'approved' | 'rejected';
    expediente_json: Record<string, unknown> | null;
  };
  onClose: () => void;
  onAction: () => void; // kept for compatibility, no longer awaited
  onApplyStatus?: (id: string, status: 'approved' | 'rejected') => void;
}

export function LeadDossierModal({ lead, onClose, onApplyStatus }: DossierProps) {
  const [copied, setCopied] = useState(false);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const json     = lead.expediente_json as Record<string, unknown> | null;
  const decisor  = json?.decisor as Record<string, unknown> | null;
  const borradores = json?.borradores as Record<string, unknown> | null;

  const nombre   = decisor?.nombre as string || '';
  const cargo    = decisor?.cargo  as string || '';
  const emailDecispr = decisor?.email as string || lead.email || '';
  const resumen  = (json?.resumen_empresa as string) || (json?.resumen as string) || 'Sin resumen disponible.';
  const dolor    = (json?.dolor_operativo as string) || (json?.pain_point as string) || '';
  const asunto   = borradores?.email_asunto as string || borradores?.asunto as string || '';
  const cuerpo   = borradores?.email_cuerpo as string || borradores?.cuerpo as string || '';
  const techStack = (json?.datos_tecnicos as Record<string, unknown>)?.tech_stack as string || '';
  const ciudad   = (json?.ciudad as string) || lead.city || '';
  const domain   = lead.url.replace(/^https?:\/\//, '').split('/')[0];
  const initial  = (lead.company_name || domain || '?')[0].toUpperCase();
  const apellido = (lead.company_name || domain || '').split(' ')[0].toUpperCase();
  const score    = lead.score ?? 0;
  const isApto   = lead.hitl_status === 'approved' || (lead.hitl_status === 'pending' && score >= 60);

  // Derive chips from data
  const chips: string[] = [];
  if (score >= 85) chips.push('Alta intención');
  else if (score >= 70) chips.push('Interés creciente');
  if (techStack && techStack !== 'No detectado') chips.push(techStack.split(',')[0].trim());
  if (ciudad) chips.push(ciudad);
  if (chips.length === 0) chips.push('Prospecto');

  const copyDraft = () => {
    const text = asunto ? `Asunto: ${asunto}\n\n${cuerpo}` : cuerpo;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const doApprove = () => {
    onApplyStatus?.(lead._id, 'approved');
    onClose();
  };

  const doReject = () => {
    onApplyStatus?.(lead._id, 'rejected');
    onClose();
  };

  return (
    /* Backdrop */
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(13,13,24,0.85)', backdropFilter: 'blur(6px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
      }}
    >
      {/* Modal */}
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 640, maxHeight: '90vh',
          background: 'rgba(18,18,29,0.95)', backdropFilter: 'blur(12px)',
          borderRadius: 12,
          border: '1px solid rgba(62,73,74,0.35)',
          boxShadow: '0 0 60px rgba(171,157,242,0.1)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        {/* ── Header ── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 24px',
          background: 'rgba(41,41,53,0.5)',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {/* Status badge */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '4px 10px',
              background: isApto ? C.greenDim : C.pinkDim,
              border: `1px solid ${isApto ? 'rgba(169,220,118,0.3)' : 'rgba(255,97,136,0.3)'}`,
              borderRadius: 4,
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: isApto ? C.green : C.pink, boxShadow: `0 0 6px ${isApto ? C.green : C.pink}` }} />
              <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 10, color: isApto ? C.green : C.pink, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                {isApto ? 'Apto' : 'No apto'}
              </span>
            </div>
            {/* Path */}
            <span style={{ fontFamily: C.MONO, fontSize: 12, color: 'rgba(172,246,255,0.6)', cursor: 'default' }}>
              landa.sys/dossier/{lead._id.slice(-8).toUpperCase()}
            </span>
          </div>
          <button onClick={onClose} style={{
            width: 28, height: 28, border: 'none', background: 'transparent',
            color: C.faint, cursor: 'pointer', fontSize: 18, lineHeight: 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 4,
            transition: 'color 0.15s',
          }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = C.text; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = C.faint; }}
          >✕</button>
        </div>

        {/* ── Body (scrollable) ── */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '28px 28px 8px', display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Identity + score */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <h2 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 26, letterSpacing: '-0.03em', color: C.text, lineHeight: 1.1 }}>
                Lead Dossier: <span style={{ color: C.cyan }}>{apellido}</span>
              </h2>
              <div style={{ fontFamily: C.SG, fontSize: 9, color: C.faint, textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 6 }}>
                Expediente ID: #{lead._id.slice(-12).toUpperCase()}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 16 }}>
                {chips.map(c => <Chip key={c} text={c} />)}
              </div>
            </div>
            {lead.score !== null && <ScoreGauge score={score} />}
          </div>

          {/* Decisor */}
          <div>
            <SectionLabel text="El Decisor" />
            <div style={{
              display: 'flex', alignItems: 'center', gap: 16,
              padding: '16px 20px', background: '#1e1e2e', borderRadius: 10,
              border: '1px solid rgba(120,220,232,0.06)',
              transition: 'border-color 0.2s',
            }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(120,220,232,0.2)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'rgba(120,220,232,0.06)'; }}
            >
              {/* Avatar */}
              <div style={{
                width: 56, height: 56, borderRadius: '50%', flexShrink: 0,
                background: `linear-gradient(135deg,${C.s3},${C.s4})`,
                border: `2px solid rgba(120,220,232,0.2)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: C.SG, fontWeight: 700, fontSize: 20, color: C.cyan,
              }}>
                {nombre ? nombre[0].toUpperCase() : initial}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 16, color: C.cyan }}>
                  {nombre || lead.company_name}
                </div>
                {cargo && (
                  <div style={{ fontFamily: C.IN, fontSize: 13, color: 'rgba(227,224,241,0.65)', marginTop: 2 }}>
                    {cargo}
                  </div>
                )}
                {emailDecispr && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, fontFamily: C.IN, fontSize: 11, color: C.faint }}>
                    @ {emailDecispr}
                  </div>
                )}
              </div>
              <a href={lead.url} target="_blank" rel="noreferrer" style={{ color: C.faint, fontSize: 18, textDecoration: 'none', transition: 'color 0.15s' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = C.cyan; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = C.faint; }}
              >↗</a>
            </div>
          </div>

          {/* 2-col insights */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div style={{ padding: '16px', background: 'rgba(27,26,38,0.5)', borderRadius: 8, border: '1px solid rgba(62,73,74,0.2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <span style={{ fontSize: 14 }}>✦</span>
                <span style={{ fontFamily: C.SG, fontSize: 9, fontWeight: 700, color: C.faint, textTransform: 'uppercase', letterSpacing: '0.15em' }}>Resumen</span>
              </div>
              <p style={{ fontFamily: C.IN, fontSize: 12, lineHeight: 1.65, color: 'rgba(227,224,241,0.75)' }}>
                {resumen}
              </p>
            </div>
            <div style={{ padding: '16px', background: 'rgba(27,26,38,0.5)', borderRadius: 8, border: '1px solid rgba(62,73,74,0.2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <span style={{ fontSize: 14, color: C.green }}>◈</span>
                <span style={{ fontFamily: C.SG, fontSize: 9, fontWeight: 700, color: C.faint, textTransform: 'uppercase', letterSpacing: '0.15em' }}>Dolor operativo</span>
              </div>
              <p style={{ fontFamily: C.IN, fontSize: 12, lineHeight: 1.65, color: 'rgba(227,224,241,0.75)' }}>
                {dolor || (techStack ? `Stack: ${techStack}` : 'Sin datos de dolor operativo detectados.')}
              </p>
            </div>
          </div>

          {/* Email draft */}
          {(asunto || cuerpo) && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <SectionLabel text="Borrador de outreach" />
                <button onClick={copyDraft} style={{
                  display: 'flex', alignItems: 'center', gap: 6, border: 'none', background: 'transparent',
                  fontFamily: C.SG, fontSize: 9, fontWeight: 700, color: copied ? C.green : C.cyan,
                  textTransform: 'uppercase', letterSpacing: '0.12em', cursor: 'pointer', transition: 'color 0.2s',
                }}>
                  {copied ? '✓ Copiado' : '⎘ Copiar borrador'}
                </button>
              </div>
              <div style={{
                position: 'relative', background: C.bg, padding: '20px 24px',
                borderRadius: 8, border: '1px solid rgba(62,73,74,0.4)',
                fontFamily: C.MONO, fontSize: 12, lineHeight: 1.75,
                color: 'rgba(227,224,241,0.85)',
              }}>
                {asunto && (
                  <p style={{ color: 'rgba(120,220,232,0.6)', marginBottom: 16 }}>
                    Asunto: {asunto}
                  </p>
                )}
                {cuerpo.split(/\\n\\n|\n\n/).map((p, i) => (
                  <p key={i} style={{ marginBottom: 12 }}>{p}</p>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* ── Footer ── */}
        <div style={{
          display: 'flex', gap: 12, padding: '20px 28px',
          background: 'rgba(41,41,53,0.3)',
          borderTop: '1px solid rgba(255,255,255,0.05)',
        }}>
          {lead.hitl_status === 'pending' && (
            <>
              <button onClick={doReject} style={{
                flex: 1, padding: '12px', border: '1px solid rgba(62,73,74,0.6)',
                borderRadius: 6, background: C.s2, cursor: 'pointer',
                fontFamily: C.SG, fontWeight: 700, fontSize: 11, color: C.text,
                textTransform: 'uppercase', letterSpacing: '0.1em',
                transition: 'background 0.15s',
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.s3; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = C.s2; }}
              >
                Descartar
              </button>
              <button onClick={doApprove} style={{
                flex: 1, padding: '12px', border: 'none', borderRadius: 6,
                background: C.grad, cursor: 'pointer',
                fontFamily: C.SG, fontWeight: 700, fontSize: 11, color: '#fff',
                textTransform: 'uppercase', letterSpacing: '0.1em',
                boxShadow: '0 4px 16px rgba(6,182,212,0.25)',
                transition: 'opacity 0.15s',
              }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '0.9'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
              >
                Aprobar ↗
              </button>
            </>
          )}
          {lead.hitl_status !== 'pending' && (
            <button onClick={onClose} style={{
              flex: 1, padding: '12px', border: '1px solid rgba(62,73,74,0.4)',
              borderRadius: 6, background: 'transparent', cursor: 'pointer',
              fontFamily: C.SG, fontWeight: 700, fontSize: 11, color: C.muted,
              textTransform: 'uppercase', letterSpacing: '0.1em',
            }}>
              Cerrar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
