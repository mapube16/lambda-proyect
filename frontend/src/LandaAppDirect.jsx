/* ============================================================
   LANDA — APP COMPLETA (single file)
   Includes: shared utils, shell, y todas las vistas
   ============================================================ */
const { useState, useEffect } = React;

// ============ HERO ICONS ============
function Icon({ name, size = 18, stroke = 1.5 }) {
  const icons = {
    home: 'M3 12a9 9 0 1 1 18 0a9 9 0 0 1-18 0M2.25 12c0 5.385 4.365 9.75 9.75 9.75S21.75 17.385 21.75 12 17.385 2.25 12 2.25 2.25 6.615 2.25 12Zm9-3.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z',
    rocket: 'M15.59 14.37a6 6 0 0 1-5.84 7.38A6.52 6.52 0 0 1 2.54 15.6a6.5 6.5 0 1 1 13.05-1.23zM11.5 12.5v5.5m-4-3h7',
    list: 'M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5',
    check: 'M9 12.75L11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
    chat: 'M12 20.887L8.265 23.5a.75.75 0 01-1.19-.75l1.08-6.3H3.75a.75.75 0 01-.728-.994l1.5-6A.75.75 0 015.25 9h5.568l.844-4.923A.75.75 0 0112 3.75c.369 0 .713.201.894.518l1.44 2.232h5.895a.75.75 0 01.728.994l-1.5 6a.75.75 0 01-.728.506H17.25l-.844 4.923a.75.75 0 01-.744.626.75.75 0 01-.75-.75v-5.249H12z',
    spark: 'M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 3.75l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z',
    bell: 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75c0-.78-.125-1.533-.357-2.25M15.75 9.75H7.5a6 6 0 0 0 0 12h8.25m.75-12V5.25A2.25 2.25 0 0 0 13.5 3h-3a2.25 2.25 0 0 0-2.25 2.25v2.25m13.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
    search: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 1 0 5.5 5.5a7.5 7.5 0 0 0 10.5 10.5z',
    gear: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.592c.55 0 1.02.398 1.11.94a6.47 6.47 0 0 0 1.5 1.237V3c0-.557.45-1 1-1h2c.55 0 1 .443 1 1v2.177a6.47 6.47 0 0 0 1.5-1.237c.09-.542.56-.94 1.11-.94h2.592c.55 0 1.02.398 1.11.94a6.47 6.47 0 0 0 1.5 1.237V3c0-.557.45-1 1-1h2c.55 0 1 .443 1 1v2.177a6.47 6.47 0 0 0 1.5-1.237c.09-.542.56-.94 1.11-.94h2.592c.55 0 1.02.398 1.11.94a6.47 6.47 0 0 0 1.5 1.237V3c0-.557.45-1 1-1h2c.55 0 1 .443 1 1v2.177a6.47 6.47 0 0 0 1.5-1.237c.09-.542.56-.94 1.11-.94h2.592c.55 0 1.02.398 1.11.94a6.47 6.47 0 0 0 1.5 1.237V3c0-.557.45-1 1-1h2c.55 0 1 .443 1 1v18c0 .557-.45 1-1 1h-2c-.55 0-1-.443-1-1v-2.177a6.47 6.47 0 0 1-1.5 1.237c-.09.542-.56.94-1.11.94h-2.592c-.55 0-1.02-.398-1.11-.94a6.47 6.47 0 0 1-1.5-1.237V21c0 .557-.45 1-1 1h-2c-.55 0-1-.443-1-1v-2.177a6.47 6.47 0 0 1-1.5 1.237c-.09.542-.56.94-1.11.94H9.594c-.55 0-1.02-.398-1.11-.94a6.47 6.47 0 0 1-1.5-1.237V21c0 .557-.45 1-1 1h-2c-.55 0-1-.443-1-1V3c0-.557.45-1 1-1h2c.55 0 1 .443 1 1v2.177a6.47 6.47 0 0 1 1.5-1.237z',
    eye: 'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7C7.523 19 3.732 16.057 2.458 12z',
    x: 'M6 18L18 6M6 6l12 12',
    send: 'M6 12L3.269 3.125A59.769 59.769 0 0 1 21.485 11.8a59.768 59.768 0 0 1-18.215 8.675 59.72 59.72 0 0 1 4.244-5.514m-4.894-2.611a59.921 59.921 0 0 0 7.552 2.399m7.145-13.75a20.908 20.908 0 0 1 .856 6.026A20.908 20.908 0 0 1 7.3 20.25M6 12a20.908 20.908 0 0 0 17.856-5.676',
    copy: 'M16 16.5V9.75a4.5 4.5 0 0 0-4.5-4.5h-1.5a4.5 4.5 0 0 0-4.5 4.5v6.75m12 0a4.5 4.5 0 0 1-4.5 4.5h-1.5a4.5 4.5 0 0 1-4.5-4.5m12 0V9.362m0 16.5a4.5 4.5 0 0 0-4.5-4.5m0 0H9a4.5 4.5 0 0 0-4.5 4.5',
    clock: 'M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
    pen: 'M16.862 4.487l1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931zm0 0L19.5 7.125',
    arrow: 'M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3',
    dots: 'M12 8.25a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5zM12.75 12a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0zM12 15.75a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5z',
    plus: 'M12 4.5v15m7.5-7.5h-15',
    play: 'M8.25 4.5L19.5 12m0 0l-11.25 7.5M19.5 12v.75c0 .414-.337.75-.75.75H4.5',
    pause: 'M6 4.5h4.5m7.5 0H18M6 20.25h4.5m7.5 0H18',
    filter: 'M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5',
  };
  const p = icons[name] || '';
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round">
      <path d={p} />
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

function AgentAvatar({ role, size = 40, live = false }) {
  const r = ROLES[role];
  return (
    <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <div style={{ width: size, height: size, borderRadius: size * 0.32, background: r.soft, color: r.color, display: 'grid', placeItems: 'center', border: `1px solid ${r.color}22` }}>
        <Icon name={r.icon} size={size * 0.5} stroke={1.9} />
      </div>
      {live && <span style={{ position: 'absolute', right: -2, bottom: -2, width: 11, height: 11, borderRadius: '50%', background: 'var(--green)', border: '2px solid #fff', display: 'block' }} />}
    </div>
  );
}

function scoreColor(s) { return s >= 85 ? 'var(--green)' : s >= 75 ? 'var(--amber)' : 'var(--text-muted)'; }
function scoreSoft(s) { return s >= 85 ? 'var(--green-soft)' : s >= 75 ? 'var(--amber-soft)' : 'var(--surface-3)'; }

function Spark({ data, color, w = 76, h = 28 }) {
  const min = Math.min(...data), max = Math.max(...data);
  const pts = data.map((d, i) => [(i / (data.length - 1)) * w, h - 3 - ((d - min) / (max - min || 1)) * (h - 6)]);
  const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const id = 'g' + Math.round(min * 7 + max + w);
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.18" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <path d={line + ` L${w} ${h} L0 ${h} Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.6" fill={color} />
    </svg>
  );
}

