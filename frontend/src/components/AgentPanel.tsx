import { useState, useRef, useEffect } from 'react';
import { useOfficeStore } from '../store/officeStore';
import type { Lead as StoreLead } from '../store/officeStore';
import type { AgentRole } from '../types';
import { CheckpointModal } from './CheckpointModal';
import { HandoverModal } from './HandoverModal';
import { apiFetch } from '../lib/apiFetch';

const API_URL = '';

interface AgentPanelProps {
  createAgent: (name: string, role: string) => void;
  runTask: (agentId: string, task: string) => void;
  startProspect: (campaign: Record<string, string>, max_results: number) => void;
  approveLead: (leadId: string | undefined, url: string) => void;
  rejectLead: (leadId: string | undefined, url: string) => void;
}

const ROLE_ICONS: Record<AgentRole, string> = {
  coder: '👨‍💻', researcher: '🔬', writer: '✍️', reviewer: '🔍', planner: '📋',
  voice: '📞', secop: '🏛️',
};
const STATE_LABELS: Record<string, { label: string; color: string }> = {
  idle:     { label: 'Idle',       color: '#888' },
  thinking: { label: 'Pensando...', color: '#ffd866' },
  tool_use: { label: 'Trabajando', color: '#78dce8' },
  waiting:  { label: 'Listo',      color: '#a9dc76' },
  error:    { label: 'Error',      color: '#ff6188' },
};

const CAMPAIGN_LABELS: Record<string, string> = {
  nombre_remitente:      'Remitente',
  empresa_remitente:     'Empresa',
  sector_propio_cliente: 'Nuestro sector (excluir competidores)',
  industria_objetivo:    'Industria objetivo',
  ciudad_objetivo:       'Ciudad',
  dolor_operativo:       'Dolor operativo',
  solucion_ofrecida:     'Solución ofrecida',
  software_clave:        'Software clave',
  jerarquia_decisores:   'Jerarquía de decisores',
};

const DEFAULT_CAMPAIGN = {
  nombre_remitente: 'Maximiliano Pulido',
  empresa_remitente: 'Lambda',
  sector_propio_cliente: 'tecnología, software, inteligencia artificial',
  industria_objetivo: 'Logística y Transporte',
  ciudad_objetivo: 'Bogotá',
  dolor_operativo: 'gestión manual de rutas y despachos',
  solucion_ofrecida: 'automatización de operaciones logísticas con IA',
  software_clave: 'SAP, Excel, WhatsApp Business, TMS',
  jerarquia_decisores: 'Gerente General > Director de Operaciones > Jefe de Logística',
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  const color = score >= 90 ? '#a9dc76' : score >= 70 ? '#ffd866' : '#ff6188';
  return (
    <span style={{ background: color, color: '#000', borderRadius: 4,
      padding: '2px 7px', fontSize: 12, fontWeight: 700 }}>
      {score}
    </span>
  );
}

const REJECTION_LABELS: Record<string, string> = {
  MICRO_BUSINESS_LOW_BUDGET: 'Micro-negocio sin presupuesto',
  LOW_SCORE_QUALIFICATION: 'Puntaje insuficiente',
  WRONG_SECTOR_OR_NO_DATA: 'No coincide con el sector objetivo o falta evidencia',
  SCRAPING_BLOCKED: 'No fue posible acceder al sitio web para analizarlo',
  KILL_DIRECT_COMPETITOR: 'Competidor directo',
  KILL_INFORMAL_BUSINESS: 'Negocio informal sin presencia seria',
  NO_B2B_PROFILE: 'No es perfil B2B',
  KILL_TOO_SMALL: 'Empresa demasiado pequeña',
  NO_CLEAR_OPERATIONAL_PAIN: 'No se detectó dolor operativo relevante',
  NO_DECISION_MAKER_CONTACT: 'No se encontró contacto de decisor',
  PARSE_ERROR: 'Error al interpretar la respuesta del modelo',
};

function WhyCandidateBlock({ payload, status }: {
  payload: Record<string, unknown> | null;
  status: string;
}) {
  if (!payload) return <div style={wb.container}><div style={{ color: '#555', fontSize: 12 }}>Sin datos de análisis</div></div>;
  // If JSON parsing failed we only have { raw: "..." }
  if (payload.raw && Object.keys(payload).length === 1) {
    return <div style={wb.container}><div style={{ color: '#666', fontSize: 11, fontStyle: 'italic' }}>El modelo no devolvió JSON estructurado para este resultado.</div></div>;
  }

  if (status === 'rejected') {
    const motivoRaw =
      payload.motivo_descalificacion_texto ??
      payload.motivo_descalificacion ??
      payload.motivo ??
      payload.reason ??
      payload.razon_sector ??
      payload.error;
    const motivo = typeof motivoRaw === 'string' ? motivoRaw.trim() : '';

    const evidenciaRaw =
      payload.evidencia_encontrada ??
      payload.evidencia ??
      payload.razon_tamano ??
      payload.evidencia_dolor ??
      payload.analisis_previo ??
      payload.detalle ??
      payload.observacion;
    const evidencia = typeof evidenciaRaw === 'string' ? evidenciaRaw.trim() : '';

    const motivoLabel = motivo
      ? (REJECTION_LABELS[motivo] || motivo)
      : 'Sin motivo detallado en este análisis';

    return (
      <div style={wb.container}>
        <div style={wb.title}>❌ Por qué fue descartado</div>
        <div style={wb.rejectReason}>{motivoLabel}</div>
        {evidencia && <div style={wb.evidence}>"{evidencia}"</div>}
      </div>
    );
  }

  // SUCCESS — show scoring factors
  const dt = payload.datos_tecnicos as Record<string, unknown> | null;
  const perfil = dt?.perfil as string;
  const tech = dt?.tech_stack as string;
  const enZona = payload.es_visitable_zona_objetivo as boolean;
  const decisor = payload.decisor as Record<string, unknown> | null;
  const email = decisor?.email as string;
  const hasNominal = email && !['contacto@', 'info@', 'ventas@', 'hola@', 'admin@'].some(x => email.includes(x));

  const factors: { label: string; pts: string; good: boolean }[] = [
    { label: 'Validación B2B base', pts: '+20', good: true },
    perfil === 'B'
      ? { label: 'Dolor operativo alto detectado', pts: '+30', good: true }
      : { label: 'Perfil A (dolor leve)', pts: '+25', good: true },
    tech && tech !== 'No detectado'
      ? { label: `Tech stack: ${tech}`, pts: '+30', good: true }
      : { label: 'Sin software clave detectado', pts: '+0', good: false },
    { label: enZona ? 'En ciudad objetivo' : 'Fuera de ciudad objetivo', pts: enZona ? '+10' : '+0', good: enZona },
    hasNominal
      ? { label: 'Email directo identificado', pts: '+10', good: true }
      : { label: 'Solo email genérico', pts: '+5', good: false },
  ];

  return (
    <div style={wb.container}>
      <div style={wb.title}>Por qué es un buen candidato</div>
      {factors.map((f, i) => (
        <div key={i} style={wb.factor}>
          <span style={{ color: f.good ? '#a9dc76' : '#888' }}>{f.good ? '✓' : '·'}</span>
          <span style={{ flex: 1, color: f.good ? '#ccc' : '#666', fontSize: 12 }}>{f.label}</span>
          <span style={{ color: f.good ? '#ffd866' : '#555', fontWeight: 600, fontSize: 12 }}>{f.pts}</span>
        </div>
      ))}
    </div>
  );
}

const wb: Record<string, React.CSSProperties> = {
  container: { background: '#12121d', borderRadius: 7, padding: '10px 12px', marginTop: 8, display: 'flex', flexDirection: 'column', gap: 5, border: '1px solid rgba(62,73,74,0.2)' },
  title: { color: '#ab9df2', fontSize: 10, fontWeight: 700, fontFamily: "'Space Grotesk',system-ui,sans-serif", textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 },
  factor: { display: 'flex', alignItems: 'center', gap: 6 },
  rejectReason: { color: '#ff6188', fontWeight: 700, fontSize: 13 },
  evidence: { color: '#8a8a9a', fontSize: 12, fontStyle: 'italic', marginTop: 2 },
};

