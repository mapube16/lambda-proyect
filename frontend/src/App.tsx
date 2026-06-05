import React, { useState, useEffect } from 'react';
import './landa.css';
import * as api from './api';

// ============ ICON COMPONENT ============
function Icon({ name, size = 18, stroke = 1.5 }: any) {
  const icons: any = {
    home: 'M3 12a9 9 0 1 1 18 0a9 9 0 0 1-18 0M2.25 12c0 5.385 4.365 9.75 9.75 9.75S21.75 17.385 21.75 12 17.385 2.25 12 2.25 2.25 6.615 2.25 12Zm9-3.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z',
    rocket: 'M15.59 14.37a6 6 0 0 1-5.84 7.38A6.52 6.52 0 0 1 2.54 15.6a6.5 6.5 0 1 1 13.05-1.23zM11.5 12.5v5.5m-4-3h7',
    list: 'M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5',
    check: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
    chat: 'M12 20.887L8.265 23.5a.75.75 0 01-1.19-.75l1.08-6.3H3.75a.75.75 0 01-.728-.994l1.5-6A.75.75 0 015.25 9h5.568l.844-4.923A.75.75 0 0112 3.75c.369 0 .713.201.894.518l1.44 2.232h5.895a.75.75 0 01.728.994l-1.5 6a.75.75 0 01-.728.506H17.25l-.844 4.923a.75.75 0 01-.744.626.75.75 0 01-.75-.75v-5.249H12z',
    spark: 'M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 3.75l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z',
    bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75c0-.78-.125-1.533-.357-2.25M15.75 9.75H7.5a6 6 0 0 0 0 12h8.25m.75-12V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v2.25m13.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
    search: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 1 0 5.5 5.5a7.5 7.5 0 0 0 10.5 10.5z',
    gear: 'M9 12a3 3 0 1 1 6 0 3 3 0 0 1-6 0z',
    x: 'M6 18L18 6M6 6l12 12',
    send: 'M6 12L3.269 3.125A59.769 59.769 0 0 1 21.485 11.8a59.768 59.768 0 0 1-18.215 8.675',
    arrow: 'M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3',
    dots: 'M12 8.25a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5zM12.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0zM12 15.75a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5z',
    plus: 'M12 4.5v15m7.5-7.5h-15',
    play: 'M8.25 4.5L19.5 12m0 0l-11.25 7.5M19.5 12v.75c0 .414-.337.75-.75.75H4.5',
    pause: 'M6 4.5h4.5m7.5 0H18M6 20.25h4.5m7.5 0H18',
    pen: 'M16.862 4.487l1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685',
    eye: 'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7C7.523 19 3.732 16.057 2.458 12z',
    copy: 'M16 16.5V9.75a4.5 4.5 0 0 0-4.5-4.5h-1.5a4.5 4.5 0 0 0-4.5 4.5v6.75m12 0a4.5 4.5 0 0 1-4.5 4.5h-1.5a4.5 4.5 0 0 1-4.5-4.5m12 0V9.362',
    clock: 'M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
    filter: 'M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5',
    globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0 0c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3M3.6 9h16.8M3.6 15h16.8',
    building: 'M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21',
    home2: 'M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25',
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
      <path d={icons[name] || ''} />
    </svg>
  );
}

// ============ SPARK CHART ============
function Spark({ data, color, w = 76, h = 28 }: any) {
  if (!data || data.length === 0) return <svg width={w} height={h} />;
  if (data.length === 1) data = [data[0], data[0]];
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pts = data.map((d: any, i: any) => [(i / (data.length - 1)) * w, h - 3 - ((d - min) / (max - min || 1)) * (h - 6)]);
  const line = pts.map((p: any, i: any) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const id = 'g' + Math.round(Math.abs(min * 7 + max + w));
  const lastPt = pts[pts.length - 1];
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.18" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={line + ` L${w} ${h} L0 ${h} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastPt[0]} cy={lastPt[1]} r="2.6" fill={color} />
    </svg>
  );
}

// ============ ROLES ============
const ROLES = {
  buscador: { name: 'Buscador', job: 'Descubre empresas', color: 'var(--r-buscador)', soft: 'var(--r-buscador-soft)', icon: 'search', verb: 'Buscando' },
  scraper: { name: 'Scraper', job: 'Extrae datos', color: 'var(--r-scraper)', soft: 'var(--r-scraper-soft)', icon: 'arrow', verb: 'Leyendo' },
  analista: { name: 'Analista', job: 'Califica leads', color: 'var(--r-analista)', soft: 'var(--r-analista-soft)', icon: 'check', verb: 'Analizando' },
  redactor: { name: 'Redactor', job: 'Escribe correos', color: 'var(--r-redactor)', soft: 'var(--r-redactor-soft)', icon: 'pen', verb: 'Escribiendo' },
};

function AgentAvatar({ role, size = 40, live = false }: any) {
  const r = (ROLES as any)[role];
  return (
    <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <div style={{ width: size, height: size, borderRadius: size * 0.32, background: r.soft, color: r.color, display: 'grid', placeItems: 'center', border: `1px solid ${r.color}22` }}>
        <Icon name={r.icon} size={size * 0.5} stroke={1.9} />
      </div>
      {live && <span style={{ position: 'absolute', right: -2, bottom: -2, width: 11, height: 11, borderRadius: '50%', background: 'var(--green)', border: '2px solid #fff', display: 'block' }} />}
    </div>
  );
}

