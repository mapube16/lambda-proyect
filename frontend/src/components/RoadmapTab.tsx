import React, { useEffect, useState } from 'react';
import { apiFetch } from '../lib/apiFetch';
import { useOfficeStore } from '../store/officeStore';

// Checklist and hito definitions (copied from tu HTML original)
const CHECKLISTS = {
  current: [
    { id: 'cur1',  label: 'Constituir SAS',                                        tag: 'urgent' },
    { id: 'cur2',  label: 'Comprar dominio',                                        tag: null },
    { id: 'cur3',  label: 'Ciberseguridad del desarrollo',                          tag: null },
    { id: 'cur4',  label: 'Definir pricing beta',                                   tag: 'urgent' },
    { id: 'cur5',  label: 'Actualizar landing page con lógica real del negocio',    tag: null },
    { id: 'cur6',  label: 'Mejorar UI del desarrollo',                              tag: null },
    { id: 'cur7',  label: 'Estrategia de propuesta a clientes prospectos',          tag: null },
    { id: 'cur8',  label: 'Agente SECOP listo para despliegue',                     tag: null },
    { id: 'cur9',  label: 'NDA socios estratégicos',                                tag: 'prelabel' },
    { id: 'cur10', label: 'NDA freelancers y consultores',                          tag: 'prelabel' },
    { id: 'cur11', label: 'NDA mutuo entre cofundadores',                           tag: 'prelabel' },
  ],
  f1: [
    { id: 'f1-1', label: 'Cliente 1 activo con ingreso recurrente',                tag: null },
    { id: 'f1-2', label: 'Cliente 2 activo con ingreso recurrente',                tag: null },
    { id: 'f1-3', label: 'Cliente 3 activo con ingreso recurrente',                tag: null },
    { id: 'f1-4', label: 'Cliente 4 activo con ingreso recurrente',                tag: 'signal' },
    { id: 'f1-5', label: 'Segundo vertical validado con cliente real',             tag: null },
    { id: 'f1-6', label: 'Pricing definitivo por vertical documentado',            tag: null },
    { id: 'f1-7', label: 'LLC en US constituida y operativa',                      tag: null },
    { id: 'f1-8', label: 'Estructura legal CO–US definida',                        tag: null },
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

export const RoadmapTab: React.FC = () => {
  const { userRole, authToken } = useOfficeStore();
  const [state, setState] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Cargar estado desde backend
  useEffect(() => {
    if (!authToken) return;
    setLoading(true);
    apiFetch('/api/roadmap-state', {
      headers: { Authorization: 'Bearer ' + authToken }
    })
      .then(r => r.json())
      .then(data => {
        setState(data.state || {});
        setLoading(false);
      })
      .catch(() => {
        setError('No se pudo cargar el estado');
        setLoading(false);
      });
  }, [authToken]);

  // Guardar estado en backend
  const saveState = (newState: Record<string, boolean>) => {
    if (!authToken) return;
    apiFetch('/api/roadmap-state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + authToken },
      body: JSON.stringify({ state: newState })
    });
  };

  const toggle = (id: string) => {
    const newState = { ...state, [id]: !state[id] };
    setState(newState);
    saveState(newState);
  };

  // Render helpers
  const renderChecklist = (listId: keyof typeof CHECKLISTS, items: typeof CHECKLISTS[typeof listId]) => (
    <div style={{ marginBottom: 24 }}>
      {items.map(item => {
        const done = !!state[item.id];
        return (
          <div
            key={item.id}
            onClick={() => toggle(item.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8,
              border: '1px solid #e0e0e0', background: done ? '#EAF3DE' : '#f0efe9', cursor: 'pointer',
              opacity: done ? 0.7 : 1, marginBottom: 6
            }}
          >
            <span style={{ width: 18, height: 18, border: '1.5px solid #9FE1CB', borderRadius: 5, background: done ? '#9FE1CB' : '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {done && <svg width="10" height="8" viewBox="0 0 10 8" fill="none"><path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>}
            </span>
            <span style={{ fontSize: 13, color: done ? '#085041' : '#5a5a55', textDecoration: done ? 'line-through' : 'none' }}>{item.label}</span>
            {item.tag === 'urgent' && !done && <span style={{ fontSize: 11, background: '#FAECE7', color: '#993C1D', borderRadius: 20, padding: '2px 8px' }}>urgente</span>}
            {item.tag === 'signal' && !done && <span style={{ fontSize: 11, background: '#FAECE7', color: '#993C1D', borderRadius: 20, padding: '2px 8px' }}>señal de salida</span>}
          </div>
        );
      })}
    </div>
  );

  const renderHitos = () => (
    <div style={{ marginTop: 24, background: '#fff', border: '1px solid #e0e0e0', borderRadius: 16, padding: '24px 28px' }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#999892', marginBottom: 16 }}>Hitos transversales</div>
      {HITOS.map(h => {
        const done = !!state[h.id];
        return (
          <div key={h.id} onClick={() => toggle(h.id)} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 0', borderBottom: '1px solid #e0e0e0', cursor: 'pointer', opacity: done ? 0.7 : 1 }}>
            <span style={{ fontSize: 11, fontWeight: 600, padding: '4px 10px', borderRadius: 20, minWidth: 78, textAlign: 'center', background: done ? '#EAF3DE' : h.badge === 'urg' ? '#FAECE7' : h.badge === 'wip' ? '#FAEEDA' : h.badge === 'pend' ? '#f0efe9' : '#fff', color: done ? '#085041' : h.badge === 'urg' ? '#993C1D' : h.badge === 'wip' ? '#633806' : h.badge === 'pend' ? '#5a5a55' : '#085041', border: '1px solid #9FE1CB' }}>{done ? '✓ Listo' : h.badgeText}</span>
            <p style={{ fontSize: 14, color: done ? '#085041' : '#5a5a55', textDecoration: done ? 'line-through' : 'none', flex: 1 }}><strong>{h.label}</strong>{h.desc ? ' — ' + h.desc : ''}</p>
          </div>
        );
      })}
    </div>
  );

  if (userRole !== 'staff') return null;
  if (loading) return <div>Cargando roadmap...</div>;
  if (error) return <div style={{ color: 'red' }}>{error}</div>;

  return (
    <div style={{ maxWidth: 780, margin: '0 auto', padding: '48px 24px 80px' }}>
      <div style={{ marginBottom: 48, paddingBottom: 24, borderBottom: '1px solid #e0e0e0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#999892' }}>LANDA PROJECT</span>
          <span style={{ fontSize: 12, color: '#999892', fontFamily: 'monospace' }}>Roadmap · Confidencial</span>
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 600, letterSpacing: '-0.02em', color: '#1a1a18', marginBottom: 6 }}>Roadmap de fases</h1>
        <p style={{ fontSize: 15, color: '#5a5a55' }}>Sin fechas — las fases avanzan por señales, no por calendario</p>
      </div>
      <div style={{ background: '#fff', border: '1px solid #e0e0e0', borderRadius: 16, padding: 28, marginBottom: 12 }}>
        <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4, color: '#BA7517' }}>Ahora mismo</p>
        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#1a1a18', marginBottom: 20 }}>Estado actual</h2>
        {renderChecklist('current', CHECKLISTS.current)}
      </div>
      <div style={{ background: '#E1F5EE', border: '1px solid #9FE1CB', borderRadius: 16, padding: 28, marginBottom: 12 }}>
        <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4, color: '#0F6E56' }}>Fase 1</p>
        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#1a1a18', marginBottom: 20 }}>Oficina Funcional</h2>
        {renderChecklist('f1', CHECKLISTS.f1)}
      </div>
      <div style={{ background: '#EEEDFE', border: '1px solid #CECBF6', borderRadius: 16, padding: 28, marginBottom: 12 }}>
        <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4, color: '#534AB7' }}>Fase 2</p>
        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#1a1a18', marginBottom: 20 }}>Oficina Conectada</h2>
        {renderChecklist('f2', CHECKLISTS.f2)}
      </div>
      <div style={{ background: '#E6F1FB', border: '1px solid #B5D4F4', borderRadius: 16, padding: 28, marginBottom: 12 }}>
        <p style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 4, color: '#185FA5' }}>Fase 3</p>
        <h2 style={{ fontSize: 22, fontWeight: 600, color: '#1a1a18', marginBottom: 20 }}>Oficina con Presencia + Marketplace</h2>
        {renderChecklist('f3', CHECKLISTS.f3)}
      </div>
      {renderHitos()}
    </div>
  );
};
