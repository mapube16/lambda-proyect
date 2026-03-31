import { useState, useEffect, useCallback, useRef } from 'react';
import { useOfficeStore } from '../store/officeStore';
import { apiFetch } from '../lib/apiFetch';

// ─── Inject keyframes once ─────────────────────────────────────────────────────
if (typeof document !== 'undefined' && !document.getElementById('cobr-styles')) {
  const s = document.createElement('style');
  s.id = 'cobr-styles';
  s.textContent = `
    @keyframes cobr-pulse { 0%,100%{opacity:1;box-shadow:0 0 6px #ffd866} 50%{opacity:0.4;box-shadow:0 0 2px #ffd866} }
    @keyframes cobr-spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
    @keyframes cobr-fade-in { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }
  `;
  document.head.appendChild(s);
}

// ─── Tokens (same as ClientDashboard) ──────────────────────────────────────────
const C = {
  bg:        '#0d0d18',
  s0:        '#12121d',
  s1:        '#1b1a26',
  s2:        '#22212e',
  s3:        '#2c2b3a',
  s4:        '#343440',
  text:      '#e3e0f1',
  muted:     '#8a8a9a',
  faint:     'rgba(227,224,241,0.3)',
  cyan:      '#78dce8',
  cyanBg:    'rgba(120,220,232,0.08)',
  cyanBdr:   'rgba(120,220,232,0.2)',
  green:     '#a9dc76',
  greenBg:   'rgba(169,220,118,0.08)',
  pink:      '#ff6188',
  pinkBg:    'rgba(255,97,136,0.08)',
  orange:    '#fc9867',
  orangeBg:  'rgba(252,152,103,0.08)',
  purple:    '#ab9df2',
  purpleBg:  'rgba(171,157,242,0.08)',
  yellow:    '#ffd866',
  yellowBg:  'rgba(255,216,102,0.08)',
  SG:        "'Space Grotesk', system-ui, sans-serif",
  IN:        "'Inter', system-ui, sans-serif",
};

const lbl = (color = C.muted, size = 10): React.CSSProperties => ({
  fontFamily: C.SG, fontSize: size, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.12em', color,
});

// ─── Types ─────────────────────────────────────────────────────────────────────
interface CallRecord {
  call_id: string;
  fecha: string;
  duracion_segundos: number;
  resultado: string;
  transcript?: string;
  summary?: string;
  recording_url?: string;
}

interface Debtor {
  _id: string;
  nombre: string;
  telefono: string;
  monto: number;
  vencimiento: string;
  estado: 'pendiente' | 'llamando' | 'promesa_de_pago' | 'sin_contacto' |
          'pagado' | 'fallido' | 'escalado' | 'agotado' | 'pausado';
  intentos: number;
  max_intentos: number;
  historial_llamadas: CallRecord[];
  monto_prometido?: number;
  fecha_promesa?: string;
  notas?: string;
  escalado?: boolean;
}

type EstadoFilter = Debtor['estado'] | null;

// ─── Estado badge config ────────────────────────────────────────────────────────
function getEstadoConfig(estado: Debtor['estado']): { color: string; bg: string; label: string; pulsing?: boolean } {
  switch (estado) {
    case 'pendiente':        return { color: C.cyan,    bg: C.cyanBg,    label: 'PENDIENTE' };
    case 'llamando':         return { color: C.yellow,  bg: C.yellowBg,  label: 'LLAMANDO',  pulsing: true };
    case 'promesa_de_pago':  return { color: C.green,   bg: C.greenBg,   label: 'PROMESA' };
    case 'sin_contacto':     return { color: C.muted,   bg: 'transparent', label: 'SIN CONTACTO' };
    case 'pagado':           return { color: C.green,   bg: C.greenBg,   label: 'PAGADO' };
    case 'fallido':          return { color: C.pink,    bg: C.pinkBg,    label: 'FALLIDO' };
    case 'escalado':         return { color: C.orange,  bg: C.orangeBg,  label: 'ESCALADO' };
    case 'agotado':          return { color: C.muted,   bg: 'transparent', label: 'AGOTADO' };
    case 'pausado':          return { color: C.purple,  bg: C.purpleBg,  label: 'PAUSADO' };
    default:                 return { color: C.muted,   bg: 'transparent', label: String(estado).toUpperCase() };
  }
}

function EstadoBadge({ estado }: { estado: Debtor['estado'] }) {
  const cfg = getEstadoConfig(estado);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      ...lbl(cfg.color, 9), background: cfg.bg, padding: '3px 9px',
      border: `1px solid ${cfg.color}30`,
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: '50%', background: cfg.color, flexShrink: 0,
        ...(cfg.pulsing ? { animation: 'cobr-pulse 1.5s infinite', boxShadow: `0 0 6px ${cfg.color}` } : {}),
      }} />
      {cfg.label}
    </span>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────────
function formatCOP(amount: number): string {
  return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(amount);
}

function formatDate(iso: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return iso; }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

// ─── Toast ─────────────────────────────────────────────────────────────────────
interface CobrToast { id: string; message: string; ok: boolean; }

function CobranzaToast({ toast, onDismiss }: { toast: CobrToast; onDismiss: (id: string) => void }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '11px 16px', minWidth: 260,
      background: C.s3, border: `1px solid ${toast.ok ? 'rgba(169,220,118,0.25)' : 'rgba(255,97,136,0.25)'}`,
      boxShadow: '0 8px 32px rgba(0,0,0,0.45)', pointerEvents: 'all',
      opacity: visible ? 1 : 0, transform: visible ? 'translateX(0)' : 'translateX(12px)',
      transition: 'opacity 0.2s, transform 0.2s',
    }}>
      <span style={{ fontSize: 13, color: toast.ok ? C.green : C.pink, flexShrink: 0 }}>
        {toast.ok ? '✓' : '✕'}
      </span>
      <span style={{ fontFamily: C.SG, fontSize: 12, color: C.text, flex: 1 }}>{toast.message}</span>
      <button onClick={() => onDismiss(toast.id)} style={{
        background: 'transparent', border: 'none', color: C.muted, cursor: 'pointer',
        fontSize: 14, width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>✕</button>
    </div>
  );
}