// ============ DATA ============
const LEADS = [
  { id: 1, name: 'Transportes Andina', sector: 'Logística', ciudad: 'Bogotá', score: 86, decisor: 'Carolina Rojas', cargo: 'Directora de Operaciones', email: 'crojas@andina.co', phone: '+57 310 555 0142', reason: 'Flota propia de 40+ vehículos.', opens: 2, clicks: 0, replies: 0, status: 'opened' },
  { id: 2, name: 'Constructora Vértice', sector: 'Construcción', ciudad: 'Medellín', score: 91, decisor: 'Andrés Díaz', cargo: 'CEO', email: 'adiaz@vertice.co', phone: '+57 304 555 0199', reason: 'Obras activas en 3 ciudades.', opens: 0, clicks: 0, replies: 0, status: 'pending' },
  { id: 3, name: 'Frigorífico del Sur', sector: 'Alimentos', ciudad: 'Cali', score: 79, decisor: 'Mónica Peña', cargo: 'Gerente General', email: 'mpena@frigosur.co', phone: '+57 315 555 0177', reason: 'Cadena de frío industrial.', opens: 1, clicks: 1, replies: 1, status: 'opened' },
  { id: 4, name: 'AgroExport Caribe', sector: 'Agro', ciudad: 'Barranquilla', score: 73, decisor: 'Luis Mora', cargo: 'Director Comercial', email: 'lmora@agrocaribe.co', phone: '+57 300 555 0123', reason: 'Exportadora con bodegas.', opens: 0, clicks: 0, replies: 0, status: 'bounce' },
  { id: 5, name: 'Manufacturas Lumen', sector: 'Industria', ciudad: 'Bogotá', score: 82, decisor: 'Paula Gómez', cargo: 'COO', email: 'pgomez@lumen.co', phone: '+57 311 555 0188', reason: 'Planta con maquinaria costosa.', opens: 3, clicks: 1, replies: 0, status: 'opened' },
];

const KPIS = [
  { label: 'Leads calificados', value: 24, trend: '+5', spark: [8, 10, 9, 13, 12, 18, 24], color: 'var(--primary)' },
  { label: 'Aprobados por ti', value: 16, trend: '+3', spark: [4, 6, 7, 9, 11, 13, 16], color: 'var(--green)' },
  { label: 'Tasa de aprobación', value: '68%', trend: '+4%', spark: [52, 55, 58, 61, 60, 64, 68], color: 'var(--r-buscador)' },
  { label: 'Empresas analizadas', value: 142, trend: '+31', spark: [70, 85, 95, 110, 120, 132, 142], color: 'var(--r-scraper)' },
];

// ============ SHELL ============
function Sidebar({ view, setView }) {
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
          <div key={key} className={'nav-item' + (view === key ? ' active' : '')} onClick={() => setView(key)} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 12px', borderRadius: 10, color: view === key ? 'var(--primary-700)' : 'var(--text-muted)', fontWeight: view === key ? 700 : 600, fontSize: 14, cursor: 'pointer', background: view === key ? 'var(--primary-soft)' : 'transparent', transition: 'all .12s' }}>
            <Icon name={ic} size={19} />
            <span>{label}</span>
            {key === 'resultados' && <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 700, color: view === key ? '#fff' : '#fff', background: view === key ? 'var(--primary)' : 'var(--primary)', borderRadius: 999, padding: '2px 8px' }}>8</span>}
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
          <Icon name="gear" size={16} />
        </div>
      </div>
    </aside>
  );
}

function Topbar({ onLaunch }) {
  return (
    <header style={{ height: 70, flex: 'none', display: 'flex', alignItems: 'center', gap: 16, padding: '0 28px', borderBottom: '1px solid var(--border)', background: 'rgba(255,255,255,.8)', backdropFilter: 'blur(8px)', zIndex: 5 }}>
      <div style={{ position: 'relative', width: 320, maxWidth: '32%' }}>
        <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-faint)' }}><Icon name="search" size={17} /></span>
        <input placeholder="Buscar empresas, leads, decisores…" style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '10px 12px 10px 36px', fontFamily: 'inherit', fontSize: 13.5, color: 'var(--text)', outline: 'none' }} />
      </div>
      <div style={{ flex: 1 }} />
      <button className="btn btn-ghost btn-icon" title="Notificaciones" style={{ position: 'relative' }}>
        <Icon name="bell" size={19} />
        <span style={{ position: 'absolute', top: 7, right: 7, width: 7, height: 7, borderRadius: '50%', background: 'var(--red)', border: '1.5px solid #fff' }} />
      </button>
      <button className="btn btn-primary" onClick={onLaunch}><Icon name="rocket" size={16} /> Lanzar campaña</button>
    </header>
  );
}

