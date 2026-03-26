import { useState, useEffect } from 'react';
import { useOfficeStore } from '../store/officeStore';
import { apiFetch } from '../lib/apiFetch';

const API_URL = '';

export interface LandaHandoverLead {
  leadId: string;
  empresa: string;
  canal: string;
}

interface HandoverModalProps {
  lead: LandaHandoverLead;
  onClose: () => void;
}

interface HiloEntry {
  canal?: string;
  mensaje?: string;
  message?: string;
  fecha?: string;
  date?: string;
  tipo?: string;
  role?: string;
}

interface Calificacion {
  puntaje?: number;
  criterios?: string[];
}

interface HandoverDetail {
  lead?: Record<string, unknown>;
  hilo_conversacion?: HiloEntry[];
  historial_conversacion?: HiloEntry[];
  calificacion_original?: Calificacion;
  sugerencia_cierre?: string;
}

export function HandoverModal({ lead, onClose }: HandoverModalProps) {
  const authToken = useOfficeStore(s => s.authToken);
  const [detail, setDetail] = useState<HandoverDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  function fetchDetail() {
    setLoading(true);
    setError(null);

    apiFetch(`${API_URL}/api/leads/${lead.leadId}/handover`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    })
      .then(r => {
        if (!r.ok) throw new Error(`Error ${r.status}`);
        return r.json() as Promise<HandoverDetail>;
      })
      .then(data => {
        setDetail(data);
      })
      .catch(e => {
        setError(String(e));
      })
      .finally(() => {
        setLoading(false);
      });
  }

  useEffect(() => {
    fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lead.leadId]);

  async function handleTomar() {
    setSubmitting(true);
    setActionError(null);
    try {
      const res = await apiFetch(`${API_URL}/api/leads/${lead.leadId}/handover/tomar`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || `Error ${res.status}`);
      }
      onClose();
    } catch (e) {
      setActionError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  const hilo = detail?.hilo_conversacion ?? detail?.historial_conversacion ?? [];
  const calificacion = detail?.calificacion_original;
  const sugerencia = detail?.sugerencia_cierre;

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={header}>
          <div>
            <div style={titleRow}>
              <span style={opportunityBadge}>Oportunidad lista!</span>
              {lead.canal && <span style={canalBadge(lead.canal)}>{lead.canal}</span>}
            </div>
            <div style={empresaName}>{lead.empresa}</div>
          </div>
          <button style={closeBtn} onClick={onClose}>✕</button>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          {loading && (
            <div style={{ color: '#888', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
              Cargando oportunidad...
            </div>
          )}

          {error && !loading && (
            <div style={errorBox}>
              <div style={{ color: '#ff6188', fontSize: 13, marginBottom: 8 }}>
                No se pudo cargar: {error}
              </div>
              <button style={retryBtn} onClick={fetchDetail}>Reintentar</button>
            </div>
          )}

          {!loading && detail && (
            <>
              {/* Calificacion */}
              {calificacion && (
                <div style={section}>
                  <div style={sectionTitle}>Calificacion del lead</div>
                  <div style={calCard}>
                    {calificacion.puntaje !== undefined && (
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 8 }}>
                        <span style={{ fontSize: 36, fontWeight: 800, color: puntajeColor(calificacion.puntaje), lineHeight: 1 }}>
                          {calificacion.puntaje}
                        </span>
                        <span style={{ color: '#888', fontSize: 16 }}>/100</span>
                      </div>
                    )}
                    {calificacion.criterios && calificacion.criterios.length > 0 && (
                      <ul style={listStyle}>
                        {calificacion.criterios.map((c, i) => (
                          <li key={i} style={listItem}>
                            <span style={{ color: '#a9dc76', marginRight: 6 }}>✓</span>
                            {c}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}

              {/* Sugerencia de cierre */}
              {sugerencia && (
                <div style={section}>
                  <div style={sectionTitle}>Sugerencia de cierre</div>
                  <div style={sugerenciaBox}>
                    <div style={{ color: '#ddd', fontSize: 13, lineHeight: 1.6 }}>
                      {sugerencia}
                    </div>
                  </div>
                </div>
              )}

              {/* Hilo de conversacion */}
              {hilo.length > 0 && (
                <div style={section}>
                  <div style={sectionTitle}>Hilo de conversacion ({hilo.length} mensajes)</div>
                  <div style={hiloContainer}>
                    {hilo.map((entry, i) => {
                      const msg = entry.mensaje ?? entry.message ?? '';
                      const canal = entry.canal ?? '';
                      const fecha = entry.fecha ?? entry.date ?? '';
                      const tipo = entry.tipo ?? entry.role ?? '';
                      const isHuman = tipo === 'humano' || tipo === 'human' || tipo === 'user';

                      return (
                        <div key={i} style={hiloEntry(isHuman)}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                            <span style={{ color: isHuman ? '#ffd866' : '#78dce8', fontSize: 11, fontWeight: 600 }}>
                              {isHuman ? 'Decisor' : 'Agente'}
                              {canal ? ` · ${canal}` : ''}
                            </span>
                            {fecha && <span style={{ color: '#666', fontSize: 10 }}>{fecha}</span>}
                          </div>
                          <div style={{ color: '#ddd', fontSize: 12, lineHeight: 1.5 }}>
                            {msg.length > 100 ? `${msg.slice(0, 100)}...` : msg}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {hilo.length === 0 && !sugerencia && !calificacion && (
                <div style={{ color: '#666', fontSize: 13, textAlign: 'center', padding: '12px 0' }}>
                  Sin datos adicionales disponibles.
                </div>
              )}
            </>
          )}

          {/* Action error */}
          {actionError && (
            <div style={{ color: '#ff6188', fontSize: 12, background: '#2a1a1e', borderRadius: 6, padding: '8px 12px', border: '1px solid #ff618844' }}>
              {actionError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={footer}>
          <button style={cerrarBtn} disabled={submitting} onClick={onClose}>
            Cerrar
          </button>
          <button
            style={tomarBtn}
            disabled={submitting || loading}
            onClick={handleTomar}
          >
            {submitting ? 'Tomando control...' : 'Tomar el control'}
          </button>
        </div>

      </div>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function puntajeColor(score: number): string {
  if (score >= 85) return '#a9dc76';
  if (score >= 70) return '#ffd866';
  return '#ff6188';
}

function canalBadge(canal: string): React.CSSProperties {
  const color = canal === 'whatsapp' ? '#a9dc76'
    : canal === 'email' ? '#78dce8'
    : canal === 'linkedin' ? '#ab9df2'
    : '#ffd866';
  return {
    background: `${color}22`, border: `1px solid ${color}`, color,
    borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 600,
  };
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
};

const modal: React.CSSProperties = {
  background: '#1e1e2e', border: '1px solid #3a3a5e', borderRadius: 12,
  maxWidth: 500, width: '90%', maxHeight: '85vh',
  display: 'flex', flexDirection: 'column', overflow: 'hidden',
  boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
};

const header: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  padding: '18px 20px 14px', borderBottom: '1px solid #2a2a4e',
};

const titleRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
};

const opportunityBadge: React.CSSProperties = {
  background: '#a9dc7622', border: '1px solid #a9dc76', color: '#a9dc76',
  borderRadius: 4, padding: '3px 10px', fontSize: 12, fontWeight: 700,
};

const empresaName: React.CSSProperties = {
  color: '#fff', fontSize: 16, fontWeight: 700,
};

const closeBtn: React.CSSProperties = {
  background: 'none', border: 'none', color: '#888', fontSize: 18, cursor: 'pointer', padding: 4,
};

const bodyStyle: React.CSSProperties = {
  overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16, flex: 1,
};

const footer: React.CSSProperties = {
  display: 'flex', gap: 10, padding: '14px 20px', borderTop: '1px solid #2a2a4e', justifyContent: 'flex-end',
};

const section: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 8,
};

const sectionTitle: React.CSSProperties = {
  color: '#ab9df2', fontWeight: 600, fontSize: 12, textTransform: 'uppercase', letterSpacing: 1,
};

const calCard: React.CSSProperties = {
  background: '#252538', borderRadius: 8, padding: '12px 14px',
};

const sugerenciaBox: React.CSSProperties = {
  background: '#252535', border: '1px solid #a9dc7644', borderRadius: 8, padding: '12px 14px',
};

const hiloContainer: React.CSSProperties = {
  maxHeight: 200, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6,
  paddingRight: 4,
};

const hiloEntry = (isHuman: boolean): React.CSSProperties => ({
  background: isHuman ? '#2a2520' : '#1e2a35',
  border: `1px solid ${isHuman ? '#ffd86633' : '#78dce833'}`,
  borderRadius: 6, padding: '8px 10px',
});

const listStyle: React.CSSProperties = {
  margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4,
};

const listItem: React.CSSProperties = {
  color: '#ccc', fontSize: 13, display: 'flex', alignItems: 'flex-start',
};

const errorBox: React.CSSProperties = {
  background: '#2a1a1e', borderRadius: 8, padding: '14px', border: '1px solid #ff618844',
};

const retryBtn: React.CSSProperties = {
  background: 'transparent', border: '1px solid #ff6188', borderRadius: 6,
  color: '#ff6188', cursor: 'pointer', fontSize: 12, padding: '5px 14px',
};

const cerrarBtn: React.CSSProperties = {
  padding: '8px 18px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
  background: 'transparent', border: '1px solid #555', color: '#aaa',
  fontFamily: 'inherit',
};

const tomarBtn: React.CSSProperties = {
  padding: '8px 20px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
  background: '#a9dc7622', border: '1px solid #a9dc76', color: '#a9dc76',
  fontWeight: 700, fontFamily: 'inherit',
};
