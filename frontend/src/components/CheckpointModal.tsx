import { useState, useEffect } from 'react';
import { useOfficeStore } from '../store/officeStore';
import { apiFetch } from '../lib/apiFetch';

const API_URL = '';

export interface LandaCheckpointLead {
  leadId: string;
  empresa: string;
  puntaje: number;
}

interface CheckpointModalProps {
  lead: LandaCheckpointLead;
  onClose: () => void;
}

interface Canal {
  canal: string;
  probabilidad?: number;
  probability?: number;
}

interface CheckpointDetail {
  id?: string;
  _id?: string;
  empresa?: string;
  puntaje?: number;
  decisor?: { nombre?: string; cargo?: string } | null;
  criterios?: string[];
  senales_intencion?: string[];
  canales?: Canal[];
}

export function CheckpointModal({ lead, onClose }: CheckpointModalProps) {
  const authToken = useOfficeStore(s => s.authToken);
  const [detail, setDetail] = useState<CheckpointDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCanal, setSelectedCanal] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    apiFetch(`${API_URL}/api/leads/checkpoint`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    })
      .then(r => {
        if (!r.ok) throw new Error(`Error ${r.status}`);
        return r.json();
      })
      .then((data: unknown) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data as CheckpointDetail[]
          : (data as { leads?: CheckpointDetail[] }).leads ?? [];
        const found = list.find(
          l => (l.id ?? l._id) === lead.leadId
        );
        const resolved = found ?? { empresa: lead.empresa, puntaje: lead.puntaje };
        setDetail(resolved);

        // Pre-select the canal with the highest probability
        const canales: Canal[] = resolved.canales ?? [];
        if (canales.length > 0) {
          const best = canales.reduce((a, b) => {
            const pa = a.probabilidad ?? a.probability ?? 0;
            const pb = b.probabilidad ?? b.probability ?? 0;
            return pb > pa ? b : a;
          });
          setSelectedCanal(best.canal);
        }
      })
      .catch(e => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [lead.leadId, authToken, lead.empresa, lead.puntaje]);

  async function postDecision(decision: 'aprobar' | 'pausar' | 'rechazar') {
    setSubmitting(true);
    setActionError(null);
    try {
      const body: Record<string, string> = { decision };
      if (decision === 'aprobar' && selectedCanal) body.canal_elegido = selectedCanal;
      if (decision === 'rechazar') body.motivo = 'rechazado_humano';

      const res = await apiFetch(`${API_URL}/api/leads/${lead.leadId}/decision`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify(body),
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

  const puntaje = detail?.puntaje ?? lead.puntaje;
  const empresa = detail?.empresa ?? lead.empresa;
  const puntajeColor = puntaje >= 85 ? '#a9dc76' : puntaje >= 70 ? '#ffd866' : '#ff6188';

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={header}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div>
              <div style={empresaTitle}>{empresa}</div>
              <div style={{ color: '#888', fontSize: 12, marginTop: 2 }}>Revisión de checkpoint</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={puntajeBadge(puntajeColor)}>{puntaje}</div>
            <button style={closeBtn} onClick={onClose}>✕</button>
          </div>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          {loading && (
            <div style={{ color: '#888', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
              Cargando datos del lead...
            </div>
          )}

          {error && !loading && (
            <div style={{ color: '#ff6188', fontSize: 13, padding: '12px 0' }}>
              No se pudo cargar el detalle: {error}
            </div>
          )}

          {!loading && detail && (
            <>
              {/* Decisor */}
              {detail.decisor && (
                <div style={section}>
                  <div style={sectionTitle}>Decisor clave</div>
                  <div style={decisorCard}>
                    <div style={decisorName}>{detail.decisor.nombre ?? '—'}</div>
                    <div style={decisorRole}>{detail.decisor.cargo ?? ''}</div>
                  </div>
                </div>
              )}

              {/* Criterios */}
              {detail.criterios && detail.criterios.length > 0 && (
                <div style={section}>
                  <div style={sectionTitle}>Criterios cumplidos</div>
                  <ul style={listStyle}>
                    {detail.criterios.map((c, i) => (
                      <li key={i} style={listItem}>
                        <span style={{ color: '#a9dc76', marginRight: 6 }}>✓</span>
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Senales de intencion */}
              {detail.senales_intencion && detail.senales_intencion.length > 0 && (
                <div style={section}>
                  <div style={sectionTitle}>Senales de intencion</div>
                  <ul style={listStyle}>
                    {detail.senales_intencion.map((s, i) => (
                      <li key={i} style={listItem}>
                        <span style={{ color: '#ffd866', marginRight: 6 }}>◆</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Canales */}
              {detail.canales && detail.canales.length > 0 && (
                <div style={section}>
                  <div style={sectionTitle}>Canales recomendados</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {detail.canales.map((c, i) => {
                      const prob = c.probabilidad ?? c.probability ?? 0;
                      return (
                        <div key={i} style={canalRow}>
                          <span style={{ color: '#ddd', fontSize: 13 }}>{c.canal}</span>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={probBar}>
                              <div style={{ ...probFill, width: `${prob}%`, background: prob >= 70 ? '#a9dc76' : prob >= 40 ? '#ffd866' : '#ff6188' }} />
                            </div>
                            <span style={{ color: '#aaa', fontSize: 12, minWidth: 36, textAlign: 'right' }}>{prob}%</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Canal selector */}
              {detail.canales && detail.canales.length > 0 && (
                <div style={section}>
                  <div style={sectionTitle}>Canal para outreach</div>
                  <select
                    value={selectedCanal}
                    onChange={e => setSelectedCanal(e.target.value)}
                    style={selectStyle}
                  >
                    {detail.canales.map((c, i) => (
                      <option key={i} value={c.canal}>{c.canal}</option>
                    ))}
                  </select>
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

        {/* Buttons */}
        <div style={footer}>
          <button
            style={{ ...actionBtn, background: '#ff618822', border: '1px solid #ff6188', color: '#ff6188' }}
            disabled={submitting}
            onClick={() => postDecision('rechazar')}
          >
            Rechazar
          </button>
          <button
            style={{ ...actionBtn, background: '#ffd86622', border: '1px solid #ffd866', color: '#ffd866' }}
            disabled={submitting}
            onClick={() => postDecision('pausar')}
          >
            Pausar
          </button>
          <button
            style={{ ...actionBtn, background: '#a9dc7622', border: '1px solid #a9dc76', color: '#a9dc76', fontWeight: 700 }}
            disabled={submitting}
            onClick={() => postDecision('aprobar')}
          >
            {submitting ? 'Enviando...' : 'Aprobar'}
          </button>
        </div>

      </div>
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
};

const modal: React.CSSProperties = {
  background: '#1e1e2e', border: '1px solid #3a3a5e', borderRadius: 12,
  padding: 0, maxWidth: 480, width: '90%', maxHeight: '85vh',
  display: 'flex', flexDirection: 'column', overflow: 'hidden',
  boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
};

const header: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  padding: '18px 20px 14px', borderBottom: '1px solid #2a2a4e',
};

const empresaTitle: React.CSSProperties = {
  color: '#fff', fontSize: 16, fontWeight: 700,
};

const puntajeBadge = (color: string): React.CSSProperties => ({
  background: color, color: '#000', borderRadius: 6,
  padding: '3px 10px', fontSize: 14, fontWeight: 700, minWidth: 36, textAlign: 'center',
});

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

const decisorCard: React.CSSProperties = {
  background: '#252538', borderRadius: 8, padding: '10px 14px',
};

const decisorName: React.CSSProperties = { color: '#fff', fontWeight: 600, fontSize: 14 };
const decisorRole: React.CSSProperties = { color: '#aaa', fontSize: 12, marginTop: 2 };

const listStyle: React.CSSProperties = {
  margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4,
};

const listItem: React.CSSProperties = {
  color: '#ccc', fontSize: 13, display: 'flex', alignItems: 'flex-start',
};

const canalRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  background: '#252538', borderRadius: 6, padding: '6px 12px',
};

const probBar: React.CSSProperties = {
  width: 80, height: 6, background: '#333', borderRadius: 3, overflow: 'hidden',
};

const probFill: React.CSSProperties = {
  height: '100%', borderRadius: 3, transition: 'width 0.3s ease',
};

const selectStyle: React.CSSProperties = {
  background: '#252538', border: '1px solid #444', borderRadius: 6,
  color: '#ddd', fontSize: 13, padding: '6px 10px', width: '100%',
};

const actionBtn: React.CSSProperties = {
  padding: '8px 18px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
  fontFamily: 'inherit', transition: 'opacity 0.15s',
};
