import { useState, useRef, useEffect } from 'react';
import { useOfficeStore } from '../store/officeStore';
import type { Lead as StoreLead } from '../store/officeStore';
import type { AgentRole } from '../types';
import { CheckpointModal } from './CheckpointModal';
import { HandoverModal } from './HandoverModal';

const API_URL = 'http://localhost:8000';

interface AgentPanelProps {
  createAgent: (name: string, role: string) => void;
  runTask: (agentId: string, task: string) => void;
  startProspect: (campaign: Record<string, string>, max_results: number) => void;
  approveLead: (leadId: string | undefined, url: string) => void;
  rejectLead: (leadId: string | undefined, url: string) => void;
}

const ROLE_ICONS: Record<AgentRole, string> = {
  coder: '👨‍💻', researcher: '🔬', writer: '✍️', reviewer: '🔍', planner: '📋',
};
const STATE_LABELS: Record<string, { label: string; color: string }> = {
  idle:     { label: 'Idle',       color: '#888' },
  thinking: { label: 'Pensando...', color: '#ffd866' },
  tool_use: { label: 'Trabajando', color: '#78dce8' },
  waiting:  { label: 'Listo',      color: '#a9dc76' },
  error:    { label: 'Error',      color: '#ff6188' },
};

const DEFAULT_CAMPAIGN = {
  nombre_remitente: 'Maximiliano Pulido',
  empresa_remitente: 'Isomorph',
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
  container: { background: '#131326', borderRadius: 6, padding: '8px 10px', marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 },
  title: { color: '#ab9df2', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 },
  factor: { display: 'flex', alignItems: 'center', gap: 6 },
  rejectReason: { color: '#ff6188', fontWeight: 600, fontSize: 13 },
  evidence: { color: '#888', fontSize: 12, fontStyle: 'italic', marginTop: 2 },
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
      // Get token from sessionStorage fallback or try anonymous
      const tokenKey = 'hive_token';
      let token = sessionStorage.getItem(tokenKey);
      if (!token) {
        // Quick register+login
        const email = `chat-${Math.random().toString(36).slice(7)}@example.com`;
        await fetch(`${API_URL}/auth/register`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password: 'demo-password-123' }),
        });
        const res = await fetch(`${API_URL}/auth/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password: 'demo-password-123' }),
        });
        const data = await res.json();
        token = data.access_token;
        if (token) sessionStorage.setItem(tokenKey, token);
      }

      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
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
    fetch(`${API_URL}/auth/register`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: `chat-${Math.random().toString(36).slice(7)}@example.com`, password: 'demo-password-123' }),
    }).catch(() => {});
    // Trigger first AI message
    (async () => {
      try {
        const email = `chat-init-${Math.random().toString(36).slice(7)}@example.com`;
        await fetch(`${API_URL}/auth/register`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password: 'demo-password-123' }),
        });
        const loginRes = await fetch(`${API_URL}/auth/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password: 'demo-password-123' }),
        });
        const loginData = await loginRes.json();
        const token = loginData.access_token;
        if (token) sessionStorage.setItem('hive_token', token);

        const res = await fetch(`${API_URL}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
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
    gap: 12, padding: '24px 16px', textAlign: 'center',
  },
  startIcon: { fontSize: 40 },
  startTitle: { color: '#fff', fontWeight: 700, fontSize: 15 },
  startDesc: { color: '#888', fontSize: 13, lineHeight: 1.5 },
  startBtn: {
    padding: '10px 24px', border: 'none', borderRadius: 8,
    background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
    color: '#fff', fontWeight: 700, fontSize: 14, cursor: 'pointer',
  },
  container: { display: 'flex', flexDirection: 'column', height: 320, gap: 8 },
  messages: {
    flex: 1, overflowY: 'auto', display: 'flex',
    flexDirection: 'column', gap: 8, padding: '4px 0',
  },
  bubble: {
    maxWidth: '85%', padding: '8px 12px', borderRadius: 10,
    fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
  },
  bubbleAI: { background: '#363650', color: '#e5e5e5', alignSelf: 'flex-start' },
  bubbleUser: { background: '#7c3aed', color: '#fff', alignSelf: 'flex-end' },
  inputRow: { display: 'flex', gap: 6 },
  input: {
    flex: 1, padding: '8px 12px', border: 'none', borderRadius: 8,
    background: '#363650', color: '#fff', fontSize: 13,
  },
  sendBtn: {
    padding: '8px 14px', border: 'none', borderRadius: 8,
    background: '#7c3aed', color: '#fff', cursor: 'pointer', fontSize: 14,
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
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: ChatMsg = { role: 'user', content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    setLoading(true);

    try {
      const token = useOfficeStore.getState().authToken;
      const res = await fetch(`${API_URL}/api/chat/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
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
                <span style={{ color: INTENT_COLORS[intents[i].type], fontSize: 11 }}>
                  {INTENT_LABELS[intents[i].type] || intents[i].type}
                </span>
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
  introText: { color: '#888', fontSize: 12 },
  messages: { flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 },
  suggestions: { display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 0' },
  suggestion: {
    padding: '7px 10px', background: '#1e1e35', border: '1px solid #2a2a4e',
    borderRadius: 7, color: '#888', cursor: 'pointer', fontSize: 12, textAlign: 'left',
  },
  bubble: {
    maxWidth: '90%', padding: '8px 11px', borderRadius: 9,
    fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap',
  },
  bubbleAI: { background: '#363650', color: '#e5e5e5', alignSelf: 'flex-start' },
  bubbleUser: { background: '#7c3aed', color: '#fff', alignSelf: 'flex-end' },
  intentBadge: {
    background: '#131326', borderRadius: 6, padding: '5px 9px',
    border: '1px solid', marginTop: 3, maxWidth: '90%',
  },
  proposal: { color: '#ccc', fontSize: 11, marginTop: 4 },
  inputRow: { display: 'flex', gap: 6 },
  input: {
    flex: 1, padding: '8px 11px', border: 'none', borderRadius: 7,
    background: '#363650', color: '#fff', fontSize: 13,
  },
  sendBtn: {
    padding: '8px 13px', border: 'none', borderRadius: 7,
    background: '#7c3aed', color: '#fff', cursor: 'pointer', fontSize: 13,
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

export function AgentPanel({ startProspect, approveLead, rejectLead }: AgentPanelProps) {
  const {
    agents, connected, prospecting, leads, campaignSummary,
    activeTab, setActiveTab, clearLeads, activeCampaign,
    checkpointLeads, handoverLead, clearCheckpointLead, setHandoverLead,
  } = useOfficeStore();

  const [campaign, setCampaign] = useState<Record<string, string>>(DEFAULT_CAMPAIGN);
  const [maxResults, setMaxResults] = useState(20);
  const [campaignReady, setCampaignReady] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [chatResetKey, setChatResetKey] = useState(0);
  const [showCheckpoint, setShowCheckpoint] = useState(false);
  const [showHandover, setShowHandover] = useState(false);

  const handleAgentClick = (agentState: string) => {
    if (agentState !== 'waiting') return;
    if (checkpointLeads.length > 0) {
      setShowCheckpoint(true);
    } else if (handoverLead) {
      setShowHandover(true);
    }
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
            {tab === 'campaign' ? '⚙️ Campaña'
              : tab === 'results' ? `📊${tabCount(tab) ? ` (${tabCount(tab)})` : ''}`
              : tab === 'approved' ? `✅${tabCount(tab) ? ` (${tabCount(tab)})` : ''}`
              : '💬'}
          </button>
        ))}
        <div style={{ ...s.connDot, background: connected ? '#a9dc76' : '#ff6188' }} title={connected ? 'Conectado' : 'Desconectado'} />
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
                    style={{ ...s.agentMini, cursor: isWaiting ? 'pointer' : 'default' }}
                    onClick={() => handleAgentClick(agent.state)}
                    title={isWaiting ? 'Click para abrir panel de acción' : undefined}
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

          {/* Chat OR ready state */}
          {!campaignReady ? (
            <CampaignChat onCampaignReady={handleCampaignReady} resetKey={chatResetKey} />
          ) : (
            <>
              {/* Campaign summary */}
              <div style={s.section}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={s.sectionTitle}>✅ Campaña configurada</div>
                  <button style={s.toggleBtn} onClick={() => setShowForm(v => !v)}>
                    {showForm ? 'Ocultar' : 'Editar'}
                  </button>
                </div>
                <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={s.summaryRow}><span style={s.summaryKey}>Industria</span><span style={s.summaryVal}>{campaign.industria_objetivo}</span></div>
                  <div style={s.summaryRow}><span style={s.summaryKey}>Ciudad</span><span style={s.summaryVal}>{campaign.ciudad_objetivo}</span></div>
                  <div style={s.summaryRow}><span style={s.summaryKey}>Dolor</span><span style={s.summaryVal}>{campaign.dolor_operativo}</span></div>
                  <div style={s.summaryRow}><span style={s.summaryKey}>Solución</span><span style={s.summaryVal}>{campaign.solucion_ofrecida}</span></div>
                </div>
                {showForm && (
                  <div style={{ ...s.campaignForm, marginTop: 10 }}>
                    {Object.entries(campaign).map(([key, val]) => (
                      <div key={key} style={s.fieldGroup}>
                        <label style={s.fieldLabel}>{key}</label>
                        <input style={s.fieldInput} value={val}
                          onChange={e => updateCampaign(key, e.target.value)} />
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Max results */}
              <div style={s.section}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={s.sectionTitle}>Empresas a analizar</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="range" min={5} max={50} step={5} value={maxResults}
                      onChange={e => setMaxResults(Number(e.target.value))}
                      style={{ width: 80 }} />
                    <span style={{ color: '#ffd866', fontWeight: 700, fontSize: 16 }}>{maxResults}</span>
                  </div>
                </div>
              </div>

              <button
                style={{ ...s.launchBtn, opacity: prospecting ? 0.5 : 1, cursor: prospecting ? 'not-allowed' : 'pointer' }}
                disabled={prospecting}
                onClick={() => startProspect(campaign, maxResults)}
              >
                {prospecting ? '⏳ Agentes trabajando...' : '🚀 Lanzar campaña'}
              </button>

              <button style={s.resetBtn} onClick={() => { setCampaignReady(false); setChatResetKey(k => k + 1); }}>
                ↩ Nueva campaña
              </button>

              {prospecting && leads.length > 0 && (
                <div style={s.progressInfo}>Analizando empresa {leads.length} de ~{maxResults}...</div>
              )}
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
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  container: {
    width: '100%',
    background: '#2a2a3e',
    borderRadius: 12,
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  tabs: {
    display: 'flex',
    gap: 2,
    padding: '10px 10px 0',
    alignItems: 'center',
    borderBottom: '1px solid #3a3a5e',
  },
  tab: {
    flex: 1,
    padding: '8px 4px',
    border: 'none',
    borderRadius: '6px 6px 0 0',
    background: 'transparent',
    color: '#888',
    fontSize: 11,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  tabActive: {
    background: '#363650',
    color: '#fff',
  },
  connDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    flexShrink: 0,
    marginLeft: 4,
  },
  tabContent: {
    flex: 1,
    overflowY: 'auto',
    padding: 12,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  agentsMini: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    padding: 8,
    background: '#1e1e35',
    borderRadius: 8,
  },
  agentMini: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  miniDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
  section: {
    background: '#1e1e35',
    borderRadius: 8,
    padding: 10,
  },
  sectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  sectionTitle: {
    color: '#ab9df2',
    fontSize: 12,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  toggleBtn: {
    background: 'transparent',
    border: 'none',
    color: '#888',
    cursor: 'pointer',
    fontSize: 12,
  },
  campaignForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
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
    color: '#888',
    fontSize: 11,
  },
  fieldInput: {
    padding: '6px 10px',
    border: 'none',
    borderRadius: 5,
    background: '#252538',
    color: '#fff',
    fontSize: 12,
  },
  launchBtn: {
    padding: 12,
    border: 'none',
    borderRadius: 8,
    background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
    color: '#fff',
    fontWeight: 700,
    fontSize: 14,
    transition: 'opacity 0.2s',
  },
  progressInfo: {
    color: '#ffd866',
    fontSize: 12,
    textAlign: 'center',
  },
  summary: {
    display: 'flex',
    gap: 8,
    padding: '10px 0',
  },
  summaryItem: {
    flex: 1,
    background: '#1e1e35',
    borderRadius: 8,
    padding: '8px 4px',
    textAlign: 'center',
  },
  summaryNum: {
    fontSize: 22,
    fontWeight: 800,
    color: '#fff',
    lineHeight: 1,
  },
  summaryLabel: {
    fontSize: 10,
    color: '#888',
    marginTop: 3,
  },
  emptyState: {
    color: '#888',
    fontSize: 13,
    textAlign: 'center',
    padding: '24px 8px',
  },
  leadList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  leadCard: {
    background: '#363650',
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
    width: 8,
    height: 8,
    borderRadius: '50%',
    flexShrink: 0,
  },
  leadTitle: {
    color: '#fff',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: 140,
  },
  leadUrl: {
    color: '#888',
    fontSize: 10,
    marginTop: 1,
  },
  leadActions: {
    display: 'flex',
    gap: 4,
  },
  approveBtn: {
    width: 24,
    height: 24,
    border: 'none',
    borderRadius: 4,
    background: '#a9dc76',
    color: '#000',
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 13,
  },
  discardBtn: {
    width: 24,
    height: 24,
    border: 'none',
    borderRadius: 4,
    background: '#ff6188',
    color: '#fff',
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 13,
  },
  approvedTag: {
    fontSize: 10,
    color: '#a9dc76',
    background: '#a9dc7622',
    padding: '2px 6px',
    borderRadius: 4,
    whiteSpace: 'nowrap',
  },
  discardedTag: {
    fontSize: 10,
    color: '#ff6188',
    background: '#ff618822',
    padding: '2px 6px',
    borderRadius: 4,
    whiteSpace: 'nowrap',
  },
  leadDetail: {
    padding: '0 12px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    borderTop: '1px solid #2a2a4e',
  },
  detailBlock: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    marginTop: 8,
  },
  detailLabel: {
    color: '#ab9df2',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  detailValue: {
    color: '#fff',
    fontSize: 13,
  },
  summaryText: {
    color: '#c9c9d6',
    fontSize: 12,
    lineHeight: 1.5,
  },
  sourceList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  sourceLink: {
    color: '#78dce8',
    fontSize: 12,
    textDecoration: 'underline',
    wordBreak: 'break-all',
  },
  emailBox: {
    background: '#252538',
    borderRadius: 6,
    padding: '10px 12px',
    color: '#e5e5e5',
    fontSize: 12,
    lineHeight: 1.6,
    maxHeight: 160,
    overflowY: 'auto',
  },
  copyBtn: {
    padding: '2px 10px',
    border: '1px solid #78dce8',
    borderRadius: 4,
    background: 'transparent',
    color: '#78dce8',
    fontSize: 11,
    cursor: 'pointer',
  },
  approveFullBtn: {
    flex: 1,
    padding: '8px 0',
    border: 'none',
    borderRadius: 6,
    background: '#a9dc76',
    color: '#000',
    fontWeight: 600,
    fontSize: 12,
    cursor: 'pointer',
  },
  discardFullBtn: {
    flex: 1,
    padding: '8px 0',
    border: 'none',
    borderRadius: 6,
    background: '#ff618844',
    color: '#ff6188',
    fontWeight: 600,
    fontSize: 12,
    cursor: 'pointer',
  },
  analyzing: {
    color: '#ffd866',
    fontSize: 12,
    textAlign: 'center',
    padding: '8px 0',
  },
  approvedHeader: {
    color: '#a9dc76',
    fontWeight: 600,
    fontSize: 13,
    textAlign: 'center',
    padding: '4px 0',
  },
  approvedCard: {
    background: '#363650',
    borderRadius: 8,
    padding: 12,
    border: '1px solid #a9dc7633',
  },
  approvedCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  copyEmailBtn: {
    marginTop: 8,
    padding: '6px 12px',
    border: '1px solid #78dce8',
    borderRadius: 6,
    background: 'transparent',
    color: '#78dce8',
    fontSize: 12,
    cursor: 'pointer',
    width: '100%',
  },
  clearBtn: {
    padding: '4px 10px', border: '1px solid #4a4a6a', borderRadius: 6,
    background: 'transparent', color: '#888', cursor: 'pointer', fontSize: 11,
  },
  summaryRow: { display: 'flex', gap: 6, fontSize: 12 },
  summaryKey: { color: '#888', minWidth: 70 },
  summaryVal: { color: '#fff', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  resetBtn: {
    padding: '6px 0', border: '1px solid #4a4a6a', borderRadius: 6,
    background: 'transparent', color: '#888', cursor: 'pointer', fontSize: 12,
  },
  automateHint: {
    color: '#888',
    fontSize: 12,
    textAlign: 'center',
    padding: '12px 0 4px',
    borderTop: '1px solid #2a2a4e',
  },
};