// ============ DEFAULT EMPTY KPIS FOR LAYOUT ============
const EMPTY_KPIS = [
  { label: 'Leads calificados', value: 0, trend: '—', spark: [0], color: 'var(--primary)' },
  { label: 'Aprobados por ti', value: 0, trend: '—', spark: [0], color: 'var(--green)' },
  { label: 'Tasa de aprobación', value: '0%', trend: '—', spark: [0], color: 'var(--r-buscador)' },
  { label: 'Empresas analizadas', value: 0, trend: '—', spark: [0], color: 'var(--r-scraper)' },
];

// ============ VIEWS ============

function ViewInicio({ campaignId }: any) {
  const [running, setRunning] = useState(true);
  const [kpis, setKpis] = useState(EMPTY_KPIS);
  const AGENT_TASKS = {
    buscador: ['Buscando en Bogotá...', 'Rastreando SECOP II...', 'Explorando Medellín...', 'Consultando directorios...'],
    scraper: ['Leyendo web de empresa...', 'Extrayendo contactos...', 'Analizando descripción...', 'Verificando flota...'],
    analista: ['Evaluando activos físicos...', 'Calculando score...', 'Verificando decisor...', 'Aplicando scoring B2B...'],
    redactor: ['Personalizando apertura...', 'Ajustando tono...', 'Finalizando ≤80 palabras...', 'Redactando correo...'],
  };
  const [agentStates, setAgentStates] = useState([
    { role: 'buscador', task: 'Buscando en Bogotá...', count: 38 },
    { role: 'scraper', task: 'Leyendo web de empresa...', count: 24 },
    { role: 'analista', task: 'Evaluando activos físicos...', count: 12 },
    { role: 'redactor', task: 'Personalizando apertura...', count: 8 },
  ]);

  useEffect(() => {
    (async () => {
      try {
        if (!api.getToken() || !campaignId) return;
        const data = await api.getKPIs(campaignId);
        if (data.kpis) setKpis(data.kpis);
      } catch (err) {
        console.log('Failed to load KPIs:', err);
      }
    })();
  }, [campaignId]);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setAgentStates(prev => prev.map((a: any) => {
        const tasks = (AGENT_TASKS as any)[a.role];
        return { ...a, task: tasks[Math.floor(Math.random() * tasks.length)] };
      }));
    }, 2400);
    return () => clearInterval(id);
  }, [running]);

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Buenos días, DPG Seguros</h1>
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Tu equipo encontró <strong style={{ color: 'var(--ink)' }}>8 leads nuevos</strong> para revisar hoy.</p>
        </div>
        <button className={'btn ' + (running ? 'btn-soft' : 'btn-primary')} onClick={() => setRunning(r => !r)} style={{ fontFamily: 'inherit' }}>
          <Icon name={running ? 'pause' : 'play'} size={15} />
          {running ? 'Pausar campaña' : 'Reanudar campaña'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16 }}>
        {kpis.map((k) => (
          <div key={k.label} className="card" style={{ padding: 18 }}>
            <span className="label">{k.label}</span>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontSize: 30, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.03em' }}>{k.value}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--green)' }}>{k.trend}</span>
              </div>
              <Spark data={k.spark} color={k.color} />
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ padding: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div>
            <h3 style={{ fontSize: 17, margin: 0, marginBottom: 3 }}>Pipeline en vivo</h3>
            <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: 0 }}>Buscador → Scraper → Analista → Redactor</p>
          </div>
          {running ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <div style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--green)' }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--green)' }}>Operando</span>
            </div>
          ) : (
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-faint)' }}>Pausado</span>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 22px 1fr 22px 1fr 22px 1fr', alignItems: 'stretch', gap: 0 }}>
          {agentStates.map((a: any, i: any) => {
            const r = (ROLES as any)[a.role];
            const progPct = [72, 58, 44, 30][i];
            return (
              <React.Fragment key={a.role}>
                <div style={{ borderRadius: 14, border: '1.5px solid ' + (running ? r.color + '44' : 'var(--border)'), background: running ? r.soft : 'var(--surface-2)', padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <AgentAvatar role={a.role} size={36} live={running} />
                    <span style={{ fontSize: 22, fontWeight: 800, color: running ? r.color : 'var(--text-faint)' }}>{a.count}</span>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', marginBottom: 3 }}>{r.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4, minHeight: 30 }}>{running ? a.task : r.job}</div>
                  </div>
                  <div style={{ height: 5, borderRadius: 999, background: 'var(--surface-3)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 999, background: running ? r.color : 'var(--border-2)', width: (running ? progPct : 0) + '%' }} />
                  </div>
                </div>
                {i < 3 && (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon name="arrow" size={15} style={{ color: 'var(--text-faint)' }} />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 1fr', gap: 16 }}>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h3 style={{ fontSize: 16, margin: 0 }}>Listos para revisar</h3>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', background: 'var(--primary)', borderRadius: 999, padding: '3px 9px' }}>8 nuevos</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {campaignId ? (
              <>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', textAlign: 'center' }}>Cargando leads de la campaña...</p>
                <button className="btn btn-soft" style={{ justifyContent: 'center', marginTop: 4, fontSize: 13, fontFamily: 'inherit' }}>Ver todos los leads →</button>
              </>
            ) : (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', textAlign: 'center' }}>Selecciona una campaña para ver leads</p>
            )}
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <h3 style={{ fontSize: 16, margin: 0, marginBottom: 14 }}>Actividad reciente</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { id: 1, text: 'Constructora Vértice — Score 91 · Aprobada', time: 'hace 1 min', color: 'var(--green)' },
              { id: 2, text: 'Ferretería Los Alpes — Score 52 · Descartada', time: 'hace 3 min', color: 'var(--red)' },
              { id: 3, text: 'Correo listo para Transportes Andina', time: 'hace 5 min', color: 'var(--primary)' },
              { id: 4, text: 'Manufacturas Lumen — Score 82 · Aprobada', time: 'hace 7 min', color: 'var(--green)' },
            ].map((f) => (
              <div key={f.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{ width: 9, height: 9, borderRadius: '50%', background: f.color, flex: 'none', marginTop: 5 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.4 }}>{f.text}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 2 }}>{f.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const SECTOR_OPTIONS = ['Seguros', 'Logística', 'Construcción', 'Alimentos', 'Industria', 'Agro', 'Salud', 'Distribución'];
const CITY_OPTIONS = ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena', 'Bucaramanga', 'Cúcuta'];

// Pre-configured prospecting pipelines. Each maps to backend signal-source flags
// (use_rues / use_secop / use_fincaraiz) that hive_tools reads from the campaign doc.
const PIPELINE_TEMPLATES = [
  { id: 'scraping',  icon: 'globe',    title: 'Scraping de empresas',     desc: 'Búsqueda web abierta de empresas en cualquier sector y ciudad.',         flags: { source_priority: 'serper' }, tag: 'Web' },
  { id: 'arriendos', icon: 'home2',    title: 'Búsqueda de arriendos',    desc: 'Propietarios con inmuebles en arriendo activo (Fincaraíz).',             flags: { use_fincaraiz: true },       tag: 'Fincaraíz' },
  { id: 'secop',     icon: 'list',     title: 'Pólizas de cumplimiento',  desc: 'Contratistas del Estado con contratos adjudicados (SECOP).',             flags: { use_secop: true },           tag: 'SECOP' },
  { id: 'rues',      icon: 'building', title: 'Empresas recién creadas',  desc: 'Compañías registradas recientemente en Cámara de Comercio (RUES).',      flags: { use_rues: true },            tag: 'RUES' },
];

const WIZARD_STEPS = [
  { title: '¿Qué tipo de campaña quieres lanzar?', subtitle: 'Elige el pipeline de prospección. Define de dónde vienen tus leads.' },
  { title: '¿Cuál es el nombre de tu campaña?', subtitle: 'Dale un nombre descriptivo para identificarla fácilmente.' },
  { title: '¿Qué sector vas a prospeccionar?', subtitle: 'Elige el sector objetivo.' },
  { title: '¿En qué ciudades?', subtitle: 'Selecciona las ciudades donde buscarás leads.' },
  { title: '¿Cuál es tu cliente ideal?', subtitle: 'Describe el perfil: tamaño de empresa, rol del decisor, etc.' },
  { title: '¿Cuántos leads esperas?', subtitle: 'Estimado para calibrar la operación.' },
  { title: 'Resumen y lanzamiento', subtitle: 'Revisa todo y lanza tu campaña.' },
];

function ViewCampanas({ onSelectCampaign, showWizard, setShowWizard }: any) {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Wizard state (showWizard is owned by App so the Topbar can trigger it)
  const [step, setStep] = useState(0);
  const [launching, setLaunching] = useState(false);
  const [form, setForm] = useState({ pipeline: '', name: '', sector: '', cities: [] as string[], targetProfile: '', estimatedLeads: '' });

  const openWizard = () => setShowWizard(true);

  // Reset the form whenever the wizard opens
  useEffect(() => {
    if (showWizard) {
      setStep(0);
      setForm({ pipeline: '', name: '', sector: '', cities: [], targetProfile: '', estimatedLeads: '' });
    }
  }, [showWizard]);

  useEffect(() => {
    (async () => {
      try {
        setError(null);
        setLoading(true);
        if (!api.getToken()) {
          setError('No autenticado. Por favor, recarga la página.');
          setLoading(false);
          return;
        }
        const data = await api.getCampaigns();
        const formatted = (data.campaigns || []).map((c: any) => ({
          id: c.id,
          name: c.name,
          status: c.is_active ? 'active' : 'draft',
          leads: 0,
          approved: 0,
          cities: (c.cities || []).join(', ') || '—',
          progress: 0,
        }));
        setCampaigns(formatted);
      } catch (err: any) {
        console.error('Failed to load campaigns:', err);
        setError('Error: ' + (err.message || 'No se pudieron cargar las campañas'));
      } finally {
        setLoading(false);
      }
    })();
  }, [reloadKey]);

  const canAdvance = () => {
    if (step === 0) return form.pipeline.length > 0;
    if (step === 1) return form.name.trim().length > 0;
    if (step === 2) return form.sector.length > 0;
    if (step === 3) return form.cities.length > 0;
    return true;
  };

  const handleNext = async () => {
    if (step < WIZARD_STEPS.length - 1) {
      setStep(step + 1);
      return;
    }
    // Final step → create + launch on the backend
    setLaunching(true);
    try {
      const tmpl = PIPELINE_TEMPLATES.find(t => t.id === form.pipeline);
      const flags = (tmpl?.flags || {}) as any;
      const created = await api.createCampaign({
        name: form.name,
        sectors: form.sector ? [form.sector] : [],
        cities: form.cities,
        icp_description: form.targetProfile,
        // Signal-source flags — consumed by hive_tools.discover_companies
        use_rues: !!flags.use_rues,
        use_secop: !!flags.use_secop,
        use_fincaraiz: !!flags.use_fincaraiz,
        source_priority: flags.source_priority || 'serper',
        pipeline: form.pipeline,
      });
      const newId = created.campaign_id || created.id;
      try {
        await api.launchCampaign(newId);
      } catch (e: any) {
        console.warn('launch failed:', e.message);
      }
      setShowWizard(false);
      setReloadKey(k => k + 1);
      if (newId) onSelectCampaign && onSelectCampaign(newId);
    } catch (err: any) {
      alert('Error al crear la campaña: ' + err.message);
    } finally {
      setLaunching(false);
    }
  };

  const inputStyle: React.CSSProperties = { width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' };

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Campañas</h1>
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{campaigns.length} campañas · {campaigns.filter(c => c.status === 'active').length} activa(s)</p>
        </div>
        <button className="btn btn-primary" onClick={openWizard} style={{ fontFamily: 'inherit' }}><Icon name="plus" size={16} /> Nueva campaña</button>
      </div>

      {error && <div style={{ padding: 20, background: 'var(--red-soft)', color: 'var(--red)', borderRadius: 10, textAlign: 'center' }}>{error}</div>}
      {loading && <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Cargando campañas...</div>}

      {!error && !loading && campaigns.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No hay campañas todavía. Haz click en "Nueva campaña" para crear una.</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, flex: 1 }}>
        {campaigns.map((c) => (
          <div key={c.id} className="card" style={{ padding: 20, display: 'flex', flexDirection: 'column', cursor: 'pointer' }} onClick={() => onSelectCampaign && onSelectCampaign(c.id)}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: 16, margin: 0, marginBottom: 4, fontWeight: 800, color: 'var(--ink)' }}>{c.name}</h3>
                <span className="chip" style={{ background: c.status === 'active' ? 'var(--green-soft)' : c.status === 'paused' ? 'var(--amber-soft)' : 'var(--surface-3)', color: c.status === 'active' ? 'var(--green)' : c.status === 'paused' ? 'var(--amber)' : 'var(--text-faint)', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  {c.status === 'active' && <><Icon name="check" size={13} /> Activa</>}
                  {c.status === 'paused' && <><Icon name="pause" size={13} /> Pausada</>}
                  {c.status === 'draft' && <><Icon name="pen" size={13} /> Borrador</>}
                </span>
              </div>
              <button className="btn btn-icon btn-ghost" style={{ padding: 8 }}><Icon name="dots" size={16} /></button>
            </div>

            <div style={{ marginBottom: 14, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 6 }}>Ubicaciones</div>
              <div style={{ fontSize: 13, color: 'var(--text)' }}>{c.cities}</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 4 }}>Leads</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--primary)' }}>{c.leads}</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 4 }}>Aprobados</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--green)' }}>{c.approved}</div>
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>Progreso</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)' }}>{c.progress}%</span>
              </div>
              <div style={{ height: 6, background: '#EDEDF4', borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ width: c.progress + '%', height: '100%', background: 'var(--primary)', borderRadius: 999 }} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Wizard Modal — 6-step conversational flow */}
      {showWizard && (
        <>
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(16,16,29,.5)', zIndex: 9, backdropFilter: 'blur(4px)' }} onClick={() => !launching && setShowWizard(false)} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '90%', maxWidth: 600, maxHeight: '90vh', background: 'var(--surface)', borderRadius: 'var(--r-xl)', zIndex: 10, display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,.3)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', flex: 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                  <h2 style={{ fontSize: 18, margin: 0, fontWeight: 800 }}>Asistente de campaña</h2>
                  <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>Paso {step + 1} de {WIZARD_STEPS.length}</div>
                </div>
                <button className="btn btn-icon btn-ghost" onClick={() => setShowWizard(false)}><Icon name="x" size={22} /></button>
              </div>
              <div style={{ height: 4, background: '#EDEDF4', borderRadius: 999 }}>
                <div style={{ width: ((step + 1) / WIZARD_STEPS.length) * 100 + '%', height: '100%', background: 'var(--primary)', borderRadius: 999, transition: 'width .3s' }} />
              </div>
            </div>

            <div style={{ flex: 1, padding: 24, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
              <div>
                <h3 style={{ fontSize: 16, margin: 0, marginBottom: 4, fontWeight: 800, color: 'var(--ink)' }}>{WIZARD_STEPS[step].title}</h3>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>{WIZARD_STEPS[step].subtitle}</p>
              </div>

              {step === 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {PIPELINE_TEMPLATES.map((t) => {
                    const sel = form.pipeline === t.id;
                    return (
                      <button key={t.id} onClick={() => setForm({ ...form, pipeline: t.id })} className="btn btn-ghost" style={{ alignItems: 'flex-start', textAlign: 'left', flexDirection: 'column', gap: 4, background: sel ? 'var(--primary-soft)' : 'var(--surface-2)', border: sel ? '2px solid var(--primary)' : '2px solid var(--border-2)', borderRadius: 12, padding: '14px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
                          <span style={{ color: sel ? 'var(--primary)' : 'var(--text-muted)', display: 'flex' }}><Icon name={t.icon} size={22} /></span>
                          <span style={{ fontWeight: 800, fontSize: 14.5, color: 'var(--ink)' }}>{t.title}</span>
                          <span className="chip" style={{ marginLeft: 'auto', fontSize: 10.5, background: 'var(--surface-3)', color: 'var(--text-muted)' }}>{t.tag}</span>
                        </div>
                        <span style={{ fontSize: 12.5, color: 'var(--text-muted)', fontWeight: 400, lineHeight: 1.45 }}>{t.desc}</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {step === 1 && (
                <input type="text" autoFocus placeholder="ej. Seguros corporativos" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inputStyle} />
              )}

              {step === 2 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {SECTOR_OPTIONS.map((s) => (
                    <button key={s} onClick={() => setForm({ ...form, sector: s })} className="btn btn-ghost" style={{ justifyContent: 'flex-start', background: form.sector === s ? 'var(--primary-soft)' : 'var(--surface-2)', color: form.sector === s ? 'var(--primary-700)' : 'var(--text)', border: form.sector === s ? '1px solid var(--primary)' : '1px solid var(--border-2)', padding: '12px 14px' }}>{s}</button>
                  ))}
                </div>
              )}

              {step === 3 && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {CITY_OPTIONS.map((c) => (
                    <button key={c} onClick={() => setForm({ ...form, cities: form.cities.includes(c) ? form.cities.filter(x => x !== c) : [...form.cities, c] })} className="btn btn-ghost" style={{ justifyContent: 'flex-start', background: form.cities.includes(c) ? 'var(--primary-soft)' : 'var(--surface-2)', color: form.cities.includes(c) ? 'var(--primary-700)' : 'var(--text)', border: form.cities.includes(c) ? '1px solid var(--primary)' : '1px solid var(--border-2)', padding: '10px 12px', fontSize: 13 }}>{c}</button>
                  ))}
                </div>
              )}

              {step === 4 && (
                <textarea autoFocus placeholder="ej. Empresas de 100-300 empleados, industria, con operación propia..." value={form.targetProfile} onChange={(e) => setForm({ ...form, targetProfile: e.target.value })} style={{ ...inputStyle, resize: 'vertical', minHeight: 100 }} />
              )}

              {step === 5 && (
                <input type="number" autoFocus placeholder="ej. 50" value={form.estimatedLeads} onChange={(e) => setForm({ ...form, estimatedLeads: e.target.value })} style={inputStyle} />
              )}

              {step === 6 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div className="card" style={{ padding: 16, background: 'var(--primary-soft)' }}>
                    <div className="label" style={{ marginBottom: 12 }}>RESUMEN DE CAMPAÑA</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Pipeline:</span> <span style={{ color: 'var(--primary)', display: 'flex' }}><Icon name={PIPELINE_TEMPLATES.find(t => t.id === form.pipeline)?.icon || 'globe'} size={15} /></span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{PIPELINE_TEMPLATES.find(t => t.id === form.pipeline)?.title}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Nombre:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{form.name}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Sector:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{form.sector}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Ciudades:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{form.cities.join(', ')}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Leads estimados:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{form.estimatedLeads || '—'}</span></div>
                    </div>
                  </div>
                  <div style={{ background: 'var(--green-soft)', border: '1px solid var(--green)', borderRadius: 10, padding: 12 }}>
                    <div style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--green)' }}>
                      <Icon name="check" size={16} />
                      <span>Tu campaña está lista. Los agentes comenzarán la prospección inmediatamente.</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={{ padding: 20, borderTop: '1px solid var(--border)', display: 'flex', gap: 10, flex: 'none' }}>
              {step > 0
                ? <button className="btn btn-ghost" disabled={launching} onClick={() => setStep(step - 1)} style={{ flex: 1, justifyContent: 'center', fontFamily: 'inherit' }}>← Atrás</button>
                : <button className="btn btn-ghost" disabled={launching} onClick={() => setShowWizard(false)} style={{ flex: 1, justifyContent: 'center', fontFamily: 'inherit' }}>Cancelar</button>}
              <button className="btn btn-primary" disabled={!canAdvance() || launching} onClick={handleNext} style={{ flex: 1, justifyContent: 'center', fontFamily: 'inherit', opacity: (!canAdvance() || launching) ? 0.6 : 1, gap: 8 }}>
                {launching ? 'Lanzando…' : step === WIZARD_STEPS.length - 1 ? <><Icon name="rocket" size={15} /> Lanzar campaña</> : <>Siguiente <Icon name="arrow" size={15} /></>}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ViewAprobados({ campaignId }: any) {
  const [leads, setLeads] = useState<any[]>([]);
  const [selectedLead, setSelectedLead] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const onChanged = () => setReloadKey(k => k + 1);

  useEffect(() => {
    (async () => {
      try {
        setError(null);
        setLoading(true);
        if (!api.getToken() || !campaignId) {
          setError('Selecciona una campaña primero');
          setLoading(false);
          return;
        }
        const data = await api.getLeads(campaignId);
        setLeads(data.leads || []);
      } catch (err: any) {
        console.error('Failed to load leads:', err);
        setError('Error: ' + (err.message || 'No se pudieron cargar los leads'));
      } finally {
        setLoading(false);
      }
    })();
  }, [campaignId, reloadKey]);

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Aprobados para enviar</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{leads.length} leads listos. {leads.filter(l => l.opens > 0).length} abiertos, {leads.filter(l => l.replies > 0).length} respondieron.</p>
      </div>

      {error && <div style={{ padding: 20, background: 'var(--red-soft)', color: 'var(--red)', borderRadius: 10, textAlign: 'center' }}>{error}</div>}
      {loading && <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Cargando leads...</div>}

      {!error && !loading && leads.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No hay leads en esta campaña.</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Enviados</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--primary)' }}>{leads.length}</div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Abiertos</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--green)' }}>{leads.filter(l => l.opens > 0).length}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--green)' }}>100%</div>
          </div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Click-Through</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--amber)' }}>{leads.filter(l => l.clicks > 0).length}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--amber)' }}>50%</div>
          </div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Respuestas</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--r-analista)' }}>{leads.filter(l => l.replies > 0).length}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--r-analista)' }}>20%</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 0.8fr 0.9fr 1fr', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
          {['Empresa', 'Decisor', 'Enviado', 'Aperturas', 'Clicks', 'Estado'].map((h, i) => <span key={i} className="label" style={{ fontSize: 10.5 }}>{h}</span>)}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {leads.map((l) => (
            <div key={l.id} style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 0.8fr 0.9fr 1fr', gap: 12, padding: '14px 20px', borderBottom: '1px solid var(--border)', alignItems: 'center', cursor: 'pointer' }} onClick={() => setSelectedLead(l)}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>{l.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>{l.sector}</div>
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>{l.decisor}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{l.cargo}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>hace 2 días</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>15:04</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 800, color: l.opens > 0 ? 'var(--primary)' : 'var(--text-faint)' }}>{l.opens}</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 800, color: l.clicks > 0 ? 'var(--amber)' : 'var(--text-faint)' }}>{l.clicks}</div>
              </div>
              <div>
                <span className="chip" style={{ background: l.status === 'opened' ? 'var(--green-soft)' : l.status === 'pending' ? 'var(--amber-soft)' : 'var(--red-soft)', color: l.status === 'opened' ? 'var(--green)' : l.status === 'pending' ? 'var(--amber)' : 'var(--red)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  {l.status === 'opened' && <><Icon name="check" size={13} /> Abierto</>}
                  {l.status === 'pending' && <><Icon name="clock" size={13} /> Pendiente</>}
                  {l.status === 'bounce' && <><Icon name="x" size={13} /> Bounce</>}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {selectedLead && (
        <>
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(16,16,29,.5)', zIndex: 9, backdropFilter: 'blur(4px)' }} onClick={() => setSelectedLead(null)} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '90%', maxWidth: 620, maxHeight: '90vh', background: 'var(--surface)', borderRadius: 'var(--r-xl)', zIndex: 10, display: 'flex', flexDirection: 'column', overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,.3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 24, borderBottom: '1px solid var(--border)', flex: 'none' }}>
              <div>
                <h2 style={{ fontSize: 20, margin: 0, fontWeight: 800 }}>{selectedLead.name}</h2>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6 }}>{selectedLead.decisor} · {selectedLead.cargo}</div>
              </div>
              <button className="btn btn-icon btn-ghost" onClick={() => setSelectedLead(null)}><Icon name="x" size={22} /></button>
            </div>
            <div style={{ flex: 1, padding: 24, overflowY: 'auto' }}>
              <p style={{ margin: 0, color: 'var(--text)' }}>Score: <strong>{selectedLead.score}</strong></p>
              <p style={{ margin: 0, marginTop: 12, color: 'var(--text-muted)' }}>Email: {selectedLead.email}</p>
              <p style={{ margin: 0, marginTop: 8, color: 'var(--text-muted)' }}>Teléfono: {selectedLead.phone}</p>
              <button className="btn btn-soft" style={{ width: '100%', marginTop: 24, justifyContent: 'center', fontFamily: 'inherit' }} onClick={async () => {
                try {
                  await api.approveLead(campaignId, selectedLead.id, 'Aprobado desde UI');
                  alert('Lead aprobado exitosamente');
                  setSelectedLead(null);
                  onChanged && onChanged();
                } catch (err: any) {
                  alert('Error al aprobar: ' + err.message);
                }
              }}>
                <Icon name="check" size={16} /> Aprobar
              </button>
              <button className="btn btn-primary" style={{ width: '100%', marginTop: 12, justifyContent: 'center', fontFamily: 'inherit' }} onClick={async () => {
                try {
                  await api.sendLead(campaignId, selectedLead.id, 'email', 'Propuesta de valor personalizada para tu empresa.', 'Oportunidad para tu empresa');
                  alert('Lead enviado exitosamente');
                  setSelectedLead(null);
                  onChanged && onChanged();
                } catch (err: any) {
                  alert('Error al enviar: ' + err.message);
                }
              }}>
                <Icon name="send" size={16} /> Enviar por email
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ViewResultados() {
  const funnel = [
    ['Descubiertas', 142, 'var(--primary)'],
    ['Analizadas', 96, 'var(--r-scraper)'],
    ['Calificadas', 24, 'var(--amber)'],
    ['Aprobadas', 16, 'var(--green)'],
    ['Enviadas', 16, 'var(--r-buscador)'],
    ['Abiertas', 11, 'var(--r-analista)'],
    ['Respondidas', 4, 'var(--r-redactor)'],
  ];

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Resultados de campaña</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Seguros corporativos · Bogotá, Medellín, Cali · últimos 30 días</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {[
          { label: 'Tasa de apertura', value: '69%', trend: '+6%', spark: [48, 52, 55, 58, 62, 65, 69], color: 'var(--green)' },
          { label: 'Tasa de respuesta', value: '25%', trend: '+3%', spark: [14, 16, 18, 19, 22, 23, 25], color: 'var(--primary)' },
          { label: 'Costo por lead', value: '$4.2', trend: '−$0.6', spark: [6.1, 5.8, 5.4, 5.0, 4.8, 4.5, 4.2], color: 'var(--r-scraper)' },
          { label: 'Reuniones agendadas', value: 7, trend: '+2', spark: [1, 2, 3, 3, 5, 6, 7], color: 'var(--r-redactor)' },
        ].map((k: any) => (
          <div key={k.label} className="card" style={{ padding: 18 }}>
            <span className="label">{k.label}</span>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontSize: 28, fontWeight: 800, color: 'var(--ink)' }}>{k.value}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--green)' }}>{k.trend}</span>
              </div>
              <Spark data={k.spark} color={k.color} />
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ padding: 22 }}>
        <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Embudo de conversión</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 18 }}>
          {funnel.map(([label, val, color]: any) => {
            const fMax = funnel[0][1] as number;
            const pct = Math.round(((val as number) / fMax) * 100);
            return (
              <div key={label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)' }}>{label}</span>
                  <span style={{ fontSize: 15, fontWeight: 800, color: 'var(--ink)' }}>{val}</span>
                </div>
                <div style={{ height: 12, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: pct + '%', height: '100%', background: color, borderRadius: 999 }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ViewChat() {
  const [messages, setMessages] = useState([
    { id: 1, role: 'assistant', text: 'Hola, soy la Reina de Landa. Cuéntame sobre tus resultados o pídeme ajustar la campaña.', time: '09:15' },
    { id: 2, role: 'user', text: '¿Cuál es el sector con mejor tasa?', time: '09:17' },
    { id: 3, role: 'assistant', text: 'Construcción lidera con 74%, seguido por Logística (68%) e Industria (64%).', time: '09:18' },
  ]);
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim()) return;
    setMessages([...messages, { id: Date.now(), role: 'user', text: input, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }]);
    setInput('');
  };

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20, overflow: 'hidden' }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Chat con la Reina</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Conversa sobre tus resultados. La Reina propone ajustes concretos.</p>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--surface)', borderRadius: 'var(--r-lg)', border: '1px solid var(--border)', overflow: 'hidden' }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {messages.map((msg) => (
            <div key={msg.id} style={{ display: 'flex', gap: 12, justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              {msg.role === 'assistant' && <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,var(--primary),#7C74F0)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 15, flex: 'none' }}>L</div>}
              <div style={{ maxWidth: '72%' }}>
                <div style={{ padding: '12px 16px', borderRadius: 14, background: msg.role === 'user' ? 'var(--primary)' : 'var(--surface-2)', color: msg.role === 'user' ? '#fff' : 'var(--text)', fontSize: 14 }}>{msg.text}</div>
                <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{msg.time}</span>
              </div>
              {msg.role === 'user' && <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#F59E0B,#EF6C5A)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 14, flex: 'none' }}>DP</div>}
            </div>
          ))}
        </div>
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--surface)', display: 'flex', gap: 10 }}>
          <input type="text" placeholder="Escribe tu pregunta..." value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSend()} style={{ flex: 1, border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '11px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' }} />
          <button onClick={handleSend} className="btn btn-primary" style={{ padding: '10px 16px', fontFamily: 'inherit' }}><Icon name="send" size={16} /></button>
        </div>
      </div>
    </div>
  );
}

function ViewAprendizaje() {
  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Aprendizaje</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Lo que Landa aprendió de tus aprobaciones para afinar la próxima corrida.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Tu cliente ideal</h3>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 18px' }}>Perfil que más aprobaste, con nivel de confianza.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[
              { attr: 'Tamaño', value: '100–300 empleados', conf: 88 },
              { attr: 'Activos físicos', value: 'Flota o planta propia', conf: 82 },
              { attr: 'Decisor', value: 'Director de Operaciones / COO', conf: 76 },
            ].map((r) => (
              <div key={r.attr}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)', fontWeight: 600 }}>{r.attr}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>{r.conf}%</span>
                </div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 7 }}>{r.value}</div>
                <div style={{ height: 6, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: r.conf + '%', height: '100%', background: 'var(--primary)', borderRadius: 999 }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Señales predictivas</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { text: 'Tiene flota o planta propia que asegurar', weight: '+34%', up: true },
              { text: 'Abrió una nueva sede en los últimos 6 meses', weight: '+28%', up: true },
              { text: 'El decisor respondió en menos de 24 h', weight: '+19%', up: true },
            ].map((s) => (
              <div key={s.text} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 13px', borderRadius: 12, background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div style={{ width: 26, height: 26, borderRadius: 7, flex: 'none', display: 'grid', placeItems: 'center', background: s.up ? 'var(--green-soft)' : 'var(--red-soft)', color: s.up ? 'var(--green)' : 'var(--red)' }}>
                  {s.up ? '↑' : '↓'}
                </div>
                <span style={{ flex: 1, fontSize: 13.5, color: 'var(--text)' }}>{s.text}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: s.up ? 'var(--green)' : 'var(--red)' }}>{s.weight}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ SIDEBAR ============
function Sidebar({ view, setView }: any) {
  const nav = [
    ['inicio', 'home', 'Inicio'],
    ['campanas', 'rocket', 'Campañas'],
    ['resultados', 'list', 'Resultados'],
    ['aprobados', 'check', 'Aprobados'],
    ['chat', 'chat', 'Chat'],
    ['aprendizaje', 'spark', 'Aprendizaje'],
  ];

  return (
    <aside style={{ width: 248, flex: 'none', background: 'var(--surface)', borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '6px 8px 18px' }}>
        <div style={{ width: 34, height: 34, borderRadius: 10, background: 'linear-gradient(135deg, var(--primary), #7C74F0)', display: 'grid', placeItems: 'center', boxShadow: '0 4px 12px -4px rgba(79,70,229,.6)' }}>
          <div style={{ width: 13, height: 13, borderRadius: 4, background: '#fff' }} />
        </div>
        <div>
          <div style={{ fontWeight: 800, fontSize: 17, color: 'var(--ink)', letterSpacing: '-0.02em' }}>Landa</div>
          <div style={{ fontSize: 11, color: 'var(--text-faint)', fontWeight: 600 }}>Prospección B2B</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {nav.map(([key, ic, label]) => (
          <div key={key} onClick={() => setView(key)} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 12px', borderRadius: 10, color: view === key ? 'var(--primary-700)' : 'var(--text-muted)', fontWeight: view === key ? 700 : 600, fontSize: 14, cursor: 'pointer', background: view === key ? 'var(--primary-soft)' : 'transparent', transition: 'all .12s' }}>
            <span style={{ display: 'flex' }}><Icon name={ic} size={19} /></span>
            <span>{label}</span>
            {key === 'resultados' && <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 700, color: '#fff', background: 'var(--primary)', borderRadius: 999, padding: '2px 8px' }}>8</span>}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 14, padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span className="label">Plan Pro</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>62%</span>
          </div>
          <div style={{ height: 7, background: '#E9E9F1', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: '62%', height: '100%', background: 'var(--primary)', borderRadius: 999 }} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8 }}>8.420 / 13.500 créditos</div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 8, borderRadius: 12, cursor: 'pointer' }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#F59E0B,#EF6C5A)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 14 }}>DP</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--ink)' }}>DPG Seguros</div>
            <div style={{ fontSize: 11.5, color: 'var(--text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>dpg.seguros@gmail.com</div>
          </div>
          <span style={{ display: 'flex', color: 'var(--text-faint)' }}><Icon name="gear" size={16} /></span>
        </div>
      </div>
    </aside>
  );
}

// ============ TOPBAR ============
function Topbar({ onLaunch }: any) {
  return (
    <header style={{ height: 70, flex: 'none', display: 'flex', alignItems: 'center', gap: 16, padding: '0 28px', borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,.8)', backdropFilter: 'blur(8px)', zIndex: 5 }}>
      <div style={{ position: 'relative', width: 320, maxWidth: '32%' }}>
        <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)', display: 'flex' }}><Icon name="search" size={17} /></span>
        <input placeholder="Buscar empresas, leads, decisores…" style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '10px 12px 10px 36px', fontFamily: 'inherit', fontSize: 13.5, color: 'var(--text)', outline: 'none' }} />
      </div>
      <div style={{ flex: 1 }} />
      <button style={{ width: 40, height: 40, borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text)', position: 'relative' }}>
        <Icon name="bell" size={19} />
        <span style={{ position: 'absolute', top: 7, right: 7, width: 7, height: 7, borderRadius: '50%', background: 'var(--red)', border: '1.5px solid #fff' }} />
      </button>
      <button className="btn btn-primary" style={{ fontFamily: 'inherit' }} onClick={onLaunch}><Icon name="rocket" size={16} /> Lanzar campaña</button>
    </header>
  );
}

