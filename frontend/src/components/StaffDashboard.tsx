import { useState, useEffect, useCallback, useRef } from 'react';
import { useOfficeStore } from '../store/officeStore';

const API_URL = 'http://localhost:8001';

// Pipeline agents definition (mirrors hive_graph.py PIPELINE_AGENTS)
const PIPELINE_AGENTS = [
  { id: 'buscador-001', name: 'Buscador',    role: 'researcher', palette: 0 },
  { id: 'scraper-001',  name: 'Scraper',      role: 'planner',    palette: 1 },
  { id: 'analista-001', name: 'Analista B2B', role: 'reviewer',   palette: 2 },
  { id: 'redactor-001', name: 'Redactor',     role: 'writer',     palette: 3 },
];

const PALETTE_COLORS = ['#78dce8', '#a9dc76', '#ffd866', '#ff6188'];

const CAMPAIGN_LABELS: Record<string, string> = {
  nombre_remitente:    'Remitente',
  empresa_remitente:   'Empresa',
  industria_objetivo:  'Industria objetivo',
  ciudad_objetivo:     'Ciudad',
  dolor_operativo:     'Dolor operativo',
  solucion_ofrecida:   'Solución',
  software_clave:      'Software clave',
  jerarquia_decisores: 'Decisores',
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

  const auth = () => ({ Authorization: `Bearer ${useOfficeStore.getState().authToken}` });

  const resetOnboardingWorkspace = async (userId: string) => {
    try {
      await fetch(`${API_URL}/api/staff/clients/${userId}/knowledge`, {
        method: 'DELETE',
        headers: auth(),
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
        await fetch(`${API_URL}/api/staff/onboard/discard/${tempUserId}`, {
          method: 'POST',
          headers: auth(),
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
      const res = await fetch(`${API_URL}/api/staff/onboard/debug-knowledge/${tempUserId}`, {
        headers: auth(),
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
      const res = await fetch(`${API_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password: password.trim() }),
      });
      if (!res.ok) {
        const d = await res.json();
        const detail = String(d?.detail || '');
        if (detail.toLowerCase().includes('already registered')) {
          const loginRes = await fetch(`${API_URL}/auth/login`, {
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
      const res = await fetch(`${API_URL}/api/staff/onboard/save-conversation/${tempUserId}`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
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
      const res = await fetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge/upload`, {
        method: 'POST',
        headers: auth(),
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
      const res = await fetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge/url`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
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
    const res = await fetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge`, { headers: auth() });
    if (res.ok) setSources(await res.json());
  };

  const deleteSource = async (filename: string) => {
    await fetch(`${API_URL}/api/staff/clients/${tempUserId}/knowledge/${encodeURIComponent(filename)}`, {
      method: 'DELETE', headers: auth(),
    });
    setSources(prev => prev.filter(s => s.filename !== filename));
  };

  // Step 3: Queen analyzes docs
  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError('');
    try {
      const res = await fetch(`${API_URL}/api/staff/onboard/propose/${tempUserId}`, {
        method: 'POST', headers: auth(),
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
      // Log in as the new client to get their token, then save campaign
      const loginRes = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!loginRes.ok) throw new Error('No se pudo autenticar al nuevo cliente');
      const loginData = await loginRes.json();
      const clientToken = loginData.access_token;

      const saveCampRes = await fetch(`${API_URL}/api/campaigns`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${clientToken}` },
        body: JSON.stringify(editedProposal.campaign),
      });
      if (!saveCampRes.ok) throw new Error('No se pudo guardar la campaña');

      const saveProfileRes = await fetch(`${API_URL}/api/staff/clients/${tempUserId}/profile`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          business_summary: editedProposal.resumen_negocio,
          personality_prompt: editedProposal.system_prompt_analista,
          campaign: editedProposal.campaign,
          agents: editedProposal.agents,
        }),
      });
      if (!saveProfileRes.ok) throw new Error('No se pudo guardar el perfil de onboarding');

      // Send welcome email (fire & forget — don't block UX if it fails)
      fetch(`${API_URL}/api/staff/clients/${tempUserId}/send-welcome`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
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
          <div style={wz.title}>🐝 Onboarding de nuevo cliente</div>
          <div style={wz.steps}>
            {(() => {
              const ORDER: WizardStep[] = ['account','conversation','upload','analyze','review','done'];
              const cur = ORDER.indexOf(step);
              return ORDER.map((s, i) => (
                <div key={s} style={{ ...wz.stepDot, background: i === cur ? '#78dce8' : i < cur ? '#a9dc76' : '#2a2a4a' }} />
              ));
            })()}
          </div>
          <button style={wz.closeBtn} onClick={closeWizard}>✕</button>
        </div>

        <div style={wz.body}>
          {error && <div style={wz.error}>{error}</div>}

          {step !== 'done' && (
            <button style={wz.cancelBtn} onClick={closeWizard}>
              🗑 Cancelar onboarding y borrar borrador
            </button>
          )}

          {tempUserId && step !== 'account' && step !== 'done' && (
            <>
              <button
                style={wz.debugBtn}
                onClick={fetchKnowledgeDebug}
                disabled={knowledgeDebugLoading}
              >
                {knowledgeDebugLoading ? '⏳ Cargando contexto...' : '👁 Ver contexto que verá la Reina'}
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
                  fontFamily: 'inherit',
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
                {transcriptSaving ? '⏳ Guardando transcripción...' : transcript.trim() ? 'Guardar y continuar →' : 'Continuar sin transcripción →'}
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
                  {uploading ? '⏳ Procesando...' : '📎 Subir archivos'}
                </button>
                <span style={{ fontSize: 11, color: '#666', alignSelf: 'center' }}>Puedes seleccionar varios a la vez</span>
              </div>

              {/* URL ingest: Empresa */}
              <div style={wz.urlRow}>
                <input style={{ ...wz.input, ...((companyUrlInvalid) ? wz.inputError : {}), flex: 1 }} value={companyUrlInput}
                  onChange={e => setCompanyUrlInput(e.target.value)}
                  placeholder="https://web-oficial-de-la-empresa.com"
                  onKeyDown={e => e.key === 'Enter' && handleCompanyUrlIngest()} />
                <button style={wz.uploadBtn} onClick={handleCompanyUrlIngest} disabled={uploading || !companyUrlInput.trim() || companyUrlInvalid}>
                  🏢 Agregar web empresa
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
                  🥊 Agregar competencia (lote)
                </button>
              </div>

              <div style={{ fontSize: 11, color: '#555', marginTop: -4 }}>
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
                      <span style={{ ...wz.chunkBadge, background: '#1e1e35', borderColor: '#2a2a4e' }}>
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
                  <div style={{ color: '#ffd866', fontWeight: 600 }}>Analizando documentación...</div>
                  <div style={{ color: '#888', fontSize: 12, marginTop: 8 }}>Esto tarda ~15 segundos</div>
                </div>
              ) : (
                <button style={wz.primaryBtn} onClick={handleAnalyze}>
                  🐝 Analizar con la Reina
                </button>
              )}
            </div>
          )}

          {/* Step 4 — Review */}
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
                {creating ? '⏳ Creando cuenta...' : '✅ Aprobar y crear cuenta'}
              </button>
            </div>
          )}

          {/* Step 5 — Done */}
          {step === 'done' && (
            <div style={{ ...wz.stepBody, alignItems: 'center', textAlign: 'center' }}>
              <div style={{ fontSize: 56, marginBottom: 16 }}>🎉</div>
              <div style={{ color: '#a9dc76', fontWeight: 700, fontSize: 18 }}>¡Cliente onboardado!</div>
              <div style={{ color: '#888', fontSize: 13, marginTop: 8 }}>{email}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const wz: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    width: 540, maxHeight: '85vh', background: '#1a1a2e',
    border: '1px solid #2a2a4a', borderRadius: 16,
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '16px 20px', borderBottom: '1px solid #2a2a4a',
    flexShrink: 0,
  },
  title: { fontSize: 16, fontWeight: 700, color: '#e0e0e0', flex: 1 },
  steps: { display: 'flex', gap: 6, alignItems: 'center' },
  stepDot: { width: 10, height: 10, borderRadius: '50%', transition: 'background 0.3s' },
  closeBtn: { background: 'transparent', border: 'none', color: '#888', cursor: 'pointer', fontSize: 16 },
  body: { flex: 1, overflowY: 'auto', padding: '20px 24px' },
  error: {
    background: '#2a1a1a', border: '1px solid #ff618844', borderRadius: 8,
    color: '#ff6188', fontSize: 13, padding: '10px 14px', marginBottom: 16,
  },
  cancelBtn: {
    width: '100%',
    padding: '9px 0',
    marginBottom: 10,
    background: 'transparent',
    border: '1px solid #ff618855',
    borderRadius: 8,
    color: '#ff9ab0',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
  },
  debugBtn: {
    width: '100%',
    padding: '9px 0',
    marginBottom: 10,
    background: '#1a1a30',
    border: '1px solid #2a2a4a',
    borderRadius: 8,
    color: '#78dce8',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
  },
  debugPanel: {
    background: '#101022',
    border: '1px solid #2a2a4a',
    borderRadius: 8,
    padding: '10px 12px',
    marginBottom: 12,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  debugTitle: { fontSize: 11, color: '#78dce8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.8 },
  debugMeta: { fontSize: 11, color: '#999' },
  debugText: {
    margin: 0,
    maxHeight: 220,
    overflowY: 'auto',
    whiteSpace: 'pre-wrap',
    fontSize: 11,
    lineHeight: 1.4,
    color: '#cfcfe6',
    background: '#0a0a16',
    border: '1px solid #222238',
    borderRadius: 6,
    padding: '8px 9px',
  },
  stepBody: { display: 'flex', flexDirection: 'column', gap: 14 },
  stepTitle: { fontSize: 15, fontWeight: 700, color: '#78dce8' },
  hint: { color: '#888', fontSize: 13, lineHeight: 1.5 },
  field: { display: 'flex', flexDirection: 'column', gap: 4 },
  label: { fontSize: 12, color: '#888' },
  input: {
    padding: '9px 12px', background: '#252540', border: '1px solid #2a2a4a',
    borderRadius: 8, color: '#e0e0e0', fontSize: 13,
  },
  inputError: {
    border: '1px solid #ff6188',
    boxShadow: '0 0 0 1px #ff618833 inset',
  },
  inlineError: {
    color: '#ff6188',
    fontSize: 11,
    marginTop: -8,
  },
  primaryBtn: {
    padding: '11px 0', background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
    border: 'none', borderRadius: 8, color: '#fff', fontWeight: 700,
    fontSize: 14, cursor: 'pointer',
  },
  uploadRow: { display: 'flex', gap: 8 },
  urlRow: { display: 'flex', gap: 8 },
  uploadBtn: {
    padding: '9px 14px', background: '#252540', border: '1px solid #2a2a4a',
    borderRadius: 8, color: '#78dce8', cursor: 'pointer', fontSize: 13,
    whiteSpace: 'nowrap',
  },
  sourcesList: {
    background: '#131326', borderRadius: 8, padding: '10px 12px',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  sourcesTitle: { fontSize: 11, color: '#888', fontWeight: 600, marginBottom: 4 },
  sourceRow: { display: 'flex', alignItems: 'center', gap: 8 },
  sourceName: { flex: 1, fontSize: 12, color: '#ccc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  chunkBadge: { fontSize: 10, color: '#888', background: '#2a2a4a', padding: '2px 6px', borderRadius: 4 },
  deleteBtn: { background: 'transparent', border: 'none', color: '#ff6188', cursor: 'pointer', fontSize: 13 },
  convBox: {
    flex: 1,
    minHeight: 200,
    maxHeight: 280,
    overflowY: 'auto',
    background: '#131326',
    borderRadius: 10,
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  convBubbleBot: {
    background: '#1e2a3a',
    border: '1px solid #2a3a4a',
    borderRadius: '12px 12px 12px 4px',
    padding: '10px 14px',
    fontSize: 13,
    color: '#ccc',
    maxWidth: '85%',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
  },
  convBubbleUser: {
    background: '#2a1a4a',
    border: '1px solid #3a2a5a',
    borderRadius: '12px 12px 4px 12px',
    padding: '10px 14px',
    fontSize: 13,
    color: '#e0e0e0',
    maxWidth: '85%',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
  },
  analyzingBox: {
    background: '#131326', borderRadius: 12, padding: '32px 24px',
    display: 'flex', flexDirection: 'column', alignItems: 'center',
  },
  proposalSection: {
    background: '#131326', borderRadius: 10, padding: '12px 14px',
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  proposalLabel: { fontSize: 11, fontWeight: 600, color: '#78dce8', textTransform: 'uppercase', letterSpacing: 1 },
  proposalText: { fontSize: 13, color: '#ccc', lineHeight: 1.5 },
  agentCard: {
    background: '#1a1a30',
    border: '1px solid #2a2a4a',
    borderRadius: 8,
    padding: '8px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  agentRow: { display: 'flex', alignItems: 'center', gap: 8 },
  agentDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0 },
  agentNameInput: {
    padding: '5px 9px', background: '#1e1e35', border: '1px solid #2a2a4a',
    borderRadius: 6, color: '#e0e0e0', fontSize: 13, flex: 1,
  },
  agentRole: {
    fontSize: 10,
    color: '#78dce8',
    background: '#131326',
    border: '1px solid #2a2a4a',
    borderRadius: 999,
    padding: '2px 8px',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  agentPersona: { fontSize: 12, color: '#aaa', lineHeight: 1.45, whiteSpace: 'normal', wordBreak: 'break-word' },
  campRow: { display: 'flex', alignItems: 'center', gap: 8 },
  campLabel: { fontSize: 11, color: '#888', minWidth: 110 },
  campInput: {
    flex: 1, padding: '5px 9px', background: '#1e1e35', border: '1px solid #2a2a4a',
    borderRadius: 6, color: '#e0e0e0', fontSize: 12,
  },
};


// ── Main Dashboard ─────────────────────────────────────────────────────────────

interface LearningData {
  ideal_count: number;
  rejected_count: number;
  patterns: Array<{ description: string; confidence: string; evidence_count: number }>;
}

export function StaffDashboard() {
  const { userEmail, clearAuth } = useOfficeStore();
  const [clients, setClients] = useState<ClientData[]>([]);
  const [selectedClient, setSelectedClient] = useState<ClientData | null>(null);
  const [clientDetail, setClientDetail] = useState<ClientDetail | null>(null);
  const [clientLeads, setClientLeads] = useState<Lead[]>([]);
  const [clientLearning, setClientLearning] = useState<LearningData | null>(null);
  const [loadingClients, setLoadingClients] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [checkingMaps, setCheckingMaps] = useState(false);

  const auth = () => ({ Authorization: `Bearer ${useOfficeStore.getState().authToken}` });

  const loadClients = useCallback(async () => {
    setLoadingClients(true);
    try {
      const res = await fetch(`${API_URL}/api/staff/clients`, { headers: auth() });
      if (res.ok) setClients(await res.json());
    } finally {
      setLoadingClients(false);
    }
  }, []);

  useEffect(() => { loadClients(); }, [loadClients]);

  const sendLeadEmail = async (leadId: string) => {
    try {
      const res = await fetch(`${API_URL}/api/leads/${leadId}/send-email`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject_index: 0 }),
      });
      if (!res.ok) {
        const d = await res.json();
        alert(d.detail || 'No se pudo enviar el correo');
        return;
      }
      // Mark as sent locally
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
        fetch(`${API_URL}/api/staff/clients/${client.id}`, { headers: auth() }),
        fetch(`${API_URL}/api/staff/clients/${client.id}/leads`, { headers: auth() }),
        fetch(`${API_URL}/api/staff/clients/${client.id}/learning`, { headers: auth() }),
      ]);
      if (detailRes.ok) setClientDetail(await detailRes.json());
      if (leadsRes.ok) setClientLeads(await leadsRes.json());
      if (learningRes.ok) setClientLearning(await learningRes.json());
    } finally {
      setLoadingDetail(false);
    }
  };

  const checkMapsDiagnostics = async () => {
    setCheckingMaps(true);
    try {
      const res = await fetch(`${API_URL}/api/diagnostics/maps`, { headers: auth() });
      const data = await res.json();
      if (!res.ok) {
        alert(data?.detail || 'No se pudo consultar el diagnóstico de Maps');
        return;
      }
      const providers = Array.isArray(data.discovery_providers)
        ? data.discovery_providers.join(' → ')
        : 'N/D';
      const fallback = Array.isArray(data.fallback_if_maps_fails)
        ? data.fallback_if_maps_fails.join(' → ')
        : 'N/D';
      alert(
        `Google Maps configurado: ${data.google_maps_configured ? 'Sí' : 'No'}\n`
        + `Key preview: ${data.google_maps_key_preview || 'No disponible'}\n`
        + `Providers: ${providers}\n`
        + `Fallback: ${fallback}`
      );
    } catch {
      alert('Error de conexión al consultar diagnóstico de Maps');
    } finally {
      setCheckingMaps(false);
    }
  };

  return (
    <div style={s.page}>
      {showOnboarding && (
        <OnboardingWizard
          onClose={() => setShowOnboarding(false)}
          onSuccess={() => loadClients()}
        />
      )}

      {/* Header */}
      <header style={s.header}>
        <div style={s.logoRow}>
          <span style={{ fontSize: 28 }}>🐝</span>
          <div>
            <div style={s.logoText}>Isomorph Staff</div>
            <div style={s.logoSub}>Panel de control</div>
          </div>
        </div>
        <div style={s.headerRight}>
          <button style={s.onboardBtn} onClick={() => setShowOnboarding(true)}>
            + Nuevo cliente
          </button>
          <button style={s.diagBtn} onClick={checkMapsDiagnostics} disabled={checkingMaps}>
            {checkingMaps ? 'Revisando Maps...' : 'Diagnóstico Maps'}
          </button>
          <span style={s.emailBadge}>🛡️ {userEmail}</span>
          <button style={s.logoutBtn} onClick={clearAuth}>Salir</button>
        </div>
      </header>

      <div style={s.body}>
        {/* Client list */}
        <div style={s.sidebar}>
          <div style={s.sidebarTitle}>Clientes ({clients.length})</div>
          {loadingClients ? (
            <div style={s.loading}>Cargando...</div>
          ) : clients.length === 0 ? (
            <div style={{ color: '#555', fontSize: 12, padding: '12px 4px' }}>
              Sin clientes activos. Onboarda el primero →
            </div>
          ) : (
            clients.map(client => (
              <div
                key={client.id}
                style={{ ...s.clientCard, ...(selectedClient?.id === client.id ? s.clientCardActive : {}) }}
                onClick={() => selectClient(client)}
              >
                <div style={s.clientEmail}>{client.email}</div>
                <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>
                  {new Date(client.created_at).toLocaleDateString('es-CO')}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Client detail */}
        <div style={s.detail}>
          {!selectedClient ? (
            <div style={s.emptyState}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>👈</div>
              <div style={{ color: '#888', fontSize: 15 }}>Selecciona un cliente</div>
            </div>
          ) : (
            <>
              <div style={s.detailHeader}>
                <div style={s.detailEmail}>{selectedClient.email}</div>
                {clientDetail && (
                  <div style={s.detailSubRow}>
                    <span style={s.statPill}>{clientDetail.total_runs} runs</span>
                    <span style={s.statPill}>{clientDetail.total_leads} leads totales</span>
                    <span style={{ ...s.statPill, background: '#1a3a1a', color: '#a9dc76' }}>
                      {clientDetail.approved_leads} aprobados
                    </span>
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

                  return (
                <div style={s.agentGrid}>
                  {runtimeAgents.map((agent, i) => (
                    <div key={agent.id} style={s.agentCard}>
                      <div style={{ ...s.agentDot, background: PALETTE_COLORS[i % PALETTE_COLORS.length] }} />
                      <div>
                        <div style={s.agentName}>{agent.name}</div>
                        <div style={s.agentRole}>{agent.role}</div>
                      </div>
                    </div>
                  ))}
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
                  <div style={{ color: '#888', fontSize: 13 }}>Sin snapshot onboarding en raíz de usuario</div>
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
                  <div style={{ color: '#888', fontSize: 13 }}>Sin campaña configurada</div>
                )}
              </Section>

              {/* Leads */}
              <Section title={`Leads (${clientLeads.length})`}>
                {clientLeads.length === 0 ? (
                  <div style={{ color: '#888', fontSize: 13 }}>Sin leads aún</div>
                ) : (
                  <div style={s.leadsList}>
                    {clientLeads.map(lead => {
                      const approved = lead.system_state === 'SUCCESS_READY_FOR_REVIEW';
                      const score = lead.expediente_json?.score as number | null;
                      const decisor = lead.expediente_json?.decisor as Record<string, string> | null;
                      return (
                        <div key={lead._id} style={s.leadRow}>
                          <div style={{ ...s.leadDot, background: approved ? '#a9dc76' : '#ff6188' }} />
                          <div style={s.leadInfo}>
                            <div style={s.leadName}>{lead.company_name || lead.url}</div>
                            <div style={s.leadUrl}>{lead.url.replace(/^https?:\/\//, '').slice(0, 45)}</div>
                            {decisor?.email && (
                              <div style={s.leadDecissor}>✉️ {decisor.email}</div>
                            )}
                          </div>
                          <div style={s.leadMeta}>
                            {score != null && <span style={s.scoreBadge}>{score}pts</span>}
                            <span style={{ ...s.hitlBadge, color: lead.hitl_status === 'approved' ? '#a9dc76' : lead.hitl_status === 'rejected' ? '#ff6188' : '#888' }}>
                              {lead.hitl_status === 'approved' ? '✓ aprobado' : lead.hitl_status === 'rejected' ? '✗ rechazado' : '⏳ pendiente'}
                            </span>
                            {decisor?.email && !!((lead.expediente_json?.borradores as Record<string,unknown> | null)?.email_cuerpo) && (
                              <button
                                style={{ ...s.sendEmailBtn, ...(lead.email_sent ? s.sendEmailBtnSent : {}) }}
                                onClick={() => !lead.email_sent && sendLeadEmail(lead._id)}
                                title={lead.email_sent ? 'Correo enviado' : `Enviar a ${decisor.email}`}
                              >
                                {lead.email_sent ? '✅ enviado' : '📧 enviar'}
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
                <Section title="Tu cliente ideal 🧬">
                  <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <span style={s.statPill}>{clientLearning.ideal_count} aprobados analizados</span>
                    <span style={{ ...s.statPill, color: '#ff6188' }}>{clientLearning.rejected_count} rechazados</span>
                  </div>
                  {clientLearning.patterns.length === 0 ? (
                    <div style={{ color: '#555', fontSize: 12 }}>
                      Se necesitan al menos 3 leads aprobados para detectar patrones.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {clientLearning.patterns.map((p, i) => (
                        <div key={i} style={s.patternCard}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 16 }}>{['🥇','🥈','🥉'][i]}</span>
                            <span style={s.patternText}>{p.description}</span>
                          </div>
                          <div style={{ display: 'flex', gap: 6, marginTop: 4, paddingLeft: 24 }}>
                            <span style={{ ...s.statPill, fontSize: 10 }}>
                              {p.confidence === 'alta' ? '🔥 Alta confianza' : '📊 Confianza media'}
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
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={sectionStyles.wrap}>
      <div style={sectionStyles.title}>{title}</div>
      <div style={sectionStyles.body}>{children}</div>
    </div>
  );
}

const sectionStyles: Record<string, React.CSSProperties> = {
  wrap: { marginBottom: 24 },
  title: { fontSize: 12, fontWeight: 600, color: '#78dce8', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12 },
  body: {},
};

const s: Record<string, React.CSSProperties> = {
  page: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'linear-gradient(180deg, #1a1a2e 0%, #16162a 100%)',
    color: '#e0e0e0',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '14px 24px',
    borderBottom: '1px solid #2a2a4a',
    flexShrink: 0,
  },
  logoRow: { display: 'flex', alignItems: 'center', gap: 12 },
  logoText: {
    fontSize: 18,
    fontWeight: 700,
    background: 'linear-gradient(90deg, #78dce8, #a9dc76)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  logoSub: { fontSize: 11, color: '#888' },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  onboardBtn: {
    padding: '7px 14px', borderRadius: 7, border: '1px solid #7c3aed',
    background: 'transparent', color: '#ab9df2', cursor: 'pointer', fontSize: 13, fontWeight: 600,
  },
  diagBtn: {
    padding: '7px 12px', borderRadius: 7, border: '1px solid #2a4a6a',
    background: 'transparent', color: '#78dce8', cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  emailBadge: { fontSize: 13, color: '#ffd866', background: '#2a2a1a', padding: '4px 10px', borderRadius: 20 },
  logoutBtn: {
    padding: '6px 14px', borderRadius: 6, border: '1px solid #2a2a4a',
    background: 'transparent', color: '#888', cursor: 'pointer', fontSize: 13,
  },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  sidebar: {
    width: 260,
    flexShrink: 0,
    borderRight: '1px solid #2a2a4a',
    overflowY: 'auto',
    padding: '16px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  sidebarTitle: { fontSize: 11, fontWeight: 600, color: '#78dce8', textTransform: 'uppercase', letterSpacing: 1, padding: '0 4px 8px' },
  clientCard: {
    padding: '12px 14px',
    borderRadius: 10,
    border: '1px solid #2a2a4a',
    background: '#1e1e32',
    cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  clientCardActive: { borderColor: '#78dce8', background: '#1e2a3a' },
  clientEmail: { fontSize: 13, fontWeight: 600, color: '#e0e0e0', marginBottom: 6 },
  clientStats: { display: 'flex', gap: 8, flexWrap: 'wrap' },
  stat: { fontSize: 11, color: '#888', background: '#16162a', padding: '2px 7px', borderRadius: 10 },
  clientLastRun: { fontSize: 11, color: '#666', marginTop: 6 },
  detail: { flex: 1, overflowY: 'auto', padding: '24px 28px' },
  emptyState: { height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' },
  detailHeader: { marginBottom: 28 },
  detailEmail: { fontSize: 22, fontWeight: 700, color: '#e0e0e0', marginBottom: 10 },
  detailSubRow: { display: 'flex', gap: 8 },
  statPill: { fontSize: 12, padding: '4px 10px', borderRadius: 12, background: '#2a2a4a', color: '#aaa' },
  agentGrid: { display: 'flex', gap: 10, flexWrap: 'wrap' },
  agentCard: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '10px 14px', borderRadius: 10, border: '1px solid #2a2a4a',
    background: '#1e1e32', minWidth: 150,
  },
  agentDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0 },
  agentName: { fontSize: 13, fontWeight: 600, color: '#e0e0e0' },
  agentRole: { fontSize: 11, color: '#888' },
  runtimeLimitNote: { fontSize: 11, color: '#ffd866', marginTop: 8 },
  rootPromptBox: {
    fontSize: 12,
    color: '#cfcfcf',
    background: '#1e1e32',
    border: '1px solid #2a2a4a',
    borderRadius: 8,
    padding: '10px 12px',
    whiteSpace: 'pre-wrap',
    lineHeight: 1.45,
    marginBottom: 10,
  },
  rootAgentsList: { display: 'flex', flexDirection: 'column', gap: 8 },
  rootAgentRow: {
    padding: '8px 10px',
    borderRadius: 8,
    border: '1px solid #2a2a4a',
    background: '#1e1e32',
  },
  rootAgentName: { fontSize: 12, fontWeight: 600, color: '#e0e0e0' },
  rootAgentMeta: { fontSize: 11, color: '#888', marginTop: 2 },
  campaignGrid: { display: 'flex', flexDirection: 'column', gap: 8 },
  campaignRow: { display: 'flex', gap: 12, alignItems: 'flex-start' },
  campaignLabel: { fontSize: 11, color: '#78dce8', minWidth: 130, flexShrink: 0, paddingTop: 1 },
  campaignValue: { fontSize: 13, color: '#ccc', flex: 1 },
  leadsList: { display: 'flex', flexDirection: 'column', gap: 8 },
  leadRow: {
    display: 'flex', alignItems: 'flex-start', gap: 10,
    padding: '10px 14px', borderRadius: 10, border: '1px solid #2a2a4a',
    background: '#1e1e32',
  },
  leadDot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0, marginTop: 5 },
  leadInfo: { flex: 1, minWidth: 0 },
  leadName: { fontSize: 13, fontWeight: 600, color: '#e0e0e0', marginBottom: 2 },
  leadUrl: { fontSize: 11, color: '#888' },
  leadDecissor: { fontSize: 11, color: '#78dce8', marginTop: 3 },
  leadMeta: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 },
  scoreBadge: { fontSize: 11, padding: '2px 8px', borderRadius: 10, background: '#2a3a2a', color: '#a9dc76' },
  hitlBadge: { fontSize: 11 },
  sendEmailBtn: {
    fontSize: 11, padding: '3px 8px', borderRadius: 8,
    background: '#1a2a3a', border: '1px solid #2a4a6a',
    color: '#78dce8', cursor: 'pointer',
  },
  sendEmailBtnSent: {
    background: '#1a3a1a', border: '1px solid #2a5a2a',
    color: '#a9dc76', cursor: 'default',
  },
  loading: { color: '#888', fontSize: 13 },
  patternCard: {
    background: '#1e1e32', border: '1px solid #2a2a4a', borderRadius: 8,
    padding: '10px 12px',
  },
  patternText: { fontSize: 13, color: '#e0e0e0', flex: 1, lineHeight: 1.4 },
};