function LeadCard({ lead, onApprove, onDiscard }: {
  lead: StoreLead;
  onApprove: () => void;
  onDiscard: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const payload = lead.json_payload as Record<string, unknown> | null;
  const score = payload?.score != null ? Number(payload.score) : null;
  const empresa = payload?.empresa as string || lead.title;
  const decisor = payload?.decisor as Record<string, unknown> | null;
  const emailBody = (payload?.borradores as Record<string, unknown>)?.email_cuerpo as string;
  const resumenEmpresa = (payload?.resumen_empresa as string) || (payload?.resumen as string) || '';
  const fuentesConsultadas = Array.isArray(payload?.fuentes_consultadas)
    ? (payload?.fuentes_consultadas as unknown[])
      .filter((src): src is string => typeof src === 'string' && /^https?:\/\//.test(src))
    : [];
  const fuentesUnicas = Array.from(new Set(fuentesConsultadas));

  const statusColor = lead.status === 'success' ? '#a9dc76'
    : lead.status === 'rejected' ? '#ff6188' : '#888';

  return (
    <div style={{
      ...s.leadCard,
      borderColor: lead.approved === true ? '#a9dc76'
        : lead.approved === false ? '#ff618844' : 'transparent',
      opacity: lead.approved === false ? 0.5 : 1,
    }}>
      {/* Row — clickable for ALL statuses */}
      <div style={{ ...s.leadRow, cursor: lead.status !== 'error' ? 'pointer' : 'default' }}
        onClick={() => lead.status !== 'error' && setExpanded(v => !v)}>
        <div style={{ ...s.leadDot, background: statusColor }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={s.leadTitle}>{empresa}</div>
          <div style={s.leadUrl}>{lead.url.replace(/^https?:\/\//, '').slice(0, 40)}</div>
        </div>
        {score !== null && <ScoreBadge score={score} />}
        {lead.status === 'rejected' && !expanded && (
          <span style={{ fontSize: 10, color: '#ff6188' }}>▼ ver motivo</span>
        )}
        {lead.status === 'success' && lead.approved === null && (
          <div style={s.leadActions}>
            <button style={s.approveBtn} onClick={e => { e.stopPropagation(); onApprove(); }}>✓</button>
            <button style={s.discardBtn} onClick={e => { e.stopPropagation(); onDiscard(); }}>✗</button>
          </div>
        )}
        {lead.approved === true && <span style={s.approvedTag}>Aprobado</span>}
        {lead.approved === false && <span style={s.discardedTag}>Descartado</span>}
      </div>

      {/* Expanded detail — works for success AND rejected */}
      {expanded && lead.status !== 'error' && (
        <div style={s.leadDetail}>
          {/* Always show "why" first — most important info */}
          <WhyCandidateBlock payload={payload} status={lead.status} />

          {resumenEmpresa && (
            <div style={s.detailBlock}>
              <div style={s.detailLabel}>Resumen de empresa</div>
              <div style={s.summaryText}>{resumenEmpresa}</div>
            </div>
          )}

          {fuentesUnicas.length > 0 && (
            <div style={s.detailBlock}>
              <div style={s.detailLabel}>Fuentes consultadas</div>
              <div style={s.sourceList}>
                {fuentesUnicas.map((source) => (
                  <a
                    key={source}
                    href={source}
                    target="_blank"
                    rel="noreferrer"
                    style={s.sourceLink}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {source.replace(/^https?:\/\//, '')}
                  </a>
                ))}
              </div>
            </div>
          )}

          {lead.status === 'success' && (
            <>
              {(lead.phone || lead.address) && (
                <div style={s.detailBlock}>
                  {lead.phone && <div style={{ color: '#a9dc76', fontSize: 12 }}>📞 {lead.phone}</div>}
                  {lead.address && <div style={{ color: '#888', fontSize: 11 }}>📍 {lead.address}</div>}
                </div>
              )}
              {decisor && (
                <div style={s.detailBlock}>
                  <div style={s.detailLabel}>Decisor</div>
                  <div style={s.detailValue}>
                    {String(decisor.nombre ?? '')} · {String(decisor.cargo ?? '')}
                  </div>
                  {!!decisor.email && (
                    <div style={{ color: '#78dce8', fontSize: 12 }}>✉ {String(decisor.email)}</div>
                  )}
                </div>
              )}
              {emailBody && (
                <div style={s.detailBlock}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={s.detailLabel}>Borrador de correo</div>
                    <button style={s.copyBtn} onClick={() => navigator.clipboard.writeText(emailBody)}>
                      📋 Copiar
                    </button>
                  </div>
                  <div style={s.emailBox}>
                    {emailBody.split(/\\n\\n|\n\n/).map((p, i) =>
                      <p key={i} style={{ margin: '0 0 8px 0' }}>{p}</p>
                    )}
                  </div>
                </div>
              )}
              {lead.approved === null && (
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  <button style={s.approveFullBtn} onClick={onApprove}>✅ Aprobar lead</button>
                  <button style={s.discardFullBtn} onClick={onDiscard}>❌ Descartar</button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── NL Prospect Input ─────────────────────────────────────────────────────────

function NLProspectInput({
  onExtracted,
  onClarification,
}: {
  onExtracted: (campaign: Record<string, unknown>) => void;
  onClarification: (reply: string) => void;
}) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const msg = text.trim();
    if (!msg || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`${API_URL}/api/chat/prospect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      });
      if (!res.ok) {
        setError('Error de conexión. Intenta de nuevo.');
        return;
      }
      const body = await res.json();
      if (body.status === 'extracted' && body.campaign) {
        onExtracted(body.campaign);
      } else if (body.status === 'needs_clarification') {
        onClarification(body.reply || 'No pude extraer todos los parámetros. ¿Puedes agregar más detalle?');
      } else {
        setError('No pude extraer todos los parámetros. ¿Puedes agregar más detalle?');
      }
    } catch {
      setError('Error de conexión. Intenta de nuevo.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 22, fontWeight: 600, fontFamily: "'Space Grotesk', system-ui, sans-serif", color: '#e3e0f1', marginBottom: 8 }}>
        Configurar Campaña
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ej: busca propietarios arrendando en Bogotá..."
          rows={3}
          disabled={loading}
          style={{
            flex: 1,
            background: '#1b1a26',
            border: 'none',
            borderBottom: '1px solid rgba(120,220,232,0.2)',
            borderRadius: 6,
            padding: '8px 12px',
            color: '#e3e0f1',
            fontSize: 13,
            fontFamily: "'Space Grotesk', system-ui, sans-serif",
            resize: 'none',
            outline: 'none',
            opacity: loading ? 0.6 : 1,
          }}
        />
        <button
          onClick={submit}
          disabled={loading || !text.trim()}
          aria-label="Enviar descripción"
          style={{
            background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)',
            border: 'none',
            borderRadius: 6,
            padding: '8px 16px',
            color: '#fff',
            fontSize: 14,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading || !text.trim() ? 0.5 : 1,
            fontFamily: "'Space Grotesk', system-ui, sans-serif",
          }}
        >
          {loading ? '...' : '➤'}
        </button>
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'rgba(227,224,241,0.35)', fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
        Describe en una frase a quién quieres prospectar
      </div>
      {error && (
        <div style={{ fontSize: 13, color: '#ff6188', fontFamily: "'Space Grotesk', system-ui, sans-serif", marginTop: 4 }}>
          {error}
        </div>
      )}
    </div>
  );
}

function ExtractedParamsCard({ campaign }: { campaign: Record<string, unknown> }) {
  const fields: Array<[string, string]> = [
    ['Industria', String(campaign.industria_objetivo || '')],
    ['Ciudad', String(campaign.ciudad_objetivo || '')],
    ['Remitente', String(campaign.nombre_remitente || '')],
    ['Empresa', String(campaign.empresa_remitente || '')],
    ['Dolor', String(campaign.dolor_operativo || '')],
    ['Solución', String(campaign.solucion_ofrecida || '')],
    ['Software clave', String(campaign.software_clave || '')],
    ['Decisores', String(campaign.jerarquia_decisores || '')],
  ];
  const filledCount = fields.filter(([, v]) => v && v.trim()).length;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#ab9df2', fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
          Parámetros extraídos
        </div>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#78dce8', fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
          {filledCount} campos
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {fields.map(([label, value]) => (
          <div key={label} style={{ background: '#12121d', borderRadius: 8, padding: '8px 12px', border: '1px solid rgba(120,220,232,0.05)' }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: 'rgba(227,224,241,0.35)', fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
              {label}
            </div>
            <div style={{ fontSize: 14, color: value ? '#e3e0f1' : 'rgba(227,224,241,0.25)', fontFamily: "'Space Grotesk', system-ui, sans-serif", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {value || '—'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Knowledge Base Panel ──────────────────────────────────────────────────────

function KnowledgeBasePanel() {
  const [expanded, setExpanded] = useState(false);
  const [value, setValue] = useState('');
  const [originalValue, setOriginalValue] = useState('');
  const [approvedCount, setApprovedCount] = useState(0);
  const [rejectedCount, setRejectedCount] = useState(0);
  const [labelState, setLabelState] = useState<'idle' | 'saved' | 'error'>('idle');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch(`${API_URL}/api/knowledge`, { method: 'GET' });
        if (!res.ok || cancelled) return;
        const body = await res.json();
        setValue(body.product_description || '');
        setOriginalValue(body.product_description || '');
        setApprovedCount((body.approved_lead_signals || []).length);
        setRejectedCount((body.rejected_lead_signals || []).length);
      } catch {
        // silent — panel is non-critical
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const handleBlur = async () => {
    if (value === originalValue) return;  // no change
    try {
      const res = await apiFetch(`${API_URL}/api/knowledge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_description: value }),
      });
      if (res.ok) {
        setOriginalValue(value);
        setLabelState('saved');
        setTimeout(() => setLabelState('idle'), 1500);
      } else {
        setLabelState('error');
        setTimeout(() => setLabelState('idle'), 2000);
      }
    } catch {
      setLabelState('error');
      setTimeout(() => setLabelState('idle'), 2000);
    }
  };

  const hasSignals = approvedCount > 0 || rejectedCount > 0;
  const badgeText = hasSignals
    ? `${approvedCount} aprobados · ${rejectedCount} rechazados`
    : 'Sin señales aún';

  const fieldLabelColor = labelState === 'saved' ? '#a9dc76' : labelState === 'error' ? '#ff6188' : 'rgba(227,224,241,0.4)';
  const fieldLabelText = labelState === 'saved' ? 'Guardado ✓' : labelState === 'error' ? 'Error al guardar' : 'Tu producto / ICP';

  return (
    <div style={{ background: '#12121d', borderRadius: 10, padding: '12px 14px', marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: '#ab9df2', fontFamily: "'Space Grotesk', system-ui, sans-serif" }}>
          Base de conocimiento
        </div>
        <div style={{
          fontSize: 11,
          fontFamily: "'Space Grotesk', system-ui, sans-serif",
          color: 'rgba(227,224,241,0.4)',
          border: '1px solid rgba(120,220,232,0.15)',
          borderRadius: 4,
          padding: '4px 8px',
          background: 'rgba(120,220,232,0.04)',
        }}>
          {badgeText}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'rgba(227,224,241,0.35)',
            fontSize: 11,
            cursor: 'pointer',
            fontFamily: "'Space Grotesk', system-ui, sans-serif",
          }}
        >
          {expanded ? '↑ Ocultar' : '▼ Expandir'}
        </button>
      </div>
      {expanded && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: fieldLabelColor, fontFamily: "'Space Grotesk', system-ui, sans-serif", marginBottom: 6 }}>
            {fieldLabelText}
          </div>
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onBlur={handleBlur}
            placeholder="Describe tu producto, a quién le vendes y qué dolor resuelve..."
            rows={4}
            style={{
              width: '100%',
              background: '#1b1a26',
              border: 'none',
              borderBottom: '1px solid rgba(120,220,232,0.2)',
              borderRadius: 6,
              padding: '8px 12px',
              color: '#e3e0f1',
              fontSize: 13,
              fontFamily: "'Space Grotesk', system-ui, sans-serif",
              resize: 'vertical',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>
      )}
    </div>
  );
}

// ── Campaign Chat ─────────────────────────────────────────────────────────────

interface ChatMessage { role: 'user' | 'assistant'; content: string }

function CampaignChat({ onCampaignReady, resetKey }: {
  onCampaignReady: (campaign: Record<string, string>) => void;
  resetKey: number;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [started, setStarted] = useState(false);

  // Reset chat when resetKey changes
  useEffect(() => {
    setMessages([]);
    setInput('');
    setLoading(false);
    setStarted(false);
  }, [resetKey]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMessage = { role: 'user', content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    setLoading(true);

    try {
      // apiFetch sends httpOnly cookie automatically via credentials:'include'
      const res = await apiFetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next }),
      });
      const data = await res.json();
      const reply: string = data.reply || '';

      // Check for CAMPAIGN_READY signal
      if (reply.includes('CAMPAIGN_READY:')) {
        const jsonStart = reply.indexOf('{', reply.indexOf('CAMPAIGN_READY:'));
        if (jsonStart !== -1) {
          // Find matching closing brace
          let depth = 0, jsonEnd = -1;
          for (let i = jsonStart; i < reply.length; i++) {
            if (reply[i] === '{') depth++;
            else if (reply[i] === '}') { depth--; if (depth === 0) { jsonEnd = i; break; } }
          }
          if (jsonEnd !== -1) {
            try {
              const campaign = JSON.parse(reply.slice(jsonStart, jsonEnd + 1));
              const cleanReply = reply.slice(0, reply.indexOf('CAMPAIGN_READY:')).trim();
              setMessages(prev => [...prev, { role: 'assistant', content: cleanReply || '¡Listo! Tengo todo lo que necesito.' }]);
              onCampaignReady(campaign);
              return;
            } catch { /* fallthrough */ }
          }
        }
      }

      setMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error de conexión. Intenta de nuevo.' }]);
    } finally {
      setLoading(false);
    }
  };

  const startChat = () => {
    setStarted(true);
    setLoading(true);
    // Trigger first AI message — cookie auth handled by apiFetch
    (async () => {
      try {
        const res = await apiFetch(`${API_URL}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: [] }),
        });
        const data = await res.json();
        setMessages([{ role: 'assistant', content: data.reply }]);
      } catch {
        setMessages([{ role: 'assistant', content: '¡Hola! Soy tu configurador de campañas. ¿Cuál es tu nombre y empresa?' }]);
      } finally {
        setLoading(false);
      }
    })();
  };

  if (!started) {
    return (
      <div style={cc.startBox}>
        <div style={cc.startIcon}>🤖</div>
        <div style={cc.startTitle}>Configura tu campaña con IA</div>
        <div style={cc.startDesc}>
          Cuéntame sobre tu negocio y te haré las preguntas necesarias para configurar la búsqueda automáticamente.
        </div>
        <button style={cc.startBtn} onClick={startChat}>
          Comenzar →
        </button>
      </div>
    );
  }

  return (
    <div style={cc.container}>
      <div style={cc.messages}>
        {messages.map((m, i) => (
          <div key={i} style={{ ...cc.bubble, ...(m.role === 'user' ? cc.bubbleUser : cc.bubbleAI) }}>
            {m.content}
          </div>
        ))}
        {loading && (
          <div style={{ ...cc.bubble, ...cc.bubbleAI, color: '#888' }}>...</div>
        )}
        <div ref={bottomRef} />
      </div>
      <div style={cc.inputRow}>
        <input
          style={cc.input}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send(input)}
          placeholder="Escribe tu respuesta..."
          disabled={loading}
          autoFocus
        />
        <button style={cc.sendBtn} onClick={() => send(input)} disabled={loading || !input.trim()}>
          ➤
        </button>
      </div>
    </div>
  );
}

const cc: Record<string, React.CSSProperties> = {
  startBox: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    gap: 16, padding: '32px 20px', textAlign: 'center',
  },
  startIcon: { fontSize: 36, lineHeight: '1' },
  startTitle: {
    color: '#e3e0f1', fontWeight: 700, fontSize: 16,
    fontFamily: "'Space Grotesk', system-ui, sans-serif", letterSpacing: '-0.02em',
  },
  startDesc: { color: 'rgba(227,224,241,0.45)', fontSize: 13, lineHeight: 1.6, maxWidth: 280 },
  startBtn: {
    padding: '10px 28px', border: 'none', borderRadius: 6,
    background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)',
    color: '#fff', fontWeight: 700, fontSize: 13, cursor: 'pointer',
    fontFamily: "'Space Grotesk', system-ui, sans-serif", letterSpacing: '0.02em',
    boxShadow: '0 4px 20px rgba(120,220,232,0.15)',
  },
  container: { display: 'flex', flexDirection: 'column', height: 320, gap: 8 },
  messages: {
    flex: 1, overflowY: 'auto', display: 'flex',
    flexDirection: 'column', gap: 8, padding: '4px 0',
  },
  bubble: {
    maxWidth: '85%', padding: '9px 13px', borderRadius: 10,
    fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
  },
  bubbleAI: { background: '#22212e', color: '#e3e0f1', alignSelf: 'flex-start' },
  bubbleUser: { background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)', color: '#fff', alignSelf: 'flex-end' },
  inputRow: { display: 'flex', gap: 6 },
  input: {
    flex: 1, padding: '9px 13px', border: 'none',
    borderBottom: '1px solid rgba(120,220,232,0.25)',
    background: '#1b1a26', color: '#e3e0f1', fontSize: 13, borderRadius: 6, outline: 'none',
  },
  sendBtn: {
    padding: '9px 15px', border: 'none', borderRadius: 6,
    background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)',
    color: '#fff', cursor: 'pointer', fontSize: 14,
  },
};

// ── Leads Chat ────────────────────────────────────────────────────────────────

interface ChatMsg { role: 'user' | 'assistant'; content: string }
interface ChatIntent { type: string; payload: Record<string, string>; proposal: string | null }

const INTENT_COLORS: Record<string, string> = {
  refine_target:    '#ffd866',
  adjust_tone:      '#ab9df2',
  blacklist_company:'#ff6188',
  clone_lead:       '#78dce8',
  campaign_feedback:'#a9dc76',
  none:             'transparent',
};
const INTENT_LABELS: Record<string, string> = {
  refine_target:    '🎯 Ajustar objetivo',
  adjust_tone:      '✍️ Tono de correo',
  blacklist_company:'🚫 Excluir empresa',
  clone_lead:       '🔁 Buscar similares',
  campaign_feedback:'📊 Feedback campaña',
};

function LeadsChat() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [intents, setIntents] = useState<Record<number, ChatIntent>>({});
  const [applied, setApplied] = useState<Record<number, boolean>>({});
  const [applying, setApplying] = useState<Record<number, boolean>>({});
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { setActiveCampaign } = useOfficeStore();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const applyIntent = async (idx: number, intent: ChatIntent) => {
    setApplying(prev => ({ ...prev, [idx]: true }));
    try {
      const res = await apiFetch(`${API_URL}/api/campaign/apply-intent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent_type: intent.type, payload: intent.payload }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.campaign) setActiveCampaign(data.campaign);
        setApplied(prev => ({ ...prev, [idx]: true }));
      }
    } finally {
      setApplying(prev => ({ ...prev, [idx]: false }));
    }
  };

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMsg = { role: 'user', content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    setLoading(true);

    try {
      const res = await apiFetch(`${API_URL}/api/chat/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next }),
      });
      const data = await res.json();
      const replyMsg: ChatMsg = { role: 'assistant', content: data.reply || '' };
      const newMessages = [...next, replyMsg];
      setMessages(newMessages);
      if (data.intent && data.intent.type !== 'none') {
        setIntents(prev => ({ ...prev, [newMessages.length - 1]: data.intent }));
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error de conexión. Intenta de nuevo.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={lc.container}>
      <div style={lc.intro}>
        <span style={{ fontSize: 16 }}>🐝</span>
        <span style={lc.introText}>Cuéntame qué piensas sobre los resultados. ¿Qué cambiarías?</span>
      </div>
      <div style={lc.messages}>
        {messages.length === 0 && !loading && (
          <div style={lc.suggestions}>
            {['¿Por qué rechazaste empresas?', 'Busca más como las aprobadas', 'El tono es muy corporativo'].map(s => (
              <button key={s} style={lc.suggestion} onClick={() => send(s)}>{s}</button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i}>
            <div style={{ ...lc.bubble, ...(m.role === 'user' ? lc.bubbleUser : lc.bubbleAI) }}>
              {m.content}
            </div>
            {intents[i] && (
              <div style={{ ...lc.intentBadge, borderColor: INTENT_COLORS[intents[i].type] || '#888' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: INTENT_COLORS[intents[i].type], fontSize: 11 }}>
                    {INTENT_LABELS[intents[i].type] || intents[i].type}
                  </span>
                  {!applied[i] && intents[i].proposal && intents[i].type !== 'campaign_feedback' && intents[i].type !== 'clone_lead' && (
                    <button
                      style={{ ...lc.applyBtn, opacity: applying[i] ? 0.5 : 1 }}
                      disabled={!!applying[i]}
                      onClick={() => applyIntent(i, intents[i])}
                    >
                      {applying[i] ? '...' : 'Aplicar ✓'}
                    </button>
                  )}
                  {applied[i] && <span style={{ color: '#a9dc76', fontSize: 11 }}>✓ Aplicado</span>}
                </div>
                {intents[i].proposal && (
                  <div style={lc.proposal}>{intents[i].proposal}</div>
                )}
              </div>
            )}
          </div>
        ))}
        {loading && <div style={{ ...lc.bubble, ...lc.bubbleAI, color: '#888' }}>...</div>}
        <div ref={bottomRef} />
      </div>
      <div style={lc.inputRow}>
        <input
          style={lc.input}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send(input)}
          placeholder="Escribe tu feedback..."
          disabled={loading}
        />
        <button style={lc.sendBtn} onClick={() => send(input)} disabled={loading || !input.trim()}>➤</button>
      </div>
    </div>
  );
}

const lc: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', gap: 8 },
  intro: { display: 'flex', alignItems: 'center', gap: 6, padding: '4px 0 2px' },
  introText: { color: 'rgba(227,224,241,0.4)', fontSize: 12 },
  messages: { flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 },
  suggestions: { display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 0' },
  suggestion: {
    padding: '8px 12px', background: '#1b1a26', border: 'none',
    borderRadius: 7, color: 'rgba(227,224,241,0.5)', cursor: 'pointer', fontSize: 12, textAlign: 'left',
    transition: 'background 0.15s',
  },
  bubble: {
    maxWidth: '90%', padding: '9px 12px', borderRadius: 9,
    fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
  },
  bubbleAI: { background: '#22212e', color: '#e3e0f1', alignSelf: 'flex-start' },
  bubbleUser: { background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)', color: '#fff', alignSelf: 'flex-end' },
  intentBadge: {
    background: '#12121d', borderRadius: 6, padding: '6px 10px',
    border: '1px solid', marginTop: 3, maxWidth: '90%',
  },
  proposal: { color: 'rgba(227,224,241,0.5)', fontSize: 11, marginTop: 4 },
  applyBtn: {
    padding: '3px 9px', border: 'none', borderRadius: 4,
    background: 'rgba(169,220,118,0.1)', color: '#a9dc76', cursor: 'pointer', fontSize: 11,
  },
  inputRow: { display: 'flex', gap: 6 },
  input: {
    flex: 1, padding: '9px 12px', border: 'none',
    borderBottom: '1px solid rgba(120,220,232,0.25)',
    background: '#1b1a26', color: '#e3e0f1', fontSize: 13, borderRadius: 6, outline: 'none',
  },
  sendBtn: {
    padding: '9px 14px', border: 'none', borderRadius: 6,
    background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)',
    color: '#fff', cursor: 'pointer', fontSize: 13,
  },
};


// ── Main panel ────────────────────────────────────────────────────────────────

function getSemanticWaitingText(agentName: string, checkpointCount: number): string {
  const name = agentName.toLowerCase();
  if (name.includes('investigador') || name.includes('buscador')) {
    return checkpointCount > 0
      ? `Tengo ${checkpointCount} candidato${checkpointCount > 1 ? 's' : ''} listos`
      : 'En espera';
  }
  if (name.includes('outreach') || name.includes('redactor')) {
    return 'Esperando respuesta';
  }
  if (name.includes('nurturing')) {
    return 'Monitoreando señales';
  }
  return 'Listo';
}

// ── Agent Log Modal ────────────────────────────────────────────────────────────

const ROLE_TO_LOG_KEY: Record<string, string> = {
  researcher: 'buscador',
  planner:    'buscador',
  reviewer:   'analista',
  writer:     'redactor',
};

const LOG_KEY_LABELS: Record<string, string> = {
  buscador: 'Buscador — Decisiones de Discovery',
  analista: 'Analista B2B — Decisiones por Empresa',
  redactor: 'Redactor — Scoring & Emails',
};

function AgentLogModal({ logKey, lines, onClose }: {
  logKey: string; lines: string[]; onClose: () => void;
}) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 2000, padding: 16,
    }} onClick={onClose}>
      <div style={{
        background: '#1e1e2e', border: '1px solid #363650',
        borderRadius: 12, padding: 20, maxWidth: 560, width: '100%',
        maxHeight: '80vh', display: 'flex', flexDirection: 'column', gap: 12,
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: '#78dce8', fontWeight: 700, fontSize: 13 }}>
            {LOG_KEY_LABELS[logKey] || logKey}
          </span>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#888',
            cursor: 'pointer', fontSize: 16, lineHeight: 1,
          }}>✕</button>
        </div>
        <div style={{
          overflowY: 'auto', flex: 1,
          fontFamily: 'monospace', fontSize: 12, color: '#ccc', lineHeight: 1.7,
        }}>
          {lines.length === 0
            ? <span style={{ color: '#555' }}>Sin datos aún — ejecuta una campaña primero.</span>
            : lines.map((line, i) => {
                const isApproved = line.startsWith('APROBADO');
                const isRejected = line.startsWith('RECHAZADO');
                const isSummary  = line.startsWith('RESUMEN') || line.startsWith('RESULTADO');
                const color = isApproved ? '#a9dc76' : isRejected ? '#ff6188' : isSummary ? '#ffd866' : '#ccc';
                return (
                  <div key={i} style={{ color, borderBottom: isSummary ? '1px solid #363650' : 'none', paddingBottom: isSummary ? 6 : 0 }}>
                    {line || '\u00a0'}
                  </div>
                );
              })
          }
        </div>
      </div>
    </div>
  );
}

// ── Signal Source Definitions ────────────────────────────────────────────────

const SIGNAL_SOURCES = [
  {
    id: 'serper',
    icon: '🌐',
    title: 'Búsqueda Web',
    description: 'Google + Bing: empresas en cualquier sector y ciudad',
    tag: 'Serper',
    tagColor: '#78dce8',
    tagBg: 'rgba(120,220,232,0.1)',
    alwaysOn: true,
  },
  {
    id: 'rues',
    icon: '🏢',
    title: 'Empresas recién creadas',
    description: 'Compañías registradas recientemente en Cámara de Comercio',
    tag: 'RUES',
    tagColor: '#ab9df2',
    tagBg: 'rgba(171,157,242,0.1)',
    alwaysOn: false,
  },
  {
    id: 'secop',
    icon: '📋',
    title: 'Contratistas del Estado',
    description: 'Proveedores con contratos públicos adjudicados (SECOP)',
    tag: 'SECOP',
    tagColor: '#ffd866',
    tagBg: 'rgba(255,216,102,0.1)',
    alwaysOn: false,
  },
  {
    id: 'fincaraiz',
    icon: '🏠',
    title: 'Propietarios con arriendo',
    description: 'Inmuebles en arriendo activo en Fincaraíz',
    tag: 'Fincaraíz',
    tagColor: '#a9dc76',
    tagBg: 'rgba(169,220,118,0.1)',
    alwaysOn: false,
  },
] as const;

function SignalSourceSelector({
  selected,
  onChange,
  disabled,
}: {
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  disabled?: boolean;
}) {
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  const activeCount = selected.size;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ marginBottom: 8 }}>
        <span style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif", fontSize: 11, fontWeight: 600, color: '#e3e0f1', letterSpacing: '0.02em' }}>
          ¿Cómo quieres encontrar prospectos?
        </span>
        <div style={{ fontSize: 11, color: 'rgba(227,224,241,0.4)', marginTop: 2 }}>
          Elige las fuentes de señales. Puedes combinar varias.
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {SIGNAL_SOURCES.map(src => {
          const isSelected = src.alwaysOn || selected.has(src.id);
          const cardBorder = src.alwaysOn
            ? '2px solid rgba(120,220,232,0.4)'
            : isSelected
            ? '2px solid #78dce8'
            : '2px solid transparent';
          const cardBg = isSelected ? '#1b1a26' : '#1b1a26';
          const cardShadow = isSelected && !src.alwaysOn ? '0 0 0 1px rgba(120,220,232,0.12)' : 'none';
          return (
            <button
              key={src.id}
              aria-pressed={isSelected}
              aria-disabled={src.alwaysOn || disabled}
              aria-label={`Señal ${src.title}: ${src.description}`}
              disabled={src.alwaysOn || disabled}
              onClick={() => !src.alwaysOn && !disabled && toggle(src.id)}
              style={{
                background: cardBg,
                border: cardBorder,
                boxShadow: cardShadow,
                borderRadius: 8,
                padding: '10px 12px',
                textAlign: 'left',
                cursor: src.alwaysOn || disabled ? 'default' : 'pointer',
                opacity: disabled && !src.alwaysOn ? 0.6 : 1,
                transition: 'border-color 0.15s, box-shadow 0.15s',
                minHeight: 44,
              }}
              onMouseEnter={e => {
                if (!src.alwaysOn && !disabled)
                  (e.currentTarget as HTMLButtonElement).style.background = '#22212e';
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLButtonElement).style.background = cardBg;
              }}
            >
              <div style={{ fontSize: 24, lineHeight: 1, marginBottom: 4 }}>{src.icon}</div>
              <div style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif", fontSize: 14, fontWeight: 600, color: '#e3e0f1', marginBottom: 2 }}>
                {src.title}
              </div>
              <div style={{ fontFamily: "'Inter', system-ui, sans-serif", fontSize: 13, color: 'rgba(227,224,241,0.5)', lineHeight: 1.5, marginBottom: 8 }}>
                {src.description}
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' as const }}>
                <span style={{
                  fontSize: 10, fontFamily: "'Space Grotesk', system-ui, sans-serif",
                  fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.06em',
                  padding: '2px 6px', borderRadius: 4,
                  color: src.tagColor, background: src.tagBg,
                }}>
                  {src.tag}
                </span>
                {src.alwaysOn && (
                  <span style={{ fontSize: 10, color: 'rgba(227,224,241,0.35)', alignSelf: 'center' }}>
                    Siempre activo
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
      {activeCount > 0 && (
        <div style={{ fontSize: 11, color: 'rgba(227,224,241,0.4)', marginTop: 6 }}>
          Fuentes seleccionadas: {['Búsqueda Web', ...SIGNAL_SOURCES.filter(s => !s.alwaysOn && selected.has(s.id)).map(s => s.title)].join(', ')}. La IA configurará la búsqueda.
        </div>
      )}
    </div>
  );
}

function SignalBadge({ selected }: { selected: Set<string> }) {
  const activeLabels = ['Búsqueda Web', ...SIGNAL_SOURCES.filter(s => !s.alwaysOn && selected.has(s.id)).map(s => s.title)];
  if (activeLabels.length === 0) return null;
  return (
    <div style={{ background: '#12121d', borderRadius: 8, padding: '10px 12px', border: '1px solid rgba(120,220,232,0.05)', gridColumn: '1 / -1', display: 'flex', flexWrap: 'wrap' as const, gap: 6, alignItems: 'center', marginBottom: 4 }}>
      <span style={{ fontFamily: "'Space Grotesk', system-ui, sans-serif", fontSize: 9, fontWeight: 600, color: 'rgba(227,224,241,0.35)', textTransform: 'uppercase' as const, letterSpacing: '0.1em', marginRight: 4 }}>
        FUENTES ACTIVAS:
      </span>
      {SIGNAL_SOURCES.filter(s => s.alwaysOn || selected.has(s.id)).map(src => (
        <span key={src.id} style={{
          fontSize: 10, fontFamily: "'Space Grotesk', system-ui, sans-serif",
          fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.06em',
          padding: '2px 6px', borderRadius: 4,
          color: src.tagColor, background: src.tagBg,
        }}>
          {src.tag}
        </span>
      ))}
    </div>
  );
}

export function AgentPanel({ startProspect, approveLead, rejectLead }: AgentPanelProps) {
  const {
    agents, connected, prospecting, leads, campaignSummary,
    activeTab, setActiveTab, clearLeads, activeCampaign,
    checkpointLeads, handoverLead, clearCheckpointLead, setHandoverLead,
    agentLogs,
  } = useOfficeStore();

  const [campaign, setCampaign] = useState<Record<string, string>>(DEFAULT_CAMPAIGN);
  const [maxResults, setMaxResults] = useState(20);
  const [campaignReady, setCampaignReady] = useState(false);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [showForm, setShowForm] = useState(false);
  const [chatResetKey, setChatResetKey] = useState(0);
  const [extractedCampaign, setExtractedCampaign] = useState<Record<string, unknown> | null>(null);
  const [clarificationReply, setClarificationReply] = useState<string | null>(null);
  const [showCheckpoint, setShowCheckpoint] = useState(false);
  const [showHandover, setShowHandover] = useState(false);
  const [agentLogModal, setAgentLogModal] = useState<{ logKey: string; lines: string[] } | null>(null);

  const handleAgentClick = (agentState: string, agentRole: string) => {
    // If there's a checkpoint/handover waiting, show that first
    if (agentState === 'waiting') {
      if (checkpointLeads.length > 0) { setShowCheckpoint(true); return; }
      if (handoverLead) { setShowHandover(true); return; }
    }
    // Otherwise show the agent's decision log
    const logKey = ROLE_TO_LOG_KEY[agentRole] || agentRole;
    const lines = agentLogs?.[logKey] || [];
    setAgentLogModal({ logKey, lines });
  };

  // Pre-fill campaign from DB when it loads (only once, when not yet manually configured)
  const didHydrate = useRef(false);
  useEffect(() => {
    if (activeCampaign && !campaignReady && !didHydrate.current) {
      didHydrate.current = true;
      setCampaign({ ...DEFAULT_CAMPAIGN, ...activeCampaign });
      setCampaignReady(true);
    }
  }, [activeCampaign, campaignReady]);

  const updateCampaign = (key: string, value: string) =>
    setCampaign(prev => ({ ...prev, [key]: value }));

  const handleCampaignReady = (extracted: Record<string, string>) => {
    setCampaign({ ...DEFAULT_CAMPAIGN, ...extracted });
    setCampaignReady(true);
  };

  const approvedLeads = leads.filter(l => l.approved === true);
  const pendingLeads  = leads.filter(l => l.status === 'success' && l.approved === null);
  const allResults    = leads.filter(l => l.status !== 'error');

  const tabCount = (tab: string) => {
    if (tab === 'results') return allResults.length || undefined;
    if (tab === 'approved') return approvedLeads.length || undefined;
    return undefined;
  };

  return (
    <div style={s.container}>
      {/* ── Tabs ── */}
      <div style={s.tabs}>
        {(['campaign', 'results', 'approved', 'chat'] as const).map(tab => (
          <button
            key={tab}
            style={{ ...s.tab, ...(activeTab === tab ? s.tabActive : {}) }}
            onClick={() => setActiveTab(tab)}
          >
            {tab === 'campaign' ? 'Campaña'
              : tab === 'results' ? `Resultados${tabCount(tab) ? ` (${tabCount(tab)})` : ''}`
              : tab === 'approved' ? `Aprobados${tabCount(tab) ? ` (${tabCount(tab)})` : ''}`
              : 'Chat Reina'}
          </button>
        ))}
      </div>

      {/* ── Tab: Campaña ── */}
      {activeTab === 'campaign' && (
        <div style={s.tabContent}>
          {/* Agents mini-list */}
          {agents.size > 0 && (
            <div style={s.agentsMini}>
              {Array.from(agents.values()).map(agent => {
                const isWaiting = agent.state === 'waiting';
                const stateLabel = isWaiting
                  ? getSemanticWaitingText(agent.name, checkpointLeads.length)
                  : (STATE_LABELS[agent.state]?.label || agent.state);
                const stateColor = STATE_LABELS[agent.state]?.color || '#888';
                return (
                  <div
                    key={agent.id}
                    style={{ ...s.agentMini, cursor: 'pointer' }}
                    onClick={() => handleAgentClick(agent.state, agent.role)}
                    title="Click para ver bitácora del agente"
                    onMouseEnter={e => (e.currentTarget.style.background = '#22212e')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <span>{ROLE_ICONS[agent.role]}</span>
                    <span style={{ flex: 1, fontSize: 12, color: '#ccc' }}>{agent.name}</span>
                    {isWaiting ? (
                      <span style={{ fontSize: 10, color: stateColor, fontStyle: 'italic' }}>{stateLabel}</span>
                    ) : (
                      <span style={{ ...s.miniDot, background: stateColor }} />
                    )}
                    {agent.tool_status && !isWaiting && (
                      <span style={{ fontSize: 10, color: '#78dce8', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {agent.tool_status}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Signal source selector (always visible above chat / ready state) */}
          <SignalSourceSelector
            selected={selectedSources}
            onChange={setSelectedSources}
            disabled={campaignReady && prospecting}
          />

          {/* Chat OR ready state */}
          {!campaignReady ? (
            <>
              {!clarificationReply ? (
                <NLProspectInput
                  onExtracted={(camp) => {
                    setExtractedCampaign(camp);
                    setCampaign({ ...DEFAULT_CAMPAIGN, ...(camp as Record<string, string>) });
                    setCampaignReady(true);
                  }}
                  onClarification={(reply) => setClarificationReply(reply)}
                />
              ) : (
                <CampaignChat onCampaignReady={handleCampaignReady} resetKey={chatResetKey} />
              )}
            </>
          ) : (
            <>
              {/* Campaign header */}
              <div style={s.campaignHeader}>
                <div style={s.campaignHeaderTitle}>Configuración de Campaña</div>
                <div style={s.campaignHeaderSub}>PARÁMETROS_DE_EJECUCIÓN_v4.0</div>
              </div>

              {/* Extracted params confirmation card (from NL extraction) */}
              {extractedCampaign && (
                <ExtractedParamsCard campaign={extractedCampaign} />
              )}

              {/* Active signal sources badge */}
              {selectedSources.size > 0 && (
                <SignalBadge selected={selectedSources} />
              )}

              {/* Parameter cards grid */}
              <div style={s.paramGrid}>
                {Object.entries(campaign).map(([key, val]) => {
                  const fullWidth = ['dolor_operativo', 'solucion_ofrecida', 'software_clave', 'jerarquia_decisores'].includes(key);
                  return (
                    <div key={key} style={{ ...s.paramCard, ...(fullWidth ? { gridColumn: '1 / -1' } : {}) }}>
                      <div style={s.paramLabel}>{CAMPAIGN_LABELS[key] ?? key}</div>
                      <div style={s.paramValue} title={val}>{val || '—'}</div>
                    </div>
                  );
                })}
              </div>

              {/* Edit toggle */}
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button style={s.toggleBtn} onClick={() => setShowForm(v => !v)}>
                  {showForm ? '↑ Ocultar' : '✎ Editar parámetros'}
                </button>
              </div>
              {showForm && (
                <div style={s.campaignForm}>
                  {Object.entries(campaign).map(([key, val]) => {
                    const fullWidth = ['dolor_operativo', 'solucion_ofrecida', 'software_clave', 'jerarquia_decisores'].includes(key);
                    return (
                      <div key={key} style={{ ...s.fieldGroup, ...(fullWidth ? { gridColumn: '1 / -1' } : {}) }}>
                        <label style={s.fieldLabel}>{CAMPAIGN_LABELS[key] ?? key}</label>
                        <input style={s.fieldInput} value={val}
                          onChange={e => updateCampaign(key, e.target.value)} />
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Knowledge base panel */}
              <KnowledgeBasePanel />

              {/* MAX PROSPECTS slider */}
              <div style={s.sliderSection}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={s.paramLabel}>MAX PROSPECTS</span>
                  <span style={s.sliderNum}>{maxResults}</span>
                </div>
                <input type="range" min={5} max={50} step={5} value={maxResults}
                  onChange={e => setMaxResults(Number(e.target.value))}
                  style={{ width: '100%', accentColor: '#78dce8', margin: '8px 0 4px', cursor: 'pointer' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={s.sliderRange}>5</span>
                  <span style={s.sliderRange}>50</span>
                </div>
              </div>

              {/* Launch button */}
              <button
                style={{ ...s.launchBtn, opacity: prospecting ? 0.5 : 1, cursor: prospecting ? 'not-allowed' : 'pointer' }}
                disabled={prospecting}
                onClick={() => {
                  const campaignWithSources = {
                    ...campaign,
                    use_rues: selectedSources.has('rues') ? 'true' : 'false',
                    use_secop: selectedSources.has('secop') ? 'true' : 'false',
                    use_fincaraiz: selectedSources.has('fincaraiz') ? 'true' : 'false',
                  };
                  startProspect(campaignWithSources, maxResults);
                }}
              >
                {prospecting ? 'AGENTES TRABAJANDO...' : 'INICIAR PROSPECCIÓN 🚀'}
              </button>

              <button style={s.resetBtn} onClick={() => { setCampaignReady(false); setExtractedCampaign(null); setClarificationReply(null); setChatResetKey(k => k + 1); setSelectedSources(new Set()); }}>
                ↩ Nueva campaña
              </button>

              {prospecting && leads.length > 0 && (
                <div style={s.progressInfo}>Analizando empresa {leads.length} de ~{maxResults}...</div>
              )}

              {/* Bee preview */}
              <div style={s.beePreview}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={s.beeAvatar}>🐝</div>
                  <div>
                    <div style={s.beeName}>Technological Drone Bee</div>
                    <div style={s.beeStatus}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#a9dc76', display: 'inline-block', boxShadow: '0 0 4px #a9dc76' }} />
                      Online | System Queen
                    </div>
                  </div>
                </div>
                <div style={s.beeMessage}>
                  Saludos, Administrador. La colmena de datos está lista. ¿Desea que inicie el escaneo de prospectos de alta fidelidad?
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Tab: Resultados ── */}
      {activeTab === 'results' && (
        <div style={s.tabContent}>
          {campaignSummary && (
            <div style={s.summary}>
              <div style={s.summaryItem}>
                <div style={s.summaryNum}>{campaignSummary.total_analyzed}</div>
                <div style={s.summaryLabel}>Analizadas</div>
              </div>
              <div style={s.summaryItem}>
                <div style={{ ...s.summaryNum, color: '#a9dc76' }}>{campaignSummary.total_approved}</div>
                <div style={s.summaryLabel}>Aprobadas</div>
              </div>
              <div style={s.summaryItem}>
                <div style={{ ...s.summaryNum, color: '#ff6188' }}>{campaignSummary.total_rejected}</div>
                <div style={s.summaryLabel}>Descartadas</div>
              </div>
              <div style={s.summaryItem}>
                <div style={{ ...s.summaryNum, color: '#ffd866' }}>{pendingLeads.length}</div>
                <div style={s.summaryLabel}>Por revisar</div>
              </div>
            </div>
          )}

          {leads.length > 0 && (
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button style={s.clearBtn} onClick={clearLeads}>🗑 Limpiar</button>
            </div>
          )}

          {prospecting && leads.length === 0 && (
            <div style={s.emptyState}>Buscando empresas...</div>
          )}

          {leads.length === 0 && !prospecting && (
            <div style={s.emptyState}>
              Configura la campaña y lánzala para ver los resultados aquí.
            </div>
          )}

          <div style={s.leadList}>
            {allResults.map(lead => (
              <LeadCard
                key={lead.leadId ?? lead.id}
                lead={lead}
                onApprove={() => approveLead(lead.leadId, lead.url)}
                onDiscard={() => rejectLead(lead.leadId, lead.url)}
              />
            ))}
            {prospecting && leads.length > 0 && (
              <div style={s.analyzing}>⏳ Analizando siguiente empresa...</div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Chat ── */}
      {activeTab === 'chat' && (
        <div style={{ ...s.tabContent, overflow: 'hidden' }}>
          <LeadsChat />
        </div>
      )}

      {/* ── Tab: Aprobados ── */}
      {activeTab === 'approved' && (
        <div style={s.tabContent}>
          {approvedLeads.length === 0 ? (
            <div style={s.emptyState}>
              Aprueba leads desde la pestaña Resultados para verlos aquí.
            </div>
          ) : (
            <>
              <div style={s.approvedHeader}>
                {approvedLeads.length} lead{approvedLeads.length !== 1 ? 's' : ''} listos para contacto
              </div>
              <div style={s.leadList}>
                {approvedLeads.map(lead => {
                  const payload = lead.json_payload as Record<string, unknown> | null;
                  const score = payload?.score != null ? Number(payload.score) : null;
                  const empresa = payload?.empresa as string || lead.title;
                  const decisor = payload?.decisor as Record<string, unknown> | null;
                  const emailBody = (payload?.borradores as Record<string, unknown>)?.email_cuerpo as string;

                  return (
                    <div key={lead.leadId ?? lead.id} style={s.approvedCard}>
                      <div style={s.approvedCardHeader}>
                        <div>
                          <div style={s.leadTitle}>{empresa}</div>
                          <div style={s.leadUrl}>{lead.url.replace(/^https?:\/\//, '').slice(0, 45)}</div>
                        </div>
                        {score !== null && <ScoreBadge score={score} />}
                      </div>
                      {lead.phone && (
                        <div style={{ color: '#a9dc76', fontSize: 12, marginTop: 6 }}>
                          📞 {lead.phone}
                        </div>
                      )}
                      {decisor && (
                        <div style={{ marginTop: 6, fontSize: 13 }}>
                          <span style={{ color: '#ab9df2' }}>Decisor:</span>{' '}
                          <span style={{ color: '#fff' }}>{String(decisor.nombre ?? '')} — {String(decisor.cargo ?? '')}</span>
                          {!!decisor.email && (
                            <div style={{ color: '#78dce8', fontSize: 12, marginTop: 2 }}>
                              ✉ {String(decisor.email)}
                            </div>
                          )}
                        </div>
                      )}
                      {emailBody && (
                        <button style={s.copyEmailBtn}
                          onClick={() => navigator.clipboard.writeText(emailBody)}>
                          📋 Copiar correo
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
              <div style={s.automateHint}>
                💡 Próximo paso: automatizar el envío de estos correos
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Landa modals ── */}
      {showCheckpoint && checkpointLeads.length > 0 && (
        <CheckpointModal
          lead={checkpointLeads[0]}
          onClose={() => {
            clearCheckpointLead(checkpointLeads[0].leadId);
            setShowCheckpoint(false);
          }}
        />
      )}
      {showHandover && handoverLead && (
        <HandoverModal
          lead={handoverLead}
          onClose={() => {
            setHandoverLead(null);
            setShowHandover(false);
          }}
        />
      )}
      {agentLogModal && (
        <AgentLogModal
          logKey={agentLogModal.logKey}
          lines={agentLogModal.lines}
          onClose={() => setAgentLogModal(null)}
        />
      )}

      {/* ── Footer ── */}
      <div style={s.footer}>
        <div style={{ ...s.connDot, background: connected ? '#a9dc76' : '#ff6188', boxShadow: connected ? '0 0 5px #a9dc76' : 'none' }} title={connected ? 'Conectado' : 'Desconectado'} />
        <span style={s.footerLabel}>{connected ? 'API Status: Stable' : 'API Status: Offline'}</span>
        <div style={{ flex: 1 }} />
        <span style={s.footerVersion}>v2.8.4-stable</span>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  container: {
    width: '100%',
    background: '#1b1a26',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  tabs: {
    display: 'flex',
    gap: 2,
    padding: '10px 12px 0',
    alignItems: 'center',
    background: '#12121d',
    borderBottom: '1px solid rgba(120,220,232,0.06)',
  },
  tab: {
    flex: 1,
    padding: '8px 4px',
    border: 'none',
    borderRadius: '6px 6px 0 0',
    background: 'transparent',
    color: 'rgba(227,224,241,0.4)',
    fontSize: 10,
    fontWeight: 700,
    cursor: 'pointer',
    transition: 'all 0.2s',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
  },
  tabActive: {
    background: 'rgba(120,220,232,0.07)',
    color: '#78dce8',
    boxShadow: '0 -2px 0 #78dce8 inset',
  },
  connDot: {
    width: 7,
    height: 7,
    borderRadius: '50%',
    flexShrink: 0,
  },
  tabContent: {
    flex: 1,
    overflowY: 'auto',
    padding: 14,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  footer: {
    padding: '8px 14px',
    background: '#12121d',
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    borderTop: '1px solid rgba(120,220,232,0.06)',
    flexShrink: 0,
  },
  footerLabel: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 9, color: 'rgba(227,224,241,0.3)',
    textTransform: 'uppercase', letterSpacing: '0.1em',
  },
  footerVersion: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 9, color: 'rgba(227,224,241,0.18)',
    letterSpacing: '0.06em',
  },
  agentsMini: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    padding: 8,
    background: '#12121d',
    borderRadius: 8,
  },
  agentMini: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '5px 8px',
    borderRadius: 6,
    transition: 'background 0.15s',
  },
  miniDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
  section: {
    background: '#12121d',
    borderRadius: 10,
    padding: 12,
  },
  sectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sectionTitle: {
    color: '#ab9df2',
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  toggleBtn: {
    background: 'transparent',
    border: 'none',
    color: 'rgba(227,224,241,0.35)',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  campaignForm: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 12,
    marginTop: 10,
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  groupTitle: {
    color: '#78dce8',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: 2,
  },
  fieldLabel: {
    color: 'rgba(227,224,241,0.4)',
    fontSize: 9,
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  fieldInput: {
    padding: '7px 0',
    border: 'none',
    borderBottom: '1px solid rgba(120,220,232,0.2)',
    borderRadius: 0,
    background: 'transparent',
    color: '#e3e0f1',
    fontSize: 12,
    outline: 'none',
  },
  launchBtn: {
    padding: 12,
    border: 'none',
    borderRadius: 6,
    background: 'linear-gradient(135deg, #7c3aed 0%, #06b6d4 100%)',
    color: '#fff',
    fontWeight: 700,
    fontSize: 13,
    transition: 'opacity 0.2s',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    letterSpacing: '0.03em',
    boxShadow: '0 4px 24px rgba(120,220,232,0.12)',
    cursor: 'pointer',
  },
  progressInfo: {
    color: '#ffd866',
    fontSize: 10,
    textAlign: 'center',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    letterSpacing: '0.04em',
  },
  summary: {
    display: 'flex',
    gap: 6,
    padding: '8px 0',
  },
  summaryItem: {
    flex: 1,
    background: '#12121d',
    borderRadius: 8,
    padding: '10px 4px',
    textAlign: 'center',
  },
  summaryNum: {
    fontSize: 22,
    fontWeight: 800,
    color: '#e3e0f1',
    lineHeight: 1,
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  summaryLabel: {
    fontSize: 9,
    color: 'rgba(227,224,241,0.35)',
    marginTop: 4,
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  emptyState: {
    color: 'rgba(227,224,241,0.3)',
    fontSize: 13,
    textAlign: 'center',
    padding: '32px 8px',
    lineHeight: 1.6,
  },
  leadList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  leadCard: {
    background: '#22212e',
    borderRadius: 8,
    border: '2px solid transparent',
    overflow: 'hidden',
    transition: 'border-color 0.2s',
  },
  leadRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '10px 12px',
    cursor: 'pointer',
  },
  leadDot: {
    width: 7,
    height: 7,
    borderRadius: '50%',
    flexShrink: 0,
  },
  leadTitle: {
    color: '#e3e0f1',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: 140,
  },
  leadUrl: {
    color: 'rgba(227,224,241,0.32)',
    fontSize: 10,
    marginTop: 1,
  },
  leadActions: {
    display: 'flex',
    gap: 4,
  },
  approveBtn: {
    width: 26,
    height: 26,
    border: 'none',
    borderRadius: 4,
    background: 'rgba(169,220,118,0.18)',
    color: '#a9dc76',
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 13,
  },
  discardBtn: {
    width: 26,
    height: 26,
    border: 'none',
    borderRadius: 4,
    background: 'rgba(255,97,136,0.15)',
    color: '#ff6188',
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 13,
  },
  approvedTag: {
    fontSize: 9,
    color: '#a9dc76',
    background: 'rgba(169,220,118,0.1)',
    padding: '2px 7px',
    borderRadius: 4,
    whiteSpace: 'nowrap',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    letterSpacing: '0.04em',
  },
  discardedTag: {
    fontSize: 9,
    color: '#ff6188',
    background: 'rgba(255,97,136,0.1)',
    padding: '2px 7px',
    borderRadius: 4,
    whiteSpace: 'nowrap',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    letterSpacing: '0.04em',
  },
  leadDetail: {
    padding: '0 12px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    borderTop: '1px solid rgba(62,73,74,0.25)',
  },
  detailBlock: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    marginTop: 8,
  },
  detailLabel: {
    color: '#ab9df2',
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  detailValue: {
    color: '#e3e0f1',
    fontSize: 13,
  },
  summaryText: {
    color: 'rgba(227,224,241,0.6)',
    fontSize: 12,
    lineHeight: 1.6,
  },
  sourceList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  sourceLink: {
    color: '#78dce8',
    fontSize: 12,
    textDecoration: 'none',
    wordBreak: 'break-all',
    opacity: 0.75,
  },
  emailBox: {
    background: '#12121d',
    borderRadius: 6,
    padding: '10px 12px',
    color: 'rgba(227,224,241,0.7)',
    fontSize: 12,
    lineHeight: 1.6,
    maxHeight: 160,
    overflowY: 'auto',
  },
  copyBtn: {
    padding: '3px 10px',
    border: '1px solid rgba(120,220,232,0.25)',
    borderRadius: 4,
    background: 'transparent',
    color: '#78dce8',
    fontSize: 11,
    cursor: 'pointer',
  },
  approveFullBtn: {
    flex: 1,
    padding: '9px 0',
    border: 'none',
    borderRadius: 6,
    background: 'rgba(169,220,118,0.14)',
    color: '#a9dc76',
    fontWeight: 700,
    fontSize: 12,
    cursor: 'pointer',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  discardFullBtn: {
    flex: 1,
    padding: '9px 0',
    border: 'none',
    borderRadius: 6,
    background: 'rgba(255,97,136,0.1)',
    color: '#ff6188',
    fontWeight: 700,
    fontSize: 12,
    cursor: 'pointer',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  analyzing: {
    color: '#ffd866',
    fontSize: 10,
    textAlign: 'center',
    padding: '8px 0',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  approvedHeader: {
    color: '#a9dc76',
    fontWeight: 700,
    fontSize: 10,
    textAlign: 'center',
    padding: '4px 0',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  approvedCard: {
    background: '#22212e',
    borderRadius: 8,
    padding: 12,
    border: '1px solid rgba(169,220,118,0.15)',
  },
  approvedCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  copyEmailBtn: {
    marginTop: 8,
    padding: '7px 12px',
    border: '1px solid rgba(120,220,232,0.18)',
    borderRadius: 6,
    background: 'transparent',
    color: '#78dce8',
    fontSize: 12,
    cursor: 'pointer',
    width: '100%',
  },
  clearBtn: {
    padding: '4px 10px', border: '1px solid rgba(120,220,232,0.12)', borderRadius: 6,
    background: 'transparent', color: 'rgba(227,224,241,0.35)', cursor: 'pointer', fontSize: 11,
  },
  summaryRow: { display: 'flex', gap: 6, fontSize: 12 },
  summaryKey: { color: 'rgba(227,224,241,0.4)', minWidth: 70, fontFamily: "'Space Grotesk', system-ui, sans-serif", fontSize: 11 },
  summaryVal: { color: '#e3e0f1', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  resetBtn: {
    padding: '7px 0', border: '1px solid rgba(120,220,232,0.12)', borderRadius: 6,
    background: 'transparent', color: 'rgba(227,224,241,0.35)', cursor: 'pointer', fontSize: 11,
  },
  automateHint: {
    color: 'rgba(227,224,241,0.3)',
    fontSize: 12,
    textAlign: 'center',
    padding: '12px 0 4px',
    borderTop: '1px solid rgba(62,73,74,0.2)',
  },
  campaignHeader: {
    paddingBottom: 4,
  },
  campaignHeaderTitle: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 22, fontWeight: 700, color: '#e3e0f1', letterSpacing: '-0.02em',
  },
  campaignHeaderSub: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 9, color: 'rgba(227,224,241,0.3)',
    letterSpacing: '0.1em', textTransform: 'uppercase', marginTop: 3,
  },
  paramGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8,
  },
  paramCard: {
    background: '#12121d', borderRadius: 8, padding: '10px 12px',
    display: 'flex', flexDirection: 'column', gap: 5,
    border: '1px solid rgba(120,220,232,0.05)',
  },
  paramLabel: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 9, fontWeight: 600, color: 'rgba(227,224,241,0.35)',
    textTransform: 'uppercase', letterSpacing: '0.1em',
  },
  paramValue: {
    color: '#e3e0f1', fontSize: 14, fontWeight: 500,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  sliderSection: {
    background: '#12121d', borderRadius: 8, padding: '12px 14px',
    border: '1px solid rgba(120,220,232,0.05)',
  },
  sliderNum: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 26, fontWeight: 800, color: '#78dce8', lineHeight: 1,
  },
  sliderRange: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 9, color: 'rgba(227,224,241,0.2)', letterSpacing: '0.06em',
  },
  beePreview: {
    background: '#12121d', borderRadius: 10, padding: '12px 14px',
    display: 'flex', flexDirection: 'column', gap: 10,
    border: '1px solid rgba(120,220,232,0.05)',
  },
  beeAvatar: {
    width: 38, height: 38, borderRadius: '50%',
    background: '#22212e', border: '1px solid rgba(120,220,232,0.1)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 18, flexShrink: 0,
  },
  beeName: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 13, fontWeight: 700, color: '#e3e0f1',
  },
  beeStatus: {
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
    fontSize: 10, color: 'rgba(227,224,241,0.4)',
    display: 'flex', alignItems: 'center', gap: 5, marginTop: 2,
  },
  beeMessage: {
    color: 'rgba(227,224,241,0.6)', fontSize: 12, lineHeight: 1.7,
    padding: '9px 11px', background: '#1b1a26', borderRadius: 7,
  },
};