// ============ VISTAS ============
function ViewInicio() {
  const [running, setRunning] = useState(true);
  const AGENT_TASKS = {
    buscador: ['Buscando en Bogotá...', 'Rastreando SECOP II...', 'Explorando Medellín...', 'Consultando directorios...'],
    scraper:  ['Leyendo web de empresa...', 'Extrayendo contactos...', 'Analizando descripción...', 'Verificando flota...'],
    analista: ['Evaluando activos físicos...', 'Calculando score...', 'Verificando decisor...', 'Aplicando scoring B2B...'],
    redactor: ['Personalizando apertura...', 'Ajustando tono...', 'Finalizando ≤80 palabras...', 'Redactando correo...'],
  };
  const [agentStates, setAgentStates] = useState([
    { role: 'buscador', task: 'Buscando en Bogotá...', count: 38 },
    { role: 'scraper',  task: 'Leyendo web de empresa...', count: 24 },
    { role: 'analista', task: 'Evaluando activos físicos...', count: 12 },
    { role: 'redactor', task: 'Personalizando apertura...', count: 8 },
  ]);
  const [feed] = useState([
    { id: 1, text: 'Constructora Vértice — Score 91 ✓ Aprobada', time: 'hace 1 min', color: 'var(--green)' },
    { id: 2, text: 'Ferretería Los Alpes — Score 52 ✗ Descartada', time: 'hace 3 min', color: 'var(--red)' },
    { id: 3, text: 'Correo listo para Transportes Andina', time: 'hace 5 min', color: 'var(--primary)' },
    { id: 4, text: 'Manufacturas Lumen — Score 82 ✓ Aprobada', time: 'hace 7 min', color: 'var(--green)' },
  ]);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setAgentStates(prev => prev.map((a) => {
        const tasks = AGENT_TASKS[a.role];
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
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>
            Tu equipo encontró <strong style={{ color: 'var(--ink)' }}>8 leads nuevos</strong> para revisar hoy.
          </p>
        </div>
        <button className={'btn ' + (running ? 'btn-soft' : 'btn-primary')} onClick={() => setRunning(r => !r)}>
          <Icon name={running ? 'pause' : 'play'} size={15} />
          {running ? 'Pausar campaña' : 'Reanudar campaña'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16 }}>
        {KPIS.map((k) => (
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
              <div style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--green)', animation: 'landa-pulse 1.6s infinite' }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--green)' }}>Operando</span>
            </div>
          ) : (
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-faint)' }}>Pausado</span>
          )}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 22px 1fr 22px 1fr 22px 1fr', alignItems: 'stretch', gap: 0 }}>
          {agentStates.map((a, i) => {
            const r = ROLES[a.role];
            const progPct = [72, 58, 44, 30][i];
            return (
              <React.Fragment key={a.role}>
                <div style={{ borderRadius: 14, border: '1.5px solid ' + (running ? r.color + '44' : 'var(--border)'), background: running ? r.soft : 'var(--surface-2)', padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 10, transition: 'background .4s, border-color .4s' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <AgentAvatar role={a.role} size={36} live={running} />
                    <span style={{ fontSize: 22, fontWeight: 800, color: running ? r.color : 'var(--text-faint)', fontVariantNumeric: 'tabular-nums' }}>{a.count}</span>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', marginBottom: 3 }}>{r.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4, minHeight: 30 }}>{running ? a.task : r.job}</div>
                  </div>
                  <div style={{ height: 5, borderRadius: 999, background: 'var(--surface-3)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 999, background: running ? r.color : 'var(--border-2)', width: (running ? progPct : 0) + '%', transition: 'width 2s ease' }} />
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
            {LEADS.slice(0, 3).map((l) => (
              <div key={l.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 12px', borderRadius: 11, background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div style={{ width: 40, height: 40, borderRadius: 11, background: scoreSoft(l.score), color: scoreColor(l.score), display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 14, flex: 'none' }}>{l.score}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>{l.decisor} · {l.sector}</div>
                </div>
                <Icon name="arrow" size={15} style={{ color: 'var(--text-faint)', flex: 'none' }} />
              </div>
            ))}
            <button className="btn btn-soft" style={{ justifyContent: 'center', marginTop: 4, fontSize: 13 }}>Ver todos los leads →</button>
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <h3 style={{ fontSize: 16, margin: 0, marginBottom: 14 }}>Actividad reciente</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {feed.map((f) => (
              <div key={f.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{ width: 9, height: 9, borderRadius: '50%', background: f.color, flex: 'none', marginTop: 5 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.4 }}>{f.text}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 2 }}>{f.time}</div>
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 10, background: 'var(--primary-soft)', display: 'flex', gap: 8, alignItems: 'center' }}>
            <Icon name="spark" size={16} style={{ color: 'var(--primary)', flex: 'none' }} />
            <span style={{ fontSize: 12.5, color: 'var(--text)' }}>Próximo: <strong>AgroExport Caribe</strong> en análisis</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function getScoreBreakdown(lead) {
  const activos = { 'Logística': 30, 'Construcción': 30, 'Industria': 28, 'Alimentos': 25, 'Agro': 23 }[lead.sector] || 25;
  const base = 20, decisor = lead.decisor ? 16 : 0;
  const complejidad = Math.max(0, lead.score - base - activos - decisor);
  return [
    { label: 'Validación base', pts: base, max: 20, color: 'var(--primary)' },
    { label: 'Activos físicos', pts: activos, max: 30, color: 'var(--r-scraper)' },
    { label: 'Complejidad operativa', pts: complejidad, max: 30, color: 'var(--r-analista)' },
    { label: 'Decisor identificado', pts: decisor, max: 20, color: 'var(--green)' },
  ];
}

function ViewAprobados() {
  const [selectedLead, setSelectedLead] = useState(null);
  const [tab, setTab] = useState('todos');
  const [channel, setChannel] = useState('both');
  const [editing, setEditing] = useState(false);
  const [sent, setSent] = useState(false);
  const [draft, setDraft] = useState({ subject: '', body: '' });

  useEffect(() => {
    if (selectedLead) {
      setChannel('both');
      setEditing(false);
      setSent(false);
      setDraft({
        subject: `Propuesta de cobertura para ${selectedLead.name}`,
        body: `Hola ${selectedLead.decisor.split(' ')[0]},\n\nEn DPG Seguros acompañamos a empresas de ${selectedLead.sector.toLowerCase()} como ${selectedLead.name} a proteger su operación con pólizas a la medida.\n\nMe gustaría mostrarle cómo lo hemos hecho con compañías similares. ¿Tendría 15 minutos esta semana?\n\nSaludos,\nEquipo DPG Seguros`,
      });
    }
  }, [selectedLead]);

  const filtered = LEADS.filter((l) => {
    if (tab === 'abiertos') return l.opens > 0;
    if (tab === 'pendientes') return l.status === 'pending';
    if (tab === 'respondidos') return l.replies > 0;
    return true;
  });

  const stats = {
    enviados: LEADS.length,
    abiertos: LEADS.filter((l) => l.opens > 0).length,
    ctr: LEADS.filter((l) => l.clicks > 0).length,
    respuestas: LEADS.filter((l) => l.replies > 0).length,
  };

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Aprobados para enviar</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{LEADS.length} leads listos. {stats.abiertos} abiertos, {stats.respuestas} respondieron.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Enviados</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--primary)' }}>{stats.enviados}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>100%</div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Abiertos</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--green)' }}>{stats.abiertos}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--green)' }}>{Math.round((stats.abiertos / stats.enviados) * 100)}%</div>
          </div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Click-Through</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--amber)' }}>{stats.ctr}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--amber)' }}>50%</div>
          </div>
        </div>
        <div className="card" style={{ padding: 16 }}>
          <div className="label" style={{ marginBottom: 8 }}>Respuestas</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--r-analista)' }}>{stats.respuestas}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--r-analista)' }}>20%</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <h3 style={{ fontSize: 17, margin: 0 }}>Seguimiento de envíos</h3>
          <div style={{ display: 'flex', gap: 4, padding: 4, background: 'var(--surface-3)', borderRadius: 11 }}>
            {['todos', 'abiertos', 'pendientes', 'respondidos'].map((t) => (
              <div key={t} onClick={() => setTab(t)} style={{ padding: '7px 12px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: t === tab ? 'var(--surface)' : 'transparent', color: t === tab ? 'var(--ink)' : 'var(--text-muted)', boxShadow: t === tab ? 'var(--sh-xs)' : 'none', textTransform: 'capitalize' }}>{t}</div>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 0.8fr 0.9fr 1fr', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
          {['Empresa', 'Decisor', 'Enviado', 'Aperturas', 'Clicks', 'Estado'].map((h, i) => <span key={i} className="label" style={{ fontSize: 10.5 }}>{h}</span>)}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {filtered.length === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '56px 24px', gap: 14, textAlign: 'center' }}>
              <div style={{ width: 56, height: 56, borderRadius: 16, background: 'var(--surface-2)', border: '1px solid var(--border)', display: 'grid', placeItems: 'center', color: 'var(--text-faint)' }}>
                <Icon name="filter" size={26} />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--ink)', marginBottom: 6 }}>Sin leads en esta vista</div>
                <div style={{ fontSize: 13.5, color: 'var(--text-muted)', lineHeight: 1.5 }}>Prueba otra pestaña o aprueba más leads desde <strong>Resultados</strong>.</div>
              </div>
            </div>
          )}
          {filtered.map((l) => (
            <div key={l.id} className="lead-row" style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 0.8fr 0.9fr 1fr', gap: 12, padding: '14px 20px', borderBottom: '1px solid var(--border)', alignItems: 'center', cursor: 'pointer' }} onClick={() => setSelectedLead(l)}>
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
                <div style={{ fontSize: 10, color: 'var(--text-faint)' }}>{l.opens > 0 ? '100%' : '0%'}</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 800, color: l.clicks > 0 ? 'var(--amber)' : 'var(--text-faint)' }}>{l.clicks}</div>
              </div>
              <div>
                <span className="chip" style={{ background: l.status === 'opened' ? 'var(--green-soft)' : l.status === 'pending' ? 'var(--amber-soft)' : 'var(--red-soft)', color: l.status === 'opened' ? 'var(--green)' : l.status === 'pending' ? 'var(--amber)' : 'var(--red)' }}>
                  {l.status === 'opened' && '✓ Abierto'}
                  {l.status === 'pending' && '⏳ Pendiente'}
                  {l.status === 'bounce' && '✕ Bounce'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Modal */}
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
            <div style={{ flex: 1, padding: 24, display: 'flex', flexDirection: 'column', gap: 20, overflowY: 'auto' }}>
              <div>
                <div className="label" style={{ marginBottom: 12 }}>📈 MÉTRICAS DE ENVÍO</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="card" style={{ padding: 14 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 6 }}>Aperturas</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--primary)' }}>{selectedLead.opens}</div>
                  </div>
                  <div className="card" style={{ padding: 14 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 6 }}>Clicks</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-muted)' }}>{selectedLead.clicks}</div>
                  </div>
                </div>
              </div>
              <div className="card" style={{ padding: 14, background: 'var(--green-soft)', border: '1px solid var(--green)' }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Icon name="check" size={18} style={{ color: 'var(--green)', flex: 'none' }} />
                  <div style={{ fontSize: 13, color: 'var(--text)' }}>
                    <strong>Email abierto</strong><br />
                    <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Enviado hace 2 días. Aperturas confirmadas.</span>
                  </div>
                </div>
              </div>

              {/* Score — desglose del Analista */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div className="label">Calificación del Analista</div>
                  <div style={{ fontSize: 22, fontWeight: 800, color: scoreColor(selectedLead.score), letterSpacing: '-0.02em' }}>{selectedLead.score} <span style={{ fontSize: 13, color: 'var(--text-faint)', fontWeight: 500 }}>/ 100</span></div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  {getScoreBreakdown(selectedLead).map((ph) => (
                    <div key={ph.label}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
                        <span style={{ fontSize: 12.5, color: 'var(--text)', fontWeight: 600 }}>{ph.label}</span>
                        <span style={{ fontSize: 13, fontWeight: 800, color: ph.color, fontVariantNumeric: 'tabular-nums' }}>+{ph.pts} <span style={{ fontSize: 11, color: 'var(--text-faint)', fontWeight: 400 }}>/ {ph.max}</span></span>
                      </div>
                      <div style={{ height: 6, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{ width: Math.round((ph.pts / ph.max) * 100) + '%', height: '100%', background: ph.color, borderRadius: 999 }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Canal de envío */}
              <div>
                <div className="label" style={{ marginBottom: 10 }}>Canal de envío</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                  {[
                    { id: 'email', label: 'Email', icon: 'send', sub: selectedLead.email },
                    { id: 'whatsapp', label: 'WhatsApp', icon: 'chat', sub: selectedLead.phone },
                    { id: 'both', label: 'Ambos', icon: 'check', sub: 'Email + WhatsApp' },
                  ].map((ch) => {
                    const on = channel === ch.id;
                    return (
                      <button key={ch.id} onClick={() => setChannel(ch.id)} style={{ cursor: 'pointer', textAlign: 'left', borderRadius: 12, padding: '11px 12px', background: on ? 'var(--primary-soft)' : 'var(--surface-2)', border: on ? '1.5px solid var(--primary)' : '1.5px solid var(--border-2)', transition: 'all .12s', fontFamily: 'inherit' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, color: on ? 'var(--primary-700)' : 'var(--text)', fontWeight: 700, fontSize: 13.5 }}>
                          <Icon name={ch.icon} size={16} /> {ch.label}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{ch.sub}</div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Mensaje a enviar */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div className="label">Mensaje a enviar</div>
                  <button className="btn btn-soft" style={{ padding: '6px 12px', fontSize: 12.5 }} onClick={() => setEditing((e) => !e)}>
                    <Icon name="pen" size={14} /> {editing ? 'Listo' : 'Editar mensaje'}
                  </button>
                </div>
                {editing ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {channel !== 'whatsapp' && (
                      <input value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} placeholder="Asunto" style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '10px 12px', fontFamily: 'inherit', fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', outline: 'none' }} />
                    )}
                    <textarea value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px', fontFamily: 'inherit', fontSize: 13.5, lineHeight: 1.55, color: 'var(--text)', outline: 'none', resize: 'vertical', minHeight: 150 }} />
                  </div>
                ) : (
                  <div className="card" style={{ padding: 16, background: 'var(--surface-2)' }}>
                    {channel !== 'whatsapp' && <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--ink)', marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>{draft.subject}</div>}
                    <div style={{ fontSize: 13.5, color: 'var(--text)', lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>{draft.body}</div>
                  </div>
                )}
              </div>

              {/* Info de envío + acción */}
              {sent ? (
                <div className="card" style={{ padding: 14, background: 'var(--green-soft)', border: '1px solid var(--green)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Icon name="check" size={20} style={{ color: 'var(--green)', flex: 'none' }} />
                  <div style={{ fontSize: 13, color: 'var(--text)' }}>
                    <strong>Mensaje enviado</strong> · {channel === 'email' ? 'por correo' : channel === 'whatsapp' ? 'por WhatsApp' : 'por correo y WhatsApp'}. Empezaremos a rastrear aperturas en breve.
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12.5, color: 'var(--text-muted)', background: 'var(--primary-softer)', borderRadius: 10, padding: '10px 12px' }}>
                    <Icon name="bell" size={15} style={{ color: 'var(--primary)', flex: 'none', marginTop: 1 }} />
                    <span>
                      {channel === 'email' && <>Se enviará por correo a <strong style={{ color: 'var(--ink)' }}>{selectedLead.email}</strong> y rastrearemos aperturas y clicks.</>}
                      {channel === 'whatsapp' && <>Se enviará por WhatsApp a <strong style={{ color: 'var(--ink)' }}>{selectedLead.phone}</strong> y rastrearemos entrega y lectura.</>}
                      {channel === 'both' && <>Se enviará por correo (<strong style={{ color: 'var(--ink)' }}>{selectedLead.email}</strong>) y WhatsApp (<strong style={{ color: 'var(--ink)' }}>{selectedLead.phone}</strong>), con seguimiento de aperturas en ambos.</>}
                    </span>
                  </div>
                  <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setSent(true)}>
                    <Icon name="send" size={16} /> Enviar {channel === 'email' ? 'por correo' : channel === 'whatsapp' ? 'por WhatsApp' : 'por correo y WhatsApp'}
                  </button>
                </div>
              )}
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
  const fMax = funnel[0][1];

  const topStats = [
    { label: 'Tasa de apertura', value: '69%', trend: '+6%', spark: [48, 52, 55, 58, 62, 65, 69], color: 'var(--green)' },
    { label: 'Tasa de respuesta', value: '25%', trend: '+3%', spark: [14, 16, 18, 19, 22, 23, 25], color: 'var(--primary)' },
    { label: 'Costo por lead', value: '$4.2', trend: '−$0.6', spark: [6.1, 5.8, 5.4, 5.0, 4.8, 4.5, 4.2], color: 'var(--r-scraper)' },
    { label: 'Reuniones agendadas', value: 7, trend: '+2', spark: [1, 2, 3, 3, 5, 6, 7], color: 'var(--r-redactor)' },
  ];

  const sectors = [
    { name: 'Construcción', leads: 38, rate: 74, spark: [55, 60, 62, 66, 70, 72, 74], color: 'var(--green)' },
    { name: 'Logística', leads: 44, rate: 68, spark: [50, 54, 58, 60, 63, 66, 68], color: 'var(--primary)' },
    { name: 'Industria', leads: 29, rate: 64, spark: [48, 50, 55, 58, 60, 62, 64], color: 'var(--r-buscador)' },
    { name: 'Alimentos', leads: 18, rate: 58, spark: [40, 44, 48, 50, 53, 56, 58], color: 'var(--amber)' },
    { name: 'Agro', leads: 13, rate: 49, spark: [38, 40, 42, 44, 46, 47, 49], color: 'var(--r-scraper)' },
  ];

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Resultados de campaña</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Seguros corporativos · Bogotá, Medellín, Cali · últimos 30 días</p>
      </div>

      {/* KPIs con tendencia */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {topStats.map((k) => (
          <div key={k.label} className="card" style={{ padding: 18 }}>
            <span className="label">{k.label}</span>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontSize: 28, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.03em' }}>{k.value}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--green)' }}>{k.trend}</span>
              </div>
              <Spark data={k.spark} color={k.color} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr', gap: 16, alignItems: 'start' }}>
        {/* Embudo */}
        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Embudo de conversión</h3>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 18px' }}>De empresa descubierta a respuesta del decisor.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {funnel.map(([label, val, color], i) => {
              const pct = Math.round((val / fMax) * 100);
              const conv = i === 0 ? 100 : Math.round((val / funnel[i - 1][1]) * 100);
              return (
                <div key={label}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)' }}>{label}</span>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                      <span className="num" style={{ fontSize: 15, fontWeight: 800, color: 'var(--ink)' }}>{val}</span>
                      {i > 0 && <span className="num" style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--text-faint)' }}>{conv}%</span>}
                    </div>
                  </div>
                  <div style={{ height: 12, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden' }}>
                    <div style={{ width: pct + '%', height: '100%', background: color, borderRadius: 999, transition: 'width .5s' }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Desempeño por sector */}
        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Desempeño por sector</h3>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 8px' }}>Tasa de aprobación y tendencia de 7 semanas.</p>
          <div>
            {sectors.map((s, i) => (
              <div key={s.name} style={{ display: 'grid', gridTemplateColumns: '1.1fr 76px auto', gap: 14, alignItems: 'center', padding: '14px 0', borderBottom: i < sectors.length - 1 ? '1px solid var(--border)' : 'none' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>{s.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>{s.leads} leads</div>
                </div>
                <Spark data={s.spark} color={s.color} />
                <div style={{ textAlign: 'right', minWidth: 54 }}>
                  <span style={{ fontSize: 19, fontWeight: 800, color: s.color, letterSpacing: '-0.02em' }}>{s.rate}%</span>
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 16, padding: '12px 14px', background: 'var(--green-soft)', borderRadius: 12, display: 'flex', gap: 9, alignItems: 'flex-start' }}>
            <Icon name="spark" size={17} style={{ color: 'var(--green)', flex: 'none', marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: 'var(--text)', lineHeight: 1.5 }}>
              <strong>Construcción</strong> es tu sector más rentable (74%). Considera redirigir más leads ahí desde Agro.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ViewCampanas() {
  const [campaigns, setCampaigns] = useState([
    { id: 1, name: 'Seguros corporativos', status: 'active', leads: 24, approved: 16, cities: 'Bogotá, Medellín, Cali', progress: 66, created: '2025-01-15', sector: 'Seguros', description: 'Prospección de empresas con operación propia para seguros corporativos y pólizas de cumplimiento.', leads_per_city: { 'Bogotá': 12, 'Medellín': 8, 'Cali': 4 }, top_sectors: ['Construcción 8', 'Logística 6', 'Industria 5'] },
    { id: 2, name: 'Pólizas de cumplimiento', status: 'paused', leads: 12, approved: 5, cities: 'Bogotá', progress: 42, created: '2025-01-10', sector: 'Seguros', description: 'Enfocada en empresas con requisitos de cumplimiento normativo.', leads_per_city: { 'Bogotá': 12 }, top_sectors: ['Industria 7', 'Manufactura 4'] },
    { id: 3, name: 'Flotas y transporte', status: 'draft', leads: 0, approved: 0, cities: '—', progress: 0, created: '2025-01-18', sector: 'Logística', description: 'Nueva campaña para empresas de transporte y logística.', leads_per_city: {}, top_sectors: [] },
  ]);
  const [showWizard, setShowWizard] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [step, setStep] = useState(0);
  const [formData, setFormData] = useState({ name: '', sector: '', cities: [], description: '', targetProfile: '', estimatedLeads: '' });

  const SECTOR_OPTIONS = ['Seguros', 'Logística', 'Construcción', 'Alimentos', 'Industria', 'Agro', 'Salud', 'Distribución'];
  const CITY_OPTIONS = ['Bogotá', 'Medellín', 'Cali', 'Barranquilla', 'Cartagena', 'Bucaramanga', 'Cúcuta'];
  const STEPS = [
    { title: '¿Cuál es el nombre de tu campaña?', subtitle: 'Dale un nombre descriptivo para identificarla fácilmente.' },
    { title: '¿Qué sector vas a prospeccionar?', subtitle: 'Elige el sector objetivo o ingresa uno personalizado.' },
    { title: '¿En qué ciudades?', subtitle: 'Selecciona las ciudades donde buscarás leads.' },
    { title: '¿Cuál es tu cliente ideal?', subtitle: 'Describe el perfil: tamaño de empresa, rol del decisor, etc.' },
    { title: '¿Cuántos leads esperas?', subtitle: 'Estimado para calibrar la operación.' },
    { title: 'Resumen y lanzamiento', subtitle: 'Revisa todo y lanza tu campaña.' },
  ];

  const openWizard = () => {
    setShowWizard(true);
    setSelectedCampaign(null);
    setStep(0);
    setFormData({ name: '', sector: '', cities: [], description: '', targetProfile: '', estimatedLeads: '' });
  };

  const handleNext = () => {
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      handleLaunch();
    }
  };

  const handleLaunch = () => {
    setCampaigns([...campaigns, { id: Date.now(), name: formData.name, status: 'draft', leads: 0, approved: 0, cities: formData.cities.join(', '), progress: 0, created: new Date().toISOString().split('T')[0], sector: formData.sector, description: formData.description, leads_per_city: {}, top_sectors: [] }]);
    setShowWizard(false);
    setFormData({ name: '', sector: '', cities: [], description: '', targetProfile: '', estimatedLeads: '' });
    setStep(0);
  };

  const statusColor = (s) => s === 'active' ? 'var(--green)' : s === 'paused' ? 'var(--amber)' : 'var(--text-faint)';
  const statusBg = (s) => s === 'active' ? 'var(--green-soft)' : s === 'paused' ? 'var(--amber-soft)' : 'var(--surface-3)';
  const statusLabel = (s) => s === 'active' ? '● Activa' : s === 'paused' ? '⏸ Pausada' : '○ Borrador';

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Campañas</h1>
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{campaigns.length} campañas · {campaigns.filter(c => c.status === 'active').length} activa(s)</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <a href="https://wa.me/573005551234?text=Hola%20Landa%2C%20necesito%20ayuda%20con%20mi%20campaña" target="_blank" rel="noopener noreferrer" className="btn btn-ghost">
            <Icon name="chat" size={16} /> Solicitar ayuda
          </a>
          <button className="btn btn-primary" onClick={openWizard}><Icon name="plus" size={16} /> Nueva campaña</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, flex: 1, minHeight: 0 }}>
        {campaigns.map((c) => (
          <div key={c.id} className="card" style={{ padding: 20, display: 'flex', flexDirection: 'column', cursor: 'pointer', transition: 'all .2s' }} onClick={() => setSelectedCampaign(c)}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: 16, margin: 0, marginBottom: 4, fontWeight: 800, color: 'var(--ink)' }}>{c.name}</h3>
                <span className="chip" style={{ background: statusBg(c.status), color: statusColor(c.status), fontSize: 12 }}>{statusLabel(c.status)}</span>
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
                <span className="num" style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)' }}>{c.progress}%</span>
              </div>
              <div style={{ height: 6, background: '#EDEDF4', borderRadius: 999, overflow: 'hidden' }}>
                <div style={{ width: c.progress + '%', height: '100%', background: 'var(--primary)', borderRadius: 999 }} />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Modal de detalles de campaña */}
      {selectedCampaign && (
        <>
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(16,16,29,.5)', zIndex: 9, backdropFilter: 'blur(4px)' }} onClick={() => setSelectedCampaign(null)} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '90%', maxWidth: 700, maxHeight: '90vh', background: 'var(--surface)', borderRadius: 'var(--r-xl)', zIndex: 10, display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,.3)', overflow: 'hidden' }}>
            {/* header */}
            <div style={{ padding: '24px 28px', borderBottom: '1px solid var(--border)', flex: 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <h2 style={{ fontSize: 22, margin: 0, fontWeight: 800 }}>{selectedCampaign.name}</h2>
                <button className="btn btn-icon btn-ghost" onClick={() => setSelectedCampaign(null)}><Icon name="x" size={22} /></button>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>Creada el {selectedCampaign.created}</p>
            </div>

            {/* content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 24 }}>
              {/* status y métricas */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
                <div className="card" style={{ padding: 16, textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, fontWeight: 700, textTransform: 'uppercase' }}>Estado</div>
                  <span className="chip" style={{ background: statusBg(selectedCampaign.status), color: statusColor(selectedCampaign.status), fontSize: 13, justifyContent: 'center' }}>{statusLabel(selectedCampaign.status)}</span>
                </div>
                <div className="card" style={{ padding: 16, textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, fontWeight: 700 }}>LEADS</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--primary)' }}>{selectedCampaign.leads}</div>
                </div>
                <div className="card" style={{ padding: 16, textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, fontWeight: 700 }}>APROBADOS</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--green)' }}>{selectedCampaign.approved}</div>
                </div>
                <div className="card" style={{ padding: 16, textAlign: 'center' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 8, fontWeight: 700 }}>TASA</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--amber)' }}>{selectedCampaign.leads > 0 ? Math.round((selectedCampaign.approved / selectedCampaign.leads) * 100) : 0}%</div>
                </div>
              </div>

              {/* descripción */}
              <div>
                <h3 style={{ fontSize: 14, margin: 0, marginBottom: 8, fontWeight: 800, color: 'var(--ink)' }}>Descripción</h3>
                <p style={{ margin: 0, fontSize: 14, color: 'var(--text)', lineHeight: 1.6 }}>{selectedCampaign.description}</p>
              </div>

              {/* sector y ciudades */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <h3 style={{ fontSize: 14, margin: 0, marginBottom: 8, fontWeight: 800, color: 'var(--ink)' }}>Sector</h3>
                  <span className="chip" style={{ background: 'var(--primary-soft)', color: 'var(--primary-700)', fontSize: 13 }}>{selectedCampaign.sector}</span>
                </div>
                <div>
                  <h3 style={{ fontSize: 14, margin: 0, marginBottom: 8, fontWeight: 800, color: 'var(--ink)' }}>Ciudades</h3>
                  <p style={{ margin: 0, fontSize: 14, color: 'var(--text)' }}>{selectedCampaign.cities}</p>
                </div>
              </div>

              {/* embudo de progreso */}
              <div>
                <h3 style={{ fontSize: 14, margin: 0, marginBottom: 12, fontWeight: 800, color: 'var(--ink)' }}>Progreso del embudo</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[['Descubiertas', Math.round(selectedCampaign.leads * 1.4), 'var(--primary)'], ['Analizadas', Math.round(selectedCampaign.leads * 0.8), 'var(--r-scraper)'], ['Calificadas', selectedCampaign.leads, 'var(--amber)'], ['Aprobadas', selectedCampaign.approved, 'var(--green)']].map(([l, v, c]) => (
                    <div key={l}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{l}</span>
                        <span className="num" style={{ fontSize: 13, fontWeight: 700, color: c }}>{v}</span>
                      </div>
                      <div style={{ height: 8, background: '#EDEDF4', borderRadius: 999, overflow: 'hidden' }}>
                        <div style={{ width: (v / (Math.round(selectedCampaign.leads * 1.4) || 1)) * 100 + '%', height: '100%', background: c, borderRadius: 999 }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* footer */}
            <div style={{ padding: 20, borderTop: '1px solid var(--border)', display: 'flex', gap: 10, flex: 'none' }}>
              <button className="btn btn-ghost" onClick={() => setSelectedCampaign(null)} style={{ flex: 1, justifyContent: 'center' }}>Cerrar</button>
              <button className="btn btn-primary" style={{ flex: 1, justifyContent: 'center' }}>
                {selectedCampaign.status === 'active' ? '⏸ Pausar' : '▶ Reanudar'}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Wizard Modal (igual que antes) */}
      {showWizard && (
        <>
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(16,16,29,.5)', zIndex: 9, backdropFilter: 'blur(4px)' }} onClick={() => setShowWizard(false)} />
          <div style={{ position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '90%', maxWidth: 600, maxHeight: '90vh', background: 'var(--surface)', borderRadius: 'var(--r-xl)', zIndex: 10, display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,.3)', overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)', flex: 'none' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                  <h2 style={{ fontSize: 18, margin: 0, fontWeight: 800 }}>Asistente de campaña</h2>
                  <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>Paso {step + 1} de {STEPS.length}</div>
                </div>
                <button className="btn btn-icon btn-ghost" onClick={() => setShowWizard(false)}><Icon name="x" size={22} /></button>
              </div>
              <div style={{ height: 4, background: '#EDEDF4', borderRadius: 999 }}>
                <div style={{ width: ((step + 1) / STEPS.length) * 100 + '%', height: '100%', background: 'var(--primary)', borderRadius: 999, transition: 'width .3s' }} />
              </div>
            </div>

            <div style={{ flex: 1, padding: 24, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
              <div>
                <h3 style={{ fontSize: 16, margin: 0, marginBottom: 4, fontWeight: 800, color: 'var(--ink)' }}>{STEPS[step].title}</h3>
                <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>{STEPS[step].subtitle}</p>
              </div>

              {step === 0 && (
                <input type="text" placeholder="ej. Seguros corporativos" value={formData.name} onChange={(e) => setFormData({...formData, name: e.target.value})} style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' }} />
              )}

              {step === 1 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {SECTOR_OPTIONS.map((s) => (
                    <button key={s} onClick={() => setFormData({...formData, sector: s})} className="btn btn-ghost" style={{ justifyContent: 'flex-start', background: formData.sector === s ? 'var(--primary-soft)' : 'var(--surface-2)', color: formData.sector === s ? 'var(--primary-700)' : 'var(--text)', border: formData.sector === s ? '1px solid var(--primary)' : '1px solid var(--border-2)', padding: '12px 14px' }}>{s}</button>
                  ))}
                </div>
              )}

              {step === 2 && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {CITY_OPTIONS.map((c) => (
                    <button key={c} onClick={() => setFormData({...formData, cities: formData.cities.includes(c) ? formData.cities.filter(x => x !== c) : [...formData.cities, c]})} className="btn btn-ghost" style={{ justifyContent: 'flex-start', background: formData.cities.includes(c) ? 'var(--primary-soft)' : 'var(--surface-2)', color: formData.cities.includes(c) ? 'var(--primary-700)' : 'var(--text)', border: formData.cities.includes(c) ? '1px solid var(--primary)' : '1px solid var(--border-2)', padding: '10px 12px', fontSize: 13 }}>{c}</button>
                  ))}
                </div>
              )}

              {step === 3 && (
                <textarea placeholder="ej. Empresas de 100-300 empleados, industria, con operación propia..." value={formData.targetProfile} onChange={(e) => setFormData({...formData, targetProfile: e.target.value})} style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none', resize: 'vertical', minHeight: 100 }} />
              )}

              {step === 4 && (
                <input type="number" placeholder="ej. 50" value={formData.estimatedLeads} onChange={(e) => setFormData({...formData, estimatedLeads: e.target.value})} style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' }} />
              )}

              {step === 5 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div className="card" style={{ padding: 16, background: 'var(--primary-soft)' }}>
                    <div className="label" style={{ marginBottom: 12 }}>RESUMEN DE CAMPAÑA</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Nombre:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{formData.name}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Sector:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{formData.sector}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Ciudades:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{formData.cities.join(', ')}</span></div>
                      <div><span style={{ color: 'var(--text-faint)', fontSize: 12 }}>Leads estimados:</span> <span style={{ fontWeight: 700, color: 'var(--ink)' }}>{formData.estimatedLeads}</span></div>
                    </div>
                  </div>
                  <div style={{ background: 'var(--green-soft)', border: '1px solid var(--green)', borderRadius: 10, padding: 12 }}>
                    <div style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--green)' }}>
                      <Icon name="check" size={16} style={{ flex: 'none' }} />
                      <span>Tu campaña está lista para lanzarse. Los agentes comenzarán la prospección inmediatamente.</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div style={{ padding: 20, borderTop: '1px solid var(--border)', display: 'flex', gap: 10, flex: 'none' }}>
              <button className="btn btn-ghost" onClick={() => setShowWizard(false)} style={{ flex: 1, justifyContent: 'center' }}>Cancelar</button>
              {step > 0 && <button className="btn btn-ghost" onClick={() => setStep(step - 1)} style={{ flex: 1, justifyContent: 'center' }}>← Atrás</button>}
              <button className="btn btn-primary" onClick={handleNext} style={{ flex: 1, justifyContent: 'center' }}>{step === STEPS.length - 1 ? '🚀 Lanzar campaña' : 'Siguiente →'}</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ViewChat() {
  function detectIntent(text) {
    const t = text.toLowerCase();
    if (/pequeñ|tamaño|empleado|grande|mediana|chic/.test(t)) return 'refine_target';
    if (/frío|formal|tono|estilo|cálido|cercano|corpor/.test(t)) return 'adjust_tone';
    if (/client|exclu|bloqu|ya son|competen/.test(t)) return 'blacklist_company';
    if (/como est|similar|igual|clon|parecid|más de est/.test(t)) return 'clone_lead';
    return null;
  }
  const INTENT_META = {
    refine_target:    { label: 'Ajustar perfil objetivo',   icon: 'filter', color: 'var(--primary)',    reply: 'Detecté que quieres empresas de un tamaño diferente. Puedo actualizar los criterios del Buscador para filtrar por rango de empleados.',         proposal: 'Aplicar filtro: 100–500 empleados con activos físicos confirmados' },
    adjust_tone:      { label: 'Cambiar tono del correo',   icon: 'pen',    color: 'var(--r-redactor)', reply: 'Entendido. El tono actual puede sentirse muy formal. Puedo actualizar la plantilla del Redactor para un estilo más cercano y directo.',       proposal: 'Actualizar plantilla: tono amable y cercano, menos corporativo' },
    blacklist_company:{ label: 'Excluir del pipeline',      icon: 'x',      color: 'var(--red)',        reply: 'Puedo agregar esas empresas o sectores a la lista negra para que el Buscador los omita en futuras corridas.',                                proposal: 'Agregar a lista negra: omitir en próximas campañas' },
    clone_lead:       { label: 'Buscar leads similares',    icon: 'copy',   color: 'var(--green)',      reply: '¡Buena señal! Puedo pedirle al Buscador que encuentre 20 empresas con el mismo perfil que ese lead aprobado.',                            proposal: 'Buscar 20 empresas similares al perfil aprobado más reciente' },
  };
  const [messages, setMessages] = useState([
    { id: 1, role: 'assistant', text: 'Hola, soy la Reina de Landa. Cuéntame sobre tus resultados o pídeme ajustar la campaña en curso.', time: '09:15', intent: null },
    { id: 2, role: 'user', text: '¿Cuál es el sector con mejor tasa?', time: '09:17' },
    { id: 3, role: 'assistant', text: 'Construcción lidera con 74%, seguido por Logística (68%) e Industria (64%). Son tus sectores más rentables — vale la pena concentrar más leads ahí.', time: '09:18', intent: null },
  ]);
  const [input, setInput] = useState('');
  const [pendingAction, setPendingAction] = useState(null);
  const QUICK = ['Quiero leads más grandes', 'El tono del correo es muy frío', 'Ya son nuestros clientes', 'Busca más como Vértice'];

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    const userMsg = { id: Date.now(), role: 'user', text, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    const intent = detectIntent(text);
    const meta = intent ? INTENT_META[intent] : null;
    const botId = Date.now() + 1;
    const botMsg = { id: botId, role: 'assistant', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), text: meta ? meta.reply : 'Analicé tu campaña. Basado en los datos recientes, tu tasa sigue mejorando. ¿Quieres ajustar algo específico?', intent };
    setMessages(m => [...m, userMsg, botMsg]);
    if (intent) setPendingAction({ msgId: botId, intent });
    setInput('');
  };

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20, overflow: 'hidden' }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Chat con la Reina</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Conversa sobre tus resultados. La Reina detecta tu intención y propone ajustes concretos.</p>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--surface)', borderRadius: 'var(--r-lg)', border: '1px solid var(--border)', overflow: 'hidden' }}>
        <div style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {messages.map((msg) => (
            <div key={msg.id}>
              <div style={{ display: 'flex', gap: 12, justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {msg.role === 'assistant' && (
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,var(--primary),#7C74F0)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 15, flex: 'none' }}>L</div>
                )}
                <div style={{ maxWidth: '72%', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ padding: '12px 16px', borderRadius: 14, background: msg.role === 'user' ? 'var(--primary)' : 'var(--surface-2)', color: msg.role === 'user' ? '#fff' : 'var(--text)', fontSize: 14, lineHeight: 1.55, wordBreak: 'break-word' }}>{msg.text}</div>
                  <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{msg.time}</span>
                  {msg.intent && pendingAction && pendingAction.msgId === msg.id && (function() {
                    const m = INTENT_META[msg.intent];
                    return (
                      <div style={{ marginTop: 4, padding: '14px 16px', borderRadius: 14, border: '1.5px solid ' + m.color + '33', background: m.color + '0C' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                          <div style={{ width: 28, height: 28, borderRadius: 8, background: m.color + '22', color: m.color, display: 'grid', placeItems: 'center', flex: 'none' }}><Icon name={m.icon} size={14} /></div>
                          <span style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--ink)' }}>{m.label}</span>
                        </div>
                        <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>{m.proposal}</div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button className="btn btn-primary" style={{ flex: 1, justifyContent: 'center', fontSize: 13 }} onClick={() => setPendingAction(null)}><Icon name="check" size={14} /> Aplicar ajuste</button>
                          <button className="btn btn-ghost" style={{ fontSize: 13, padding: '8px 14px' }} onClick={() => setPendingAction(null)}>Descartar</button>
                        </div>
                      </div>
                    );
                  })()}
                </div>
                {msg.role === 'user' && (
                  <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#F59E0B,#EF6C5A)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 14, flex: 'none' }}>DP</div>
                )}
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: '8px 16px 10px', borderTop: '1px solid var(--border)', display: 'flex', gap: 7, flexWrap: 'wrap', background: 'var(--surface-2)' }}>
          {QUICK.map((q) => (
            <button key={q} onClick={() => setInput(q)} style={{ cursor: 'pointer', background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 999, padding: '5px 12px', fontSize: 12.5, fontWeight: 600, color: 'var(--text)', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>{q}</button>
          ))}
        </div>
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--surface)', display: 'flex', gap: 10 }}>
          <input type="text" placeholder="ej. 'Quiero leads más grandes' · 'El tono es muy frío' · 'Más como Vértice'" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSend()} style={{ flex: 1, border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '11px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' }} />
          <button onClick={handleSend} className="btn btn-primary" style={{ padding: '10px 16px' }}><Icon name="arrow" size={16} /></button>
        </div>
      </div>
    </div>
  );
}


function ViewAprendizaje() {
  const [locked, setLocked] = useState(false);

  if (locked) return (
    <div style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%', gap: 0 }}>
      <div style={{ textAlign: 'center', maxWidth: 400 }}>
        <div style={{ width: 72, height: 72, borderRadius: 20, background: 'var(--primary-soft)', color: 'var(--primary)', display: 'grid', placeItems: 'center', margin: '0 auto 22px' }}>
          <Icon name="spark" size={34} />
        </div>
        <h2 style={{ fontSize: 22, margin: '0 0 10px', color: 'var(--ink)' }}>Aprendizaje en progreso</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5, lineHeight: 1.65, margin: '0 0 28px' }}>
          Landa necesita al menos <strong style={{ color: 'var(--ink)' }}>3 leads aprobados</strong> para detectar los patrones de tu cliente ideal. Ya tienes 2.
        </p>
        <div style={{ height: 10, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden', marginBottom: 8 }}>
          <div style={{ width: '67%', height: '100%', background: 'var(--primary)', borderRadius: 999, transition: 'width .6s' }} />
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-faint)', marginBottom: 28 }}>2 / 3 leads aprobados</div>
        <button className="btn btn-soft" style={{ justifyContent: 'center', fontSize: 13 }} onClick={() => setLocked(false)}>
          <Icon name="eye" size={15} /> Vista previa del panel completo
        </button>
      </div>
    </div>
  );

  const icp = [
    { attr: 'Tamaño', value: '100–300 empleados', conf: 88 },
    { attr: 'Activos físicos', value: 'Flota o planta propia', conf: 82 },
    { attr: 'Decisor', value: 'Director de Operaciones / COO', conf: 76 },
    { attr: 'Geografía', value: 'Bogotá y Medellín', conf: 71 },
    { attr: 'Momento', value: 'Expansión reciente', conf: 64 },
  ];
  const signals = [
    { text: 'Tiene flota o planta propia que asegurar', weight: '+34%', up: true },
    { text: 'Abrió una nueva sede en los últimos 6 meses', weight: '+28%', up: true },
    { text: 'El decisor respondió en menos de 24 h', weight: '+19%', up: true },
    { text: 'Empresa con menos de 20 empleados', weight: '−22%', up: false },
    { text: 'Sin presencia digital verificable', weight: '−15%', up: false },
  ];
  const recs = [
    { icon: 'rocket', title: 'Duplica esfuerzo en Construcción', text: 'Es tu sector con mejor tasa (74%). Sube el objetivo de leads de 38 a 60 esta semana.' },
    { icon: 'pen', title: 'Acorta los correos', text: 'Los mensajes de menos de 90 palabras tienen 1.4× más respuestas. Ajusta la plantilla del Redactor.' },
    { icon: 'clock', title: 'Envía martes 9–11 a.m.', text: 'Es tu ventana con mayor apertura (72%). Programa los envíos en ese rango.' },
  ];

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Aprendizaje</h1>
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Lo que Landa aprendió de tus 16 aprobaciones para afinar la próxima corrida.</p>
        </div>
        <button className="btn btn-ghost" style={{ fontSize: 12.5 }} onClick={() => setLocked(true)}>
          <Icon name="eye" size={14} /> Simular &lt; 3 leads
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
        {/* Perfil del cliente ideal */}
        <div className="card" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 4 }}>
            <div style={{ width: 30, height: 30, borderRadius: 9, background: 'var(--primary-soft)', color: 'var(--primary)', display: 'grid', placeItems: 'center', flex: 'none' }}><Icon name="check" size={17} /></div>
            <h3 style={{ fontSize: 17, margin: 0 }}>Tu cliente ideal</h3>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 18px' }}>Perfil que más aprobaste, con nivel de confianza.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {icp.map((r) => (
              <div key={r.attr}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-faint)', fontWeight: 600 }}>{r.attr}</span>
                  <span className="num" style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>{r.conf}%</span>
                </div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', marginBottom: 7 }}>{r.value}</div>
                <div style={{ height: 6, background: 'var(--surface-3)', borderRadius: 999, overflow: 'hidden' }}>
                  <div style={{ width: r.conf + '%', height: '100%', background: 'var(--primary)', borderRadius: 999 }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Señales predictivas */}
        <div className="card" style={{ padding: 22 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 4 }}>
            <div style={{ width: 30, height: 30, borderRadius: 9, background: 'var(--r-redactor-soft)', color: 'var(--r-redactor)', display: 'grid', placeItems: 'center', flex: 'none' }}><Icon name="spark" size={17} /></div>
            <h3 style={{ fontSize: 17, margin: 0 }}>Señales que predicen aprobación</h3>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 16px' }}>Cómo cada señal mueve la probabilidad de que apruebes.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {signals.map((s) => (
              <div key={s.text} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 13px', borderRadius: 12, background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                <div style={{ width: 26, height: 26, borderRadius: 7, flex: 'none', display: 'grid', placeItems: 'center', background: s.up ? 'var(--green-soft)' : 'var(--red-soft)', color: s.up ? 'var(--green)' : 'var(--red)' }}>
                  <Icon name={s.up ? 'arrow' : 'x'} size={14} stroke={2.2} />
                </div>
                <span style={{ flex: 1, fontSize: 13.5, color: 'var(--text)', lineHeight: 1.4 }}>{s.text}</span>
                <span className="num" style={{ fontSize: 14, fontWeight: 800, color: s.up ? 'var(--green)' : 'var(--red)' }}>{s.weight}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recomendaciones accionables */}
      <div className="card" style={{ padding: 22 }}>
        <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Recomendaciones para la próxima corrida</h3>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 16px' }}>Aplica con un clic y Landa ajustará a tus agentes.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
          {recs.map((r) => (
            <div key={r.title} style={{ borderRadius: 14, border: '1px solid var(--border)', padding: 18, display: 'flex', flexDirection: 'column', gap: 10, background: 'var(--surface-2)' }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--primary-soft)', color: 'var(--primary)', display: 'grid', placeItems: 'center' }}><Icon name={r.icon} size={19} /></div>
              <div style={{ fontWeight: 700, fontSize: 14.5, color: 'var(--ink)' }}>{r.title}</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.5, flex: 1 }}>{r.text}</div>
              <button className="btn btn-soft" style={{ justifyContent: 'center', fontSize: 13 }}><Icon name="check" size={15} /> Aplicar ajuste</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ============ APP ============
function App() {
  const [view, setView] = useState('inicio');

  return (
    <div className="lc" style={{ display: 'flex' }}>
      <Sidebar view={view} setView={setView} />
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Topbar onLaunch={() => setView('campanas')} />
        <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
          {view === 'inicio' && <ViewInicio />}
          {view === 'aprobados' && <ViewAprobados />}
          {view === 'resultados' && <ViewResultados />}
          {view === 'campanas' && <ViewCampanas />}
          {view === 'chat' && <ViewChat />}
          {view === 'aprendizaje' && <ViewAprendizaje />}
        </div>
      </main>

      {/* Botón de ayuda persistente → WhatsApp soporte Landa */}
      <a
        href="https://wa.me/573005551234?text=Hola%20equipo%20Landa%2C%20necesito%20ayuda%20con%20mi%20panel"
        target="_blank"
        rel="noopener noreferrer"
        title="Contactar soporte de Landa"
        style={{ position: 'fixed', bottom: 26, right: 26, height: 50, display: 'flex', alignItems: 'center', gap: 10, padding: '0 18px 0 16px', borderRadius: 999, background: 'linear-gradient(135deg, var(--primary), #7C74F0)', color: '#fff', textDecoration: 'none', fontWeight: 700, fontSize: 14, boxShadow: '0 10px 28px -8px rgba(79,70,229,.55)', zIndex: 50 }}
      >
        <Icon name="chat" size={19} stroke={1.9} />
        Soporte
      </a>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
