import React, { useState, useEffect, createContext, useContext } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import './landa.css';
import * as api from './api';
import { DebtorsSoftSegurosTab } from './components/DebtorsSoftSegurosTab';

// Context for shared email status (used by multiple views)
const EmailStatusContext = createContext<{ connected: boolean } | null>(null);
const useEmailStatus = () => useContext(EmailStatusContext);

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
    phone: 'M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 0 0 2.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 0 1-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 0 0-1.091-.852H4.5A2.25 2.25 0 0 0 2.25 4.5v2.25z',
    shield: 'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.249-8.25-3.285z',
    refresh: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99',
    link: 'M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244',
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

function ViewInicio({ campaignId, onNavigate }: any) {
  const enabled = !!api.getToken() && !!campaignId;

  // KPIs
  const { data: kpisData } = useQuery({
    queryKey: ['kpis', campaignId],
    queryFn: () => api.getKPIs(campaignId!),
    enabled,
    staleTime: 30000,
  });
  const kpis = kpisData?.kpis || EMPTY_KPIS;
  const raw = kpisData?.raw || null;

  // Recent leads (limit 8)
  const { data: recentData } = useQuery({
    queryKey: ['leadsPreview', campaignId],
    queryFn: () => api.getLeads(campaignId!, 8, 0),
    enabled,
    staleTime: 30000,
  });
  const recent = recentData?.leads || [];

  // Campaign runs
  const { data: runsData } = useQuery({
    queryKey: ['runs', campaignId],
    queryFn: () => api.getCampaignRuns(campaignId!),
    enabled,
    staleTime: 15000,
  });
  const running = (runsData?.runs || runsData || []).some((x: any) => x.status === 'queued' || x.status === 'running');

  // Conteos reales (acumulados) derivados de KPIs. No es un ticker en vivo falso.
  const totalLeads = raw?.leads_qualified ?? 0;
  const approved = raw?.leads_approved ?? 0;
  const rejected = raw?.leads_rejected ?? 0;
  const sent = raw?.leads_sent ?? 0;
  const pending = Math.max(0, totalLeads - approved - rejected);
  const stageCounts: Record<string, number> = {
    buscador: totalLeads,
    scraper: totalLeads,
    analista: approved + rejected,
    redactor: approved,
  };
  const agentStates = [
    { role: 'buscador', count: stageCounts.buscador },
    { role: 'scraper', count: stageCounts.scraper },
    { role: 'analista', count: stageCounts.analista },
    { role: 'redactor', count: stageCounts.redactor },
  ];

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6, textTransform: 'capitalize' }}>Buenos días{(() => { const n = (api.getCachedUser()?.email || '').split('@')[0].replace(/[._-]/g, ' ').trim(); return n ? ', ' + n : ''; })()}</h1>
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>
            {!campaignId ? 'Selecciona o lanza una campaña para ver tu actividad.'
              : pending > 0 ? <>Tienes <strong style={{ color: 'var(--ink)' }}>{pending} lead{pending === 1 ? '' : 's'}</strong> pendiente{pending === 1 ? '' : 's'} de revisar.</>
              : <>Sin leads pendientes por ahora.</>}
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: running ? 'var(--green)' : 'var(--text-faint)' }}>
          {running && <span className="live" style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--green)', color: 'var(--green)' }} />}
          {running ? 'Campaña corriendo' : 'Sin corrida activa'}
        </div>
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
            const maxCount = Math.max(agentStates[0].count, 1);
            const progPct = Math.round((a.count / maxCount) * 100);
            const has = a.count > 0;
            return (
              <React.Fragment key={a.role}>
                <div style={{ borderRadius: 14, border: '1.5px solid ' + (has ? r.color + '44' : 'var(--border)'), background: has ? r.soft : 'var(--surface-2)', padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <AgentAvatar role={a.role} size={36} live={running} />
                    <span style={{ fontSize: 22, fontWeight: 800, color: has ? r.color : 'var(--text-faint)' }}>{a.count}</span>
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', marginBottom: 3 }}>{r.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4, minHeight: 30 }}>{r.job}</div>
                  </div>
                  <div style={{ height: 5, borderRadius: 999, background: 'var(--surface-3)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 999, background: has ? r.color : 'var(--border-2)', width: progPct + '%' }} />
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
            {pending > 0 && <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', background: 'var(--primary)', borderRadius: 999, padding: '3px 9px' }}>{pending} nuevos</span>}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {!campaignId ? (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', textAlign: 'center' }}>Selecciona una campaña para ver leads</p>
            ) : totalLeads === 0 ? (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', textAlign: 'center' }}>Aún no hay leads. Lanza una corrida.</p>
            ) : (
              <>
                <div style={{ fontSize: 13.5, color: 'var(--text)' }}>{approved} aprobados · {pending} pendientes · {sent} enviados</div>
                <button className="btn btn-soft" style={{ justifyContent: 'center', marginTop: 4, fontSize: 13, fontFamily: 'inherit' }} onClick={() => onNavigate && onNavigate('aprobados')}>Ver todos los leads →</button>
              </>
            )}
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <h3 style={{ fontSize: 16, margin: 0, marginBottom: 14 }}>Leads recientes</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {recent.length === 0 ? (
              <p style={{ margin: 0, fontSize: 13, color: 'var(--text-faint)' }}>Sin actividad todavía.</p>
            ) : recent.slice(0, 5).map((l: any) => {
              const ok = l.status === 'opened' || l.status === 'approved';
              const color = ok ? 'var(--green)' : l.status === 'pending' ? 'var(--amber)' : 'var(--text-faint)';
              return (
                <div key={l.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <div style={{ width: 9, height: 9, borderRadius: '50%', background: color, flex: 'none', marginTop: 5 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.name || 'Empresa'}{l.score ? ` — Score ${l.score}` : ''}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-faint)', marginTop: 2 }}>{l.ciudad || l.sector || '—'}</div>
                  </div>
                </div>
              );
            })}
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
  { id: 'arriendos', icon: 'home2',    title: 'Seguro de arrendamiento',  desc: 'Inmobiliarias que administran arriendos (empresas contactables, no anuncios).', flags: { source_priority: 'serper' }, tag: 'Inmobiliarias' },
  { id: 'secop',     icon: 'list',     title: 'Pólizas de cumplimiento',  desc: 'Todas las empresas que se presentan a procesos públicos (SECOP), de cualquier sector y ciudad.', flags: { use_secop: true, source_priority: 'secop' }, tag: 'SECOP' },
  { id: 'rues',      icon: 'building', title: 'Empresas recién creadas',  desc: 'Compañías registradas recientemente en Cámara de Comercio (RUES).',      flags: { use_rues: true, source_priority: 'rues' }, tag: 'RUES' },
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

function ViewCampanas({ onSelectCampaign, showWizard, setShowWizard, onLaunched }: any) {
  const queryClient = useQueryClient();

  // Wizard state
  const [step, setStep] = useState(0);
  const [launching, setLaunching] = useState(false);
  const [form, setForm] = useState({ pipeline: '', name: '', sector: '', cities: [] as string[], targetProfile: '', estimatedLeads: '' });

  const openWizard = () => setShowWizard(true);

  // Reset form when wizard opens
  useEffect(() => {
    if (showWizard) {
      setStep(0);
      setForm({ pipeline: '', name: '', sector: '', cities: [], targetProfile: '', estimatedLeads: '' });
    }
  }, [showWizard]);

  // Load campaigns (cached by token)
  const { data: campaignsData, isLoading: loading, error: campaignsError } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.getCampaigns(),
    enabled: !!api.getToken(),
    staleTime: 30000,
  });
  const campaigns = (campaignsData?.campaigns || []).map((c: any) => ({
    id: c.id,
    name: c.name,
    status: c.is_active ? 'active' : 'draft',
    leads: 0,
    approved: 0,
    cities: (c.cities || []).join(', ') || '—',
    progress: 0,
  }));
  const error = campaignsError ? 'Error: ' + (campaignsError instanceof Error ? campaignsError.message : 'No se pudieron cargar las campañas') : null;

  // SECOP (todos los que se presentan a procesos) y RUES (todas las recién creadas)
  // traen empresas de TODOS los sectores y ciudades → no exigen esos filtros.
  const ignoresSectorCity = form.pipeline === 'secop' || form.pipeline === 'rues';
  const canAdvance = () => {
    if (step === 0) return form.pipeline.length > 0;
    if (step === 1) return form.name.trim().length > 0;
    if (step === 2) return ignoresSectorCity || form.sector.length > 0;
    if (step === 3) return ignoresSectorCity || form.cities.length > 0;
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
      // Vertical arrendamiento → apunta a INMOBILIARIAS (empresas contactables), no anuncios.
      const isArr = form.pipeline === 'arriendos';
      const sectors = isArr ? ['inmobiliarias administradoras de arriendo'] : (form.sector ? [form.sector] : []);
      const created = await api.createCampaign({
        name: form.name,
        sectors,
        industria_objetivo: isArr ? 'inmobiliarias administradoras de arriendo' : (form.sector || ''),
        cities: form.cities,
        icp_description: isArr ? 'Inmobiliarias que administran arriendos — prospecto para alianza de seguro de arrendamiento.' : form.targetProfile,
        // Signal-source flags — consumed by hive_tools.discover_companies
        use_rues: !!flags.use_rues,
        use_secop: !!flags.use_secop,
        use_fincaraiz: !!flags.use_fincaraiz,
        source_priority: flags.source_priority || 'serper',
        pipeline: form.pipeline,
      });
      const newId = created.campaign_id || created.id;
      try {
        const launch = await api.launchCampaign(newId);
        if (launch?.run_id) onLaunched && onLaunched({ runId: launch.run_id, campaignId: newId, campaignName: form.name });
      } catch (e: any) {
        console.warn('launch failed:', e.message);
        alert('La campaña se creó, pero no se pudo lanzar: ' + (e.message || ''));
      }
      setShowWizard(false);
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
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
          <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{campaigns.length} campañas · {campaigns.filter((c: any) => c.status === 'active').length} activa(s)</p>
        </div>
        <button className="btn btn-primary" onClick={openWizard} style={{ fontFamily: 'inherit' }}><Icon name="plus" size={16} /> Nueva campaña</button>
      </div>

      {error && <div style={{ padding: 20, background: 'var(--red-soft)', color: 'var(--red)', borderRadius: 10, textAlign: 'center' }}>{error}</div>}
      {loading && <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Cargando campañas...</div>}

      {!error && !loading && campaigns.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No hay campañas todavía. Haz click en "Nueva campaña" para crear una.</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, flex: 1 }}>
        {campaigns.map((c: any) => (
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
                ignoresSectorCity ? (
                  <div style={{ padding: '14px 16px', borderRadius: 10, background: 'var(--primary-softer)', border: '1px solid var(--primary-soft)', fontSize: 13.5, color: 'var(--text)' }}>
                    {form.pipeline === 'rues'
                      ? <>Empresas recién creadas: trae <strong>todas las recién matriculadas</strong>, sin importar su sector (toda empresa nueva necesita seguros). Este filtro no aplica — puedes continuar.</>
                      : <>SECOP trae <strong>todas las empresas que se presentan a procesos públicos</strong>, sin importar su sector. Este filtro no aplica — puedes continuar.</>}
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {SECTOR_OPTIONS.map((s) => (
                      <button key={s} onClick={() => setForm({ ...form, sector: s })} className="btn btn-ghost" style={{ justifyContent: 'flex-start', background: form.sector === s ? 'var(--primary-soft)' : 'var(--surface-2)', color: form.sector === s ? 'var(--primary-700)' : 'var(--text)', border: form.sector === s ? '1px solid var(--primary)' : '1px solid var(--border-2)', padding: '12px 14px' }}>{s}</button>
                    ))}
                  </div>
                )
              )}

              {step === 3 && (
                ignoresSectorCity ? (
                  <div style={{ padding: '14px 16px', borderRadius: 10, background: 'var(--primary-softer)', border: '1px solid var(--primary-soft)', fontSize: 13.5, color: 'var(--text)' }}>
                    {form.pipeline === 'rues'
                      ? <>Aplica a <strong>todas las ciudades</strong> — trae todas las empresas recién matriculadas del país.</>
                      : <>Aplica a <strong>todas las ciudades</strong> — cualquier empresa presentándose a un proceso necesita su póliza de cumplimiento.</>}
                  </div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                    {CITY_OPTIONS.map((c) => (
                      <button key={c} onClick={() => setForm({ ...form, cities: form.cities.includes(c) ? form.cities.filter(x => x !== c) : [...form.cities, c] })} className="btn btn-ghost" style={{ justifyContent: 'flex-start', background: form.cities.includes(c) ? 'var(--primary-soft)' : 'var(--surface-2)', color: form.cities.includes(c) ? 'var(--primary-700)' : 'var(--text)', border: form.cities.includes(c) ? '1px solid var(--primary)' : '1px solid var(--border-2)', padding: '10px 12px', fontSize: 13 }}>{c}</button>
                    ))}
                  </div>
                )
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

function ViewAprobados({ campaignId, onNavigate }: any) {
  const [selectedLead, setSelectedLead] = useState<any>(null);
  const [compose, setCompose] = useState({ subject: '', body: '' });
  const [sending, setSending] = useState(false);
  const queryClient = useQueryClient();

  // Email status from context (loaded once at App level)
  const emailStatusCtx = useEmailStatus();
  const emailConnected = emailStatusCtx?.connected ?? false;

  // Leads (cached by campaignId, auto-refetch only if campaignId changes)
  const { data: leadsData, isLoading: loading, error: leadsError } = useQuery({
    queryKey: ['leads', campaignId],
    queryFn: () => api.getLeads(campaignId!),
    enabled: !!api.getToken() && !!campaignId,
    staleTime: 30000, // 30 sec
  });
  const leads = leadsData?.leads || [];
  const error = leadsError ? 'Error: ' + (leadsError instanceof Error ? leadsError.message : 'No se pudieron cargar los leads') : null;

  // Prefill el borrador editable al abrir un lead
  useEffect(() => {
    if (!selectedLead) return;
    setCompose({
      subject: `Propuesta para ${selectedLead.name}`,
      body: `Hola ${selectedLead.decisor || ''},\n\nTe escribo de parte de nuestro equipo. Creemos que podemos ayudar a ${selectedLead.name} con una propuesta a la medida.\n\n¿Tendrías 15 minutos esta semana para conversarlo?\n\nSaludos,`,
    });
  }, [selectedLead]);

  const qualified = leads.filter((l: any) => l.qualified);
  const descartados = leads.filter((l: any) => !l.qualified);
  const sentCount = leads.filter((l: any) => l.status === 'opened' || l.status === 'sent').length;
  const withContact = qualified.filter((l: any) => l.email || l.phone).length;
  const scoreColor = (s: number) => s >= 75 ? 'var(--green)' : s >= 50 ? 'var(--amber)' : 'var(--text-faint)';

  return (
    <div style={{ padding: '24px 28px', height: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Leads para revisar</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{qualified.length} calificados por la IA · {withContact} con contacto · {descartados.length} descartados.</p>
      </div>

      {error && <div style={{ padding: 20, background: 'var(--red-soft)', color: 'var(--red)', borderRadius: 10, textAlign: 'center' }}>{error}</div>}
      {loading && <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)' }}>Cargando leads...</div>}
      {!error && !loading && leads.length === 0 && <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No hay leads en esta campaña. Lanza una corrida.</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {[
          { label: 'Calificados', value: qualified.length, color: 'var(--primary)' },
          { label: 'Con contacto', value: withContact, color: 'var(--green)' },
          { label: 'Enviados', value: sentCount, color: 'var(--r-scraper)' },
          { label: 'Descartados', value: descartados.length, color: 'var(--text-faint)' },
        ].map((k) => (
          <div key={k.label} className="card" style={{ padding: 16 }}>
            <div className="label" style={{ marginBottom: 8 }}>{k.label}</div>
            <div style={{ fontSize: 28, fontWeight: 800, color: k.color }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Calificados — accionables, ordenados por score (backend) */}
      <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 200 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '54px 2fr 1.4fr 1.4fr 1fr', gap: 12, padding: '10px 20px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
          {['Score', 'Empresa', 'Decisor', 'Contacto', 'Estado'].map((h, i) => <span key={i} className="label" style={{ fontSize: 10.5 }}>{h}</span>)}
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {qualified.length === 0 && !loading && (
            <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-faint)', fontSize: 13.5 }}>Ningún lead calificado todavía. Revisa los descartados abajo o ajusta la búsqueda.</div>
          )}
          {qualified.map((l: any) => (
            <div key={l.id} style={{ display: 'grid', gridTemplateColumns: '54px 2fr 1.4fr 1.4fr 1fr', gap: 12, padding: '14px 20px', borderBottom: '1px solid var(--border)', alignItems: 'center', cursor: 'pointer' }} onClick={() => setSelectedLead(l)}>
              <div style={{ fontSize: 17, fontWeight: 800, color: scoreColor(l.score) }}>{l.score || '—'}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.name || 'Empresa'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>{l.ciudad || l.sector || '—'}</div>
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.decisor || '—'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{l.cargo}</div>
              </div>
              <div style={{ minWidth: 0, fontSize: 12.5, color: l.email || l.phone ? 'var(--text)' : 'var(--text-faint)' }}>
                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.email || 'sin email'}</div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{l.phone || ''}</div>
              </div>
              <div>
                <span className="chip" style={{ background: l.status === 'opened' ? 'var(--green-soft)' : 'var(--amber-soft)', color: l.status === 'opened' ? 'var(--green)' : 'var(--amber)', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                  {l.status === 'opened' ? <><Icon name="check" size={13} /> Enviado</> : <><Icon name="clock" size={13} /> Pendiente</>}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Descartados — colapsado, con motivo */}
      {descartados.length > 0 && (
        <details className="card" style={{ padding: '14px 20px' }}>
          <summary style={{ cursor: 'pointer', fontSize: 13.5, fontWeight: 700, color: 'var(--text-muted)' }}>
            {descartados.length} descartados por la IA (ver motivos)
          </summary>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {descartados.slice(0, 30).map((l: any) => (
              <div key={l.id} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12.5 }}>
                <span style={{ width: 34, fontWeight: 700, color: 'var(--text-faint)' }}>{l.score || 0}</span>
                <span style={{ flex: 1, minWidth: 0, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.name || 'Empresa'}</span>
                <span style={{ color: 'var(--text-faint)', fontStyle: 'italic' }}>{l.motivo || 'sin motivo'}</span>
              </div>
            ))}
          </div>
        </details>
      )}

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
              {/* Sobre la empresa */}
              <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, marginBottom: 18 }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 18px', marginBottom: 10 }}>
                  <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Score <strong style={{ color: 'var(--ink)' }}>{selectedLead.score}</strong></span>
                  {selectedLead.nit && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>NIT {selectedLead.nit}</span>}
                  {selectedLead.ciudad && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{selectedLead.ciudad}</span>}
                  {selectedLead.contratos_secop != null && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{selectedLead.contratos_secop} contratos · {selectedLead.valor_total || ''}</span>}
                  {selectedLead.fecha_matricula && <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Matrícula {selectedLead.fecha_matricula}</span>}
                </div>
                {(selectedLead.resumen || selectedLead.reason) && (
                  <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text)', lineHeight: 1.5 }}>{selectedLead.resumen || selectedLead.reason}</p>
                )}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', marginTop: 12, fontSize: 13 }}>
                  <span style={{ color: 'var(--text-muted)' }}>👤 {selectedLead.decisor || 'decisor no identificado'}{selectedLead.cargo ? ` · ${selectedLead.cargo}` : ''}</span>
                  <span style={{ color: selectedLead.email ? 'var(--text)' : 'var(--text-faint)' }}>✉ {selectedLead.email || 'sin email'}</span>
                  {selectedLead.phone && <span style={{ color: 'var(--text)' }}>☎ {selectedLead.phone}</span>}
                  {selectedLead.url && <a href={selectedLead.url} target="_blank" rel="noreferrer" style={{ color: 'var(--primary)' }}>🌐 sitio</a>}
                </div>
              </div>

              {emailConnected === false && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '11px 14px', borderRadius: 10, background: 'var(--amber-soft)', color: 'var(--amber)', marginBottom: 16, fontSize: 13.5, fontWeight: 600 }}>
                  <span>No tienes un buzón conectado para enviar.</span>
                  <button className="btn btn-soft" style={{ flex: 'none' }} onClick={() => { setSelectedLead(null); onNavigate && onNavigate('ajustes'); }}>Ir a Ajustes</button>
                </div>
              )}

              <label className="label" style={{ display: 'block', marginBottom: 6 }}>Asunto</label>
              <input value={compose.subject} onChange={(e) => setCompose({ ...compose, subject: e.target.value })} style={{ width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '10px 12px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none', marginBottom: 14 }} />

              <label className="label" style={{ display: 'block', marginBottom: 6 }}>Mensaje</label>
              <textarea value={compose.body} onChange={(e) => setCompose({ ...compose, body: e.target.value })} style={{ width: '100%', minHeight: 180, resize: 'vertical', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '10px 12px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none', lineHeight: 1.5 }} />

              <button className="btn btn-soft" style={{ width: '100%', marginTop: 18, justifyContent: 'center', fontFamily: 'inherit' }} onClick={async () => {
                try {
                  await api.approveLead(campaignId, selectedLead.id, 'Aprobado desde UI');
                  alert('Lead aprobado');
                  setSelectedLead(null);
                  queryClient.invalidateQueries({ queryKey: ['leads', campaignId] });
                } catch (err: any) {
                  alert('Error al aprobar: ' + err.message);
                }
              }}>
                <Icon name="check" size={16} /> Aprobar
              </button>
              <button className="btn btn-primary" disabled={sending || emailConnected === false || compose.body.trim().length < 10} style={{ width: '100%', marginTop: 12, justifyContent: 'center', fontFamily: 'inherit', opacity: (sending || emailConnected === false) ? 0.6 : 1 }} onClick={async () => {
                setSending(true);
                try {
                  await api.sendLead(campaignId, selectedLead.id, 'email', compose.body, compose.subject);
                  alert('Correo enviado a ' + (selectedLead.email || 'el decisor'));
                  setSelectedLead(null);
                  queryClient.invalidateQueries({ queryKey: ['leads', campaignId] });
                } catch (err: any) {
                  alert('Error al enviar: ' + (err.message || ''));
                } finally {
                  setSending(false);
                }
              }}>
                <Icon name="send" size={16} /> {sending ? 'Enviando…' : 'Enviar por email'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ViewResultados({ campaignId }: any) {
  const [kpis, setKpis] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!campaignId) { setLoading(false); return; }
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const [k, m] = await Promise.all([
          api.getKPIs(campaignId),
          api.getMetrics(campaignId),
        ]);
        if (!alive) return;
        setKpis(k.raw);
        setMetrics(m);
      } catch (e) {
        console.warn('Resultados load failed:', e);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [campaignId]);

  if (!campaignId) {
    return (
      <div style={{ padding: '24px 28px 28px' }}>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Resultados de campaña</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Selecciona una campaña en Campañas para ver sus resultados.</p>
      </div>
    );
  }

  const pct = (x: number) => Math.round((x || 0) * 100) + '%';
  const cards = [
    { label: 'Tasa de apertura', value: pct(metrics?.open_rate), color: 'var(--green)' },
    { label: 'Tasa de respuesta', value: pct(metrics?.reply_rate), color: 'var(--primary)' },
    { label: 'Tasa de clics', value: pct(metrics?.click_rate), color: 'var(--r-scraper)' },
    { label: 'Correos enviados', value: metrics?.total_sent ?? 0, color: 'var(--r-redactor)' },
  ];

  // Embudo a partir de datos reales: calificadas → aprobadas → enviadas → abiertas → respondidas.
  const funnel: [string, number, string][] = [
    ['Calificadas', kpis?.leads_qualified ?? 0, 'var(--amber)'],
    ['Aprobadas', kpis?.leads_approved ?? 0, 'var(--green)'],
    ['Enviadas', kpis?.leads_sent ?? 0, 'var(--r-buscador)'],
    ['Abiertas', metrics?.opens ?? 0, 'var(--r-analista)'],
    ['Respondidas', metrics?.replies ?? 0, 'var(--r-redactor)'],
  ];

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Resultados de campaña</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{loading ? 'Cargando métricas…' : 'Métricas de correo de la campaña seleccionada'}</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
        {cards.map((k: any) => (
          <div key={k.label} className="card" style={{ padding: 18 }}>
            <span className="label">{k.label}</span>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span style={{ fontSize: 28, fontWeight: 800, color: 'var(--ink)' }}>{k.value}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ padding: 22 }}>
        <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Embudo de conversión</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 18 }}>
          {funnel.map(([label, val, color]: any) => {
            const fMax = Math.max(funnel[0][1] as number, 1);
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
  const [messages, setMessages] = useState<any[]>([
    { id: 1, role: 'assistant', text: 'Hola, soy la Reina de Landa. Descríbeme a quién quieres prospectar y armo la campaña por ti.', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const now = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((m) => [...m, { id: Date.now(), role: 'user', text, time: now() }]);
    setInput('');
    setSending(true);
    try {
      const res = await api.sendChatMessage(text);
      let reply: string;
      if (res.status === 'extracted' && res.campaign) {
        const c = res.campaign;
        const desc = c.name || c.nombre || [c.industria_objetivo, c.ciudad_objetivo].filter(Boolean).join(' · ') || 'tu campaña';
        reply = `✓ Campaña lista: ${desc}. La encuentras en Campañas para lanzarla.`;
      } else {
        reply = res.reply || 'No entendí del todo, ¿puedes darme más detalle?';
      }
      setMessages((m) => [...m, { id: Date.now() + 1, role: 'assistant', text: reply, time: now() }]);
    } catch (e: any) {
      setMessages((m) => [...m, { id: Date.now() + 1, role: 'assistant', text: `Error: ${e.message || 'no pude responder'}`, time: now() }]);
    } finally {
      setSending(false);
    }
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
          <input type="text" placeholder={sending ? 'La Reina está pensando…' : 'Describe a quién prospectar...'} value={input} disabled={sending} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSend()} style={{ flex: 1, border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '11px 14px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none', opacity: sending ? 0.6 : 1 }} />
          <button onClick={handleSend} disabled={sending} className="btn btn-primary" style={{ padding: '10px 16px', fontFamily: 'inherit', opacity: sending ? 0.6 : 1 }}><Icon name="send" size={16} /></button>
        </div>
      </div>
    </div>
  );
}

function ViewAprendizaje() {
  const [stats, setStats] = useState<any>(null);
  const [patterns, setPatterns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [patternsError, setPatternsError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const s = await api.getLearningStats();
        if (alive) setStats(s);
        // Los patrones solo existen si hay suficientes aprobaciones (ready_for_patterns)
        if (s?.ready_for_patterns) {
          try {
            const p = await api.getLearningPatterns();
            const list = Array.isArray(p?.patterns) ? p.patterns : (p?.patterns ? [p.patterns] : []);
            if (alive) setPatterns(list);
          } catch (e: any) {
            if (alive) setPatternsError(e.message || 'No se pudieron calcular patrones');
          }
        }
      } catch (e) {
        console.warn('Aprendizaje load failed:', e);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const idealCount = stats?.ideal_count ?? 0;
  const rejectedCount = stats?.rejected_count ?? 0;

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Aprendizaje</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>{loading ? 'Cargando…' : 'Lo que Landa aprendió de tus aprobaciones para afinar la próxima corrida.'}</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Base de aprendizaje</h3>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 18px' }}>Leads que aprobaste vs. rechazaste. La Reina necesita 3+ aprobaciones para detectar patrones.</p>
          <div style={{ display: 'flex', gap: 14 }}>
            <div style={{ flex: 1, background: 'var(--green-soft)', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 30, fontWeight: 800, color: 'var(--green)' }}>{idealCount}</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 600 }}>Aprobados (ideales)</div>
            </div>
            <div style={{ flex: 1, background: 'var(--red-soft)', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 30, fontWeight: 800, color: 'var(--red)' }}>{rejectedCount}</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 600 }}>Rechazados</div>
            </div>
          </div>
          {!stats?.ready_for_patterns && !loading && (
            <p style={{ fontSize: 12.5, color: 'var(--text-faint)', marginTop: 14, marginBottom: 0 }}>
              Aprueba {Math.max(0, 3 - idealCount)} lead(s) más para desbloquear patrones predictivos.
            </p>
          )}
        </div>

        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Señales predictivas</h3>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 14px' }}>Patrones que la Reina detectó en lo que apruebas.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {patternsError && <span style={{ fontSize: 13, color: 'var(--red)' }}>{patternsError}</span>}
            {!patternsError && patterns.length === 0 && (
              <span style={{ fontSize: 13.5, color: 'var(--text-faint)' }}>
                {stats?.ready_for_patterns ? 'Sin patrones aún.' : 'Disponible cuando tengas 3+ aprobaciones.'}
              </span>
            )}
            {patterns.map((s: any, i: number) => {
              const text = typeof s === 'string' ? s : (s.text || s.signal || s.description || JSON.stringify(s));
              const weight = typeof s === 'object' ? (s.weight || s.impact || '') : '';
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 13px', borderRadius: 12, background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
                  <div style={{ width: 26, height: 26, borderRadius: 7, flex: 'none', display: 'grid', placeItems: 'center', background: 'var(--green-soft)', color: 'var(--green)' }}>↑</div>
                  <span style={{ flex: 1, fontSize: 13.5, color: 'var(--text)' }}>{text}</span>
                  {weight && <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--green)' }}>{weight}</span>}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ AJUSTES → EMAIL ============
function ViewAjustes() {
  const [status, setStatus] = useState<any>(null);
  const [smtp, setSmtp] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [smtpForm, setSmtpForm] = useState({ email: '', password: '', smtp_host: '', smtp_port: 587 });
  const [tpl, setTpl] = useState<{ subject_prefix: string; body_template: string; footer: string }>({ subject_prefix: '', body_template: '', footer: '' });
  const [testTo, setTestTo] = useState('');

  const reload = async () => {
    setLoading(true);
    try {
      const [s, sm, t] = await Promise.all([
        api.getEmailStatus().catch(() => null),
        api.getSmtpStatus().catch(() => null),
        api.getEmailTemplate().catch(() => ({})),
      ]);
      setStatus(s);
      setSmtp(sm);
      setTpl({ subject_prefix: t?.subject_prefix || '', body_template: t?.body_template || '', footer: t?.footer || '' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
    // Toast de retorno OAuth (?oauth_success=true&oauth_provider=gmail)
    const params = new URLSearchParams(window.location.search);
    if (params.has('oauth_success')) {
      const ok = params.get('oauth_success') === 'true';
      const prov = params.get('oauth_provider') || 'email';
      setMsg({ ok, text: ok ? `${prov} conectado correctamente` : `No se pudo conectar ${prov}` });
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const flash = (ok: boolean, text: string) => { setMsg({ ok, text }); setTimeout(() => setMsg(null), 4000); };

  const connected = status?.connected;
  const smtpConfigured = smtp?.configured;

  const handleSaveSmtp = async () => {
    if (!smtpForm.email || !smtpForm.password || !smtpForm.smtp_host) { flash(false, 'Completa email, contraseña y host'); return; }
    setBusy(true);
    try { await api.saveSmtpConfig(smtpForm); flash(true, 'SMTP guardado'); await reload(); }
    catch (e: any) { flash(false, e.message || 'Error guardando SMTP'); }
    finally { setBusy(false); }
  };

  const handleTest = async () => {
    setBusy(true);
    try { const r = await api.sendTestEmail(testTo.trim() || undefined); flash(true, r.message || 'Correo de prueba enviado'); }
    catch (e: any) { flash(false, e.message || 'No se pudo enviar la prueba'); }
    finally { setBusy(false); }
  };

  const handleSaveTpl = async () => {
    setBusy(true);
    try { await api.saveEmailTemplate(tpl); flash(true, 'Plantilla guardada'); }
    catch (e: any) { flash(false, e.message || 'Error guardando plantilla'); }
    finally { setBusy(false); }
  };

  const inputStyle: React.CSSProperties = { width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '10px 12px', fontFamily: 'inherit', fontSize: 14, color: 'var(--text)', outline: 'none' };

  return (
    <div style={{ padding: '24px 28px 28px', display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 760 }}>
      <div>
        <h1 style={{ fontSize: 26, margin: 0, marginBottom: 6 }}>Ajustes</h1>
        <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Conecta tu buzón para enviar los correos de prospección desde tu propia dirección.</p>
      </div>

      {msg && (
        <div style={{ padding: '10px 14px', borderRadius: 10, fontSize: 13.5, fontWeight: 600, background: msg.ok ? 'var(--green-soft)' : 'var(--red-soft)', color: msg.ok ? 'var(--green)' : 'var(--red)' }}>{msg.text}</div>
      )}

      {/* Estado de conexión */}
      <div className="card" style={{ padding: 22 }}>
        <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Buzón de correo</h3>
        {loading ? (
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>Cargando…</p>
        ) : connected ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--green)' }} />
              <div>
                <div style={{ fontWeight: 700, color: 'var(--ink)' }}>{status.email}</div>
                <div style={{ fontSize: 12.5, color: 'var(--text-faint)', textTransform: 'capitalize' }}>{status.provider}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-soft" disabled={busy} onClick={handleTest}>Enviar prueba</button>
              <button className="btn btn-ghost" disabled={busy} onClick={async () => { await api.disconnectEmail().catch(() => {}); flash(true, 'Buzón desconectado'); reload(); }}>Desconectar</button>
            </div>
          </div>
        ) : (
          <>
            <p style={{ fontSize: 13.5, color: 'var(--text-muted)', margin: '8px 0 16px' }}>No tienes un buzón conectado. Conecta uno para poder enviar correos reales.</p>
            <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
              <button className="btn btn-primary" onClick={() => { window.location.href = api.emailConnectUrl('gmail'); }}>Conectar Gmail</button>
              <button className="btn btn-ghost" onClick={() => { window.location.href = api.emailConnectUrl('outlook'); }}>Conectar Outlook</button>
            </div>

            {/* SMTP alternativo */}
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <span className="label">o vía SMTP</span>
                {smtpConfigured && <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--green)' }}>SMTP configurado</span>}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <input style={inputStyle} placeholder="tu@correo.com" value={smtpForm.email} onChange={(e) => setSmtpForm({ ...smtpForm, email: e.target.value })} />
                <input style={inputStyle} type="password" placeholder="Contraseña / App password" value={smtpForm.password} onChange={(e) => setSmtpForm({ ...smtpForm, password: e.target.value })} />
                <input style={inputStyle} placeholder="smtp.gmail.com" value={smtpForm.smtp_host} onChange={(e) => setSmtpForm({ ...smtpForm, smtp_host: e.target.value })} />
                <input style={inputStyle} type="number" placeholder="587" value={smtpForm.smtp_port} onChange={(e) => setSmtpForm({ ...smtpForm, smtp_port: Number(e.target.value) })} />
              </div>
              <button className="btn btn-soft" disabled={busy} style={{ marginTop: 12 }} onClick={handleSaveSmtp}>Guardar SMTP</button>
            </div>
          </>
        )}
      </div>

      {/* Probar envío — disponible con OAuth o SMTP */}
      {(connected || smtpConfigured) && (
        <div className="card" style={{ padding: 22 }}>
          <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Probar envío</h3>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 14px' }}>Envía un correo de prueba para confirmar que tu buzón {connected ? `(${status?.provider})` : '(SMTP)'} funciona. Si dejas el campo vacío, se envía a tu propia dirección.</p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <input style={{ ...inputStyle, flex: 1, minWidth: 220 }} type="email" placeholder="correo de destino (opcional)" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
            <button className="btn btn-primary" disabled={busy} style={{ flex: 'none' }} onClick={handleTest}>{busy ? 'Enviando…' : 'Enviar correo de prueba'}</button>
          </div>
        </div>
      )}

      {/* Plantilla de correo */}
      <div className="card" style={{ padding: 22 }}>
        <h3 style={{ fontSize: 17, margin: 0, marginBottom: 4 }}>Plantilla de correo</h3>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', margin: '0 0 16px' }}>Prefijo de asunto, cuerpo por defecto y firma. Usa <code>{'{nombre}'}</code>, <code>{'{mensaje}'}</code>, <code>{'{firma}'}</code>.</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input style={inputStyle} placeholder="Prefijo de asunto (ej: [Landa])" value={tpl.subject_prefix} onChange={(e) => setTpl({ ...tpl, subject_prefix: e.target.value })} />
          <textarea style={{ ...inputStyle, minHeight: 140, resize: 'vertical', fontFamily: 'inherit' }} placeholder="Cuerpo del correo…" value={tpl.body_template} onChange={(e) => setTpl({ ...tpl, body_template: e.target.value })} />
          <input style={inputStyle} placeholder="Pie / firma" value={tpl.footer} onChange={(e) => setTpl({ ...tpl, footer: e.target.value })} />
          <button className="btn btn-soft" disabled={busy} style={{ alignSelf: 'flex-start' }} onClick={handleSaveTpl}>Guardar plantilla</button>
        </div>
      </div>
    </div>
  );
}

// ============ COBRANZA ============
function ViewCobranza() {
  const [configured, setConfigured] = useState(false);
  const [onbStep, setOnbStep] = useState(0);
  const [onbDesc, setOnbDesc] = useState('');
  const [onbAnalyzing, setOnbAnalyzing] = useState(false);
  const [strategy, setStrategy] = useState<any>(null);
  const [deudores, setDeudores] = useState<any[]>([
    { id:1, nombre:'Carlos Martínez', telefono:'+57 310 555 1234', monto:3200000, vencimiento:'2025-03-15', estado:'promesa_de_pago', intentos:2, max_intentos:5, monto_prometido:3200000, fecha_promesa:'2025-03-20', notas:'Prometió pagar el lunes.', historial:[{ fecha:'2025-02-20', duracion:145, resultado:'contactado', resumen:'El deudor acordó promesa de pago para el 20 de marzo.' },{ fecha:'2025-02-15', duracion:22, resultado:'no-answer', resumen:null }] },
    { id:2, nombre:'Transportes Rápido SAS', telefono:'+57 320 444 9876', monto:8750000, vencimiento:'2025-02-28', estado:'pendiente', intentos:0, max_intentos:5, historial:[] },
    { id:3, nombre:'Laura Gómez', telefono:'+57 300 222 3344', monto:1500000, vencimiento:'2025-03-01', estado:'pagado', intentos:3, max_intentos:5, historial:[{ fecha:'2025-02-22', duracion:210, resultado:'promesa_de_pago', resumen:'Acordó pago total. Pagó al siguiente día.' }] },
    { id:4, nombre:'Inversiones Alpe Ltda', telefono:'+57 315 777 6655', monto:5600000, vencimiento:'2025-03-10', estado:'sin_contacto', intentos:5, max_intentos:5, historial:[{ fecha:'2025-02-21', duracion:0, resultado:'no-answer', resumen:null },{ fecha:'2025-02-19', duracion:0, resultado:'voicemail', resumen:null }] },
    { id:5, nombre:'Ricardo Peña', telefono:'+57 305 888 1122', monto:2100000, vencimiento:'2025-03-25', estado:'llamando', intentos:1, max_intentos:5, historial:[{ fecha:'2025-02-23', duracion:62, resultado:'en-curso', resumen:'Llamada en progreso.' }] },
    { id:6, nombre:'Constructora Vértice', telefono:'+57 318 123 4567', monto:12400000, vencimiento:'2025-02-20', estado:'escalado', intentos:5, max_intentos:5, notas:'Requiere gestión jurídica.', historial:[{ fecha:'2025-02-20', duracion:180, resultado:'disputa', resumen:'El cliente disputa el saldo. Escalar a jurídico.' }] },
  ]);
  const [filtro, setFiltro] = useState<string | null>(null);
  const [selected, setSelected] = useState<any>(null);
  const [showNew, setShowNew] = useState(false);
  const [newForm, setNewForm] = useState({ nombre:'', telefono:'', monto:'', vencimiento:'' });
  const [ley2300, setLey2300] = useState(false);
  const [pendingCall, setPendingCall] = useState<any>(null);
  const [source, setSource] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'manual' | 'softseguros'>('manual');

  const COB_ESTADO_CFG: any = {
    pendiente:       { c:'#0EA5E9', bg:'rgba(14,165,233,0.1)', label:'Pendiente' },
    llamando:        { c:'#D97A06', bg:'#FCF1E0', label:'Llamando', pulse:true },
    contactado:      { c:'#15A56A', bg:'#E6F6EE', label:'Contactado' },
    promesa_de_pago: { c:'#15A56A', bg:'#E6F6EE', label:'Promesa ✓' },
    sin_contacto:    { c:'var(--text-faint)', bg:'var(--surface-3)', label:'Sin contacto' },
    pagado:          { c:'#15A56A', bg:'#E6F6EE', label:'Pagado ✓' },
    fallido:         { c:'#E03E4C', bg:'#FCE9EA', label:'Fallido' },
    escalado:        { c:'#D97A06', bg:'#FCF1E0', label:'Escalado' },
    agotado:         { c:'var(--text-faint)', bg:'var(--surface-3)', label:'Agotado' },
    pausado:         { c:'#4F46E5', bg:'#EEEDFC', label:'Pausado' },
    disputa:         { c:'#E03E4C', bg:'#FCE9EA', label:'Disputa' },
  };
  const fmtCOP = (n: number) => new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:0}).format(n);
  const fmtDate = (d: string) => d ? new Date(d).toLocaleDateString('es-CO',{day:'2-digit',month:'short',year:'numeric'}) : '—';
  const fmtDur = (s: number) => s < 60 ? s+'s' : Math.floor(s/60)+'m '+(s%60)+'s';

  const totalCartera = deudores.reduce((s,d)=>s+d.monto,0);
  const contactados  = deudores.filter(d=>['contactado','promesa_de_pago','pagado'].includes(d.estado)).length;
  const promesas     = deudores.filter(d=>d.estado==='promesa_de_pago').length;
  const pagados      = deudores.filter(d=>d.estado==='pagado').length;
  const filtrados    = filtro ? deudores.filter(d=>d.estado===filtro) : deudores;

  const FILTROS: [string|null,string][] = [[null,'Todos'],[' pendiente','Pendiente'],['llamando','Llamando'],['contactado','Contactado'],['promesa_de_pago','Promesa'],['pagado','Pagado'],['sin_contacto','Sin contacto'],['escalado','Escalado']];
  const onbSteps = ['Describe tu cartera','Revisa la estrategia IA','Conecta tu cartera'];

  const handleAnalyze = () => {
    setOnbAnalyzing(true);
    setTimeout(() => {
      setStrategy({ tono:'Empático y firme', frecuencia:2, max_intentos:5, guion:{ saludo:'Buenos días {nombre}, le llamo de {empresa} por su obligación vencida de {monto}.', propuesta:'Podemos organizar un plan de pago flexible según su situación.', objeciones:'Entiendo su situación. ¿Cuándo podría hacer un abono inicial?', cierre:'Perfecto, queda registrada su promesa de pago para el {fecha}.' } });
      setOnbStep(1);
      setOnbAnalyzing(false);
    }, 1800);
  };

  const handleLlamar = (deudor: any) => {
    const yaLlamadoHoy = deudor.historial.some((h: any) => {
      const d = new Date(h.fecha); const today = new Date();
      return d.toDateString() === today.toDateString();
    });
    if (yaLlamadoHoy) { setPendingCall(deudor); setLey2300(true); }
    else {
      setDeudores(prev => prev.map((d: any) => d.id===deudor.id ? {...d, estado:'llamando', intentos:d.intentos+1} : d));
      if (selected && selected.id===deudor.id) setSelected((prev: any) => ({...prev, estado:'llamando', intentos:prev.intentos+1}));
    }
  };

  const handlePagar = (id: any) => {
    setDeudores(prev => prev.map((d: any) => d.id===id ? {...d, estado:'pagado'} : d));
    setSelected(null);
  };

  const handlePausar = (id: any) => {
    setDeudores(prev => prev.map((d: any) => d.id===id ? {...d, estado: d.estado==='pausado'?'pendiente':'pausado'} : d));
    if (selected && selected.id===id) setSelected((prev: any) => ({...prev, estado: prev.estado==='pausado'?'pendiente':'pausado'}));
  };

  if (!configured) return (
    <div style={{ padding:'24px 28px', display:'flex', flexDirection:'column', gap:20 }}>
      <div>
        <h1 style={{ fontSize:26, margin:0, marginBottom:6 }}>Cobranza de Voz</h1>
        <p style={{ margin:0, fontSize:14.5, color:'var(--text-muted)' }}>Agente de voz IA que llama a deudores, registra promesas y escala según necesidad.</p>
      </div>
      <div style={{ maxWidth:640 }}>
        <div style={{ display:'flex', gap:0, marginBottom:28 }}>
          {onbSteps.map((label,i) => (
            <div key={i} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:6 }}>
              <div style={{ width:28, height:28, borderRadius:'50%', background: i<onbStep?'var(--green)':i===onbStep?'var(--primary)':'var(--surface-3)', color: i<=onbStep?'#fff':'var(--text-faint)', display:'grid', placeItems:'center', fontWeight:800, fontSize:12, border: i===onbStep?'2px solid var(--primary)':'none', zIndex:1 }}>
                {i<onbStep?<Icon name="check" size={12}/>:i+1}
              </div>
              <div style={{ fontSize:11.5, color: i===onbStep?'var(--ink)':'var(--text-faint)', fontWeight: i===onbStep?700:400, textAlign:'center' }}>{label}</div>
            </div>
          ))}
        </div>

        {onbStep === 0 && (
          <div className="card" style={{ padding:24 }}>
            <h3 style={{ fontSize:17, margin:'0 0 8px', fontWeight:800 }}>Cuéntanos sobre tu cartera</h3>
            <p style={{ fontSize:13.5, color:'var(--text-muted)', margin:'0 0 18px', lineHeight:1.6 }}>La IA generará una estrategia de llamadas personalizada: tono, frecuencia, guión de saludo, objeciones y cierre.</p>
            <textarea placeholder="ej. Tenemos una cartera de seguros vencidos. Los deudores son principalmente personas naturales y pymes con deuda promedio de $3M COP. Queremos un tono empático pero firme..." value={onbDesc} onChange={e=>setOnbDesc(e.target.value)} style={{ width:'100%', minHeight:120, border:'1px solid var(--border-2)', background:'var(--surface-2)', borderRadius:10, padding:'12px 14px', fontFamily:'inherit', fontSize:14, color:'var(--text)', outline:'none', resize:'vertical', boxSizing:'border-box' }}/>
            <button className="btn btn-primary" disabled={!onbDesc.trim()||onbAnalyzing} onClick={handleAnalyze} style={{ marginTop:14, fontFamily:'inherit', opacity:(!onbDesc.trim()||onbAnalyzing)?0.6:1 }}>
              {onbAnalyzing?'Analizando con IA...':'Generar estrategia →'}
            </button>
          </div>
        )}

        {onbStep === 1 && strategy && (
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div className="card" style={{ padding:22 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
                <div style={{ width:36, height:36, borderRadius:10, background:'var(--primary-soft)', color:'var(--primary)', display:'grid', placeItems:'center' }}><Icon name="spark" size={18}/></div>
                <div><div style={{ fontWeight:800, fontSize:16, color:'var(--ink)' }}>Estrategia generada por la Reina</div><div style={{ fontSize:12, color:'var(--text-muted)' }}>Revisa y ajusta antes de aprobar</div></div>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:18 }}>
                {([['Tono',strategy.tono],['Frecuencia',strategy.frecuencia+' días entre llamadas'],['Máx. intentos',strategy.max_intentos],['Canal','Llamada de voz (Vapi + TTS)']] as [string,any][]).map(([k,v])=>(
                  <div key={k} style={{ padding:'12px 14px', background:'var(--surface-2)', borderRadius:10, border:'1px solid var(--border)' }}>
                    <div style={{ fontSize:11, color:'var(--text-faint)', marginBottom:4 }}>{k.toUpperCase()}</div>
                    <div style={{ fontWeight:700, fontSize:13.5, color:'var(--ink)' }}>{v}</div>
                  </div>
                ))}
              </div>
              <div style={{ fontSize:11.5, fontWeight:700, color:'var(--text-faint)', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:10 }}>Guión</div>
              {Object.entries(strategy.guion).map(([k,v]) => (
                <div key={k} style={{ marginBottom:10 }}>
                  <div style={{ fontSize:11.5, color:'var(--primary)', fontWeight:700, marginBottom:4, textTransform:'capitalize' }}>{k}:</div>
                  <div style={{ fontSize:13, color:'var(--text)', background:'var(--surface-2)', padding:'10px 12px', borderRadius:8, border:'1px solid var(--border)', lineHeight:1.55 }}>{v as string}</div>
                </div>
              ))}
            </div>
            <div style={{ display:'flex', gap:10 }}>
              <button className="btn btn-ghost" onClick={()=>setOnbStep(0)} style={{ fontFamily:'inherit' }}>← Modificar descripción</button>
              <button className="btn btn-primary" onClick={()=>setOnbStep(2)} style={{ flex:1, justifyContent:'center', fontFamily:'inherit' }}><Icon name="check" size={15}/> Aprobar estrategia →</button>
            </div>
          </div>
        )}

        {onbStep === 2 && (
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {source === null && (
              <div className="card" style={{ padding:24 }}>
                <h3 style={{ fontSize:17, margin:'0 0 8px', fontWeight:800 }}>Conecta tu cartera</h3>
                <p style={{ fontSize:13.5, color:'var(--text-muted)', margin:'0 0 18px', lineHeight:1.6 }}>Trae a los deudores desde tu sistema de seguros o súbelos con un archivo.</p>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                  <div onClick={()=>setSource('softseguros')} style={{ position:'relative', cursor:'pointer', border:'1.5px solid #1FA89E', background:'rgba(31,168,158,0.06)', borderRadius:14, padding:'20px 18px' }}>
                    <span style={{ position:'absolute', top:12, right:12, fontSize:10, fontWeight:800, letterSpacing:'0.06em', color:'#fff', background:'#1FA89E', borderRadius:999, padding:'3px 9px' }}>RECOMENDADO</span>
                    <div style={{ width:42, height:42, borderRadius:12, background:'#1FA89E', color:'#fff', display:'grid', placeItems:'center', marginBottom:14 }}><Icon name="link" size={21}/></div>
                    <div style={{ fontWeight:800, fontSize:15, color:'var(--ink)' }}>SoftSeguros</div>
                    <div style={{ fontSize:12.5, color:'var(--text-muted)', marginTop:5, lineHeight:1.5 }}>Sincroniza pagos vencidos directo de tus pólizas. Se actualiza solo.</div>
                  </div>
                  <div onClick={()=>setSource('csv')} style={{ cursor:'pointer', border:'1.5px solid var(--border-2)', background:'var(--surface-2)', borderRadius:14, padding:'20px 18px' }}>
                    <div style={{ width:42, height:42, borderRadius:12, background:'var(--surface-3)', color:'var(--text-muted)', display:'grid', placeItems:'center', marginBottom:14 }}><Icon name="arrow" size={21}/></div>
                    <div style={{ fontWeight:800, fontSize:15, color:'var(--ink)' }}>Subir CSV</div>
                    <div style={{ fontSize:12.5, color:'var(--text-muted)', marginTop:5, lineHeight:1.5 }}>Archivo con nombre, teléfono, monto y vencimiento.</div>
                  </div>
                </div>
                <button className="btn btn-ghost" onClick={()=>setOnbStep(1)} style={{ fontFamily:'inherit', marginTop:16 }}>← Atrás</button>
              </div>
            )}

            {source === 'softseguros' && (
              <div>
                <DebtorsSoftSegurosTab />
                <div style={{ display:'flex', gap:10, marginTop:16 }}>
                  <button className="btn btn-ghost" onClick={()=>setSource(null)} style={{ fontFamily:'inherit' }}>← Atrás</button>
                  <button className="btn btn-primary" onClick={()=>{ setActiveTab('softseguros'); setConfigured(true); }} style={{ flex:1, justifyContent:'center', fontFamily:'inherit' }}><Icon name="check" size={15}/> Lanzar agente de cobranza</button>
                </div>
              </div>
            )}

            {source === 'csv' && (
              <div className="card" style={{ padding:24 }}>
                <h3 style={{ fontSize:17, margin:'0 0 8px', fontWeight:800 }}>Sube tu cartera de deudores</h3>
                <p style={{ fontSize:13.5, color:'var(--text-muted)', margin:'0 0 18px', lineHeight:1.6 }}>CSV con columnas: <strong>nombre, telefono, monto, vencimiento</strong>. O puedes agregar deudores manualmente después.</p>
                <div style={{ border:'2px dashed var(--border-2)', borderRadius:12, padding:'32px 24px', textAlign:'center', cursor:'pointer', background:'var(--surface-2)' }}>
                  <Icon name="arrow" size={28} style={{ color:'var(--text-faint)', margin:'0 auto 12px', display:'block' }}/>
                  <div style={{ fontWeight:700, color:'var(--ink)', marginBottom:6 }}>Arrastra tu CSV aquí</div>
                  <div style={{ fontSize:13, color:'var(--text-muted)' }}>o haz clic para seleccionar</div>
                </div>
                <div style={{ display:'flex', gap:10, marginTop:16 }}>
                  <button className="btn btn-ghost" onClick={()=>setSource(null)} style={{ fontFamily:'inherit' }}>← Atrás</button>
                  <button className="btn btn-primary" onClick={()=>setConfigured(true)} style={{ flex:1, justifyContent:'center', fontFamily:'inherit' }}><Icon name="check" size={15}/> Lanzar agente de cobranza</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div style={{ padding:'24px 28px', display:'flex', flexDirection:'column', gap:20 }}>
      <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between' }}>
        <div>
          <h1 style={{ fontSize:26, margin:0, marginBottom:6 }}>Cobranza de Voz</h1>
          <p style={{ margin:0, fontSize:14.5, color:'var(--text-muted)' }}>Agente IA activo · Ley 2300 — máx. 1 contacto por día</p>
        </div>
        {activeTab === 'manual' && (
          <button className="btn btn-primary" onClick={()=>setShowNew(true)} style={{ fontFamily:'inherit' }}><Icon name="plus" size={16}/> Agregar deudor</button>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', gap:4, borderBottom:'1px solid var(--border)', paddingBottom:0, marginBottom:-8 }}>
        {([['manual','Cartera manual'],['softseguros','SoftSeguros']] as ['manual'|'softseguros',string][]).map(([tab,label])=>(
          <button key={tab} onClick={()=>setActiveTab(tab)} style={{ padding:'9px 18px', border:'none', borderBottom: activeTab===tab?'2px solid var(--primary)':'2px solid transparent', background:'transparent', fontFamily:'inherit', fontWeight: activeTab===tab?700:500, fontSize:13.5, color: activeTab===tab?'var(--primary)':'var(--text-muted)', cursor:'pointer', marginBottom:-1 }}>
            {label}
            {tab==='softseguros' && <span style={{ marginLeft:7, fontSize:10, fontWeight:700, color:'#fff', background:'#1FA89E', borderRadius:999, padding:'2px 7px' }}>REAL</span>}
          </button>
        ))}
      </div>

      {/* SoftSeguros tab — componente real con todos los filtros */}
      {activeTab === 'softseguros' && (
        <DebtorsSoftSegurosTab />
      )}

      {/* Manual tab */}
      {activeTab === 'manual' && <>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:14 }}>
        {([{l:'Cartera total',v:fmtCOP(totalCartera),c:'var(--primary)'},{l:'Contactados',v:contactados+'/'+deudores.length,c:'var(--green)'},{l:'Promesas activas',v:promesas,c:'#D97A06'},{l:'Pagados',v:pagados,c:'var(--green)'}] as {l:string,v:any,c:string}[]).map(k=>(
          <div key={k.l} className="card" style={{ padding:'16px 18px' }}>
            <div className="label" style={{ marginBottom:8 }}>{k.l}</div>
            <div style={{ fontSize:k.l==='Cartera total'?18:28, fontWeight:800, color:k.c }}>{k.v}</div>
          </div>
        ))}
      </div>

      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
        {FILTROS.map(([val,label])=>(
          <button key={String(val)} onClick={()=>setFiltro(val===filtro?null:val)} style={{ padding:'6px 14px', borderRadius:999, border:'1px solid var(--border-2)', background: filtro===val?'var(--primary)':'var(--surface-2)', color: filtro===val?'#fff':'var(--text)', fontFamily:'inherit', fontWeight:filtro===val?700:500, fontSize:12.5, cursor:'pointer' }}>
            {label} {val&&<span style={{ opacity:.7 }}>({deudores.filter((d:any)=>d.estado===val.trim()).length})</span>}
          </button>
        ))}
      </div>

      <div className="card" style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <div style={{ display:'grid', gridTemplateColumns:'2fr 1.2fr 1.2fr 1fr 1fr 100px', gap:12, padding:'10px 20px', borderBottom:'1px solid var(--border)', background:'var(--surface-2)' }}>
          {['Deudor','Monto','Vencimiento','Estado','Intentos','Acción'].map(h=><span key={h} className="label" style={{ fontSize:10.5 }}>{h}</span>)}
        </div>
        <div style={{ flex:1, overflowY:'auto' }}>
          {filtrados.length===0 && <div style={{ padding:32, textAlign:'center', color:'var(--text-faint)', fontSize:13.5 }}>No hay deudores en este filtro.</div>}
          {filtrados.map((d: any) => {
            const ec = COB_ESTADO_CFG[d.estado] || COB_ESTADO_CFG.pendiente;
            return (
              <div key={d.id} style={{ display:'grid', gridTemplateColumns:'2fr 1.2fr 1.2fr 1fr 1fr 100px', gap:12, padding:'14px 20px', borderBottom:'1px solid var(--border)', alignItems:'center', cursor:'pointer' }} onClick={()=>setSelected(d)}>
                <div>
                  <div style={{ fontWeight:700, fontSize:13.5, color:'var(--ink)' }}>{d.nombre}</div>
                  <div style={{ fontSize:12, color:'var(--text-faint)', marginTop:2, display:'flex', alignItems:'center', gap:6, flexWrap:'wrap' }}>
                    <span>{d.telefono}</span>
                    {d.fuente==='softseguros' && <>
                      <span style={{ fontSize:10, fontWeight:700, color:'#1FA89E', background:'rgba(31,168,158,0.1)', borderRadius:5, padding:'1px 6px' }}>{d.ramo}</span>
                      <span>· {d.aseguradora} · {d.poliza}</span>
                    </>}
                  </div>
                </div>
                <div style={{ fontWeight:700, fontSize:14, color:'var(--ink)' }}>{fmtCOP(d.monto)}</div>
                <div style={{ fontSize:13, color:'var(--text)' }}>{fmtDate(d.vencimiento)}</div>
                <span style={{ display:'inline-flex', alignItems:'center', gap:5, fontSize:11.5, fontWeight:700, color:ec.c, background:ec.bg, borderRadius:999, padding:'3px 10px', width:'fit-content' }}>
                  {ec.pulse && <div style={{ width:6, height:6, borderRadius:'50%', background:ec.c, animation:'landa-pulse 1.6s infinite', flexShrink:0 }}/>}
                  {ec.label}
                </span>
                <div style={{ fontSize:13, color:'var(--text-muted)' }}>{d.intentos}/{d.max_intentos}</div>
                <button className="btn btn-soft" style={{ fontSize:12, padding:'6px 10px', fontFamily:'inherit' }} onClick={(e)=>{e.stopPropagation();handleLlamar(d);}}>
                  <Icon name="phone" size={13}/> Llamar
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {selected && (
        <>
          <div style={{ position:'fixed', inset:0, background:'rgba(16,16,29,.5)', zIndex:9, backdropFilter:'blur(4px)' }} onClick={()=>setSelected(null)}/>
          <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', width:'90%', maxWidth:780, maxHeight:'90vh', background:'var(--surface)', borderRadius:'var(--r-xl)', zIndex:10, boxShadow:'0 20px 60px rgba(0,0,0,.3)', overflow:'hidden', display:'flex', flexDirection:'column' }}>
            <div style={{ padding:'22px 24px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'flex-start', justifyContent:'space-between', flexShrink:0 }}>
              <div>
                <h2 style={{ fontSize:20, margin:0, fontWeight:800 }}>{selected.nombre}</h2>
                <div style={{ fontSize:13, color:'var(--text-muted)', marginTop:6 }}>{selected.telefono} · {selected.intentos}/{selected.max_intentos} intentos</div>
              </div>
              <div style={{ display:'flex', gap:10, alignItems:'center' }}>
                <div style={{ textAlign:'right' }}>
                  <div className="label">Monto</div>
                  <div style={{ fontSize:22, fontWeight:800, color:(COB_ESTADO_CFG[selected.estado]||{}).c||'var(--ink)' }}>{fmtCOP(selected.monto)}</div>
                </div>
                <button className="btn btn-primary" style={{ fontFamily:'inherit' }} onClick={()=>handleLlamar(selected)}><Icon name="phone" size={14}/> Llamar</button>
                <button className="btn btn-icon btn-ghost" onClick={()=>setSelected(null)}><Icon name="x" size={20}/></button>
              </div>
            </div>
            <div style={{ flex:1, display:'grid', gridTemplateColumns:'260px 1fr', overflow:'hidden' }}>
              <div style={{ borderRight:'1px solid var(--border)', overflowY:'auto', padding:'20px 20px', display:'flex', flexDirection:'column', gap:18 }}>
                {selected.fuente==='softseguros' && (
                  <div style={{ padding:'14px', background:'rgba(31,168,158,0.07)', border:'1px solid rgba(31,168,158,0.25)', borderRadius:10 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:11 }}>
                      <span style={{ color:'#1FA89E', display:'inline-flex' }}><Icon name="link" size={14}/></span>
                      <span className="label" style={{ color:'#1FA89E' }}>Póliza · SoftSeguros</span>
                    </div>
                    <div style={{ display:'flex', flexDirection:'column', gap:9 }}>
                      {([['Nº póliza',selected.poliza],['Ramo',selected.ramo],['Aseguradora',selected.aseguradora],['Documento',selected.documento]] as [string,string][]).map(([k,v])=>(
                        <div key={k} style={{ display:'flex', justifyContent:'space-between', gap:10, alignItems:'baseline' }}>
                          <span style={{ fontSize:12, color:'var(--text-faint)', flexShrink:0 }}>{k}</span>
                          <span style={{ fontSize:12.5, fontWeight:700, color:'var(--ink)', textAlign:'right' }}>{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {selected.monto_prometido && (
                  <div style={{ padding:'14px', background:'var(--green-soft)', borderLeft:'3px solid var(--green)', borderRadius:'0 8px 8px 0' }}>
                    <div className="label" style={{ color:'var(--green)', marginBottom:8 }}>Promesa de pago</div>
                    <div style={{ fontWeight:800, fontSize:18, color:'var(--green)' }}>{fmtCOP(selected.monto_prometido)}</div>
                    {selected.fecha_promesa && <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:4 }}>{fmtDate(selected.fecha_promesa)}</div>}
                  </div>
                )}
                <div>
                  <div className="label" style={{ marginBottom:12 }}>Historial de llamadas</div>
                  {selected.historial.length===0 ? <div style={{ fontSize:12, color:'var(--text-faint)', fontStyle:'italic' }}>Sin llamadas registradas</div> : (
                    <div style={{ position:'relative', paddingLeft:18 }}>
                      <div style={{ position:'absolute', left:7, top:0, bottom:0, width:1, background:'var(--border)' }}/>
                      {selected.historial.map((h: any,i: number)=>(
                        <div key={i} style={{ position:'relative', marginBottom:14 }}>
                          <div style={{ position:'absolute', left:-14, top:3, width:8, height:8, borderRadius:'50%', background:'var(--surface-3)', border:'1px solid var(--border-2)' }}/>
                          <div style={{ fontSize:12, fontWeight:700, color:'var(--ink)' }}>{fmtDate(h.fecha)}</div>
                          <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:2 }}>{h.resultado} · {fmtDur(h.duracion)}</div>
                          {h.resumen && <div style={{ fontSize:12, color:'var(--text)', marginTop:4, lineHeight:1.4, background:'var(--surface-2)', padding:'8px 10px', borderRadius:8, borderLeft:'2px solid var(--primary)' }}>{h.resumen}</div>}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {selected.notas && (
                  <div>
                    <div className="label" style={{ marginBottom:6 }}>Notas</div>
                    <div style={{ fontSize:13, color:'var(--text)', lineHeight:1.5, background:'var(--surface-2)', padding:'10px 12px', borderRadius:8 }}>{selected.notas}</div>
                  </div>
                )}
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginTop:'auto' }}>
                  {([{l:'Marcar pagado',fn:()=>handlePagar(selected.id),c:'var(--green)'},{l:selected.estado==='pausado'?'Reactivar':'Pausar',fn:()=>handlePausar(selected.id),c:'#4F46E5'}] as {l:string,fn:()=>void,c:string}[]).map(({l,fn,c})=>(
                    <button key={l} onClick={fn} style={{ padding:'9px 8px', border:'1px solid var(--border-2)', background:'transparent', cursor:'pointer', fontFamily:'inherit', fontWeight:700, fontSize:11.5, color:c, borderRadius:8 }}>{l}</button>
                  ))}
                </div>
              </div>
              <div style={{ overflowY:'auto', padding:'20px 24px' }}>
                <div className="label" style={{ marginBottom:14, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>Transcripción última llamada</div>
                {selected.historial.length===0 ? (
                  <div style={{ textAlign:'center', padding:'40px 0', color:'var(--text-faint)', fontSize:13 }}>Sin llamadas registradas aún.</div>
                ) : (() => {
                  const last = selected.historial[selected.historial.length-1];
                  return (
                    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
                      <div style={{ padding:'10px 14px', background:'var(--surface-2)', borderLeft:'2px solid var(--primary)', borderRadius:'0 8px 8px 0', display:'flex', justifyContent:'space-between' }}>
                        <span style={{ fontSize:12, color:'var(--ink)', fontWeight:700 }}>Última: {fmtDate(last.fecha)}</span>
                        <span style={{ fontSize:12, color:'var(--text-muted)' }}>{fmtDur(last.duracion)} · {last.resultado}</span>
                      </div>
                      {last.resumen ? (
                        <div style={{ padding:'14px 16px', background:'var(--surface-2)', borderRadius:10, fontSize:13, color:'var(--text)', lineHeight:1.6, borderLeft:'3px solid #4F46E5' }}>
                          <div className="label" style={{ marginBottom:8 }}>Resumen IA</div>
                          {last.resumen}
                        </div>
                      ) : (
                        <div style={{ padding:'14px 16px', background:'var(--surface-2)', borderRadius:10, fontSize:13, color:'var(--text-muted)', fontStyle:'italic' }}>
                          {last.resultado==='no-answer'?'El deudor no contestó la llamada.':last.resultado==='voicemail'?'Llamada al buzón de voz.':'Llamada finalizada: '+last.resultado}
                        </div>
                      )}
                      {last.resumen && (
                        <div style={{ display:'flex', flexDirection:'column', gap:10, marginTop:4 }}>
                          {([{role:'agent',text:'Buenos días, le llamo de parte de DPG Seguros por su obligación vencida.'},{role:'debtor',text:'Sí, estaba esperando esta llamada.'},{role:'agent',text:'Entendemos su situación. ¿Podemos acordar un plan de pago?'},{role:'debtor',text:'Sí, puedo hacer un abono el lunes.'}] as {role:string,text:string}[]).map((line,i)=>(
                            <div key={i} style={{ display:'flex', gap:10, justifyContent:line.role==='agent'?'flex-start':'flex-end' }}>
                              {line.role==='agent' && <div style={{ width:28, height:28, borderRadius:8, background:'var(--primary-soft)', color:'var(--primary)', display:'grid', placeItems:'center', fontSize:12, flexShrink:0 }}>🤖</div>}
                              <div style={{ maxWidth:'72%', padding:'10px 14px', borderRadius:12, background:line.role==='agent'?'var(--surface-2)':'var(--primary)', color:line.role==='agent'?'var(--text)':'#fff', fontSize:13, lineHeight:1.45 }}>{line.text}</div>
                              {line.role==='debtor' && <div style={{ width:28, height:28, borderRadius:8, background:'var(--surface-3)', color:'var(--text-muted)', display:'grid', placeItems:'center', fontSize:14, flexShrink:0 }}>👤</div>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          </div>
        </>
      )}

      {ley2300 && pendingCall && (
        <>
          <div style={{ position:'fixed', inset:0, background:'rgba(16,16,29,.6)', zIndex:20, backdropFilter:'blur(4px)' }}/>
          <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', width:'90%', maxWidth:440, background:'var(--surface)', borderRadius:16, zIndex:21, padding:28, border:'2px solid #D97A06', boxShadow:'0 20px 60px rgba(0,0,0,.3)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14 }}>
              <span style={{ fontSize:26 }}>⚠️</span>
              <span style={{ fontWeight:800, fontSize:16, color:'#D97A06' }}>Ley 2300 — Contacto duplicado</span>
            </div>
            <p style={{ fontSize:13.5, color:'var(--text)', lineHeight:1.6, margin:'0 0 8px' }}>Este deudor <strong>ya fue contactado hoy</strong>. Volver a llamar puede constituir una infracción a la <strong>Ley 2300 de 2023</strong> (máx. 1 contacto por día).</p>
            <p style={{ fontSize:12.5, color:'var(--text-muted)', lineHeight:1.5, margin:'0 0 22px' }}>Si decides continuar, la responsabilidad del contacto adicional recae sobre el operador.</p>
            <div style={{ display:'flex', gap:10, justifyContent:'flex-end' }}>
              <button className="btn btn-ghost" style={{ fontFamily:'inherit' }} onClick={()=>{setLey2300(false);setPendingCall(null);}}>Cancelar</button>
              <button style={{ padding:'9px 18px', border:'1px solid #D97A06', background:'#FCF1E0', color:'#D97A06', fontFamily:'inherit', fontWeight:700, fontSize:12.5, cursor:'pointer', borderRadius:9 }} onClick={()=>{
                setDeudores(prev=>prev.map((d:any)=>d.id===pendingCall.id?{...d,estado:'llamando',intentos:d.intentos+1}:d));
                if(selected&&selected.id===pendingCall.id) setSelected((prev:any)=>({...prev,estado:'llamando',intentos:prev.intentos+1}));
                setLey2300(false); setPendingCall(null);
              }}>Llamar de todos modos</button>
            </div>
          </div>
        </>
      )}

      {showNew && (
        <>
          <div style={{ position:'fixed', inset:0, background:'rgba(16,16,29,.5)', zIndex:9, backdropFilter:'blur(4px)' }} onClick={()=>setShowNew(false)}/>
          <div style={{ position:'fixed', top:'50%', left:'50%', transform:'translate(-50%,-50%)', width:'90%', maxWidth:460, background:'var(--surface)', borderRadius:16, zIndex:10, padding:28, boxShadow:'0 20px 60px rgba(0,0,0,.25)' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
              <h3 style={{ fontSize:17, margin:0, fontWeight:800 }}>Agregar deudor</h3>
              <button className="btn btn-icon btn-ghost" onClick={()=>setShowNew(false)}><Icon name="x" size={20}/></button>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
              {([{k:'nombre',label:'Nombre completo',ph:'Carlos Ramírez'},{k:'telefono',label:'Teléfono',ph:'+57 300 123 4567'},{k:'monto',label:'Monto (COP)',ph:'2500000'},{k:'vencimiento',label:'Vencimiento',ph:'2025-04-01'}] as {k:string,label:string,ph:string}[]).map(({k,label,ph})=>(
                <div key={k}>
                  <div className="label" style={{ marginBottom:5 }}>{label}</div>
                  <input type={k==='monto'?'number':'text'} placeholder={ph} value={(newForm as any)[k]} onChange={e=>setNewForm(p=>({...p,[k]:e.target.value}))} style={{ width:'100%', border:'1px solid var(--border-2)', background:'var(--surface-2)', borderRadius:9, padding:'10px 12px', fontFamily:'inherit', fontSize:13.5, color:'var(--text)', outline:'none', boxSizing:'border-box' as any }}/>
                </div>
              ))}
              <button className="btn btn-primary" style={{ marginTop:4, justifyContent:'center', fontFamily:'inherit' }} onClick={()=>{
                if (!newForm.nombre||!newForm.telefono||!newForm.monto||!newForm.vencimiento) return;
                setDeudores(prev=>[...prev,{id:Date.now(),nombre:newForm.nombre,telefono:newForm.telefono,monto:Number(newForm.monto),vencimiento:newForm.vencimiento,estado:'pendiente',intentos:0,max_intentos:5,historial:[]}]);
                setNewForm({nombre:'',telefono:'',monto:'',vencimiento:''});
                setShowNew(false);
              }}>Agregar deudor</button>
            </div>
          </div>
        </>
      )}
      </>}
    </div>
  );
}

// ============ SIDEBAR ============
function Sidebar({ view, setView, user, onLogout }: any) {
  const nav = [
    ['inicio', 'home', 'Inicio'],
    ['campanas', 'rocket', 'Campañas'],
    ['resultados', 'list', 'Resultados'],
    ['aprobados', 'check', 'Aprobados'],
    ['chat', 'chat', 'Chat'],
    ['aprendizaje', 'spark', 'Aprendizaje'],
    ['ajustes', 'gear', 'Ajustes'],
  ];

  const [quota, setQuota] = useState<any>(null);
  const [cobranzaEnabled, setCobranzaEnabled] = useState(false);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const q = await api.getQuota();
        if (alive) setQuota(q);
      } catch (e) {
        console.warn('Quota load failed:', e);
      }
      try {
        const s = await api.getCobranzaStatus();
        if (alive) setCobranzaEnabled(!!s.enabled);
      } catch (e) {
        console.warn('Cobranza status load failed:', e);
      }
    })();
    return () => { alive = false; };
  }, []);

  const navItems = cobranzaEnabled ? [...nav, ['cobranza', 'phone', 'Cobranza']] : nav;

  const emailName = (user?.email || '').split('@')[0].replace(/[._-]/g, ' ').trim();
  const userName = emailName || 'Mi cuenta';
  const userInitials = (emailName ? emailName.split(' ').filter(Boolean).slice(0, 2).map((s: string) => s[0]).join('') : 'U').toUpperCase();

  const usagePct = Math.round(quota?.usage_percent ?? 0);
  const planLabel = quota?.plan ? `Plan ${String(quota.plan).charAt(0).toUpperCase() + String(quota.plan).slice(1)}` : 'Plan';
  const fmt = (n: number) => (n ?? 0).toLocaleString('es-CO');

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
        {navItems.map(([key, ic, label]) => (
          <div key={key} onClick={() => setView(key)} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 12px', borderRadius: 10, color: view === key ? 'var(--primary-700)' : 'var(--text-muted)', fontWeight: view === key ? 700 : 600, fontSize: 14, cursor: 'pointer', background: view === key ? 'var(--primary-soft)' : 'transparent', transition: 'all .12s' }}>
            <span style={{ display: 'flex' }}><Icon name={ic} size={19} /></span>
            <span>{label}</span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 14, padding: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span className="label">{planLabel}</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)' }}>{usagePct}%</span>
          </div>
          <div style={{ height: 7, background: '#E9E9F1', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: usagePct + '%', height: '100%', background: 'var(--primary)', borderRadius: 999 }} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 8 }}>
            {quota ? `${fmt(quota.credits_remaining)} / ${fmt(quota.credits_total)} créditos` : 'Cargando créditos…'}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 8, borderRadius: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 10, background: 'linear-gradient(135deg,#F59E0B,#EF6C5A)', display: 'grid', placeItems: 'center', color: '#fff', fontWeight: 800, fontSize: 14, flex: 'none' }}>{userInitials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--ink)', textTransform: 'capitalize' }}>{userName}{user?.role === 'staff' && <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--primary)', marginLeft: 6, textTransform: 'uppercase' }}>staff</span>}</div>
            <div style={{ fontSize: 11.5, color: 'var(--text-faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{user?.email || '—'}</div>
          </div>
          <button onClick={onLogout} title="Cerrar sesión" style={{ display: 'flex', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', padding: 4 }}><Icon name="arrow" size={16} /></button>
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
// ============ ONBOARDING (wizard real: describe → propuesta) ============
function OnbStepIndicator({ step, total }: any) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'center' }}>
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} style={{ width: i <= step ? 32 : 8, height: 8, borderRadius: 999, background: i <= step ? 'var(--primary)' : 'var(--border-2)', transition: 'all .3s ease' }} />
      ))}
    </div>
  );
}

function ViewOnboarding({ onComplete, onSkip }: any) {
  const [step, setStep] = useState(0);
  const [product, setProduct] = useState('');
  const [icp, setIcp] = useState('');
  const [progress, setProgress] = useState(0);
  const [proposal, setProposal] = useState<any>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const input: React.CSSProperties = { width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px', fontFamily: 'inherit', fontSize: 14.5, color: 'var(--text)', outline: 'none', minHeight: 90, resize: 'vertical', lineHeight: 1.5 };

  // Paso 2 → guarda knowledge y arranca el análisis real.
  const startAnalysis = async () => {
    setBusy(true);
    try {
      await api.saveKnowledge({ product_description: product, icp_summary: icp }).catch(() => {});
    } finally {
      setBusy(false);
    }
    setStep(2);
    runAnalysis();
  };

  // Paso 3 → llama /api/chat/prospect (que extrae y guarda la campaña real).
  const runAnalysis = async () => {
    setProgress(0);
    setAnalyzeError(null);
    const timer = setInterval(() => setProgress((p) => (p < 90 ? p + Math.random() * 18 : p)), 500);
    try {
      const msg = `Mi empresa: ${product || 'servicios B2B'}. Cliente ideal: ${icp || 'empresas medianas en Colombia'}. Arma una campaña de prospección.`;
      const res = await api.sendChatMessage(msg);
      clearInterval(timer);
      setProgress(100);
      if (res.status === 'extracted' && res.campaign) {
        setProposal(res.campaign);
      } else {
        setAnalyzeError(res.reply || 'No pudimos proponer una campaña automáticamente. Puedes crearla manualmente.');
      }
      setTimeout(() => setStep(3), 600);
    } catch (e: any) {
      clearInterval(timer);
      setProgress(100);
      setAnalyzeError(e.message || 'Error analizando');
      setTimeout(() => setStep(3), 400);
    }
  };

  const Chip = ({ children, primary }: any) => (
    <span className="chip" style={{ background: primary ? 'var(--primary-soft)' : 'var(--surface-2)', color: primary ? 'var(--primary-700)' : 'var(--text)', border: '1px solid var(--border)' }}>{children}</span>
  );

  const asArray = (v: any) => Array.isArray(v) ? v : (v ? [v] : []);

  return (
    <div className="lc" style={{ minHeight: '100vh', height: '100vh', overflow: 'auto', background: 'linear-gradient(135deg, var(--primary-softer) 0%, var(--surface) 100%)', padding: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      <div style={{ width: '100%', maxWidth: 540, display: 'flex', flexDirection: 'column', gap: 28 }}>
        <OnbStepIndicator step={step} total={5} />
        <div className="card" style={{ padding: 36 }}>

          {step === 0 && (
            <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20 }}>
              <div style={{ width: 64, height: 64, borderRadius: 18, background: 'linear-gradient(135deg, var(--primary), #7C74F0)', display: 'grid', placeItems: 'center', boxShadow: '0 8px 24px -8px rgba(79,70,229,.5)' }}>
                <div style={{ width: 22, height: 22, borderRadius: 6, background: '#fff' }} />
              </div>
              <div>
                <h1 style={{ fontSize: 28, margin: '0 0 10px' }}>Bienvenido a Landa</h1>
                <p style={{ margin: 0, fontSize: 15.5, color: 'var(--text-muted)', maxWidth: 460, lineHeight: 1.6 }}>Cuéntanos sobre tu empresa y Landa propondrá a quién buscar. Toma 1 minuto.</p>
              </div>
              <button className="btn btn-primary" style={{ marginTop: 8, paddingLeft: 28, paddingRight: 28 }} onClick={() => setStep(1)}>Empezar <Icon name="arrow" size={16} /></button>
              <button onClick={onSkip} style={{ background: 'none', border: 'none', color: 'var(--text-faint)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>Saltar por ahora</button>
            </div>
          )}

          {step === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <h2 style={{ fontSize: 23, margin: '0 0 6px' }}>Cuéntanos de tu empresa</h2>
                <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Con esto entendemos tu modelo y tu cliente ideal.</p>
              </div>
              <div>
                <label className="label" style={{ display: 'block', marginBottom: 6 }}>¿Qué vende tu empresa?</label>
                <textarea style={input} placeholder="Ej: Pólizas de seguros corporativos para flotas y plantas industriales…" value={product} onChange={(e) => setProduct(e.target.value)} />
              </div>
              <div>
                <label className="label" style={{ display: 'block', marginBottom: 6 }}>¿Quién es tu cliente ideal?</label>
                <textarea style={input} placeholder="Ej: Empresas de logística e industria con 100–500 empleados en Bogotá y Medellín…" value={icp} onChange={(e) => setIcp(e.target.value)} />
              </div>
              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={busy || product.trim().length < 5} onClick={startAnalysis}>{busy ? 'Guardando…' : 'Analizar'} <Icon name="arrow" size={16} /></button>
            </div>
          )}

          {step === 2 && (
            <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 26 }}>
              <div>
                <h2 style={{ fontSize: 23, margin: '0 0 6px' }}>Landa está analizando</h2>
                <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Esto toma solo un momento.</p>
              </div>
              <div style={{ width: 180, height: 180, position: 'relative', display: 'grid', placeItems: 'center' }}>
                <svg width="180" height="180" style={{ position: 'absolute', transform: 'rotate(-90deg)' }}>
                  <circle cx="90" cy="90" r="80" fill="none" stroke="var(--border-2)" strokeWidth="8" />
                  <circle cx="90" cy="90" r="80" fill="none" stroke="var(--primary)" strokeWidth="8" strokeDasharray={`${502 * progress / 100} 502`} strokeLinecap="round" style={{ transition: 'stroke-dasharray .3s ease' }} />
                </svg>
                <div className="num" style={{ fontSize: 34, fontWeight: 800, color: 'var(--primary)' }}>{Math.round(progress)}%</div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div>
                <h2 style={{ fontSize: 23, margin: '0 0 6px' }}>Tu campaña propuesta</h2>
                <p style={{ margin: 0, fontSize: 14.5, color: 'var(--text-muted)' }}>Basado en lo que nos contaste.</p>
              </div>
              {analyzeError && !proposal && (
                <div style={{ padding: '11px 14px', borderRadius: 10, background: 'var(--amber-soft)', color: 'var(--amber)', fontSize: 13.5 }}>{analyzeError}</div>
              )}
              {proposal && (
                <div className="card" style={{ padding: 22 }}>
                  {proposal.industria_objetivo && (<>
                    <div className="label" style={{ marginBottom: 10 }}>Industria objetivo</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9, marginBottom: 16 }}>{asArray(proposal.industria_objetivo).map((s: string) => <Chip key={s} primary>{s}</Chip>)}</div>
                  </>)}
                  {proposal.ciudad_objetivo && (<>
                    <div className="label" style={{ marginBottom: 10 }}>Ciudades</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9, marginBottom: 16 }}>{asArray(proposal.ciudad_objetivo).map((c: string) => <Chip key={c}>{c}</Chip>)}</div>
                  </>)}
                  {proposal.dolor_operativo && (<>
                    <div className="label" style={{ marginBottom: 8 }}>Dolor que resolvemos</div>
                    <p style={{ margin: '0 0 16px', fontSize: 13.5, color: 'var(--text)', lineHeight: 1.5 }}>{proposal.dolor_operativo}</p>
                  </>)}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9 }}>
                    {asArray(proposal.signal_sources).map((s: string) => <Chip key={s}>{s}</Chip>)}
                    {proposal.max_results && <Chip>{proposal.max_results} leads/corrida</Chip>}
                  </div>
                </div>
              )}
              <div className="card" style={{ padding: 14, background: 'var(--primary-softer)', border: '1px solid var(--primary-soft)' }}>
                <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start' }}>
                  <Icon name="spark" size={18} />
                  <div style={{ fontSize: 13.5, color: 'var(--text)', lineHeight: 1.5 }}><strong>Consejo:</strong> tus agentes aprenderán de los leads que apruebes y refinarán la búsqueda automáticamente.</div>
                </div>
              </div>
              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setStep(4)}><Icon name="rocket" size={16} /> {proposal ? 'Ver mi campaña' : 'Ir a campañas'}</button>
            </div>
          )}

          {step === 4 && (
            <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20 }}>
              <div style={{ width: 70, height: 70, borderRadius: '50%', background: 'var(--green)', display: 'grid', placeItems: 'center', boxShadow: '0 12px 32px -8px rgba(21,165,106,.4)' }}>
                <Icon name="check" size={34} stroke={2.5} />
              </div>
              <div>
                <h1 style={{ fontSize: 26, margin: '0 0 6px' }}>{proposal ? '¡Campaña creada!' : '¡Todo listo!'}</h1>
                <p style={{ margin: 0, fontSize: 15, color: 'var(--text-muted)', lineHeight: 1.6 }}>{proposal ? 'La encuentras en Campañas, lista para lanzar.' : 'Ya puedes crear tu primera campaña.'}</p>
              </div>
              <button className="btn btn-primary" onClick={onComplete}>Abrir panel <Icon name="arrow" size={16} /></button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

// ============ RUN STATUS BANNER ============
// Da visibilidad en vivo del run de prospección: en cola → corriendo → completado/error,
// con conteos y el motivo cuando termina con 0 leads.
function RunStatusBanner({ run, onClose, onViewLeads }: any) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    if (!run?.runId) return;
    let alive = true;
    let timer: any;
    const poll = async () => {
      try {
        const d = await api.getRunStatus(run.runId);
        if (!alive) return;
        setData(d);
        const st = d.status;
        if (st === 'complete' || st === 'error') return; // detener
      } catch { /* reintenta */ }
      if (alive) timer = setTimeout(poll, 3000);
    };
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [run?.runId]);

  if (!run?.runId) return null;

  const status = data?.status || 'queued';
  const leadCount = (data?.leads || []).length;
  const analyzed = data?.total_analyzed ?? 0;
  const running = status === 'queued' || status === 'running';

  let tone = 'var(--primary)', soft = 'var(--primary-soft)', text = '', icon = 'clock';
  if (status === 'queued') text = 'En cola… esperando al worker';
  else if (status === 'running') text = `Buscando y analizando empresas…${analyzed ? ` ${analyzed} encontradas` : ''}`;
  else if (status === 'complete') {
    if (leadCount > 0) { tone = 'var(--green)'; soft = 'var(--green-soft)'; icon = 'check'; text = `✓ ${leadCount} lead${leadCount === 1 ? '' : 's'} listo${leadCount === 1 ? '' : 's'} para revisar`; }
    else { tone = 'var(--amber)'; soft = 'var(--amber-soft)'; icon = 'bell'; text = `Se encontraron empresas pero ninguna pasó el análisis (0 leads). Causa típica: scraping bloqueado / proxy no configurado.`; }
  } else if (status === 'error') { tone = 'var(--red)'; soft = 'var(--red-soft)'; icon = 'x'; text = 'El run falló. Revisa los logs del worker.'; }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px', margin: '12px 28px 0', borderRadius: 12, background: soft, border: `1px solid ${tone}33` }}>
      {running
        ? <span style={{ width: 16, height: 16, border: `2px solid ${tone}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'lc-spin 0.7s linear infinite', flex: 'none' }} />
        : <span style={{ color: tone, display: 'flex', flex: 'none' }}><Icon name={icon} size={18} /></span>}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 700, color: tone }}>{run.campaignName || 'Campaña'}</div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{text}</div>
      </div>
      {status === 'complete' && leadCount > 0 && (
        <button className="btn btn-soft" style={{ flex: 'none' }} onClick={() => onViewLeads(run.campaignId)}>Ver leads</button>
      )}
      {!running && (
        <button onClick={onClose} title="Cerrar" style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-faint)', display: 'flex', flex: 'none' }}><Icon name="x" size={16} /></button>
      )}
    </div>
  );
}

// ============ LOGIN ============
function Login({ onLogin }: { onLogin: (u: api.AuthUser) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const doLogin = async () => {
    if (!email || !password) { setError('Ingresa email y contraseña'); return; }
    setBusy(true); setError(null);
    try { onLogin(await api.login(email, password)); }
    catch (e: any) { setError(e.message || 'No se pudo iniciar sesión'); }
    finally { setBusy(false); }
  };

  const doDemo = async () => {
    setBusy(true); setError(null);
    try { onLogin(await api.initAuth()); }
    catch (e: any) { setError(e.message || 'No se pudo entrar como demo'); }
    finally { setBusy(false); }
  };

  const input: React.CSSProperties = { width: '100%', border: '1px solid var(--border-2)', background: 'var(--surface-2)', borderRadius: 10, padding: '12px 14px', fontFamily: 'inherit', fontSize: 14.5, color: 'var(--text)', outline: 'none' };

  return (
    <div className="lc" style={{ display: 'grid', placeItems: 'center', height: '100vh', background: 'var(--bg)', fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      <div style={{ width: 380, maxWidth: '90%', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'center', marginBottom: 4 }}>
          <div style={{ width: 40, height: 40, borderRadius: 11, background: 'linear-gradient(135deg, var(--primary), #7C74F0)', display: 'grid', placeItems: 'center', boxShadow: '0 6px 16px -6px rgba(79,70,229,.6)' }}>
            <div style={{ width: 15, height: 15, borderRadius: 5, background: '#fff' }} />
          </div>
          <div style={{ fontWeight: 800, fontSize: 22, color: 'var(--ink)', letterSpacing: '-0.02em' }}>Landa</div>
        </div>
        <div className="card" style={{ padding: 28, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <h1 style={{ fontSize: 21, margin: 0 }}>Inicia sesión</h1>
            <p style={{ margin: '6px 0 0', fontSize: 13.5, color: 'var(--text-muted)' }}>Accede a tu panel de prospección.</p>
          </div>
          {error && <div style={{ padding: '9px 12px', borderRadius: 8, background: 'var(--red-soft)', color: 'var(--red)', fontSize: 13, fontWeight: 600 }}>{error}</div>}
          <input style={input} type="email" placeholder="tu@correo.com" value={email} disabled={busy} autoFocus onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doLogin()} />
          <input style={input} type="password" placeholder="Contraseña" value={password} disabled={busy} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doLogin()} />
          <button className="btn btn-primary" disabled={busy} style={{ width: '100%', justifyContent: 'center', fontFamily: 'inherit', marginTop: 2 }} onClick={doLogin}>{busy ? 'Entrando…' : 'Entrar'}</button>
          <button className="btn btn-ghost" disabled={busy} style={{ width: '100%', justifyContent: 'center', fontFamily: 'inherit' }} onClick={doDemo}>Entrar como demo</button>
        </div>
      </div>
    </div>
  );
}

export function App() {
  const [user, setUser] = useState<api.AuthUser | null>(() => {
    const hasToken = api.loadToken();
    const cached = api.getCachedUser();
    if (cached) return cached;
    if (hasToken) return { email: '', role: 'client' };
    return null;
  });
  const [view, setView] = useState('inicio');
  const [campaignId, setCampaignId] = useState<string | null>(() => localStorage.getItem('landa_campaignId'));
  const [showWizard, setShowWizard] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [activeRun, setActiveRun] = useState<any>(null);

  const handleLogout = () => { api.logout(); setUser(null); setView('inicio'); setShowOnboarding(false); localStorage.removeItem('landa_campaignId'); };

  // Persiste campaignId en localStorage para que sobreviva a reloads
  useEffect(() => {
    if (campaignId) localStorage.setItem('landa_campaignId', campaignId);
    else localStorage.removeItem('landa_campaignId');
  }, [campaignId]);

  // Si cualquier llamada recibe 401 (token expirado), volver al login.
  useEffect(() => {
    const onUnauth = () => { setUser(null); setView('inicio'); setShowOnboarding(false); };
    window.addEventListener('landa:unauthorized', onUnauth);
    return () => window.removeEventListener('landa:unauthorized', onUnauth);
  }, []);

  const finishOnboarding = (goToCampaigns: boolean) => {
    localStorage.setItem('landa_onboarded', '1');
    setShowOnboarding(false);
    if (goToCampaigns) setView('campanas');
  };

  // Onboarding de primera vez: usuario autenticado, sin flag y sin campañas.
  useEffect(() => {
    if (!user) return;
    if (localStorage.getItem('landa_onboarded')) return;
    let alive = true;
    api.getCampaigns(1, 0).then((d: any) => {
      if (!alive) return;
      const count = (d?.campaigns || []).length;
      if (count === 0) setShowOnboarding(true);
      else localStorage.setItem('landa_onboarded', '1');
    }).catch(() => {});
    return () => { alive = false; };
  }, [user]);

  // Prefetch campaign data when campaignId changes (anticipate Inicio/Aprobados views)
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!campaignId || !api.getToken()) return;
    // Prefetch KPIs, Leads, and Runs for the selected campaign
    queryClient.prefetchQuery({ queryKey: ['kpis', campaignId], queryFn: () => api.getKPIs(campaignId) });
    queryClient.prefetchQuery({ queryKey: ['leads', campaignId], queryFn: () => api.getLeads(campaignId) });
    queryClient.prefetchQuery({ queryKey: ['runs', campaignId], queryFn: () => api.getCampaignRuns(campaignId) });
  }, [campaignId, queryClient]);

  // Tras volver del OAuth de email (?oauth_success=...), abre Ajustes para mostrar el resultado.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('oauth_success')) {
      setView('ajustes');
    }
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

  // Load email status once at app level (shared by Aprobados, Campanas, etc.)
  // Must be called unconditionally before any early returns.
  const { data: emailData } = useQuery({
    queryKey: ['emailStatus'],
    queryFn: () => api.getEmailStatus(),
    staleTime: 120000, // 2 min
    enabled: !!user,
  });

  if (!user) return <Login onLogin={(u) => { setUser(u); setView('inicio'); }} />;
  if (showOnboarding) return <ViewOnboarding onComplete={() => finishOnboarding(true)} onSkip={() => finishOnboarding(false)} />;

  return (
    <EmailStatusContext.Provider value={{ connected: emailData?.connected ?? false }}>
      <div className="lc" style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: 'var(--bg)', fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif" }}>
        <Sidebar view={view} setView={setView} user={user} onLogout={handleLogout} />
        <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Topbar onLaunch={() => { setView('campanas'); setShowWizard(true); }} />
          {activeRun && <RunStatusBanner run={activeRun} onClose={() => setActiveRun(null)} onViewLeads={(cid: string) => { setCampaignId(cid); setActiveRun(null); setView('aprobados'); }} />}
          <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)' }}>
            {view === 'inicio' && <ViewInicio campaignId={campaignId} onNavigate={setView} />}
            {view === 'aprobados' && <ViewAprobados campaignId={campaignId} onNavigate={setView} />}
            {view === 'resultados' && <ViewResultados campaignId={campaignId} />}
            {view === 'campanas' && <ViewCampanas showWizard={showWizard} setShowWizard={setShowWizard} onLaunched={(r: any) => setActiveRun(r)} onSelectCampaign={(id: string) => { setCampaignId(id); setView('aprobados'); }} />}
            {view === 'chat' && <ViewChat />}
            {view === 'aprendizaje' && <ViewAprendizaje />}
            {view === 'ajustes' && <ViewAjustes />}
            {view === 'cobranza' && <ViewCobranza />}
          </div>
        </main>
      </div>
    </EmailStatusContext.Provider>
  );
}

export default App;
