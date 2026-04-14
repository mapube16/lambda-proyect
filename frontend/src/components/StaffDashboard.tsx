import { RoadmapTab } from './RoadmapTab';
type StaffTab = 'roadmap' | 'dashboard';

export function StaffDashboard() {
  const { clearAuth, userEmail } = useOfficeStore();
  const [tab, setTab] = useState<StaffTab>('dashboard');
  const [clients, setClients] = useState<ClientData[]>([]);
  const [clientSearch, setClientSearch] = useState('');
  const [selectedClient, setSelectedClient] = useState<ClientData | null>(null);
  const [clientDetail, setClientDetail] = useState<ClientDetail | null>(null);
  const [clientLeads, setClientLeads] = useState<Lead[]>([]);
  const [clientLearning, setClientLearning] = useState<LearningData | null>(null);
  const [loadingClients, setLoadingClients] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);

  const loadClients = useCallback(async () => {
    setLoadingClients(true);
    try {
      const res = await apiFetch(`${API_URL}/api/staff/clients`, { credentials: 'include' });
      if (res.ok) setClients(await res.json());
    } finally {
      setLoadingClients(false);
    }
  }, []);

  useEffect(() => { loadClients(); }, [loadClients]);

  const sendLeadEmail = async (leadId: string) => {
    try {
      const res = await apiFetch(`${API_URL}/api/leads/${leadId}/send-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ subject_index: 0 }),
      });
      if (!res.ok) {
        const d = await res.json();
        alert(d.detail || 'No se pudo enviar el correo');
        return;
      }
      setClientLeads(prev => prev.map(l => l._id === leadId ? { ...l, email_sent: true } : l));
    } catch {
      alert('Error de conexión');
    }
  };

  const selectClient = async (client: ClientData) => {
    setSelectedClient(client);
    setClientDetail(null);
    setClientLeads([]);
    setClientLearning(null);
    setLoadingDetail(true);
    try {
      const [detailRes, leadsRes, learningRes] = await Promise.all([
        apiFetch(`${API_URL}/api/staff/clients/${client.id}`, { credentials: 'include' }),
        apiFetch(`${API_URL}/api/staff/clients/${client.id}/leads`, { credentials: 'include' }),
        apiFetch(`${API_URL}/api/staff/clients/${client.id}/learning`, { credentials: 'include' }),
      ]);
      if (detailRes.ok) setClientDetail(await detailRes.json());
      if (leadsRes.ok) setClientLeads(await leadsRes.json());
      if (learningRes.ok) setClientLearning(await learningRes.json());
    } finally {
      setLoadingDetail(false);
    }
  };


  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: bg, color: text, fontFamily: IN, overflow: 'hidden' }}>
      <nav style={{ display: 'flex', alignItems: 'center', gap: 24, padding: '16px 32px', background: s0, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginRight: 32 }}>
          <img src="/assets/logo.svg" alt="Landa AI" style={{ width: 32, height: 32 }} />
          <span
            style={{
              fontWeight: 700,
              fontSize: 18,
              color: cyan,
              letterSpacing: '-0.03em',
              fontFamily: SG,
            }}
          >LANDA STAFF</span>
        </div>
        <button
          onClick={() => setTab('roadmap')}
          style={{
            background: 'none', border: 'none', color: tab === 'roadmap' ? cyan : muted,
            fontWeight: tab === 'roadmap' ? 700 : 400, fontSize: 15, cursor: 'pointer',
            borderBottom: tab === 'roadmap' ? `2px solid ${cyan}` : '2px solid transparent',
            padding: '8px 0', marginRight: 12,
          }}
        >Roadmap</button>
        <button
          onClick={() => setTab('dashboard')}
          style={{
            background: 'none', border: 'none', color: tab === 'dashboard' ? cyan : muted,
            fontWeight: tab === 'dashboard' ? 700 : 400, fontSize: 15, cursor: 'pointer',
            borderBottom: tab === 'dashboard' ? `2px solid ${cyan}` : '2px solid transparent',
            padding: '8px 0',
          }}
        >Panel</button>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          {userEmail && (
            <span style={{ fontFamily: SG, fontSize: 11, color: muted }}>{userEmail}</span>
          )}
          <button
            onClick={clearAuth}
            style={{
              padding: '4px 12px', borderRadius: 2,
              border: `1px solid rgba(120,220,232,0.2)`,
              background: 'transparent', color: cyan,
              fontFamily: SG, fontSize: 11, letterSpacing: '0.04em',
              cursor: 'pointer',
            }}
          >logout</button>
        </div>
      </nav>
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {tab === 'roadmap' && <div style={{ flex: 1, overflow: 'auto' }}><RoadmapTab /></div>}
        {tab === 'dashboard' && (
          <div style={{ ...s.page, height: '100%' }}>
            {showOnboarding && (
              <OnboardingWizard
                onClose={() => setShowOnboarding(false)}
                onSuccess={() => loadClients()}
              />
            )}
            <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
              {/* Client list sidebar */}
              <div style={s.sidebar}>
                <div style={s.sidebarStatus}>Nodes activos</div>
                <div style={s.sidebarTitle}>{loadingClients ? 'Cargando...' : `${clients.length} clientes`}</div>
                <input
                  placeholder="Buscar cliente..."
                  value={clientSearch}
                  onChange={e => setClientSearch(e.target.value)}
                  style={{ marginBottom: 8, padding: '6px 10px', background: 'rgba(120,220,232,0.06)', border: '1px solid rgba(120,220,232,0.1)', borderRadius: 6, color: text, fontSize: 12, fontFamily: IN, outline: 'none' }}
                />
                {clients
                  .filter(c => !clientSearch || c.email.toLowerCase().includes(clientSearch.toLowerCase()))
                  .map(client => (
                    <div
                      key={client.id}
                      onClick={() => selectClient(client)}
                      style={{ ...s.clientCard, ...(selectedClient?.id === client.id ? s.clientCardActive : {}) }}
                    >
                      <div style={selectedClient?.id === client.id ? s.clientEmailActive : s.clientEmail}>{client.email}</div>
                      {client.active_campaign && (
                        <div style={s.clientCampaignLabel}>campaña activa</div>
                      )}
                    </div>
                  ))}
                <button
                  onClick={() => setShowOnboarding(true)}
                  style={{ marginTop: 'auto', padding: '8px 12px', background: `${cyan}20`, border: `1px solid ${cyan}44`, borderRadius: 8, color: cyan, fontSize: 12, cursor: 'pointer', fontFamily: SG, width: '100%' }}
                >+ Nuevo cliente</button>
              </div>
              {/* Client detail */}
              <div style={s.detail}>
                {!selectedClient ? (
                  <div style={s.emptyState}>
                    <div style={s.emptyStateText}>Selecciona un cliente para ver su pipeline</div>
                  </div>
                ) : (
                  <>
                    <div style={s.detailHeader}>
                      <div style={s.detailNodeRow}>
                        <span style={s.detailNodeLabel}>
                          Nodo de Monitoreo: {selectedClient.id.slice(0, 5).toUpperCase()}-{selectedClient.id.slice(5, 8).toUpperCase()}
                        </span>
                        <span style={s.activeChip}>ACTIVO</span>
                      </div>
                      <div style={s.detailEmail}>{selectedClient.email}</div>
                      {clientDetail && (
                        <div style={s.detailSubRow}>
                          <div style={{ ...s.statCard, borderLeftColor: cyan }}>
                            <div style={s.statCardValue}>{clientDetail.total_runs}</div>
                            <div style={s.statCardLabel}>runs</div>
                          </div>
                          <div style={{ ...s.statCard, borderLeftColor: cyan }}>
                            <div style={s.statCardValue}>{clientDetail.total_leads}</div>
                            <div style={s.statCardLabel}>leads totales</div>
                          </div>
                          <div style={{ ...s.statCard, borderLeftColor: green }}>
                            <div style={{ ...s.statCardValue, color: green }}>{clientDetail.approved_leads}</div>
                            <div style={s.statCardLabel}>aprobados</div>
                          </div>
                        </div>
                      )}
                    </div>
                    {loadingDetail ? (
                      <div style={s.loading}>Cargando...</div>
                    ) : (
                      <>
                        {/* Agents */}
                        <Section title="Agentes del pipeline">
                          {(() => {
                            const runtimeAgents = (clientDetail?.user_root_onboarding?.onboarding_agents?.length
                              ? clientDetail.user_root_onboarding.onboarding_agents.map((agent, i) => ({
                                  id: agent.id || `agent-${i + 1}`,
                                  name: agent.name || `Agente ${i + 1}`,
                                  role: agent.role || 'reviewer',
                                  palette: i,
                                }))
                              : PIPELINE_AGENTS);
                            const barWidths = ['0%', '30%', '65%', '90%'];
                            return (
                              <div style={s.agentGrid}>
                                {runtimeAgents.map((agent, i) => {
                                  const color = PALETTE_COLORS[i % PALETTE_COLORS.length];
                                  return (
                                    <div key={agent.id} style={s.agentCard}>
                                      <div style={{ ...s.agentStatusDot, background: cyan, boxShadow: `0 0 6px ${cyan}` }} />
                                      <div style={{ ...s.agentIcon, background: `${color}15`, color }}>
                                        {agent.name.charAt(0).toUpperCase()}
                                      </div>
                                      <div style={s.agentName}>{agent.name}</div>
                                      <div style={s.agentRole}>{agent.role}</div>
                                      <div style={s.agentProgressTrack}>
                                        <div style={{ ...s.agentProgressBar, background: color, width: barWidths[i % barWidths.length] }} />
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            );
                          })()}
                          {!!clientDetail?.runtime_pipeline_agents && (
                            <div style={s.runtimeLimitNote}>
                              Runtime actual: {clientDetail.runtime_pipeline_agents} agentes ejecutándose por corrida.
                            </div>
                          )}
                        </Section>
                        {/* Root onboarding snapshot */}
                        <Section title="Onboarding guardado (raíz users)">
                          {clientDetail?.user_root_onboarding ? (
                            <>
                              <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                                <span style={s.statPill}>
                                  {clientDetail.user_root_onboarding.onboarding_agents_count ?? clientDetail.user_root_onboarding.onboarding_agents?.length ?? 0} agentes configurados
                                </span>
                                {clientDetail.user_root_onboarding.onboarding_updated_at && (
                                  <span style={s.statPill}>
                                    actualizado {new Date(clientDetail.user_root_onboarding.onboarding_updated_at).toLocaleString('es-CO')}
                                  </span>
                                )}
                              </div>
                              {!!clientDetail.user_root_onboarding.onboarding_personality_prompt && (
                                <div style={s.rootPromptBox}>{clientDetail.user_root_onboarding.onboarding_personality_prompt}</div>
                              )}
                              {(clientDetail.user_root_onboarding.onboarding_agents?.length ?? 0) > 0 && (
                                <div style={s.rootAgentsList}>
                                  {clientDetail.user_root_onboarding.onboarding_agents?.map((agent, idx) => (
                                    <div key={`${agent.id || agent.name || 'agent'}-${idx}`} style={s.rootAgentRow}>
                                      <div style={s.rootAgentName}>{agent.name || `Agente ${idx + 1}`}</div>
                                      <div style={s.rootAgentMeta}>{agent.role || 'sin rol'} · {agent.model || 'sin modelo'}</div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </>
                          ) : (
                            <div style={{ color: muted, fontSize: 13, fontFamily: IN }}>Sin snapshot onboarding en raíz de usuario</div>
                          )}
                        </Section>
                        {/* Campaign personality */}
                        <Section title="Personalidad activa (campaña)">
                          {clientDetail?.active_campaign ? (
                            <div style={s.campaignGrid}>
                              {Object.entries(CAMPAIGN_LABELS).map(([key, label]) => {
                                const val = clientDetail.active_campaign?.[key];
                                if (!val) return null;
                                return (
                                  <div key={key} style={s.campaignRow}>
                                    <div style={s.campaignLabel}>{label}</div>
                                    <div style={s.campaignValue}>{val}</div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div style={{ color: muted, fontSize: 13, fontFamily: IN }}>Sin campaña configurada</div>
                          )}
                        </Section>
                        {/* Fuentes de descubrimiento */}
                        <Section title="Fuentes de descubrimiento">
                          <FuentesPanel client={selectedClient} />
                        </Section>
                        {/* Agente de Llamadas */}
                        <Section title="Agente de Llamadas (Cobranza)">
                          <CobranzaToggle
                            clientId={selectedClient.id}
                            enabled={!!clientDetail?.cobranza_enabled}
                            onToggle={(val) => setClientDetail(prev => prev ? { ...prev, cobranza_enabled: val } : prev)}
                          />
                        </Section>
                        {/* Leads */}
                        <Section title={`Leads (${clientLeads.length})`}>
                          {clientLeads.length === 0 ? (
                            <div style={{ color: muted, fontSize: 13, fontFamily: IN }}>Sin leads aún</div>
                          ) : (
                            <div style={s.leadsList}>
                              {clientLeads.map(lead => {
                                const approved = lead.system_state === 'SUCCESS_READY_FOR_REVIEW';
                                const score = lead.expediente_json?.score as number | null;
                                const decisor = lead.expediente_json?.decisor as Record<string, string> | null;
                                return (
                                  <div key={lead._id} style={s.leadRow}>
                                    <div style={{ ...s.leadDot, background: approved ? green : pink }} />
                                    <div style={s.leadInfo}>
                                      <div style={s.leadName}>{lead.company_name || lead.url}</div>
                                      <div style={s.leadUrl}>{lead.url.replace(/^https?:\/\//, '').slice(0, 45)}</div>
                                      {decisor?.email && (
                                        <div style={s.leadDecissor}>{decisor.email}</div>
                                      )}
                                    </div>
                                    <div style={s.leadMeta}>
                                      {score != null && <span style={s.scoreBadge}>{score}pts</span>}
                                      <span style={{ ...s.hitlBadge, color: lead.hitl_status === 'approved' ? green : lead.hitl_status === 'rejected' ? pink : muted }}>
                                        {lead.hitl_status === 'approved' ? '✓ aprobado' : lead.hitl_status === 'rejected' ? '✗ rechazado' : 'pendiente'}
                                      </span>
                                      {decisor?.email && !!((lead.expediente_json?.borradores as Record<string,unknown> | null)?.email_cuerpo) && (
                                        <button
                                          style={{ ...s.sendEmailBtn, ...(lead.email_sent ? s.sendEmailBtnSent : {}) }}
                                          onClick={() => !lead.email_sent && sendLeadEmail(lead._id)}
                                          title={lead.email_sent ? 'Correo enviado' : `Enviar a ${decisor.email}`}
                                        >
                                          {lead.email_sent ? 'enviado' : 'enviar'}
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </Section>
                        {/* Learning — Tu cliente ideal */}
                        {clientLearning && (clientLearning.ideal_count > 0 || clientLearning.patterns.length > 0) && (
                          <Section title="Tu cliente ideal">
                            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                              <span style={s.statPill}>{clientLearning.ideal_count} aprobados analizados</span>
                              <span style={{ ...s.statPill, color: pink }}>{clientLearning.rejected_count} rechazados</span>
                            </div>
                            {clientLearning.patterns.length === 0 ? (
                              <div style={{ color: faint, fontSize: 12, fontFamily: IN }}>
                                Se necesitan al menos 3 leads aprobados para detectar patrones.
                              </div>
                            ) : (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {clientLearning.patterns.map((p, i) => (
                                  <div key={i} style={{
                                    ...s.patternCard,
                                    borderLeft: `2px solid ${p.confidence === 'alta' ? green : purple}`,
                                  }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                      <span style={{ fontSize: 16 }}>{['🥇','🥈','🥉'][i]}</span>
                                      <span style={s.patternText}>{p.description}</span>
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, marginTop: 4, paddingLeft: 24 }}>
                                      <span style={{
                                        ...s.statPill, fontSize: 10,
                                        background: p.confidence === 'alta' ? `${green}1a` : `${purple}1a`,
                                        color: p.confidence === 'alta' ? green : purple,
                                      }}>
                                        {p.confidence === 'alta' ? 'Alta confianza' : 'Confianza media'}
                                      </span>
                                      {p.evidence_count > 0 && (
                                        <span style={{ ...s.statPill, fontSize: 10 }}>{p.evidence_count} evidencias</span>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </Section>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useOfficeStore } from '../store/officeStore';
import { apiFetch } from '../lib/apiFetch';

const API_URL = '';

// Design tokens
const bg     = '#0d0d18';
const s0     = '#12121d';
const s1     = '#1b1a26';
const s2     = '#22212e';
const s3     = '#2c2b3a';
const s4     = '#343440';
const text   = '#e3e0f1';
const muted  = 'rgba(227,224,241,0.5)';
const faint  = 'rgba(227,224,241,0.25)';
const cyan   = '#78dce8';
const purple = '#ab9df2';
const green  = '#a9dc76';
const pink   = '#ff6188';
const grad   = 'linear-gradient(135deg,#7c3aed 0%,#06b6d4 100%)';
const SG     = "'Space Grotesk',system-ui,sans-serif";
const IN     = "'Inter',system-ui,sans-serif";

// Pipeline agents definition (mirrors hive_graph.py PIPELINE_AGENTS)
const PIPELINE_AGENTS = [
  { id: 'buscador-001', name: 'Buscador',    role: 'researcher', palette: 0 },
  { id: 'scraper-001',  name: 'Scraper',      role: 'planner',    palette: 1 },
  { id: 'analista-001', name: 'Analista B2B', role: 'reviewer',   palette: 2 },
  { id: 'redactor-001', name: 'Redactor',     role: 'writer',     palette: 3 },
];

const PALETTE_COLORS = ['#78dce8', '#a9dc76', '#ffd866', '#ff6188'];

const CAMPAIGN_LABELS: Record<string, string> = {
  nombre_remitente:     'Remitente',
  empresa_remitente:    'Empresa',
  sector_propio_cliente:'Nuestro sector (excluir competidores)',
  industria_objetivo:   'Industria objetivo',
  ciudad_objetivo:      'Ciudad',
  dolor_operativo:      'Dolor operativo',
  solucion_ofrecida:    'Solución',
  software_clave:       'Software clave',
  jerarquia_decisores:  'Decisores',
};

function humanizeCampaignKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

interface ClientData {
  id: string;
  email: string;
  role: string;
  created_at: string;
  total_runs: number;
  total_leads: number;
  approved_leads: number;
  last_run_at: string | null;
  last_run_status: string | null;
  active_campaign: Record<string, string> | null;
  fuentes_habilitadas?: string[];
  notification_channel?: string;
  wa_phone_number?: string;
  wa_phone_id?: string;
}

interface Lead {
  _id: string;
  company_name: string;
  url: string;
  system_state: string;
  score: number | null;
  hitl_status: string;
  created_at: string;
  expediente_json: Record<string, unknown> | null;
  email_sent?: boolean;
}

interface ClientDetail {
  total_runs: number;
  total_leads: number;
  approved_leads: number;
  last_run_at: string | null;
  last_run_status: string | null;
  active_campaign: Record<string, string> | null;
  runs: Array<{ _id: string; status: string; started_at: string; max_results: number }>;
  runtime_pipeline_agents?: number;
  user_root_onboarding?: {
    onboarding_business_summary?: string;
    onboarding_personality_prompt?: string;
    onboarding_campaign?: Record<string, string>;
    onboarding_agents?: Array<{
      id?: string;
      name?: string;
      role?: string;
      model?: string;
      persona?: string;
      responsibility?: string;
      prompt?: string;
      prompt_source?: string;
    }>;
    onboarding_agents_count?: number;
    onboarding_updated_at?: string;
  } | null;
  cobranza_enabled?: boolean;
}

interface KnowledgeSource {
  filename: string;
  source_type: string;
  chunk_count: number;
}

interface ProposalAgent {
  id: string;
  name: string;
  role: string;
  persona: string;
}

interface Proposal {
  resumen_negocio: string;
  agents: ProposalAgent[];
  system_prompt_analista: string;
  campaign: Record<string, string>;
}

interface OnboardKnowledgeDebug {
  client_id: string;
  source_counts: Record<string, number>;
  chunk_counts: Record<string, number>;
  sources: Array<{ filename: string; source_type: string; chunk_count: number }>;
  knowledge_text: string;
}

// ── Onboarding Wizard ──────────────────────────────────────────────────────────

type WizardStep = 'account' | 'conversation' | 'upload' | 'analyze' | 'review' | 'done';

function OnboardingWizard({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [step, setStep] = useState<WizardStep>('account');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [tempUserId, setTempUserId] = useState('');
  // Transcript step
  const [transcript, setTranscript] = useState('');
  const [transcriptSaving, setTranscriptSaving] = useState(false);
  // Upload step
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [companyUrlInput, setCompanyUrlInput] = useState('');
  const [competitorUrlFields, setCompetitorUrlFields] = useState<string[]>(['']);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [editedProposal, setEditedProposal] = useState<Proposal | null>(null);
  const [creating, setCreating] = useState(false);
  const [approved, setApproved] = useState(false);
  const [showKnowledgeDebug, setShowKnowledgeDebug] = useState(false);
  const [knowledgeDebugLoading, setKnowledgeDebugLoading] = useState(false);
  const [knowledgeDebug, setKnowledgeDebug] = useState<OnboardKnowledgeDebug | null>(null);
  const [error, setError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);


  const resetOnboardingWorkspace = async (userId: string) => {
    try {
      await apiFetch(`${API_URL}/api/staff/clients/${userId}/knowledge`, {
        method: 'DELETE',
        credentials: 'include',
      });
    } catch {
      // Non-blocking: onboarding can continue even if reset fails
    }
    setSources([]);
    setEditedProposal(null);
    setTranscript('');
    setCompanyUrlInput('');
    setCompetitorUrlFields(['']);
    setShowKnowledgeDebug(false);
    setKnowledgeDebug(null);
  };

  const closeWizard = async () => {
    if (!approved && tempUserId) {
      try {
        await apiFetch(`${API_URL}/api/staff/onboard/discard/${tempUserId}`, {
          method: 'POST',
          credentials: 'include',
        });
      } catch {
        // Best effort; close anyway.
      }
    }
    onClose();
  };

  const fetchKnowledgeDebug = async () => {
    if (!tempUserId) return;
    setKnowledgeDebugLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/staff/onboard/debug-knowledge/${tempUserId}`, {
        credentials: 'include',
      });
      if (!res.ok) {
        const d = await res.json();
        setError(d.detail || 'No se pudo cargar el contexto de la Reina');
        return;
      }
      const data = await res.json() as OnboardKnowledgeDebug;
      setKnowledgeDebug(data);
      setShowKnowledgeDebug(true);
    } catch {
      setError('Error de conexión al cargar el contexto de la Reina');
    } finally {
      setKnowledgeDebugLoading(false);
    }
  };

  const isValidHttpUrl = (value: string) => {
    try {
      const parsed = new URL(value);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
      return false;
    }
  };

  const companyUrlTrim = companyUrlInput.trim();
  const companyUrlInvalid = companyUrlTrim.length > 0 && !isValidHttpUrl(companyUrlTrim);

  // Step 1: Create a temp client account
  const handleAccountNext = async () => {
    if (!email.trim() || !password.trim()) return setError('Email y contraseña requeridos');
    setError('');
    try {
      const res = await apiFetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password: password.trim() }),
      });
      if (!res.ok) {
        const d = await res.json();
        const detail = String(d?.detail || '');
        if (detail.toLowerCase().includes('already registered')) {
          const loginRes = await apiFetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email.trim(), password: password.trim() }),
          });
          if (!loginRes.ok) {
            return setError('Ese email ya existe con otra contraseña. Usa la contraseña correcta o un email nuevo.');
          }
          const loginData = await loginRes.json();
          if (loginData.role && loginData.role !== 'client') {
            return setError('Ese email ya existe pero no es de tipo cliente. Usa otro email.');
          }
          if (!loginData.user_id) {
            return setError('No se pudo resolver el usuario existente. Intenta de nuevo.');
          }
          const existingUserId = String(loginData.user_id);
          await resetOnboardingWorkspace(existingUserId);
          setTempUserId(existingUserId);
          setStep('conversation');
          return;
        }
        return setError(d.detail || 'No se pudo crear la cuenta');
      }
      const data = await res.json();
      await resetOnboardingWorkspace(String(data.id));
      setTempUserId(data.id);
      setStep('conversation');
    } catch {
      setError('Error de conexión');
    }
  };

  // Step 2 → 3: Save meeting transcript then move to upload
  const handleTranscriptNext = async () => {
    if (!transcript.trim()) { setStep('upload'); return; }
    setTranscriptSaving(true);
    setError('');
    try {
      const res = await apiFetch(`${API_URL}/api/staff/onboard/save-conversation/${tempUserId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text: transcript.trim() }),
      });
      if (!res.ok) {
        const d = await res.json();
        return setError(d.detail || 'No se pudo guardar la transcripción');
      }
      setStep('upload');
    } catch {
      setError('Error de conexión');
    } finally {
      setTranscriptSaving(false);
    }
  };

  // Upload one or more files to client's knowledge base
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !tempUserId) return;
    setUploading(true);
    setError('');
    const form = new FormData();
    Array.from(files).forEach(f => form.append('files', f));
    try {
      const res = await apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge/upload`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      });
      if (!res.ok) {
        const d = await res.json();
        setError(d.detail || 'Error al subir archivos');
      } else {
        await refreshSources();
      }
    } catch {
      setError('Error de conexión');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const ingestUrls = async (urls: string[], sourceType: 'url_empresa' | 'url_competencia') => {
    if (!tempUserId || urls.length === 0) return;
    setUploading(true);
    setError('');
    try {
      const res = await apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge/url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: tempUserId,
          urls,
          source_type: sourceType,
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        setError(d.detail || 'No se pudo obtener la URL');
      } else {
        await refreshSources();
      }
    } catch {
      setError('Error de conexión');
    } finally {
      setUploading(false);
    }
  };

  // Ingest single company URL
  const handleCompanyUrlIngest = async () => {
    const url = companyUrlInput.trim();
    if (!url) return;
    if (!isValidHttpUrl(url)) {
      setError('La URL de la empresa no es válida. Usa formato http(s)://...');
      return;
    }
    await ingestUrls([url], 'url_empresa');
    setCompanyUrlInput('');
  };

  // Ingest many competitor URLs in one shot
  const handleCompetitorUrlsIngest = async () => {
    const urls = competitorUrlFields.map(u => u.trim()).filter(Boolean);
    if (urls.length === 0) return;

    const invalidUrls = urls.filter(u => !isValidHttpUrl(u));
    if (invalidUrls.length > 0) {
      setError(`Hay ${invalidUrls.length} URL(s) de competencia inválidas. Corrígelas antes de enviar.`);
      return;
    }

    await ingestUrls(urls, 'url_competencia');
    setCompetitorUrlFields(['']);
  };

  const updateCompetitorUrlField = (index: number, value: string) => {
    setCompetitorUrlFields(prev => prev.map((v, i) => (i === index ? value : v)));
  };

  const addCompetitorUrlField = () => {
    setCompetitorUrlFields(prev => [...prev, '']);
  };

  const removeCompetitorUrlField = (index: number) => {
    setCompetitorUrlFields(prev => {
      if (prev.length <= 1) return [''];
      return prev.filter((_, i) => i !== index);
    });
  };

  const refreshSources = async () => {
    if (!tempUserId) return;
    const res = await apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge`, { credentials: 'include' });
    if (res.ok) setSources(await res.json());
  };

  const deleteSource = async (filename: string) => {
    await apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge/${encodeURIComponent(filename)}`, {
      method: 'DELETE', credentials: 'include',
    });
    setSources(prev => prev.filter(s => s.filename !== filename));
  };

  // Step 3: Queen analyzes docs
  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError('');
    try {
      const res = await apiFetch(`${API_URL}/api/staff/onboard/propose/${tempUserId}`, {
        method: 'POST', credentials: 'include',
      });
      if (!res.ok) {
        const d = await res.json();
        return setError(d.detail || 'La Reina no pudo generar la propuesta');
      }
      const p: Proposal = await res.json();
      setEditedProposal(JSON.parse(JSON.stringify(p))); // deep copy for editing
      setStep('review');
    } catch {
      setError('Error de conexión');
    } finally {
      setAnalyzing(false);
    }
  };

  // Step 5: Approve — save campaign + send welcome email
  const handleApprove = async () => {
    if (!editedProposal) return;
    setCreating(true);
    setError('');
    try {
      // Save campaign on behalf of the client via staff endpoint
      const saveCampRes = await apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/campaigns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editedProposal.campaign),
      });
      if (!saveCampRes.ok) throw new Error('No se pudo guardar la campaña');

      const saveProfileRes = await apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          business_summary: editedProposal.resumen_negocio,
          personality_prompt: editedProposal.system_prompt_analista,
          campaign: editedProposal.campaign,
          agents: editedProposal.agents,
        }),
      });
      if (!saveProfileRes.ok) throw new Error('No se pudo guardar el perfil de onboarding');

      // Send welcome email (fire & forget — don't block UX if it fails)
      apiFetch(`${API_URL}/api/staff/clients/${tempUserId}/send-welcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          password,
          agents: editedProposal.agents,
          campaign: editedProposal.campaign,
          business_summary: editedProposal.resumen_negocio,
          login_url: window.location.origin,
        }),
      }).catch(() => {}); // staff sees the result but we don't block on it

      setApproved(true);
      setStep('done');
      setTimeout(() => { onSuccess(); onClose(); }, 2000);
    } catch (e: unknown) {
      setError((e as Error).message || 'Error al crear cliente');
    } finally {
      setCreating(false);
    }
  };

  const updateCampaignField = (key: string, val: string) => {
    if (!editedProposal) return;
    setEditedProposal({ ...editedProposal, campaign: { ...editedProposal.campaign, [key]: val } });
  };

  const updateAgentName = (index: number, name: string) => {
    if (!editedProposal) return;
    const agents = [...editedProposal.agents];
    agents[index] = { ...agents[index], name };
    setEditedProposal({ ...editedProposal, agents });
  };

  return (
    <div style={wz.overlay}>
      <div style={wz.modal}>
        {/* Header */}
        <div style={wz.header}>
          <div style={wz.title}>Onboarding de nuevo cliente</div>
          <div style={wz.steps}>
            {(() => {
              const ORDER: WizardStep[] = ['account','conversation','upload','analyze','review','done'];
              const cur = ORDER.indexOf(step);
              return ORDER.map((s, i) => (
                <div key={s} style={{ ...wz.stepDot, background: i === cur ? cyan : i < cur ? green : s4 }} />
              ));
            })()}
          </div>
          <button style={wz.closeBtn} onClick={closeWizard}>✕</button>
        </div>

        <div style={wz.body}>
          {error && <div style={wz.error}>{error}</div>}

          {step !== 'done' && (
            <button style={wz.cancelBtn} onClick={closeWizard}>
              Cancelar onboarding y borrar borrador
            </button>
          )}

          {tempUserId && step !== 'account' && step !== 'done' && (
            <>
              <button
                style={wz.debugBtn}
                onClick={fetchKnowledgeDebug}
                disabled={knowledgeDebugLoading}
              >
                {knowledgeDebugLoading ? 'Cargando contexto...' : 'Ver contexto que verá la Reina'}
              </button>

              {showKnowledgeDebug && knowledgeDebug && (
                <div style={wz.debugPanel}>
                  <div style={wz.debugTitle}>Contexto jerarquizado (debug)</div>
                  <div style={wz.debugMeta}>
                    <strong>Fuentes:</strong> {Object.entries(knowledgeDebug.source_counts).map(([k, v]) => `${k}=${v}`).join(' · ') || '0'}
                  </div>
                  <div style={wz.debugMeta}>
                    <strong>Chunks:</strong> {Object.entries(knowledgeDebug.chunk_counts).map(([k, v]) => `${k}=${v}`).join(' · ') || '0'}
                  </div>
                  <pre style={wz.debugText}>{knowledgeDebug.knowledge_text || '[Sin contenido todavía]'}</pre>
                </div>
              )}
            </>
          )}

          {/* Step 1 — Account */}
          {step === 'account' && (
            <div style={wz.stepBody}>
              <div style={wz.stepTitle}>Paso 1: Datos de acceso del cliente</div>
              <div style={wz.field}>
                <label style={wz.label}>Email del cliente</label>
                <input style={wz.input} type="email" value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="cliente@empresa.com"
                  onKeyDown={e => e.key === 'Enter' && handleAccountNext()} />
              </div>
              <div style={wz.field}>
                <label style={wz.label}>Contraseña temporal</label>
                <input style={wz.input} type="password" value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Mínimo 8 caracteres"
                  onKeyDown={e => e.key === 'Enter' && handleAccountNext()} />
              </div>
              <button style={wz.primaryBtn} onClick={handleAccountNext}>
                Siguiente →
              </button>
            </div>
          )}

          {/* Step 2 — Meeting Transcript */}
          {step === 'conversation' && (
            <div style={{ ...wz.stepBody, height: '100%' }}>
              <div style={wz.stepTitle}>Paso 2: Transcripción de la reunión</div>
              <div style={wz.hint}>
                Pega aquí la transcripción de la reunión de levantamiento de requisitos con el cliente. La Reina la usará para proponer los agentes y la campaña. Si no tienes transcripción aún, puedes continuar y subir documentación en el paso siguiente.
              </div>

              <textarea
                style={{
                  ...wz.input,
                  width: '100%',
                  flex: 1,
                  minHeight: 180,
                  resize: 'vertical',
                  fontFamily: IN,
                  fontSize: 13,
                  lineHeight: 1.5,
                  padding: '10px 12px',
                  boxSizing: 'border-box',
                }}
                value={transcript}
                onChange={e => setTranscript(e.target.value)}
                placeholder="Pega aquí el texto de la reunión o entrevista con el cliente..."
              />

              <button
                style={{ ...wz.primaryBtn, marginTop: 8 }}
                disabled={transcriptSaving}
                onClick={handleTranscriptNext}
              >
                {transcriptSaving ? 'Guardando transcripción...' : transcript.trim() ? 'Guardar y continuar →' : 'Continuar sin transcripción →'}
              </button>
            </div>
          )}

          {/* Step 3 — Upload */}
          {step === 'upload' && (
            <div style={wz.stepBody}>
              <div style={wz.stepTitle}>Paso 3: Documentación del cliente</div>
              <div style={wz.hint}>
                Opcional — PDF, DOCX, texto, o URLs (tu web, la de la competencia, casos de uso). Puedes subir varios archivos a la vez. Si solo tienes la conversación, puedes continuar sin documentos.
              </div>

              {/* File upload — multiple */}
              <div style={wz.uploadRow}>
                <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" multiple
                  style={{ display: 'none' }}
                  onChange={handleFileUpload} />
                <button style={wz.uploadBtn} onClick={() => fileRef.current?.click()} disabled={uploading}>
                  {uploading ? 'Procesando...' : 'Subir archivos'}
                </button>
                <span style={{ fontSize: 11, color: muted, alignSelf: 'center' }}>Puedes seleccionar varios a la vez</span>
              </div>

              {/* URL ingest: Empresa */}
              <div style={wz.urlRow}>
                <input style={{ ...wz.input, ...((companyUrlInvalid) ? wz.inputError : {}), flex: 1 }} value={companyUrlInput}
                  onChange={e => setCompanyUrlInput(e.target.value)}
                  placeholder="https://web-oficial-de-la-empresa.com"
                  onKeyDown={e => e.key === 'Enter' && handleCompanyUrlIngest()} />
                <button style={wz.uploadBtn} onClick={handleCompanyUrlIngest} disabled={uploading || !companyUrlInput.trim() || companyUrlInvalid}>
                  Agregar web empresa
                </button>
              </div>
              {companyUrlInvalid && (
                <div style={wz.inlineError}>URL inválida. Debe iniciar con http:// o https://</div>
              )}

              {/* URL ingest: Competencia (multiple) */}
              <div style={{ ...wz.field, marginTop: 8 }}>
                <label style={wz.label}>URLs de competencia (varias)</label>
                {competitorUrlFields.map((value, index) => {
                  const trimmed = value.trim();
                  const isInvalid = trimmed.length > 0 && !isValidHttpUrl(trimmed);
                  return (
                    <div key={index} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input
                          style={{ ...wz.input, ...(isInvalid ? wz.inputError : {}), flex: 1 }}
                          value={value}
                          onChange={e => updateCompetitorUrlField(index, e.target.value)}
                          placeholder={`https://competidor${index + 1}.com`}
                        />
                        <button
                          style={wz.uploadBtn}
                          onClick={() => removeCompetitorUrlField(index)}
                          disabled={uploading}
                        >
                          ✕
                        </button>
                      </div>
                      {isInvalid && (
                        <div style={wz.inlineError}>URL inválida. Debe iniciar con http:// o https://</div>
                      )}
                    </div>
                  );
                })}
                <button
                  style={{ ...wz.uploadBtn, alignSelf: 'flex-start' }}
                  onClick={addCompetitorUrlField}
                  disabled={uploading}
                >
                  + Agregar otra URL
                </button>
                <button
                  style={{ ...wz.uploadBtn, marginTop: 6 }}
                  onClick={handleCompetitorUrlsIngest}
                  disabled={uploading || !competitorUrlFields.some(v => v.trim()) || competitorUrlFields.some(v => v.trim() && !isValidHttpUrl(v.trim()))}
                >
                  Agregar competencia (lote)
                </button>
              </div>

              <div style={{ fontSize: 11, color: faint, marginTop: -4 }}>
                La web oficial va separada. En competencia agrega un campo por URL.
              </div>

              {/* Sources list */}
              {sources.length > 0 && (
                <div style={wz.sourcesList}>
                  <div style={wz.sourcesTitle}>Fuentes cargadas ({sources.length})</div>
                  {sources.map(s => (
                    <div key={s.filename} style={wz.sourceRow}>
                      <span style={{ fontSize: 14 }}>
                        {s.source_type === 'url_empresa' ? '🏢'
                          : s.source_type === 'url_competencia' ? '🥊'
                            : s.source_type.includes('url') ? '🌐' : '📄'}
                      </span>
                      <span style={wz.sourceName}>{s.filename}</span>
                      <span style={{ ...wz.chunkBadge, background: s1, borderColor: s3 }}>
                        {s.source_type === 'url_empresa' ? 'Empresa'
                          : s.source_type === 'url_competencia' ? 'Competencia'
                            : s.source_type}
                      </span>
                      <span style={wz.chunkBadge}>{s.chunk_count} chunks</span>
                      <button style={wz.deleteBtn} onClick={() => deleteSource(s.filename)}>✕</button>
                    </div>
                  ))}
                </div>
              )}

              <button
                style={wz.primaryBtn}
                onClick={() => setStep('analyze')}
              >
                {sources.length > 0
                  ? `Siguiente → (${sources.length} fuente${sources.length !== 1 ? 's' : ''})`
                  : 'Continuar sin documentos →'}
              </button>
            </div>
          )}

          {/* Step 3 — Analyze */}
          {step === 'analyze' && (
            <div style={{ ...wz.stepBody, alignItems: 'center', textAlign: 'center' }}>
              <div style={wz.stepTitle}>Paso 4: La Reina analiza los documentos</div>
              <div style={wz.hint}>
                La Abeja Reina leerá toda la documentación y propondrá los agentes, el prompt del Analista y las variables de campaña óptimas.
              </div>
              {analyzing ? (
                <div style={wz.analyzingBox}>
                  <div style={{ fontSize: 40, marginBottom: 16 }}>🐝</div>
                  <div style={{ color: '#ffd866', fontWeight: 600, fontFamily: SG }}>Analizando documentación...</div>
                  <div style={{ color: muted, fontSize: 12, marginTop: 8, fontFamily: IN }}>Esto tarda ~15 segundos</div>
                </div>
              ) : (
                <button style={wz.primaryBtn} onClick={handleAnalyze}>
                  Analizar con la Reina
                </button>
              )}
            </div>
          )}

          {/* Step 5 — Review */}
          {step === 'review' && editedProposal && (
            <div style={wz.stepBody}>
              <div style={wz.stepTitle}>Paso 5: Revisar y aprobar propuesta</div>

              {/* Business summary */}
              <div style={wz.proposalSection}>
                <div style={wz.proposalLabel}>Resumen del negocio</div>
                <div style={wz.proposalText}>{editedProposal.resumen_negocio}</div>
              </div>

              {/* Agents */}
              <div style={wz.proposalSection}>
                <div style={wz.proposalLabel}>Agentes propuestos</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {editedProposal.agents.map((agent, i) => (
                    <div key={agent.id} style={wz.agentCard}>
                      <div style={wz.agentRow}>
                        <div style={{ ...wz.agentDot, background: PALETTE_COLORS[i % PALETTE_COLORS.length] }} />
                        <input
                          style={wz.agentNameInput}
                          value={agent.name}
                          onChange={e => updateAgentName(i, e.target.value)}
                        />
                        <span style={wz.agentRole}>{agent.role}</span>
                      </div>
                      <div style={wz.agentPersona}>{agent.persona}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Campaign variables */}
              <div style={wz.proposalSection}>
                <div style={wz.proposalLabel}>Variables de campaña</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {Object.keys(editedProposal.campaign).map((key) => (
                    <div key={key} style={wz.campRow}>
                      <span style={wz.campLabel}>{CAMPAIGN_LABELS[key] || humanizeCampaignKey(key)}</span>
                      <input
                        style={wz.campInput}
                        value={editedProposal.campaign[key] || ''}
                        onChange={e => updateCampaignField(key, e.target.value)}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <button style={wz.primaryBtn} onClick={handleApprove} disabled={creating}>
                {creating ? 'Creando cuenta...' : 'Aprobar y crear cuenta'}
              </button>
            </div>
          )}

          {/* Step 5 — Done */}
          {step === 'done' && (
            <div style={{ ...wz.stepBody, alignItems: 'center', textAlign: 'center' }}>
              <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
              <div style={{ color: green, fontWeight: 700, fontSize: 18, fontFamily: SG }}>Cliente onboardado!</div>
              <div style={{ color: muted, fontSize: 13, marginTop: 8, fontFamily: IN }}>{email}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const wz: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    width: 540, maxHeight: '85vh',
    background: 'rgba(18,18,29,0.97)',
    backdropFilter: 'blur(12px)',
    border: '0.5px solid rgba(120,220,232,0.15)',
    boxShadow: '0 0 60px rgba(171,157,242,0.1)',
    borderRadius: 14,
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '16px 20px',
    borderBottom: '1px solid transparent',
    backgroundImage: 'linear-gradient(rgba(18,18,29,0.97),rgba(18,18,29,0.97)),linear-gradient(to right,transparent,rgba(120,220,232,0.2),transparent)',
    backgroundOrigin: 'border-box',
    flexShrink: 0,
  },
  title: { fontSize: 16, fontWeight: 700, color: text, flex: 1, fontFamily: SG },
  steps: { display: 'flex', gap: 6, alignItems: 'center' },
  stepDot: { width: 10, height: 10, borderRadius: '50%', transition: 'background 0.3s' },
  closeBtn: { background: 'transparent', border: 'none', color: muted, cursor: 'pointer', fontSize: 16, fontFamily: SG },
  body: { flex: 1, overflowY: 'auto', padding: '20px 24px' },
  error: {
    background: 'rgba(255,97,136,0.08)', border: '1px solid rgba(255,97,136,0.3)', borderRadius: 8,
    color: pink, fontSize: 13, padding: '10px 14px', marginBottom: 16, fontFamily: IN,
  },
  cancelBtn: {
    width: '100%',
    padding: '9px 0',
    marginBottom: 10,
    background: 'transparent',
    border: '1px solid rgba(255,97,136,0.3)',
    borderRadius: 8,
    color: 'rgba(255,97,136,0.7)',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: SG,
  },
  debugBtn: {
    width: '100%',
    padding: '9px 0',
    marginBottom: 10,
    background: s1,
    border: '1px solid rgba(120,220,232,0.15)',
    borderRadius: 8,
    color: cyan,
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: SG,
  },
  debugPanel: {
    background: bg,
    border: '1px solid rgba(120,220,232,0.12)',
    borderRadius: 8,
    padding: '10px 12px',
    marginBottom: 12,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  debugTitle: { fontSize: 11, color: cyan, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8, fontFamily: SG },
  debugMeta: { fontSize: 11, color: muted, fontFamily: IN },
  debugText: {
    margin: 0,
    maxHeight: 220,
    overflowY: 'auto',
    whiteSpace: 'pre-wrap',
    fontSize: 11,
    lineHeight: 1.4,
    color: text,
    background: s0,
    border: '1px solid rgba(120,220,232,0.1)',
    borderRadius: 6,
    padding: '8px 9px',
    fontFamily: IN,
  },
  stepBody: { display: 'flex', flexDirection: 'column', gap: 14 },
  stepTitle: { fontSize: 15, fontWeight: 700, color: cyan, fontFamily: SG },
  hint: { color: muted, fontSize: 13, lineHeight: 1.5, fontFamily: IN },
  field: { display: 'flex', flexDirection: 'column', gap: 4 },
  label: { fontSize: 12, color: muted, fontFamily: SG },
  input: {
    padding: '9px 12px',
    background: s2,
    border: 'none',
    borderBottom: '1px solid rgba(120,220,232,0.25)',
    borderRadius: 0,
    color: text,
    fontSize: 13,
    fontFamily: IN,
    outline: 'none',
  },
  inputError: {
    borderBottom: '1px solid rgba(255,97,136,0.7)',
    boxShadow: '0 0 0 1px rgba(255,97,136,0.15) inset',
  },
  inlineError: {
    color: pink,
    fontSize: 11,
    marginTop: -8,
    fontFamily: IN,
  },
  primaryBtn: {
    padding: '11px 0', background: grad,
    border: 'none', borderRadius: 8, color: '#fff', fontWeight: 700,
    fontSize: 14, cursor: 'pointer', fontFamily: SG,
  },
  uploadRow: { display: 'flex', gap: 8 },
  urlRow: { display: 'flex', gap: 8 },
  uploadBtn: {
    padding: '9px 14px', background: s2, border: '1px solid rgba(120,220,232,0.15)',
    borderRadius: 8, color: cyan, cursor: 'pointer', fontSize: 13,
    whiteSpace: 'nowrap', fontFamily: SG,
  },
  sourcesList: {
    background: s0, borderRadius: 8, padding: '10px 12px',
    display: 'flex', flexDirection: 'column', gap: 6,
    border: '1px solid rgba(120,220,232,0.1)',
  },
  sourcesTitle: { fontSize: 11, color: muted, fontWeight: 600, marginBottom: 4, fontFamily: SG },
  sourceRow: { display: 'flex', alignItems: 'center', gap: 8 },
  sourceName: { flex: 1, fontSize: 12, color: text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: IN },
  chunkBadge: { fontSize: 10, color: muted, background: s3, padding: '2px 6px', borderRadius: 4, fontFamily: SG },
  deleteBtn: { background: 'transparent', border: 'none', color: pink, cursor: 'pointer', fontSize: 13 },
  convBox: {
    flex: 1,
    minHeight: 200,
    maxHeight: 280,
    overflowY: 'auto',
    background: s0,
    borderRadius: 10,
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  convBubbleBot: {
    background: s1,
    border: '1px solid rgba(120,220,232,0.1)',
    borderRadius: '12px 12px 12px 4px',
    padding: '10px 14px',
    fontSize: 13,
    color: text,
    maxWidth: '85%',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
    fontFamily: IN,
  },
  convBubbleUser: {
    background: 'rgba(171,157,242,0.08)',
    border: '1px solid rgba(171,157,242,0.2)',
    borderRadius: '12px 12px 4px 12px',
    padding: '10px 14px',
    fontSize: 13,
    color: text,
    maxWidth: '85%',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
    fontFamily: IN,
  },
  analyzingBox: {
    background: s0, borderRadius: 12, padding: '32px 24px',
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    border: '1px solid rgba(120,220,232,0.1)',
  },
  proposalSection: {
    background: s1, borderRadius: 8, padding: '12px 16px',
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  proposalLabel: { fontSize: 9, fontWeight: 700, color: cyan, textTransform: 'uppercase', letterSpacing: 1, fontFamily: SG },
  proposalText: { fontSize: 13, color: text, lineHeight: 1.5, fontFamily: IN },
  agentCard: {
    background: s2,
    borderRadius: 6,
    padding: '8px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  agentRow: { display: 'flex', alignItems: 'center', gap: 8 },
  agentDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0 },
  agentNameInput: {
    padding: '5px 9px', background: s3, border: 'none',
    borderBottom: '1px solid rgba(120,220,232,0.2)',
    borderRadius: 0, color: text, fontSize: 13, flex: 1, fontFamily: IN, outline: 'none',
  },
  agentRole: {
    fontSize: 10,
    color: cyan,
    background: 'rgba(120,220,232,0.08)',
    borderRadius: 999,
    padding: '2px 8px',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    fontFamily: SG,
  },
  agentPersona: { fontSize: 12, color: muted, lineHeight: 1.45, whiteSpace: 'normal', wordBreak: 'break-word', fontFamily: IN },
  campRow: { display: 'flex', alignItems: 'center', gap: 8 },
  campLabel: { fontSize: 11, color: muted, minWidth: 110, fontFamily: SG },
  campInput: {
    flex: 1, padding: '5px 9px', background: s3, border: 'none',
    borderBottom: '1px solid rgba(120,220,232,0.2)',
    borderRadius: 0, color: text, fontSize: 12, fontFamily: IN, outline: 'none',
  },
};


// ── Main Dashboard ─────────────────────────────────────────────────────────────

interface LearningData {
  ideal_count: number;
  rejected_count: number;
  patterns: Array<{ description: string; confidence: string; evidence_count: number }>;
}

// Duplicate StaffDashboard removed. Only the merged, tabbed version remains at the top.


function CobranzaToggle({ clientId, enabled, onToggle }: {
  clientId: string;
  enabled: boolean;
  onToggle: (val: boolean) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggle = async () => {
    setLoading(true);
    setError('');
    const action = enabled ? 'disable' : 'enable';
    try {
      const res = await apiFetch(`${API_URL}/api/staff/clients/${clientId}/cobranza/${action}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError((d as { detail?: string }).detail || 'Error');
        return;
      }
      onToggle(!enabled);
    } catch {
      setError('Error de conexión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontSize: 13, color: text, fontFamily: IN, fontWeight: 500 }}>
            {enabled ? 'Habilitado' : 'Deshabilitado'}
          </div>
          <div style={{ fontSize: 12, color: muted, fontFamily: IN, marginTop: 3 }}>
            {enabled
              ? 'El cliente verá el onboarding de cobranza en su dashboard.'
              : 'El cliente no tiene acceso al agente de llamadas.'}
          </div>
        </div>
        <button
          onClick={toggle}
          disabled={loading}
          style={{
            padding: '8px 18px',
            borderRadius: 8,
            border: 'none',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontFamily: IN,
            fontWeight: 600,
            fontSize: 13,
            opacity: loading ? 0.6 : 1,
            background: enabled ? `${pink}22` : `${green}22`,
            color: enabled ? pink : green,
            transition: 'all 0.2s',
          }}
        >
          {loading ? '...' : enabled ? 'Deshabilitar' : 'Habilitar'}
        </button>
      </div>
      {error && <div style={{ fontSize: 12, color: pink, fontFamily: IN }}>{error}</div>}
    </div>
  );
}

function FuentesPanel({ client }: { client: ClientData }) {
  const [fuentes, setFuentes] = useState<string[]>(client.fuentes_habilitadas ?? ['google_maps']);
  const [notificationChannel, setNotificationChannel] = useState<string>(client.notification_channel ?? 'web');
  const [waPhoneNumber, setWaPhoneNumber] = useState<string>(client.wa_phone_number ?? '');
  const [waPhoneId] = useState<string>(client.wa_phone_id ?? '');
  const [waBots, setWaBots] = useState<Record<string, boolean>>({ landa: true, secop: false });
  const [saving, setSaving] = useState(false);

  // Load bot flags from backend on mount
  React.useEffect(() => {
    if (!client.wa_phone_number) return;
    apiFetch(`${API_URL}/api/staff/wa-config/${encodeURIComponent(client.wa_phone_number)}`).then(r => r.ok ? r.json() : null).then(d => {
      if (d?.bots) setWaBots(d.bots);
    }).catch(() => {});
  }, [client.wa_phone_number]);

  const toggleFuente = async (fuente: string) => {
    const updated = fuentes.includes(fuente)
      ? fuentes.filter(f => f !== fuente)
      : [...fuentes, fuente];
    // Always keep google_maps
    const final = updated.includes('google_maps') ? updated : ['google_maps', ...updated];
    setFuentes(final);
    await saveSources(final, notificationChannel, waPhoneNumber, waPhoneId);
  };

  const saveSources = async (
    fuentesList: string[],
    channel: string,
    phoneNum: string,
    phoneId: string,
  ) => {
    setSaving(true);
    try {
      const body: Record<string, any> = {
        fuentes_habilitadas: fuentesList,
        notification_channel: channel,
      };
      if (phoneNum) body.wa_phone_number = phoneNum;
      if (phoneId) body.wa_phone_id = phoneId;

      await apiFetch(`${API_URL}/api/staff/clients/${client.id}/sources`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (e) {
      console.error('[FuentesPanel]', e);
    } finally {
      setSaving(false);
    }
  };

  const handleChannelChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newChannel = e.target.value;
    setNotificationChannel(newChannel);
    await saveSources(fuentes, newChannel, waPhoneNumber, waPhoneId);
  };

  const handleWaPhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setWaPhoneNumber(e.target.value);
  };


  const FUENTE_LABELS: Record<string, string> = {
    google_maps: 'Google Maps + Web scraping',
    secop_adjudicados: 'SECOP — Empresas adjudicadas (premium)',
    secop_licitaciones: 'SECOP — Licitaciones abiertas (premium — aseguradoras)',
  };

  return (
    <div style={{
      marginTop: 12, padding: '16px', background: s1, borderRadius: 10,
    }}>
      <div style={{ color: cyan, fontFamily: SG, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
        Fuentes de descubrimiento {saving && '(guardando...)'}
      </div>
      {Object.entries(FUENTE_LABELS).map(([key, label]) => (
        <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: key === 'google_maps' ? 'default' : 'pointer' }}>
          <input
            type="checkbox"
            checked={fuentes.includes(key)}
            disabled={key === 'google_maps'}
            onChange={() => key !== 'google_maps' && toggleFuente(key)}
          />
          <span style={{ color: text, fontSize: 12, fontFamily: IN }}>{label}</span>
        </label>
      ))}

      <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${faint}` }}>
        <div style={{ color: cyan, fontFamily: SG, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
          Canal de notificación
        </div>
        <select
          value={notificationChannel}
          onChange={handleChannelChange}
          style={{
            width: '100%',
            padding: '6px 8px',
            background: s2,
            color: text,
            border: 'none',
            borderBottom: '1px solid rgba(120,220,232,0.2)',
            borderRadius: 0,
            fontFamily: IN,
            fontSize: 12,
            marginBottom: 8,
            outline: 'none',
          }}
        >
          <option value="web">Web (panel)</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="both">Web + WhatsApp</option>
        </select>

        {(notificationChannel === 'whatsapp' || notificationChannel === 'both') && (
          <div style={{ marginTop: 8 }}>
            <div style={{ color: muted, fontSize: 10, marginBottom: 4, fontFamily: SG }}>Número WhatsApp del cliente (p.ej. +57300...)</div>
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                type="text"
                placeholder="+5730012345678"
                value={waPhoneNumber}
                onChange={handleWaPhoneChange}
                style={{
                  flex: 1,
                  padding: '6px 8px',
                  background: s2,
                  color: text,
                  border: 'none',
                  borderBottom: '1px solid rgba(120,220,232,0.2)',
                  borderRadius: 0,
                  fontFamily: IN,
                  fontSize: 12,
                  outline: 'none',
                }}
              />
              <button
                onClick={() => saveSources(fuentes, notificationChannel, waPhoneNumber, waPhoneId)}
                disabled={saving}
                style={{
                  padding: '6px 14px',
                  background: saving ? s3 : grad,
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  fontFamily: SG,
                  fontSize: 12,
                  cursor: saving ? 'default' : 'pointer',
                  fontWeight: 700,
                }}
              >
                {saving ? '...' : 'Guardar'}
              </button>
            </div>

            {/* Bot flags */}
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${faint}` }}>
              <div style={{ color: muted, fontSize: 10, marginBottom: 6, fontFamily: SG }}>Bots habilitados</div>
              {[{ key: 'landa', label: 'Landa (leads y gestión)' }, { key: 'secop', label: 'SECOP (prospección)' }].map(({ key, label }) => (
                <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={!!waBots[key]}
                    onChange={async (e) => {
                      const updated = { ...waBots, [key]: e.target.checked };
                      setWaBots(updated);
                      await apiFetch(`${API_URL}/api/staff/wa-config/${encodeURIComponent(waPhoneNumber)}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ bots: updated }),
                      });
                    }}
                  />
                  <span style={{ color: text, fontSize: 12, fontFamily: IN }}>{label}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={sectionStyles.wrap}>
      <div style={sectionStyles.title}>
        <span>{title}</span>
        <div style={sectionStyles.titleLine} />
      </div>
      <div style={sectionStyles.body}>{children}</div>
    </div>
  );
}

const sectionStyles: Record<string, React.CSSProperties> = {
  wrap: { marginBottom: 28 },
  title: {
    fontSize: 13, fontWeight: 700, color: cyan,
    textTransform: 'uppercase', letterSpacing: '0.08em',
    fontFamily: SG,
    display: 'flex', alignItems: 'center', gap: 8,
  },
  titleLine: {
    flex: 1, height: 1,
    background: 'linear-gradient(to right,rgba(120,220,232,0.3),transparent)',
  },
  body: { paddingTop: 14 },
};

const s: Record<string, React.CSSProperties> = {
  page: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: bg,
    color: text,
    fontFamily: IN,
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0 24px',
    height: 64,
    background: s0,
    flexShrink: 0,
    position: 'relative',
  },
  headerGradSep: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0,
    height: 1,
    background: 'linear-gradient(to right,transparent,rgba(120,220,232,0.2),transparent)',
  },
  logoRow: { display: 'flex', alignItems: 'center', gap: 12 },
  logoText: {
    fontSize: 20,
    fontWeight: 700,
    color: cyan,
    fontFamily: SG,
    lineHeight: 1,
  },
  logoSub: {
    fontSize: 10, color: purple, fontFamily: SG,
    textTransform: 'uppercase', letterSpacing: '0.1em',
    marginTop: 2,
  },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  onboardBtn: {
    padding: '7px 16px', borderRadius: 7, border: 'none',
    background: grad, color: '#fff', cursor: 'pointer',
    fontSize: 13, fontWeight: 700, fontFamily: SG,
  },
  diagBtn: {
    padding: '7px 12px', borderRadius: 7,
    border: '0.5px solid rgba(120,220,232,0.3)',
    background: 'transparent', color: cyan, cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: SG,
  },
  emailBadge: { fontSize: 12, color: muted, fontFamily: SG },
  logoutBtn: {
    padding: '6px 14px', borderRadius: 6,
    border: '0.5px solid rgba(120,220,232,0.2)',
    background: 'transparent', color: muted, cursor: 'pointer', fontSize: 12, fontFamily: SG,
  },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  sidebar: {
    width: 260,
    flexShrink: 0,
    background: s0,
    overflowY: 'auto',
    padding: '20px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  sidebarStatus: {
    fontSize: 9, color: purple, fontFamily: SG, fontStyle: 'italic',
    textTransform: 'uppercase', letterSpacing: '0.12em',
    padding: '0 4px', marginBottom: 2,
  },
  sidebarTitle: {
    fontSize: 13, fontWeight: 700, color: cyan, fontFamily: SG,
    padding: '0 4px', marginBottom: 10,
  },
  clientCard: {
    padding: '10px 12px',
    borderRadius: 8,
    background: 'transparent',
    cursor: 'pointer',
    borderRight: '2px solid transparent',
    transition: 'background 0.15s, border-color 0.15s',
  },
  clientCardActive: {
    background: 'rgba(120,220,232,0.06)',
    borderRight: `2px solid ${cyan}`,
    boxShadow: '0 0 10px rgba(120,220,232,0.15)',
  },
  clientEmail: {
    fontSize: 11, fontWeight: 700, color: muted,
    fontFamily: SG, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  clientEmailActive: {
    fontSize: 11, fontWeight: 700, color: cyan,
    fontFamily: SG, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  clientCampaignLabel: {
    fontSize: 9, color: faint, fontFamily: SG,
    textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 3,
  },
  detail: { flex: 1, overflowY: 'auto', padding: '28px 32px', background: bg },
  emptyState: {
    height: '100%', display: 'flex',
    flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
  },
  emptyStateText: {
    color: muted, fontSize: 14, fontFamily: SG,
  },
  detailHeader: { marginBottom: 32 },
  detailNodeRow: {
    display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6,
  },
  detailNodeLabel: {
    fontSize: 10, color: purple, fontFamily: SG,
    textTransform: 'uppercase', letterSpacing: '0.1em',
  },
  activeChip: {
    fontSize: 10, color: green, fontFamily: SG,
    background: 'rgba(169,220,118,0.1)',
    padding: '2px 8px', borderRadius: 4,
    textTransform: 'uppercase', letterSpacing: '0.08em',
  },
  detailEmail: {
    fontSize: 32, fontWeight: 700, color: text,
    fontFamily: SG, marginBottom: 14, lineHeight: 1.1,
    wordBreak: 'break-all',
  },
  detailSubRow: { display: 'flex', gap: 10 },
  statCard: {
    background: s1, borderRadius: 8, padding: '10px 16px',
    borderLeft: '2px solid transparent',
    minWidth: 80,
  },
  statCardValue: {
    fontSize: 22, fontWeight: 700, color: cyan, fontFamily: SG, lineHeight: 1,
  },
  statCardLabel: {
    fontSize: 10, color: muted, fontFamily: SG,
    textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 4,
  },
  statPill: {
    fontSize: 12, padding: '4px 10px', borderRadius: 12,
    background: s3, color: muted, fontFamily: IN,
  },
  agentGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))',
    gap: 12,
  },
  agentCard: {
    background: s1,
    borderRadius: 10,
    padding: '16px',
    position: 'relative',
    overflow: 'hidden',
  },
  agentStatusDot: {
    position: 'absolute', top: 12, right: 12,
    width: 6, height: 6, borderRadius: '50%',
  },
  agentIcon: {
    width: 36, height: 36, borderRadius: 8,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 16, fontWeight: 700, fontFamily: SG,
    marginBottom: 10,
  },
  agentName: { fontSize: 13, fontWeight: 700, color: text, fontFamily: SG, marginBottom: 2 },
  agentRole: { fontSize: 10, color: muted, textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: SG, marginBottom: 10 },
  agentProgressTrack: {
    height: 3, background: s4, borderRadius: 2, overflow: 'hidden',
  },
  agentProgressBar: {
    height: '100%', borderRadius: 2, transition: 'width 0.5s ease',
  },
  runtimeLimitNote: { fontSize: 11, color: '#ffd866', marginTop: 10, fontFamily: IN },
  rootPromptBox: {
    fontSize: 12,
    color: text,
    background: s1,
    border: '1px solid rgba(120,220,232,0.1)',
    borderRadius: 8,
    padding: '10px 12px',
    whiteSpace: 'pre-wrap',
    lineHeight: 1.45,
    marginBottom: 10,
    fontFamily: IN,
  },
  rootAgentsList: { display: 'flex', flexDirection: 'column', gap: 8 },
  rootAgentRow: {
    padding: '8px 10px',
    borderRadius: 8,
    background: s1,
    border: '1px solid rgba(120,220,232,0.08)',
  },
  rootAgentName: { fontSize: 12, fontWeight: 600, color: text, fontFamily: SG },
  rootAgentMeta: { fontSize: 11, color: muted, marginTop: 2, fontFamily: IN },
  campaignGrid: { display: 'flex', flexDirection: 'column', gap: 8 },
  campaignRow: { display: 'flex', gap: 12, alignItems: 'flex-start' },
  campaignLabel: { fontSize: 11, color: cyan, minWidth: 130, flexShrink: 0, paddingTop: 1, fontFamily: SG },
  campaignValue: { fontSize: 13, color: text, flex: 1, fontFamily: IN },
  leadsList: { display: 'flex', flexDirection: 'column', gap: 0 },
  leadRow: {
    display: 'flex', alignItems: 'flex-start', gap: 12,
    padding: '12px 0',
  },
  leadDot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0, marginTop: 5 },
  leadInfo: { flex: 1, minWidth: 0 },
  leadName: { fontSize: 13, fontWeight: 700, color: text, marginBottom: 2, fontFamily: SG },
  leadUrl: { fontSize: 11, color: muted, fontFamily: IN },
  leadDecissor: { fontSize: 11, color: cyan, marginTop: 3, fontFamily: IN },
  leadMeta: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 },
  scoreBadge: {
    fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
    background: 'rgba(120,220,232,0.1)', color: cyan, fontFamily: SG,
  },
  hitlBadge: { fontSize: 11, fontFamily: SG },
  sendEmailBtn: {
    fontSize: 11, padding: '3px 8px', borderRadius: 4,
    background: 'rgba(120,220,232,0.08)', border: '1px solid rgba(120,220,232,0.2)',
    color: cyan, cursor: 'pointer', fontFamily: SG,
  },
  sendEmailBtnSent: {
    background: 'rgba(169,220,118,0.08)', border: '1px solid rgba(169,220,118,0.2)',
    color: green, cursor: 'default',
  },
  loading: { color: muted, fontSize: 13, fontFamily: IN },
  patternCard: {
    background: s1, borderRadius: 10,
    padding: '16px 18px',
  },
  patternText: { fontSize: 13, color: text, flex: 1, lineHeight: 1.4, fontFamily: IN },
};