// ============ APP ============
export function App() {
  const [view, setView] = useState('inicio');
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [showWizard, setShowWizard] = useState(false);

  useEffect(() => {
    // Try to auto-login on app start and retry if rate limited
    const attemptLogin = async () => {
      try {
        // First, check if there's a token in localStorage
        if (api.loadToken()) {
          return;
        }
        // Otherwise, try to get one
        await api.initAuth('dpg.seguros@gmail.com', 'seguros2026');
        console.log('Auto-login successful');
      } catch (err: any) {
        console.warn('Auto-login failed:', err.message);
        // Retry in 5 seconds
        setTimeout(attemptLogin, 5000);
      }
    };
    attemptLogin();
  }, []);

  // Close the wizard when navigating away from the campaigns view
  useEffect(() => {
    if (view !== 'campanas') setShowWizard(false);
  }, [view]);

  useEffect(() => {
    const root = document.documentElement;
    const colors = {
      bg: '#F6F6FB',
      surface: '#FFFFFF',
      'surface-2': '#FAFAFC',
      'surface-3': '#F2F2F8',
      border: '#ECECF3',
      'border-2': '#E3E3EC',
      primary: '#4F46E5',
      'primary-600': '#4338CA',
      'primary-700': '#3730A3',
      'primary-soft': '#EEEDFC',
      'primary-softer': '#F5F4FE',
      'r-buscador': '#6366F1',
      'r-scraper': '#0EA5E9',
      'r-analista': '#10B981',
      'r-redactor': '#F59E0B',
      'r-buscador-soft': '#EEF0FE',
      'r-scraper-soft': '#E8F6FD',
      'r-analista-soft': '#E6F8F1',
      'r-redactor-soft': '#FEF4E3',
      green: '#15A56A',
      'green-soft': '#E6F6EE',
      amber: '#D97A06',
      'amber-soft': '#FCF1E0',
      red: '#E03E4C',
      'red-soft': '#FCE9EA',
      ink: '#16161D',
      text: '#34343F',
      'text-muted': '#6B6B7A',
      'text-faint': '#9696A6',
    };
    Object.entries(colors).forEach(([k, v]) => {
      root.style.setProperty(`--${k}`, v);
    });
  }, []);

  return (
    <div className="lc" style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)', fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif" }}>
      <Sidebar view={view} setView={setView} />
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Topbar onLaunch={() => { setView('campanas'); setShowWizard(true); }} />
        <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
          {view === 'inicio' && <ViewInicio campaignId={campaignId} />}
          {view === 'aprobados' && <ViewAprobados campaignId={campaignId} />}
          {view === 'resultados' && <ViewResultados />}
          {view === 'campanas' && <ViewCampanas showWizard={showWizard} setShowWizard={setShowWizard} onSelectCampaign={(id: string) => { setCampaignId(id); setView('aprobados'); }} />}
          {view === 'chat' && <ViewChat />}
          {view === 'aprendizaje' && <ViewAprendizaje />}
        </div>
      </main>
    </div>
  );
}

export default App;