// ─── Detail Modal ──────────────────────────────────────────────────────────────
function DebtorModal({
  debtor,
  token,
  onClose,
  onAction,
}: {
  debtor: Debtor;
  token: string;
  onClose: () => void;
  onAction: (id: string, updatedDebtor: Partial<Debtor>) => void;
}) {
  const [notas, setNotas] = useState(debtor.notas || '');
  const [expandedCall, setExpandedCall] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [acting, setActing] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  // ── Edit mode ────────────────────────────────────────────────────────────
  const [editMode, setEditMode] = useState(false);
  const [editFields, setEditFields] = useState({
    nombre: debtor.nombre,
    telefono: debtor.telefono,
    monto: String(debtor.monto),
    vencimiento: debtor.vencimiento ? debtor.vencimiento.slice(0, 10) : '',
  });

  const handleSaveEdits = async () => {
    setSaving(true);
    try {
      const patch: Record<string, string | number> = {};
      if (editFields.nombre !== debtor.nombre) patch.nombre = editFields.nombre;
      if (editFields.telefono !== debtor.telefono) patch.telefono = editFields.telefono;
      if (Number(editFields.monto) !== debtor.monto) patch.monto = Number(editFields.monto);
      if (editFields.vencimiento !== debtor.vencimiento?.slice(0, 10)) patch.vencimiento = editFields.vencimiento;
      if (notas !== (debtor.notas || '')) patch.notas = notas;
      if (!Object.keys(patch).length) { setEditMode(false); return; }
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      if (r.ok) {
        const data = await r.json();
        onAction(debtor._id, data.debtor || patch);
        showToast('Cambios guardados');
        setEditMode(false);
      } else {
        const d = await r.json().catch(() => ({}));
        showToast((d as { detail?: string }).detail || 'Error al guardar');
      }
    } catch { showToast('Error de conexión'); }
    finally { setSaving(false); }
  };

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  const doAction = async (path: string, method = 'POST', body?: object): Promise<boolean> => {
    setActing(true);
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}/${path}`, {
        method,
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        showToast((data as { detail?: string }).detail || `Error ${r.status}`);
        return false;
      }
      return true;
    } catch {
      showToast('Error de conexión');
      return false;
    } finally {
      setActing(false);
    }
  };

  const handleLlamarAhora = async () => {
    const ok = await doAction('llamar-ahora');
    if (ok) showToast('Llamada iniciada');
  };

  const handlePagar = async () => {
    const ok = await doAction('pagar');
    if (ok) {
      onAction(debtor._id, { estado: 'pagado' });
      showToast('Marcado como pagado');
      onClose();
    }
  };

  const handlePausar = async () => {
    const isPausado = debtor.estado === 'pausado';
    const path = isPausado ? 'reactivar' : 'pausar';
    const ok = await doAction(path);
    if (ok) {
      onAction(debtor._id, { estado: isPausado ? 'pendiente' : 'pausado' });
      showToast(isPausado ? 'Deudor reactivado' : 'Deudor pausado');
    }
  };

  const handleEliminar = async () => {
    if (!window.confirm(`¿Eliminar a ${debtor.nombre}? Esta acción no se puede deshacer.`)) return;
    setActing(true);
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) {
        onAction(debtor._id, { _id: '__deleted__' } as Partial<Debtor> & { _id: string });
        onClose();
      } else {
        showToast('Error al eliminar');
      }
    } catch { showToast('Error de conexión'); }
    finally { setActing(false); }
  };

  const handleSaveNotas = async () => {
    setSaving(true);
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ notas }),
      });
      if (r.ok) {
        onAction(debtor._id, { notas });
        showToast('Notas guardadas');
      } else {
        showToast('Error al guardar');
      }
    } catch { showToast('Error de conexión'); }
    finally { setSaving(false); }
  };

  const estadoCfg = getEstadoConfig(debtor.estado);

  // Keyboard close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      {/* Overlay */}
      <div
        onClick={onClose}
        style={{ position: 'absolute', inset: 0, background: 'rgba(13,13,24,0.92)', backdropFilter: 'blur(4px)' }}
      />
      {/* Modal container */}
      <div style={{
        position: 'relative', zIndex: 1,
        width: '100%', maxWidth: 960, maxHeight: '90vh',
        background: C.s1, border: `1px solid rgba(120,220,232,0.12)`,
        display: 'flex', flexDirection: 'column',
        animation: 'cobr-fade-in 0.2s ease',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 28px', background: C.s0,
          borderBottom: `1px solid rgba(255,255,255,0.05)`,
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16,
          flexWrap: 'wrap',
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {editMode ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {[
                    { key: 'nombre', label: 'Nombre', flex: 2 },
                    { key: 'telefono', label: 'Teléfono', flex: 1 },
                  ].map(({ key, label, flex }) => (
                    <div key={key} style={{ flex }}>
                      <div style={{ ...lbl(C.muted, 8), marginBottom: 3 }}>{label.toUpperCase()}</div>
                      <input
                        value={editFields[key as keyof typeof editFields]}
                        onChange={e => setEditFields(p => ({ ...p, [key]: e.target.value }))}
                        style={{
                          width: '100%', boxSizing: 'border-box', background: C.s2,
                          border: `1px solid rgba(252,152,103,0.4)`, color: C.text,
                          fontFamily: C.SG, fontSize: 13, padding: '6px 10px', outline: 'none',
                        }}
                      />
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {[
                    { key: 'monto', label: 'Monto (COP)', type: 'number', flex: 1 },
                    { key: 'vencimiento', label: 'Vencimiento', type: 'date', flex: 1 },
                  ].map(({ key, label, type, flex }) => (
                    <div key={key} style={{ flex }}>
                      <div style={{ ...lbl(C.muted, 8), marginBottom: 3 }}>{label.toUpperCase()}</div>
                      <input
                        type={type}
                        value={editFields[key as keyof typeof editFields]}
                        onChange={e => setEditFields(p => ({ ...p, [key]: e.target.value }))}
                        style={{
                          width: '100%', boxSizing: 'border-box', background: C.s2,
                          border: `1px solid rgba(252,152,103,0.4)`, color: C.text,
                          fontFamily: C.SG, fontSize: 13, padding: '6px 10px', outline: 'none',
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                  <h2 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 22, color: C.text, letterSpacing: '-0.02em' }}>
                    {debtor.nombre}
                  </h2>
                  <EstadoBadge estado={debtor.estado} />
                </div>
                <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted }}>
                  {debtor.telefono} · {debtor.intentos}/{debtor.max_intentos} intentos
                </div>
              </>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
            {!editMode && (
              <div style={{ textAlign: 'right' }}>
                <div style={lbl(C.muted, 9)}>Monto</div>
                <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 22, color: estadoCfg.color }}>
                  {formatCOP(debtor.monto)}
                </div>
              </div>
            )}
            {editMode ? (
              <>
                <button
                  onClick={() => setEditMode(false)}
                  style={{
                    padding: '9px 14px', border: `1px solid rgba(255,255,255,0.1)`, cursor: 'pointer',
                    background: 'transparent', color: C.muted, fontFamily: C.SG, fontSize: 11, fontWeight: 600,
                  }}
                >Cancelar</button>
                <button
                  onClick={handleSaveEdits}
                  disabled={saving}
                  style={{
                    padding: '9px 18px', border: 'none', cursor: saving ? 'not-allowed' : 'pointer',
                    background: C.orange, color: C.bg, ...lbl('#000', 11), opacity: saving ? 0.6 : 1,
                  }}
                >{saving ? 'Guardando…' : 'Guardar cambios'}</button>
              </>
            ) : (
              <button
                onClick={handleLlamarAhora}
                disabled={acting}
                style={{
                  padding: '9px 18px', border: 'none', cursor: acting ? 'not-allowed' : 'pointer',
                  background: C.cyan, color: C.bg,
                  ...lbl('#000', 11), display: 'flex', alignItems: 'center', gap: 6,
                  opacity: acting ? 0.6 : 1,
                }}
              >
                📞 LLAMAR
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                width: 36, height: 36, border: `1px solid rgba(255,255,255,0.1)`,
                background: 'transparent', color: C.muted, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
              }}
            >✕</button>
          </div>
        </div>

        {/* Body — two columns */}
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', flex: 1, overflow: 'hidden' }}>

          {/* Left panel */}
          <div style={{
            borderRight: `1px solid rgba(255,255,255,0.05)`,
            overflowY: 'auto', padding: '20px 20px',
            display: 'flex', flexDirection: 'column', gap: 20,
          }}>

            {/* Promise info */}
            {(debtor.estado === 'promesa_de_pago' || debtor.monto_prometido) && (
              <div style={{
                padding: '14px', background: C.greenBg,
                borderLeft: `3px solid ${C.green}`,
              }}>
                <div style={lbl(C.green, 9)}>PROMESA DE PAGO</div>
                {debtor.monto_prometido && (
                  <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 18, color: C.green, marginTop: 8 }}>
                    {formatCOP(debtor.monto_prometido)}
                  </div>
                )}
                {debtor.fecha_promesa && (
                  <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, marginTop: 4 }}>
                    Fecha: {formatDate(debtor.fecha_promesa)}
                  </div>
                )}
              </div>
            )}

            {/* Historial de llamadas */}
            <div>
              <div style={{ ...lbl(C.muted, 9), marginBottom: 12 }}>INTERACTION_LOG_MATRIX</div>
              {debtor.historial_llamadas.length === 0 ? (
                <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, fontStyle: 'italic' }}>
                  Sin llamadas registradas
                </div>
              ) : (
                <div style={{ position: 'relative', paddingLeft: 20 }}>
                  {/* Timeline line */}
                  <div style={{
                    position: 'absolute', left: 7, top: 0, bottom: 0,
                    width: 1, background: 'rgba(255,255,255,0.06)',
                  }} />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {debtor.historial_llamadas.map((call) => (
                      <div key={call.call_id} style={{ position: 'relative' }}>
                        {/* Timeline dot */}
                        <div style={{
                          position: 'absolute', left: -16, top: 3,
                          width: 8, height: 8, background: C.s3,
                          border: `1px solid rgba(255,255,255,0.2)`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          <div style={{ width: 3, height: 3, background: C.cyan }} />
                        </div>
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ fontFamily: C.SG, fontSize: 10, fontWeight: 700, color: C.text }}>
                              {formatDate(call.fecha)}
                            </div>
                            <div style={{ fontFamily: C.SG, fontSize: 10, color: C.muted }}>
                              {formatDuration(call.duracion_segundos)}
                            </div>
                          </div>
                          <div style={{ ...lbl(C.muted, 9), marginTop: 2 }}>{call.resultado.toUpperCase()}</div>
                          {(call.transcript || call.summary) && (
                            <button
                              onClick={() => setExpandedCall(expandedCall === call.call_id ? null : call.call_id)}
                              style={{
                                marginTop: 4, background: 'transparent', border: 'none', cursor: 'pointer',
                                ...lbl(C.cyan, 9), padding: 0,
                              }}
                            >
                              {expandedCall === call.call_id ? '▲ ocultar' : call.transcript ? '▼ ver transcript' : '▼ ver resumen'}
                            </button>
                          )}
                          {expandedCall === call.call_id && (call.transcript || call.summary) && (
                            <div style={{
                              marginTop: 6, padding: '8px 10px', background: C.s2,
                              fontFamily: C.IN, fontSize: 11, color: C.muted,
                              lineHeight: 1.5, maxHeight: 120, overflowY: 'auto',
                              borderLeft: `2px solid ${call.transcript ? C.cyan : C.purple}40`,
                            }}>
                              {call.transcript || call.summary}
                            </div>
                          )}
                          {call.recording_url && (
                            <audio
                              controls
                              src={call.recording_url}
                              style={{ marginTop: 6, width: '100%', height: 28, opacity: 0.8 }}
                            />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Notas */}
            <div>
              <div style={{ ...lbl(C.muted, 9), marginBottom: 8 }}>NOTAS</div>
              <textarea
                value={notas}
                onChange={e => setNotas(e.target.value)}
                rows={4}
                placeholder="Agregar nota..."
                style={{
                  width: '100%', resize: 'vertical', background: C.s2,
                  border: `1px solid rgba(255,255,255,0.07)`, color: C.text,
                  fontFamily: C.IN, fontSize: 12, padding: '8px 10px', outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <button
                onClick={handleSaveNotas}
                disabled={saving}
                style={{
                  marginTop: 6, padding: '6px 14px', border: 'none', cursor: saving ? 'not-allowed' : 'pointer',
                  background: C.s3, color: C.text, ...lbl(C.text, 10), opacity: saving ? 0.6 : 1,
                }}
              >
                {saving ? 'Guardando...' : 'GUARDAR NOTA'}
              </button>
            </div>

            {/* Action grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {[
                { label: 'EDITAR', onClick: () => setEditMode(true), color: C.orange },
                { label: 'MARCAR PAGADO', onClick: handlePagar, color: C.green },
                { label: debtor.estado === 'pausado' ? 'REACTIVAR' : 'PAUSAR', onClick: handlePausar, color: C.purple },
                { label: 'ELIMINAR', onClick: handleEliminar, color: C.pink },
              ].map(({ label, onClick, color }) => (
                <button
                  key={label}
                  onClick={onClick}
                  disabled={acting}
                  style={{
                    padding: '10px 8px', border: `1px solid rgba(255,255,255,0.08)`,
                    background: 'transparent', cursor: acting ? 'not-allowed' : 'pointer',
                    ...lbl(color, 9), opacity: acting ? 0.5 : 1,
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { if (!acting) (e.currentTarget as HTMLElement).style.background = C.s3; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Right panel — transcript / last call detail */}
          <div style={{
            overflowY: 'auto', padding: '20px 24px',
            display: 'flex', flexDirection: 'column', gap: 16,
          }}>
            <div style={{ ...lbl(C.muted, 9), borderBottom: `1px solid rgba(255,255,255,0.05)`, paddingBottom: 12 }}>
              NEURAL_TRANSCRIPTION_STREAM
            </div>
            {debtor.historial_llamadas.length === 0 ? (
              <div style={{ fontFamily: C.IN, fontSize: 13, color: C.muted, fontStyle: 'italic', textAlign: 'center', marginTop: 40 }}>
                Sin llamadas registradas aún.
              </div>
            ) : (() => {
              const lastCall = debtor.historial_llamadas[debtor.historial_llamadas.length - 1];
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{
                    padding: '10px 14px', background: C.s2,
                    borderLeft: `2px solid rgba(120,220,232,0.3)`,
                    display: 'flex', justifyContent: 'space-between',
                  }}>
                    <span style={{ fontFamily: C.SG, fontSize: 11, color: C.text }}>
                      Última llamada: {formatDate(lastCall.fecha)}
                    </span>
                    <span style={{ fontFamily: C.SG, fontSize: 11, color: C.muted }}>
                      {formatDuration(lastCall.duracion_segundos)} · {lastCall.resultado}
                    </span>
                  </div>
                  {lastCall.transcript ? (
                    <div>
                      <div style={{ ...lbl(C.muted, 9), marginBottom: 10 }}>TRANSCRIPT</div>
                      {lastCall.transcript.split('\n').filter(Boolean).map((line, idx) => {
                        const isAgent = line.toLowerCase().startsWith('agente:') || line.toLowerCase().startsWith('agent:') || idx % 2 === 0;
                        return (
                          <div
                            key={idx}
                            style={{
                              display: 'flex',
                              flexDirection: isAgent ? 'row' : 'row-reverse',
                              gap: 10, marginBottom: 10,
                              maxWidth: '85%',
                              marginLeft: isAgent ? 0 : 'auto',
                            }}
                          >
                            <div style={{
                              width: 28, height: 28, flexShrink: 0, background: isAgent ? C.cyanBg : C.s2,
                              border: `1px solid ${isAgent ? C.cyanBdr : 'rgba(255,255,255,0.08)'}`,
                              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12,
                            }}>
                              {isAgent ? '🤖' : '👤'}
                            </div>
                            <div>
                              <div style={{ ...lbl(isAgent ? C.cyan : C.muted, 8), marginBottom: 4 }}>
                                {isAgent ? 'HIVE_AGENT' : debtor.nombre.split(' ')[0].toUpperCase()}
                              </div>
                              <div style={{
                                background: isAgent ? C.cyanBg : C.s2, padding: '8px 12px',
                                fontFamily: C.IN, fontSize: 12, color: C.text, lineHeight: 1.5,
                                borderLeft: isAgent ? `2px solid ${C.cyan}40` : 'none',
                              }}>
                                {line.replace(/^(agente:|agent:|deudor:)/i, '').trim()}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : lastCall.summary ? (
                    <div>
                      <div style={{ ...lbl(C.muted, 9), marginBottom: 10 }}>RESUMEN</div>
                      <div style={{
                        padding: '12px 14px', background: C.s2,
                        fontFamily: C.IN, fontSize: 12, color: C.text, lineHeight: 1.6,
                        borderLeft: `2px solid ${C.purple}60`,
                      }}>
                        {lastCall.summary}
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{
                        padding: '12px 14px', background: C.s2,
                        fontFamily: C.IN, fontSize: 12, color: C.muted, lineHeight: 1.6,
                        borderLeft: `2px solid rgba(255,255,255,0.08)`,
                      }}>
                        {lastCall.resultado === 'no-answer' && 'El deudor no contestó la llamada.'}
                        {lastCall.resultado === 'busy' && 'La línea estaba ocupada.'}
                        {lastCall.resultado === 'voicemail' && 'La llamada fue al buzón de voz.'}
                        {lastCall.resultado === 'customer-ended-call' && 'El deudor finalizó la llamada.'}
                        {lastCall.resultado === 'assistant-ended-call' && 'El agente finalizó la llamada.'}
                        {lastCall.resultado === 'hangup' && 'La llamada fue cortada.'}
                        {!['no-answer','busy','voicemail','customer-ended-call','assistant-ended-call','hangup'].includes(lastCall.resultado) && `Llamada finalizada: ${lastCall.resultado}`}
                      </div>
                      <div style={{ fontFamily: C.IN, fontSize: 11, color: C.muted, fontStyle: 'italic' }}>
                        Transcript no disponible — puede ser limitación del plan de Vapi.
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        </div>
      </div>

      {/* In-modal toast */}
      {toastMsg && (
        <div style={{
          position: 'absolute', bottom: 32, left: '50%', transform: 'translateX(-50%)',
          zIndex: 300, background: C.s3, padding: '10px 20px',
          border: `1px solid rgba(120,220,232,0.2)`, fontFamily: C.SG, fontSize: 12, color: C.text,
          animation: 'cobr-fade-in 0.2s ease',
        }}>
          {toastMsg}
        </div>
      )}
    </div>
  );
}

// ─── Create Debtor Modal ───────────────────────────────────────────────────────
function DebtorCreateModal({
  token,
  onClose,
  onCreated,
}: {
  token: string;
  onClose: () => void;
  onCreated: (debtor: Debtor) => void;
}) {
  const [fields, setFields] = useState({
    nombre: '', telefono: '', monto: '', vencimiento: '', notas: '', max_intentos: '5',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setFields(p => ({ ...p, [key]: e.target.value }));

  const handleSubmit = async () => {
    if (!fields.nombre.trim() || !fields.telefono.trim() || !fields.monto || !fields.vencimiento) {
      setError('Nombre, teléfono, monto y vencimiento son obligatorios');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const r = await apiFetch('/api/cobranza/debtors', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nombre: fields.nombre.trim(),
          telefono: fields.telefono.trim(),
          monto: Number(fields.monto),
          vencimiento: fields.vencimiento,
          notas: fields.notas.trim() || null,
          max_intentos: Number(fields.max_intentos) || 5,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        onCreated((data as { debtor: Debtor }).debtor);
        onClose();
      } else {
        setError((data as { detail?: string }).detail || `Error ${r.status}`);
      }
    } catch { setError('Error de conexión'); }
    finally { setSaving(false); }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', background: C.s2,
    border: `1px solid rgba(255,255,255,0.1)`, color: C.text,
    fontFamily: C.IN, fontSize: 13, padding: '9px 12px', outline: 'none',
  };
  const focusStyle = `border-color: rgba(252,152,103,0.5)`;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(13,13,24,0.92)', backdropFilter: 'blur(4px)' }} />
      <div style={{
        position: 'relative', zIndex: 1, width: '100%', maxWidth: 480,
        background: C.s1, border: `1px solid rgba(252,152,103,0.2)`,
        animation: 'cobr-fade-in 0.2s ease',
      }}>
        {/* Header */}
        <div style={{ padding: '18px 24px', borderBottom: `1px solid rgba(255,255,255,0.05)`, background: C.s0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={lbl(C.orange, 9)}>NUEVO DEUDOR</div>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 16, color: C.text, marginTop: 4 }}>Agregar manualmente</div>
          </div>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: C.muted, cursor: 'pointer', fontSize: 16 }}>✕</button>
        </div>
        {/* Form */}
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <div style={{ ...lbl(C.muted, 8), marginBottom: 4 }}>NOMBRE *</div>
              <input style={inputStyle} value={fields.nombre} onChange={set('nombre')} placeholder="Carlos Ramírez" onFocus={e => e.target.setAttribute('style', inputStyle.toString() + focusStyle)} />
            </div>
            <div>
              <div style={{ ...lbl(C.muted, 8), marginBottom: 4 }}>TELÉFONO *</div>
              <input style={inputStyle} value={fields.telefono} onChange={set('telefono')} placeholder="+57 300 1234567" />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <div style={{ ...lbl(C.muted, 8), marginBottom: 4 }}>MONTO COP *</div>
              <input style={inputStyle} type="number" value={fields.monto} onChange={set('monto')} placeholder="2500000" />
            </div>
            <div>
              <div style={{ ...lbl(C.muted, 8), marginBottom: 4 }}>VENCIMIENTO *</div>
              <input style={inputStyle} type="date" value={fields.vencimiento} onChange={set('vencimiento')} />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
            <div>
              <div style={{ ...lbl(C.muted, 8), marginBottom: 4 }}>NOTAS</div>
              <textarea style={{ ...inputStyle, resize: 'vertical' } as React.CSSProperties} rows={2} value={fields.notas} onChange={set('notas')} placeholder="Información adicional…" />
            </div>
            <div>
              <div style={{ ...lbl(C.muted, 8), marginBottom: 4 }}>MÁX. INTENTOS</div>
              <input style={inputStyle} type="number" min={1} max={20} value={fields.max_intentos} onChange={set('max_intentos')} />
            </div>
          </div>
          {error && (
            <div style={{ padding: '8px 12px', background: C.pinkBg, color: C.pink, fontFamily: C.IN, fontSize: 12 }}>
              {error}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
            <button onClick={onClose} style={{ padding: '9px 16px', background: 'transparent', border: `1px solid rgba(255,255,255,0.1)`, color: C.muted, fontFamily: C.SG, fontSize: 11, cursor: 'pointer' }}>
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              style={{ padding: '9px 20px', border: 'none', background: saving ? C.s3 : C.orange, color: C.bg, fontFamily: C.SG, fontWeight: 700, fontSize: 12, cursor: saving ? 'not-allowed' : 'pointer' }}
            >
              {saving ? 'Guardando…' : 'Crear deudor'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Filter pills ─────────────────────────────────────────────────────────────
const FILTERS: { value: EstadoFilter; label: string }[] = [
  { value: null,                label: 'TODOS' },
  { value: 'pendiente',         label: 'PENDIENTE' },
  { value: 'llamando',          label: 'LLAMANDO' },
  { value: 'promesa_de_pago',   label: 'PROMESA' },
  { value: 'pagado',            label: 'PAGADO' },
  { value: 'sin_contacto',      label: 'SIN CONTACTO' },
  { value: 'escalado',          label: 'ESCALADO' },
  { value: 'agotado',           label: 'AGOTADO' },
  { value: 'pausado',           label: 'PAUSADO' },
];

// ─── Onboarding step types ────────────────────────────────────────────────────
type OnboardingStep = 'describe' | 'review' | 'upload';

interface Estrategia {
  tono: string;
  frecuencia_dias: number;
  max_intentos: number;
  guion: { saludo: string; propuesta: string; objeciones: string; cierre: string };
}

// ─── Onboarding view ─────────────────────────────────────────────────────────
function CobranzaOnboarding({ token, onDone }: { token: string; onDone: () => void }) {
  const [step, setStep] = useState<OnboardingStep>('describe');
  const [descripcion, setDescripcion] = useState('');
  const [estrategia, setEstrategia] = useState<Estrategia | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uploadingCsv, setUploadingCsv] = useState(false);
  const [csvResult, setCsvResult] = useState<{ created: number } | null>(null);
  const csvRef = useRef<HTMLInputElement>(null);

  const handleStart = async () => {
    if (!descripcion.trim()) return;
    setLoading(true);
    setError('');
    try {
      const r = await apiFetch('/api/cobranza/onboarding/start', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ descripcion }),
      });
      const data = await r.json();
      if (!r.ok) { setError(data.detail || 'Error al generar la estrategia'); return; }
      setEstrategia(data.estrategia);
      setStep('review');
    } catch { setError('Error de conexión'); }
    finally { setLoading(false); }
  };

  const handleApprove = async () => {
    if (!estrategia) return;
    setLoading(true);
    setError('');
    try {
      const r = await apiFetch('/api/cobranza/onboarding/approve', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ estrategia }),
      });
      if (!r.ok) { const d = await r.json(); setError(d.detail || 'Error al guardar'); return; }
      setStep('upload');
    } catch { setError('Error de conexión'); }
    finally { setLoading(false); }
  };

  const handleCsvOnboarding = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setUploadingCsv(true);
    setCsvResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await apiFetch('/api/cobranza/debtors/csv', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await r.json().catch(() => ({})) as { created?: number };
      if (r.ok) setCsvResult({ created: data.created ?? 0 });
    } catch { /* non-fatal */ }
    finally { setUploadingCsv(false); }
  };

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '40px 28px' }}>
      {/* Header */}
      <div style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ ...lbl(C.orange, 10), marginBottom: 8 }}>CONFIGURACIÓN INICIAL</div>
        <h1 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 26, letterSpacing: '-0.03em', color: C.text, margin: 0 }}>
          Configura tu agente de cobranza
        </h1>
        <p style={{ fontFamily: C.IN, fontSize: 13, color: C.muted, marginTop: 8 }}>
          Cuéntale a la IA cómo es tu cartera y generará una estrategia de llamadas personalizada.
        </p>

        {/* Step indicator */}
        {(() => {
          const steps: OnboardingStep[] = ['describe', 'review', 'upload'];
          const labels = ['Describir cartera', 'Revisar estrategia', 'Subir cartera'];
          const currentIdx = steps.indexOf(step);
          return (
            <div style={{ display: 'flex', gap: 8, marginTop: 20, marginBottom: 32 }}>
              {steps.map((s, i) => (
                <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: C.SG, fontSize: 11, fontWeight: 700,
                    background: step === s ? C.orange : (i < currentIdx ? C.green : C.s3),
                    color: step === s || i < currentIdx ? C.bg : C.muted,
                  }}>{i + 1}</div>
                  <span style={{ fontFamily: C.IN, fontSize: 12, color: step === s ? C.text : C.muted }}>
                    {labels[i]}
                  </span>
                  {i < steps.length - 1 && <span style={{ color: C.faint, fontSize: 12 }}>→</span>}
                </div>
              ))}
            </div>
          );
        })()}

        {/* Step 1 — describe */}
        {step === 'describe' && (
          <div>
            <label style={{ ...lbl(C.muted, 10), display: 'block', marginBottom: 8 }}>
              DESCRIBE TU CARTERA DE COBRO
            </label>
            <textarea
              value={descripcion}
              onChange={e => setDescripcion(e.target.value)}
              placeholder="Ej: Tenemos 200 clientes con pagos vencidos entre 30 y 90 días. Son empresas pequeñas del sector retail. Los montos van de $500k a $5M. Preferimos un tono empático pero firme…"
              rows={6}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: C.s2, border: `1px solid ${descripcion ? 'rgba(252,152,103,0.4)' : C.faint}`,
                borderRadius: 8, color: C.text, fontFamily: C.IN, fontSize: 13,
                padding: '14px 16px', resize: 'vertical', outline: 'none',
                transition: 'border-color 0.15s', lineHeight: 1.6,
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
              <span style={{ fontFamily: C.IN, fontSize: 12, color: C.faint }}>
                {descripcion.length} caracteres · mínimo 30
              </span>
              <button
                onClick={handleStart}
                disabled={loading || descripcion.trim().length < 30}
                style={{
                  padding: '10px 22px', borderRadius: 7, border: 'none', cursor: descripcion.trim().length >= 30 && !loading ? 'pointer' : 'not-allowed',
                  background: descripcion.trim().length >= 30 && !loading ? C.orange : C.s3,
                  color: C.bg, fontFamily: C.SG, fontWeight: 700, fontSize: 13,
                  transition: 'background 0.15s',
                }}
              >
                {loading ? 'Generando…' : 'Generar estrategia →'}
              </button>
            </div>
          </div>
        )}

        {/* Step 2 — review */}
        {step === 'review' && estrategia && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Params row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {[
                { label: 'TONO', value: estrategia.tono, key: 'tono' as const },
                { label: 'FRECUENCIA', value: `Cada ${estrategia.frecuencia_dias} día(s)`, key: null },
                { label: 'MÁX. INTENTOS', value: String(estrategia.max_intentos), key: null },
              ].map(({ label, value }) => (
                <div key={label} style={{ background: C.s2, borderRadius: 8, padding: '12px 14px', border: `1px solid ${C.faint}` }}>
                  <div style={lbl(C.muted, 9)}>{label}</div>
                  <div style={{ fontFamily: C.SG, fontSize: 14, fontWeight: 600, color: C.orange, marginTop: 5 }}>{value}</div>
                </div>
              ))}
            </div>

            {/* Guion sections — editable */}
            <div style={{ ...lbl(C.muted, 10), marginBottom: 4 }}>GUION DE LLAMADA (editable)</div>
            {(['saludo', 'propuesta', 'objeciones', 'cierre'] as const).map(key => (
              <div key={key}>
                <div style={lbl(C.orange, 9)}>{key.toUpperCase()}</div>
                <textarea
                  value={estrategia.guion[key]}
                  onChange={e => setEstrategia(prev => prev ? {
                    ...prev, guion: { ...prev.guion, [key]: e.target.value }
                  } : prev)}
                  rows={3}
                  style={{
                    width: '100%', boxSizing: 'border-box', marginTop: 4,
                    background: C.s2, border: `1px solid ${C.faint}`, borderRadius: 7,
                    color: C.text, fontFamily: C.IN, fontSize: 12, padding: '10px 12px',
                    resize: 'vertical', outline: 'none', lineHeight: 1.6,
                  }}
                />
              </div>
            ))}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
              <button
                onClick={() => setStep('describe')}
                style={{
                  padding: '10px 18px', borderRadius: 7, border: `1px solid ${C.faint}`,
                  background: 'transparent', color: C.muted, fontFamily: C.SG, fontSize: 12, cursor: 'pointer',
                }}
              >← Volver</button>
              <button
                onClick={handleApprove}
                disabled={loading}
                style={{
                  padding: '10px 22px', borderRadius: 7, border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
                  background: loading ? C.s3 : C.green, color: C.bg,
                  fontFamily: C.SG, fontWeight: 700, fontSize: 13, transition: 'background 0.15s',
                }}
              >{loading ? 'Guardando…' : 'Aprobar y activar →'}</button>
            </div>
          </div>
        )}

        {/* Step 3 — upload initial CSV */}
        {step === 'upload' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ background: C.s2, border: `1px solid ${C.cyanBdr}`, borderRadius: 10, padding: '28px 24px', textAlign: 'center' }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>📋</div>
              <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 16, color: C.text, marginBottom: 6 }}>
                Sube tu cartera inicial
              </div>
              <p style={{ fontFamily: C.IN, fontSize: 13, color: C.muted, margin: '0 0 18px', lineHeight: 1.6 }}>
                CSV con columnas: <code style={{ color: C.cyan }}>nombre, telefono, monto, vencimiento</code><br />
                El campo <code style={{ color: C.cyan }}>vencimiento</code> debe ser <code style={{ color: C.cyan }}>YYYY-MM-DD</code>. También puedes omitir esto y subir la cartera después.
              </p>
              <input ref={csvRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvOnboarding} />
              {csvResult ? (
                <div style={{ background: C.greenBg, border: `1px solid rgba(169,220,118,0.3)`, borderRadius: 7, padding: '12px 16px', color: C.green, fontFamily: C.SG, fontWeight: 600, fontSize: 13 }}>
                  {csvResult.created} deudores importados correctamente
                </div>
              ) : (
                <button
                  onClick={() => csvRef.current?.click()}
                  disabled={uploadingCsv}
                  style={{
                    padding: '10px 22px', borderRadius: 7, border: `1px solid ${C.cyanBdr}`,
                    background: C.cyanBg, color: C.cyan,
                    fontFamily: C.SG, fontWeight: 700, fontSize: 13,
                    cursor: uploadingCsv ? 'not-allowed' : 'pointer',
                  }}
                >
                  {uploadingCsv ? 'Subiendo…' : '↑ Seleccionar CSV'}
                </button>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button
                onClick={onDone}
                style={{
                  padding: '10px 18px', borderRadius: 7, border: `1px solid ${C.faint}`,
                  background: 'transparent', color: C.muted, fontFamily: C.SG, fontSize: 12, cursor: 'pointer',
                }}
              >Omitir por ahora</button>
              <button
                onClick={onDone}
                style={{
                  padding: '10px 22px', borderRadius: 7, border: 'none', cursor: 'pointer',
                  background: C.green, color: C.bg,
                  fontFamily: C.SG, fontWeight: 700, fontSize: 13,
                }}
              >Ir al panel →</button>
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 12, padding: '10px 14px', background: C.pinkBg, borderRadius: 7, color: C.pink, fontFamily: C.IN, fontSize: 12 }}>
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main CobranzaTab ─────────────────────────────────────────────────────────
export function CobranzaTab() {
  const { authToken } = useOfficeStore();
  const token = authToken || sessionStorage.getItem('hive_token') || '';

  const [configured, setConfigured] = useState<boolean | null>(null);
  const [debtors, setDebtors] = useState<Debtor[]>([]);
  const [loading, setLoading] = useState(true);
  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>(null);
  const [selectedDebtor, setSelectedDebtor] = useState<Debtor | null>(null);
  const [toasts, setToasts] = useState<CobrToast[]>([]);
  const [uploadingCsv, setUploadingCsv] = useState<false | 'create' | 'update'>(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const csvInputRef = useRef<HTMLInputElement>(null);
  const csvUpdateRef = useRef<HTMLInputElement>(null);

  // ── Toast helpers ──────────────────────────────────────────────────────────
  const dismissToast = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));
  const addToast = (toast: CobrToast, duration = 3500) => {
    setToasts(prev => [...prev.filter(t => t.id !== toast.id), toast]);
    setTimeout(() => dismissToast(toast.id), duration);
  };

  // ── Check if onboarding is done ───────────────────────────────────────────
  useEffect(() => {
    apiFetch('/api/cobranza/status', { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => setConfigured(!!d.configured))
      .catch(() => setConfigured(false));
  }, [token]);

  // ── Fetch debtors ──────────────────────────────────────────────────────────
  const fetchDebtors = useCallback(async () => {
    setLoading(true);
    try {
      const params = estadoFilter ? `?estado=${estadoFilter}` : '';
      const r = await apiFetch(`/api/cobranza/debtors${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) { setDebtors([]); return; }
      const data = await r.json();
      setDebtors(Array.isArray(data) ? data : []);
    } catch { setDebtors([]); }
    finally { setLoading(false); }
  }, [token, estadoFilter]);

  useEffect(() => { fetchDebtors(); }, [fetchDebtors]);

  // ── Real-time WS updates ───────────────────────────────────────────────────
  const fetchDebtorById = useCallback(async (debtor_id: string) => {
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) return null;
      const data = await r.json() as { debtor: Debtor };
      return data.debtor ?? null;
    } catch { return null; }
  }, [token]);

  useEffect(() => {
    const handleDebtorUpdate = async (e: Event) => {
      const event = e as CustomEvent<{ debtor_id: string; estado: Debtor['estado']; intentos?: number }>;
      const { debtor_id, estado, intentos } = event.detail;

      // Update list immediately with partial data
      setDebtors(prev =>
        prev.map(d =>
          d._id === debtor_id
            ? { ...d, estado, ...(intentos !== undefined ? { intentos } : {}) }
            : d
        )
      );

      // Refetch full debtor to get historial_llamadas + transcript
      const full = await fetchDebtorById(debtor_id);
      if (full) {
        setDebtors(prev => prev.map(d => d._id === debtor_id ? full : d));
        setSelectedDebtor(prev => prev && prev._id === debtor_id ? full : prev);
      } else {
        setSelectedDebtor(prev =>
          prev && prev._id === debtor_id
            ? { ...prev, estado, ...(intentos !== undefined ? { intentos } : {}) }
            : prev
        );
      }
    };

    window.addEventListener('cobr:debtor_update', handleDebtorUpdate);
    return () => window.removeEventListener('cobr:debtor_update', handleDebtorUpdate);
  }, [fetchDebtorById]);

  // ── Quick actions ──────────────────────────────────────────────────────────
  const quickAction = async (debtorId: string, path: string, update: Partial<Debtor>) => {
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtorId}/${path}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) {
        setDebtors(prev => prev.map(d => d._id === debtorId ? { ...d, ...update } : d));
      } else {
        const data = await r.json().catch(() => ({}));
        addToast({ id: `err-${Date.now()}`, message: (data as { detail?: string }).detail || `Error ${r.status}`, ok: false });
      }
    } catch {
      addToast({ id: `err-${Date.now()}`, message: 'Error de conexión', ok: false });
    }
  };

  const handleLlamarAhora = (debtorId: string) =>
    quickAction(debtorId, 'llamar-ahora', {}).then(() =>
      addToast({ id: `call-${debtorId}`, message: 'Llamada iniciada', ok: true })
    );

  const handleMarcarPagado = (debtorId: string) =>
    quickAction(debtorId, 'pagar', { estado: 'pagado' }).then(() =>
      addToast({ id: `paid-${debtorId}`, message: 'Marcado como pagado', ok: true })
    );

  const handlePausar = (d: Debtor) => {
    const isPausado = d.estado === 'pausado';
    quickAction(d._id, isPausado ? 'reactivar' : 'pausar', {
      estado: isPausado ? 'pendiente' : 'pausado',
    });
  };

  // ── Modal action handler ───────────────────────────────────────────────────
  const handleModalAction = (id: string, updates: Partial<Debtor>) => {
    if ((updates as { _id?: string })._id === '__deleted__') {
      setDebtors(prev => prev.filter(d => d._id !== id));
    } else {
      setDebtors(prev => prev.map(d => d._id === id ? { ...d, ...updates } : d));
      setSelectedDebtor(prev => prev && prev._id === id ? { ...prev, ...updates } : prev);
    }
  };

  // ── CSV Upload ────────────────────────────────────────────────────────────
  const handleCsvUpload = (mode: 'create' | 'update') => async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setUploadingCsv(mode);
    try {
      const form = new FormData();
      form.append('file', file);
      const r = await apiFetch(`/api/cobranza/debtors/csv?mode=${mode}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await r.json().catch(() => ({})) as { created?: number; updated?: number; errors?: string[] };
      if (r.ok) {
        const msg = mode === 'create'
          ? `${data.created ?? 0} deudores agregados`
          : `${data.updated ?? 0} actualizados, ${data.created ?? 0} nuevos`;
        addToast({ id: `csv-${Date.now()}`, message: msg, ok: true });
        fetchDebtors();
      } else {
        addToast({ id: `csv-err-${Date.now()}`, message: (data as { detail?: string }).detail || `Error ${r.status}`, ok: false });
      }
    } catch {
      addToast({ id: `csv-err-${Date.now()}`, message: 'Error al subir CSV', ok: false });
    } finally {
      setUploadingCsv(false);
    }
  };

  // ── Stats ──────────────────────────────────────────────────────────────────
  const totalMonto  = debtors.reduce((s, d) => s + d.monto, 0);
  const llamandoNow = debtors.filter(d => d.estado === 'llamando').length;
  const promesas    = debtors.filter(d => d.estado === 'promesa_de_pago').length;

  // ── Filtered list ──────────────────────────────────────────────────────────
  const visible = estadoFilter ? debtors.filter(d => d.estado === estadoFilter) : debtors;

  // ── Show onboarding if strategy not yet configured ────────────────────────
  if (configured === null) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.muted, fontFamily: C.IN, fontSize: 13 }}>
      Cargando…
    </div>
  );
  if (!configured) return (
    <CobranzaOnboarding token={token} onDone={() => { setConfigured(true); fetchDebtors(); }} />
  );

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px' }}>

        {/* Page heading */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 22 }}>
          <div>
            <h1 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 28, letterSpacing: '-0.03em', color: C.text }}>
              Cobranza
            </h1>
            <p style={{ fontFamily: C.IN, fontSize: 13, color: C.muted, marginTop: 5 }}>
              Campaña de cobro automatizada con IA — control total de cada deudor.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {/* hidden inputs */}
            <input ref={csvInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvUpload('create')} />
            <input ref={csvUpdateRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvUpload('update')} />
            {/* Nuevo deudor */}
            <button
              onClick={() => setShowCreateModal(true)}
              title="Agregar deudor manualmente"
              style={{
                height: 32, padding: '0 14px', border: `1px solid rgba(169,220,118,0.3)`,
                background: C.greenBg, color: C.green,
                cursor: 'pointer', fontSize: 12,
                fontFamily: C.SG, fontWeight: 600, letterSpacing: '0.05em',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >+ Nuevo</button>
            {/* Agregar CSV */}
            <button
              onClick={() => csvInputRef.current?.click()}
              disabled={!!uploadingCsv}
              title="Agregar nuevos deudores desde CSV"
              style={{
                height: 32, padding: '0 12px', border: `1px solid ${C.cyanBdr}`,
                background: uploadingCsv === 'create' ? C.s2 : C.cyanBg,
                color: uploadingCsv === 'create' ? C.muted : C.cyan,
                cursor: uploadingCsv ? 'not-allowed' : 'pointer', fontSize: 12,
                fontFamily: C.SG, fontWeight: 600, letterSpacing: '0.05em',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              {uploadingCsv === 'create' ? '…' : '↑ Agregar CSV'}
            </button>
            {/* Actualizar CSV */}
            <button
              onClick={() => csvUpdateRef.current?.click()}
              disabled={!!uploadingCsv}
              title="Actualizar deudores existentes por teléfono"
              style={{
                height: 32, padding: '0 12px', border: `1px solid rgba(171,157,242,0.3)`,
                background: uploadingCsv === 'update' ? C.s2 : C.purpleBg,
                color: uploadingCsv === 'update' ? C.muted : C.purple,
                cursor: uploadingCsv ? 'not-allowed' : 'pointer', fontSize: 12,
                fontFamily: C.SG, fontWeight: 600, letterSpacing: '0.05em',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              {uploadingCsv === 'update' ? '…' : '↕ Actualizar CSV'}
            </button>
            <button
              onClick={fetchDebtors}
              title="Refrescar lista"
              style={{
                width: 32, height: 32, border: 'none', background: C.s1, color: C.muted,
                cursor: 'pointer', fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.s3; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = C.s1; }}
            >↺</button>
          </div>
        </div>

        {/* Stats row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 22 }}>
          {[
            { label: 'CARTERA TOTAL', value: formatCOP(totalMonto), color: C.cyan },
            { label: 'EN LLAMADA AHORA', value: String(llamandoNow), color: C.yellow },
            { label: 'PROMESAS ACTIVAS', value: String(promesas), color: C.green },
          ].map(({ label, value, color }) => (
            <div key={label} style={{
              background: C.s1, padding: '14px 18px',
              borderBottom: `2px solid ${color}40`,
            }}>
              <div style={lbl(C.muted, 9)}>{label}</div>
              <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 22, color, marginTop: 6 }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* Filter pills */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 18 }}>
          {FILTERS.map(({ value, label }) => {
            const active = estadoFilter === value;
            const cfg = value ? getEstadoConfig(value) : { color: C.cyan, bg: C.cyanBg };
            return (
              <button
                key={label}
                onClick={() => setEstadoFilter(value)}
                style={{
                  padding: '5px 14px', border: `1px solid ${active ? cfg.color : 'rgba(255,255,255,0.07)'}`,
                  background: active ? cfg.bg : 'transparent',
                  cursor: 'pointer', ...lbl(active ? cfg.color : C.muted, 9),
                  transition: 'all 0.15s',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Table */}
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ background: C.s1, padding: '16px 20px', opacity: 0.5 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <div style={{ width: '20%', height: 10, background: C.s3 }} />
                  <div style={{ width: '15%', height: 10, background: C.s2 }} />
                  <div style={{ width: '15%', height: 10, background: C.s2 }} />
                  <div style={{ width: '12%', height: 10, background: C.s3 }} />
                </div>
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div style={{ background: C.s1, padding: '52px 28px', textAlign: 'center' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>📋</div>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 15, color: C.text, marginBottom: 6 }}>
              {estadoFilter ? `Sin deudores en estado "${estadoFilter}"` : 'No hay deudores en la campaña'}
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, lineHeight: 1.6 }}>
              {estadoFilter
                ? 'Prueba con otro filtro o carga deudores desde el panel de configuración.'
                : 'Carga una lista de deudores para iniciar la campaña de cobro.'}
            </div>
          </div>
        ) : (
          <div style={{ background: C.s0 }}>
            {/* Table header */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '2fr 1fr 1.2fr 1fr 1.2fr auto',
              padding: '10px 16px',
              background: C.s2, gap: 12,
            }}>
              {['NOMBRE', 'MONTO', 'VENCIMIENTO', 'ESTADO', 'ÚLTIMO INTENTO', 'ACCIONES'].map(h => (
                <div key={h} style={lbl(C.muted, 9)}>{h}</div>
              ))}
            </div>

            {/* Table rows */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {visible.map(d => (
                <DebtorRow
                  key={d._id}
                  debtor={d}
                  onView={() => setSelectedDebtor(d)}
                  onLlamar={() => handleLlamarAhora(d._id)}
                  onPagar={() => handleMarcarPagado(d._id)}
                  onPausar={() => handlePausar(d)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selectedDebtor && (
        <DebtorModal
          debtor={selectedDebtor}
          token={token}
          onClose={() => setSelectedDebtor(null)}
          onAction={handleModalAction}
        />
      )}

      {/* Create debtor modal */}
      {showCreateModal && (
        <DebtorCreateModal
          token={token}
          onClose={() => setShowCreateModal(false)}
          onCreated={(debtor) => {
            setDebtors(prev => [debtor, ...prev]);
            addToast({ id: `new-${debtor._id}`, message: `${debtor.nombre} agregado`, ok: true });
          }}
        />
      )}

      {/* Toast stack */}
      {toasts.length > 0 && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 300,
          display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none',
        }}>
          {toasts.map(t => <CobranzaToast key={t.id} toast={t} onDismiss={dismissToast} />)}
        </div>
      )}
    </div>
  );
}

// ─── Debtor row ───────────────────────────────────────────────────────────────
function DebtorRow({
  debtor,
  onView,
  onLlamar,
  onPagar,
  onPausar,
}: {
  debtor: Debtor;
  onView: () => void;
  onLlamar: () => void;
  onPagar: () => void;
  onPausar: () => void;
}) {
  const [hover, setHover] = useState(false);
  const lastCall = debtor.historial_llamadas[debtor.historial_llamadas.length - 1];

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1.2fr 1fr 1.2fr auto',
        padding: '12px 16px', gap: 12, alignItems: 'center',
        background: hover ? C.s2 : 'transparent',
        borderBottom: `1px solid rgba(255,255,255,0.04)`,
        transition: 'background 0.15s', cursor: 'pointer',
      }}
      onClick={onView}
    >
      {/* Nombre */}
      <div>
        <div style={{ fontFamily: C.SG, fontWeight: 600, fontSize: 13, color: C.text }}>
          {debtor.nombre}
        </div>
        <div style={{ fontFamily: C.IN, fontSize: 11, color: C.muted, marginTop: 2 }}>
          {debtor.telefono}
        </div>
      </div>

      {/* Monto */}
      <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13, color: C.text }}>
        {formatCOP(debtor.monto)}
      </div>

      {/* Vencimiento */}
      <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted }}>
        {formatDate(debtor.vencimiento)}
      </div>

      {/* Estado */}
      <div>
        <EstadoBadge estado={debtor.estado} />
      </div>

      {/* Último intento */}
      <div style={{ fontFamily: C.IN, fontSize: 11, color: C.muted }}>
        {lastCall ? formatDate(lastCall.fecha) : '—'}
        {debtor.intentos > 0 && (
          <span style={{ ...lbl(C.muted, 9), marginLeft: 6 }}>
            ({debtor.intentos}/{debtor.max_intentos})
          </span>
        )}
      </div>

      {/* Acciones */}
      <div
        onClick={e => e.stopPropagation()}
        style={{ display: 'flex', gap: 4 }}
      >
        {[
          { title: 'Llamar ahora', icon: '📞', onClick: onLlamar },
          { title: 'Marcar pagado', icon: '✓', onClick: onPagar },
          { title: debtor.estado === 'pausado' ? 'Reactivar' : 'Pausar', icon: debtor.estado === 'pausado' ? '▷' : '⏸', onClick: onPausar },
          { title: 'Ver detalle', icon: '↗', onClick: onView },
        ].map(({ title, icon, onClick }) => (
          <button
            key={title}
            title={title}
            onClick={onClick}
            style={{
              width: 26, height: 26, border: `1px solid rgba(255,255,255,0.08)`,
              background: 'transparent', cursor: 'pointer', color: C.muted, fontSize: 12,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.background = C.s3;
              el.style.color = C.text;
            }}
            onMouseLeave={e => {
              const el = e.currentTarget as HTMLElement;
              el.style.background = 'transparent';
              el.style.color = C.muted;
            }}
          >
            {icon}
          </button>
        ))}
      </div>
    </div>
  );
}

export default CobranzaTab;
