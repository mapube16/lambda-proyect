import { useState, useEffect, useCallback, useRef, memo } from 'react';
import { Button, ActionIcon, CloseButton, UnstyledButton } from '@mantine/core';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';
import { apiFetch } from '../lib/apiFetch';
import { DebtorsSoftSegurosTab } from './DebtorsSoftSegurosTab';

// ─── Inject keyframes once ─────────────────────────────────────────────────────
if (typeof document !== 'undefined' && !document.getElementById('cobr-styles')) {
  const s = document.createElement('style');
  s.id = 'cobr-styles';
  s.textContent = `
    @keyframes cobr-pulse { 0%,100%{opacity:1;box-shadow:0 0 6px #234876} 50%{opacity:0.4;box-shadow:0 0 2px #234876} }
    @keyframes cobr-spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
    @keyframes cobr-fade-in { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }
  `;
  document.head.appendChild(s);
}

// ─── Tokens — paleta corporativa "Ledger Navy + Deep Teal" ─────────────────────
// Un solo acento de marca (purple/cyan = variantes de azul-marino) para toda
// acción/estado informativo; teal queda RESERVADO exclusivamente para señales
// de "en vivo / sincronización" (insignia SoftSeguros, llamada en curso) — no
// compite como un segundo color de marca. Verde/ámbar/rojo son semántica de
// estado (éxito/advertencia/peligro), nunca el acento. Mismos valores que
// mantineTheme.ts — cambiar ahí también si se ajusta la paleta.
const C = {
  bg:        '#F6F6FB',
  s0:        '#FFFFFF',
  s1:        '#FFFFFF',
  s2:        '#FAFAFC',
  s3:        '#F2F2F8',
  s4:        '#E3E3EC',
  text:      '#34343F',
  muted:     '#6B6B7A',
  faint:     '#9696A6',
  cyan:      '#3B6EA5', // azul informativo — misma familia que el navy, un tono más claro
  cyanBg:    '#EAF0F7',
  cyanBdr:   'rgba(59,110,165,0.25)',
  green:     '#157F5B', // éxito
  greenBg:   '#E5F0EA',
  pink:      '#B91C3C', // peligro
  pinkBg:    '#F7E5E8',
  orange:    '#B7791E', // advertencia
  orangeBg:  '#F7EEDC',
  purple:    '#234876', // acento de marca — Ledger Navy
  purpleBg:  '#E7ECF1',
  yellow:    '#B7791E',
  yellowBg:  '#F7EEDC',
  teal:      '#0F6B64', // reservado: solo señales "en vivo / sincronización"
  tealBg:    'rgba(15,107,100,0.08)',
  tealBdr:   'rgba(15,107,100,0.30)',
  border:    '#ECECF3',
  border2:   '#E3E3EC',
  ink:       '#16161D',
  SG:        "'Plus Jakarta Sans', system-ui, sans-serif",
  IN:        "'Plus Jakarta Sans', system-ui, sans-serif",
};

// NIT → nombre comercial de aseguradoras colombianas. El backend solo guarda el
// NIT (aseguradora_nit); este mapa lo traduce al nombre que el usuario reconoce.
// Si el NIT no está aquí, se muestra el NIT tal cual.
const ASEGURADORA_POR_NIT: Record<string, string> = {
  '860002184': 'SURA',
  '890903407': 'SURA',
  '860026182': 'Allianz',
  '860002180': 'Bolívar',
  '860009578': 'Seguros del Estado',
  '860002400': 'Mapfre',
  '860002503': 'La Previsora',
  '860037013': 'Liberty Seguros',
  '860524654': 'AXA Colpatria',
  '860002514': 'Colmena',
  '800240882': 'Equidad Seguros',
  '860028415': 'Mundial Seguros',
  '860009999': 'Solidaria',
};
function nombreAseguradora(nit?: string): string | undefined {
  if (!nit) return undefined;
  const clean = String(nit).replace(/[^\d]/g, '');
  return ASEGURADORA_POR_NIT[clean] || nit;
}

const lbl = (color = C.muted, size = 10): React.CSSProperties => ({
  fontFamily: C.SG, fontSize: size, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.12em', color,
});

// ─── SOFTSEGUROS section (collapsible) ─────────────────────────────────────────
function SoftSegurosSection() {
  const [expanded, setExpanded] = useState(true);
  return (
    <div style={{ marginBottom: 24 }}>
      <UnstyledButton
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          background: C.s0, border: `1px solid rgba(59,110,165,0.18)`,
          padding: '10px 14px', cursor: 'pointer', color: C.cyan,
          fontFamily: C.SG, fontWeight: 600, fontSize: 12, letterSpacing: '0.08em',
        }}
      >
        <span style={{ fontSize: 10, transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}>▶</span>
        DEUDORES SOFTSEGUROS
      </UnstyledButton>
      {expanded && (
        <div style={{ marginTop: 8 }}>
          <DebtorsSoftSegurosTab />
        </div>
      )}
    </div>
  );
}

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
  estado: 'pendiente' | 'llamando' | 'contactado' | 'promesa_de_pago' | 'sin_contacto' |
          'pagado' | 'fallido' | 'escalado' | 'agotado' | 'pausado' | 'reagendado' | 'disputa';
  intentos: number;
  max_intentos: number;
  historial_llamadas: CallRecord[];
  monto_prometido?: number;
  fecha_promesa?: string;
  notas?: string;
  escalado?: boolean;
  // SoftSeguros-owned fields (present only when source === 'softseguros').
  source?: 'manual' | 'softseguros';
  numero_poliza?: string;
  ramo_nombre?: string;
  cliente_documento?: string;
  cliente_celular?: string;
  aseguradora_nit?: string;
  aseguradora_nombre?: string;   // compañía de seguros (para el speech)
  forma_pago?: string;           // Contado / Financiado / Fraccionado / Acuerdo
  objeto_asegurado?: string;     // riesgo asegurado (placa, dirección…)
  fecha_pago?: string;           // vencimiento real de la cuota
  fecha_compromiso?: string;     // fecha acordada con el cliente
  dias_mora?: number;
  edad_cartera?: number;
  numero_cuota?: string | number;
  valor_cuota?: number;
  saldo_pendiente?: number;
  status_softseguros?: string;   // ya_vencidos | proximos_a_vencer
  last_synced?: string;
  // Exclusión de la campaña (informe §2): entidades estatales las gestiona un
  // humano — el bot nunca las marca. Editable (falsos positivos se liberan).
  no_llamar?: boolean;
  no_llamar_motivo?: string;
  tipo_entidad?: 'estatal' | 'privada';
}

type EstadoFilter = Debtor['estado'] | null;

// ─── Estado badge config ────────────────────────────────────────────────────────
function getEstadoConfig(estado: Debtor['estado']): { color: string; bg: string; label: string; pulsing?: boolean } {
  switch (estado) {
    case 'pendiente':        return { color: C.cyan,    bg: C.cyanBg,    label: 'PENDIENTE' };
    case 'llamando':         return { color: C.yellow,  bg: C.yellowBg,  label: 'LLAMANDO',  pulsing: true };
    case 'contactado':       return { color: C.green,   bg: C.greenBg,   label: 'CONTACTADO' };
    case 'promesa_de_pago':  return { color: C.green,   bg: C.greenBg,   label: 'PROMESA' };
    case 'sin_contacto':     return { color: C.muted,   bg: 'transparent', label: 'SIN CONTACTO' };
    case 'pagado':           return { color: C.green,   bg: C.greenBg,   label: 'PAGADO' };
    case 'fallido':          return { color: C.pink,    bg: C.pinkBg,    label: 'FALLIDO' };
    case 'escalado':         return { color: C.orange,  bg: C.orangeBg,  label: 'ESCALADO' };
    case 'agotado':          return { color: C.muted,   bg: 'transparent', label: 'AGOTADO' };
    case 'pausado':          return { color: C.purple,  bg: C.purpleBg,  label: 'PAUSADO' };
    case 'reagendado':       return { color: C.cyan,    bg: C.cyanBg,    label: 'REAGENDADO' };
    case 'disputa':          return { color: C.pink,    bg: C.pinkBg,    label: 'DISPUTA' };
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
      background: C.s3, border: `1px solid ${toast.ok ? 'rgba(21,127,91,0.25)' : 'rgba(185,28,60,0.25)'}`,
      boxShadow: '0 4px 16px rgba(20,20,40,0.10)', pointerEvents: 'all',
      opacity: visible ? 1 : 0, transform: visible ? 'translateX(0)' : 'translateX(12px)',
      transition: 'opacity 0.2s, transform 0.2s',
    }}>
      <span style={{ fontSize: 13, color: toast.ok ? C.green : C.pink, flexShrink: 0 }}>
        {toast.ok ? '✓' : '✕'}
      </span>
      <span style={{ fontFamily: C.SG, fontSize: 12, color: C.text, flex: 1 }}>{toast.message}</span>
      <CloseButton onClick={() => onDismiss(toast.id)} size="sm" c={C.muted} />
    </div>
  );
}

// ─── Detail Modal ──────────────────────────────────────────────────────────────
function DebtorModal({
  debtor,
  onClose,
  onAction,
}: {
  debtor: Debtor;
  onClose: () => void;
  onAction: (id: string, updatedDebtor: Partial<Debtor>) => void;
}) {
  const [notas, setNotas] = useState(debtor.notas || '');
  const [expandedCall, setExpandedCall] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [acting, setActing] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [showLey2300Warning, setShowLey2300Warning] = useState(false);
  const [recordingBlobs, setRecordingBlobs] = useState<Record<string, string>>({});

  // ── Edit mode ────────────────────────────────────────────────────────────
  const [editMode, setEditMode] = useState(false);
  const [editFields, setEditFields] = useState({
    nombre: debtor.nombre,
    telefono: debtor.telefono,
    monto: String(debtor.monto),
    vencimiento: debtor.vencimiento ? debtor.vencimiento.slice(0, 10) : '',
  });

  // ── Load recording blobs with authentication ────────────────────────────
  useEffect(() => {
    const loadRecordings = async () => {
      if (!debtor.historial_llamadas) return;
      const blobs: Record<string, string> = {};
      for (const call of debtor.historial_llamadas) {
        if (call.recording_url && !recordingBlobs[call.call_id]) {
          try {
            const resp = await apiFetch(call.recording_url);
            if (resp.ok) {
              const blob = await resp.blob();
              blobs[call.call_id] = URL.createObjectURL(blob);
            }
          } catch (e) {
            console.error(`Failed to load recording ${call.call_id}:`, e);
          }
        }
      }
      if (Object.keys(blobs).length) setRecordingBlobs(prev => ({ ...prev, ...blobs }));
    };
    loadRecordings();
    return () => {
      Object.values(recordingBlobs).forEach(url => URL.revokeObjectURL(url));
    };
  }, [debtor.historial_llamadas]);

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
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
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

  const handleLlamarAhora = async (force = false) => {
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    let path = isLocal ? 'llamar-ahora?test=true' : 'llamar-ahora';
    if (force) path += isLocal ? '&force=true' : '?force=true';

    setActing(true);
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (r.ok) {
        showToast('Llamada iniciada');
      } else if (r.status === 409) {
        setShowLey2300Warning(true);
      } else {
        const data = await r.json().catch(() => ({}));
        showToast((data as { detail?: string }).detail || `Error ${r.status}`);
      }
    } catch {
      showToast('Error de conexión');
    } finally {
      setActing(false);
    }
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

  const handleToggleNoLlamar = async () => {
    const nuevo = !debtor.no_llamar;
    setActing(true);
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ no_llamar: nuevo }),
      });
      if (r.ok) {
        onAction(debtor._id, { no_llamar: nuevo, tipo_entidad: nuevo ? 'estatal' : 'privada' });
        showToast(nuevo ? 'Excluido: el bot no lo llamará' : 'Liberado: vuelve a la campaña');
      } else {
        showToast('Error al actualizar');
      }
    } catch { showToast('Error de conexión'); }
    finally { setActing(false); }
  };

  const handleSaveNotas = async () => {
    setSaving(true);
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor._id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
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
        style={{ position: 'absolute', inset: 0, background: 'rgba(50,50,90,0.45)', backdropFilter: 'blur(4px)' }}
      />
      {/* Modal container */}
      <div style={{
        position: 'relative', zIndex: 1,
        width: '100%', maxWidth: 960, maxHeight: '90vh',
        background: C.s1, border: `1px solid ${C.border}`, borderRadius: 22,
        boxShadow: '0 20px 60px rgba(0,0,0,.3)',
        display: 'flex', flexDirection: 'column',
        animation: 'cobr-fade-in 0.2s ease',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '22px 24px', background: C.s0,
          borderBottom: `1px solid ${C.border}`,
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
                          border: `1px solid rgba(35,72,118,0.35)`, color: C.text,
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
                          border: `1px solid rgba(35,72,118,0.35)`, color: C.text,
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
                  <h2 style={{ fontFamily: C.SG, fontWeight: 800, fontSize: 20, color: C.ink, letterSpacing: '-0.02em' }}>
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
                <div style={lbl(C.faint, 10)}>Monto</div>
                <div style={{ fontFamily: C.SG, fontWeight: 800, fontSize: 22, color: estadoCfg.color }}>
                  {formatCOP(debtor.monto)}
                </div>
              </div>
            )}
            {editMode ? (
              <>
                <Button onClick={() => setEditMode(false)} variant="default" size="sm">Cancelar</Button>
                <Button onClick={handleSaveEdits} loading={saving} color="indigo" size="sm">Guardar cambios</Button>
              </>
            ) : (
              <Button onClick={() => handleLlamarAhora()} loading={acting} color="indigo" size="sm">
                📞 Llamar
              </Button>
            )}
            <CloseButton onClick={onClose} size="lg" />
          </div>
        </div>

        {/* Body — two columns */}
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', flex: 1, overflow: 'hidden' }}>

          {/* Left panel */}
          <div style={{
            borderRight: `1px solid #ECECF3`,
            overflowY: 'auto', padding: '20px 20px',
            display: 'flex', flexDirection: 'column', gap: 20,
          }}>

            {/* SoftSeguros: póliza + cuota/deuda (todo lo que ARIA necesita para el speech) */}
            {debtor.source === 'softseguros' && (() => {
              const row = (k: string, v: string | undefined) => (v == null || v === '') ? null : (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'baseline' }}>
                  <span style={{ fontFamily: C.IN, fontSize: 12, color: C.faint, flexShrink: 0 }}>{k}</span>
                  <span style={{ fontFamily: C.SG, fontSize: 12.5, fontWeight: 700, color: C.ink, textAlign: 'right' }}>{v}</span>
                </div>
              );
              const cop = (n?: number) => (n != null && n > 0) ? formatCOP(n) : undefined;
              const dt = (d?: string) => d ? formatDate(d) : undefined;
              const mora = debtor.dias_mora ?? debtor.edad_cartera;
              // Mora vs. por-vencer: la fecha de mora sólo aplica si YA venció.
              const venc = debtor.fecha_pago || debtor.vencimiento;
              const hoy = new Date(new Date().toDateString()).getTime();
              const diasParaVencer = venc ? Math.round((new Date(venc + 'T00:00:00').getTime() - hoy) / 86400000) : null;
              let moraLabel = 'Días de mora';
              let moraValue: string | undefined;
              if (mora != null && mora > 0) moraValue = `${mora} días`;
              else if (diasParaVencer != null && diasParaVencer > 0) { moraLabel = 'Vence en'; moraValue = `${diasParaVencer} día${diasParaVencer === 1 ? '' : 's'}`; }
              else if (diasParaVencer === 0) { moraLabel = 'Estado'; moraValue = 'Vence hoy'; }
              else if (diasParaVencer != null && diasParaVencer < 0) moraValue = `${-diasParaVencer} días`;
              return (
                <>
                  <div style={{ padding: 14, background: C.tealBg, border: `1px solid ${C.tealBdr}`, borderRadius: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 11 }}>
                      <span style={{ color: C.teal, display: 'inline-flex', fontSize: 13 }}>🔗</span>
                      <span style={{ ...lbl(C.teal, 9.5) }}>Póliza · SoftSeguros</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                      {row('Nº póliza', debtor.numero_poliza)}
                      {row('Ramo', debtor.ramo_nombre)}
                      {row('Aseguradora', debtor.aseguradora_nombre || nombreAseguradora(debtor.aseguradora_nit))}
                      {row('Riesgo asegurado', debtor.objeto_asegurado)}
                      {row('Forma de pago', debtor.forma_pago)}
                      {row('Documento', debtor.cliente_documento)}
                    </div>
                  </div>
                  <div style={{ padding: 14, background: C.s2, border: `1px solid ${C.border}`, borderRadius: 10 }}>
                    <div style={{ ...lbl(C.muted, 9.5), marginBottom: 11 }}>Cuota y deuda</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                      {row('Nº de cuota', debtor.numero_cuota != null ? String(debtor.numero_cuota) : undefined)}
                      {row('Valor de la cuota', cop(debtor.valor_cuota))}
                      {row('Saldo pendiente', cop(debtor.saldo_pendiente))}
                      {row('Vencimiento', dt(debtor.fecha_pago || debtor.vencimiento))}
                      {row('Compromiso de pago', dt(debtor.fecha_compromiso))}
                      {row(moraLabel, moraValue)}
                    </div>
                  </div>
                </>
              );
            })()}

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
              <div style={{ ...lbl(C.faint, 10), marginBottom: 12 }}>Historial de llamadas</div>
              {debtor.historial_llamadas.length === 0 ? (
                <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, fontStyle: 'italic' }}>
                  Sin llamadas registradas
                </div>
              ) : (
                <div style={{ position: 'relative', paddingLeft: 20 }}>
                  {/* Timeline line */}
                  <div style={{
                    position: 'absolute', left: 7, top: 0, bottom: 0,
                    width: 1, background: '#ECECF3',
                  }} />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {debtor.historial_llamadas.map((call) => (
                      <div key={call.call_id} style={{ position: 'relative' }}>
                        {/* Timeline dot */}
                        <div style={{
                          position: 'absolute', left: -16, top: 3,
                          width: 8, height: 8, background: C.s3,
                          border: `1px solid #D0D0DC`,
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
                            <UnstyledButton
                              onClick={() => setExpandedCall(expandedCall === call.call_id ? null : call.call_id)}
                              style={{ marginTop: 4, cursor: 'pointer', ...lbl(C.cyan, 9) }}
                            >
                              {expandedCall === call.call_id ? '▲ ocultar' : call.transcript ? '▼ ver transcript' : '▼ ver resumen'}
                            </UnstyledButton>
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
                              src={recordingBlobs[call.call_id] || call.recording_url}
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
              <div style={{ ...lbl(C.faint, 10), marginBottom: 8 }}>Notas</div>
              <textarea
                value={notas}
                onChange={e => setNotas(e.target.value)}
                rows={4}
                placeholder="Agregar nota..."
                style={{
                  width: '100%', resize: 'vertical', background: C.s2,
                  border: `1px solid ${C.border2}`, borderRadius: 10, color: C.text,
                  fontFamily: C.IN, fontSize: 12, padding: '10px 12px', outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <Button onClick={handleSaveNotas} loading={saving} variant="light" color="indigo" size="sm" mt={8}>
                Guardar nota
              </Button>
            </div>

            {/* Action grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                { label: 'Editar', onClick: () => setEditMode(true), color: 'orange' },
                { label: 'Marcar pagado', onClick: handlePagar, color: 'green' },
                { label: debtor.estado === 'pausado' ? 'Reactivar' : 'Pausar', onClick: handlePausar, color: 'indigo' },
                { label: 'Eliminar', onClick: handleEliminar, color: 'red' },
                // Exclusión informe §2: entidades estatales / no llamar. Liberar
                // un falso positivo del clasificador también pasa por aquí.
                {
                  label: debtor.no_llamar ? '🏛 Permitir llamadas' : '🏛 No llamar (estatal)',
                  onClick: handleToggleNoLlamar,
                  color: debtor.no_llamar ? 'green' : 'gray',
                },
              ].map(({ label, onClick, color }) => (
                <Button key={label} onClick={onClick} disabled={acting} variant="light" color={color} size="sm">
                  {label}
                </Button>
              ))}
            </div>
          </div>

          {/* Right panel — transcript / last call detail */}
          <div style={{
            overflowY: 'auto', padding: '20px 24px',
            display: 'flex', flexDirection: 'column', gap: 16,
          }}>
            <div style={{ ...lbl(C.faint, 10), borderBottom: `1px solid ${C.border}`, paddingBottom: 12 }}>
              Transcripción última llamada
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
                    borderLeft: `2px solid rgba(59,110,165,0.30)`,
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
                              border: `1px solid ${isAgent ? C.cyanBdr : '#E3E3EC'}`,
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
                        borderLeft: `2px solid #E3E3EC`,
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

      {/* Ley 2300 warning modal */}
      {showLey2300Warning && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 400,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(50,50,90,0.40)', backdropFilter: 'blur(4px)',
        }}>
          <div style={{
            background: C.s1, border: `1px solid ${C.orange}`,
            padding: '28px 32px', maxWidth: 420, width: '90%',
            animation: 'cobr-fade-in 0.2s ease',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <span style={{ fontSize: 22 }}>&#9888;</span>
              <span style={{ fontFamily: C.SG, fontSize: 15, fontWeight: 600, color: C.orange }}>
                Ley 2300 — Contacto duplicado
              </span>
            </div>
            <p style={{ fontFamily: C.IN, fontSize: 13, color: C.text, lineHeight: 1.6, margin: '0 0 8px' }}>
              Este deudor <strong>ya fue contactado hoy</strong>. Volver a llamar puede constituir una
              infracción a la <strong>Ley 2300 de 2023</strong> (máximo 1 contacto por día).
            </p>
            <p style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, lineHeight: 1.5, margin: '0 0 20px' }}>
              Si decides continuar, la responsabilidad del contacto adicional recae sobre el operador.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Button onClick={() => setShowLey2300Warning(false)} variant="default" size="sm">
                Cancelar
              </Button>
              <Button onClick={() => { setShowLey2300Warning(false); handleLlamarAhora(true); }} color="orange" variant="light" size="sm">
                Llamar de todos modos
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* In-modal toast */}
      {toastMsg && (
        <div style={{
          position: 'absolute', bottom: 32, left: '50%', transform: 'translateX(-50%)',
          zIndex: 300, background: C.s3, padding: '10px 20px',
          border: `1px solid rgba(59,110,165,0.22)`, fontFamily: C.SG, fontSize: 12, color: C.text,
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
  onClose,
  onCreated,
}: {
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
        headers: { 'Content-Type': 'application/json' },
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
    border: `1px solid #E3E3EC`, color: C.text,
    fontFamily: C.IN, fontSize: 13, padding: '9px 12px', outline: 'none',
  };
  const focusStyle = `border-color: rgba(35,72,118,0.45)`;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(50,50,90,0.45)', backdropFilter: 'blur(4px)' }} />
      <div style={{
        position: 'relative', zIndex: 1, width: '100%', maxWidth: 480,
        background: C.s1, border: `1px solid rgba(35,72,118,0.22)`,
        animation: 'cobr-fade-in 0.2s ease',
      }}>
        {/* Header */}
        <div style={{ padding: '18px 24px', borderBottom: `1px solid #ECECF3`, background: C.s0, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={lbl(C.orange, 9)}>NUEVO DEUDOR</div>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 16, color: C.text, marginTop: 4 }}>Agregar manualmente</div>
          </div>
          <CloseButton onClick={onClose} size="md" />
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
            <Button onClick={onClose} variant="default" size="sm">
              Cancelar
            </Button>
            <Button onClick={handleSubmit} loading={saving} color="indigo" size="sm">
              Crear deudor
            </Button>
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
  { value: 'contactado',        label: 'CONTACTADO' },
  { value: 'promesa_de_pago',   label: 'PROMESA' },
  { value: 'pagado',            label: 'PAGADO' },
  { value: 'sin_contacto',      label: 'SIN CONTACTO' },
  { value: 'reagendado',        label: 'REAGENDADO' },
  { value: 'disputa',           label: 'DISPUTA' },
  { value: 'escalado',          label: 'ESCALADO' },
  { value: 'agotado',           label: 'AGOTADO' },
  { value: 'pausado',           label: 'PAUSADO' },
];

// Presets de antigüedad de mora (edad_cartera). null = sin umbral.
const MORA_PRESETS: { value: number | null; label: string }[] = [
  { value: null, label: 'Todas' },
  { value: 30,   label: '30+' },
  { value: 60,   label: '60+' },
  { value: 90,   label: '90+' },
  { value: 180,  label: '180+' },
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
function CobranzaOnboarding({ onDone }: { onDone: () => void }) {
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
        headers: { 'Content-Type': 'application/json' },
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
        headers: { 'Content-Type': 'application/json' },
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
                background: C.s2, border: `1px solid ${descripcion ? 'rgba(35,72,118,0.35)' : C.faint}`,
                borderRadius: 8, color: C.text, fontFamily: C.IN, fontSize: 13,
                padding: '14px 16px', resize: 'vertical', outline: 'none',
                transition: 'border-color 0.15s', lineHeight: 1.6,
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
              <span style={{ fontFamily: C.IN, fontSize: 12, color: C.faint }}>
                {descripcion.length} caracteres · mínimo 30
              </span>
              <Button
                onClick={handleStart}
                disabled={descripcion.trim().length < 30}
                loading={loading}
                color="indigo"
                size="sm"
              >
                Generar estrategia →
              </Button>
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
              <Button onClick={() => setStep('describe')} variant="default" size="sm">← Volver</Button>
              <Button onClick={handleApprove} loading={loading} color="green" size="sm">Aprobar y activar →</Button>
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
                <div style={{ background: C.greenBg, border: `1px solid rgba(21,127,91,0.30)`, borderRadius: 7, padding: '12px 16px', color: C.green, fontFamily: C.SG, fontWeight: 600, fontSize: 13 }}>
                  {csvResult.created} deudores importados correctamente
                </div>
              ) : (
                <Button onClick={() => csvRef.current?.click()} loading={uploadingCsv} variant="default" size="sm">
                  ↑ Seleccionar CSV
                </Button>
              )}
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Button onClick={onDone} variant="default" size="sm">Omitir por ahora</Button>
              <Button onClick={onDone} color="green" size="sm">Ir al panel →</Button>
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
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [debtors, setDebtors] = useState<Debtor[]>([]);
  const [loading, setLoading] = useState(true);
  const [estadoFilter, setEstadoFilter] = useState<EstadoFilter>(null);
  const [minMora, setMinMora] = useState<number | null>(null);
  const [sortMora, setSortMora] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const PAGE_SIZE = 50;
  const [selectedDebtor, setSelectedDebtor] = useState<Debtor | null>(null);
  const [toasts, setToasts] = useState<CobrToast[]>([]);
  const [uploadingCsv, setUploadingCsv] = useState<false | 'create' | 'update'>(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [ley2300Confirm, setLey2300Confirm] = useState<string | null>(null); // debtor_id pending confirmation
  const csvInputRef = useRef<HTMLInputElement>(null);
  const csvUpdateRef = useRef<HTMLInputElement>(null);

  // ── Toast helpers ──────────────────────────────────────────────────────────
  const dismissToast = useCallback((id: string) => setToasts(prev => prev.filter(t => t.id !== id)), []);
  const addToast = useCallback((toast: CobrToast, duration = 3500) => {
    setToasts(prev => [...prev.filter(t => t.id !== toast.id), toast]);
    setTimeout(() => dismissToast(toast.id), duration);
  }, [dismissToast]);

  // ── Check if onboarding is done ───────────────────────────────────────────
  useEffect(() => {
    apiFetch('/api/cobranza/status')
      .then(r => r.json())
      .then(d => setConfigured(!!d.configured))
      .catch(() => setConfigured(false));
  }, []);

  // ── Fetch debtors ──────────────────────────────────────────────────────────
  const fetchDebtors = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (estadoFilter) qs.set('estado', estadoFilter);
      if (minMora != null) qs.set('min_mora', String(minMora));
      if (sortMora) qs.set('sort', 'mora');
      qs.set('page', String(page));
      qs.set('page_size', String(PAGE_SIZE));
      const r = await apiFetch(`/api/cobranza/debtors?${qs.toString()}`);
      if (!r.ok) { setDebtors([]); setTotal(0); return; }
      const data = await r.json();
      // Endpoint is now paginated: { items, total, page, page_size }.
      // Tolerate the old array shape just in case.
      if (Array.isArray(data)) {
        setDebtors(data);
        setTotal(data.length);
      } else {
        setDebtors(Array.isArray(data.items) ? data.items : []);
        setTotal(Number(data.total ?? 0));
      }
    } catch { setDebtors([]); setTotal(0); }
    finally { setLoading(false); }
  }, [estadoFilter, minMora, sortMora, page]);

  useEffect(() => { fetchDebtors(); }, [fetchDebtors]);

  // Reset to page 1 whenever a filter/sort changes.
  useEffect(() => { setPage(1); }, [estadoFilter, minMora, sortMora]);

  // ── Today's activity KPIs + funnel (whole-cartera, not the current page) ─────
  const [todayKpis, setTodayKpis] = useState<{
    llamando_ahora: number;
    contactados_hoy: number;
    promesas_hoy: { count: number; monto: number };
    pagado_hoy: { count: number; monto: number };
    sin_contacto: number;
  } | null>(null);
  const fetchTodaySummary = useCallback(async () => {
    try {
      const r = await apiFetch('/api/cobranza/today-summary');
      if (r.ok) setTodayKpis(await r.json());
    } catch { /* keep prev */ }
  }, []);
  useEffect(() => {
    fetchTodaySummary();
    // Only poll while the tab is actually visible — no point hitting the API
    // every 15s in a backgrounded tab. Refetch immediately on re-focus so the
    // user never sees stale numbers when they come back.
    let id: number | null = null;
    const start = () => { if (id === null) id = window.setInterval(fetchTodaySummary, 15000); };
    const stop = () => { if (id !== null) { window.clearInterval(id); id = null; } };
    const onVisibility = () => {
      if (document.hidden) stop();
      else { fetchTodaySummary(); start(); }
    };
    if (!document.hidden) start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => { stop(); document.removeEventListener('visibilitychange', onVisibility); };
  }, [fetchTodaySummary]);

  // ── Máximo de intentos del tenant (informe §3 = 3) — fuente única: config ───
  const [maxIntentos, setMaxIntentos] = useState(3);
  useEffect(() => {
    apiFetch('/api/cobranza/config')
      .then(r => (r.ok ? r.json() : null))
      .then(c => { const m = c?.timings?.max_intentos; if (m) setMaxIntentos(Number(m)); })
      .catch(() => {});
  }, []);

  // ── Paquete de minutos (facturación) ───────────────────────────────────────
  const [minutos, setMinutos] = useState<{
    minutos_comprados: number; minutos_consumidos: number; minutos_restantes: number;
  } | null>(null);
  useEffect(() => {
    apiFetch('/api/cobranza/minutos')
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) setMinutos(d); })
      .catch(() => {});
  }, []);

  // ── Jornada de hoy (informe §2.1: revisión previa + exclusión) ──────────────
  type JornadaItem = {
    _id: string; nombre: string; telefono: string; numero_poliza?: string;
    ramo_nombre?: string; estado: string; monto?: number; dias_mora: number;
    intento: number; hora: string; grupo: 'vence_hoy' | 'preventiva' | 'backlog';
    dentro_cupo: boolean;
  };
  const [jornadaOpen, setJornadaOpen] = useState(false);
  const [jornada, setJornada] = useState<{ fecha: string; total: number; cupo_diario: number; items: JornadaItem[] } | null>(null);
  const [jornadaLoading, setJornadaLoading] = useState(false);
  const fetchJornada = useCallback(async () => {
    setJornadaLoading(true);
    try {
      const r = await apiFetch('/api/cobranza/jornada-hoy');
      if (r.ok) setJornada(await r.json());
    } catch { /* keep prev */ }
    finally { setJornadaLoading(false); }
  }, []);
  useEffect(() => { if (jornadaOpen && !jornada) fetchJornada(); }, [jornadaOpen, jornada, fetchJornada]);
  const excluirDeJornada = useCallback(async (item: JornadaItem) => {
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${item._id}/pausar`, { method: 'POST' });
      if (r.ok) {
        setJornada(prev => prev ? { ...prev, total: prev.total - 1, items: prev.items.filter(i => i._id !== item._id) } : prev);
        addToast({ id: `excl-${item._id}`, message: `${item.nombre} excluido de la jornada (pausado)`, ok: true });
        fetchDebtors();
      }
    } catch { /* noop */ }
  }, [addToast, fetchDebtors]);

  // ── Alertas tipadas (informe §7/§12) ───────────────────────────────────────
  type Alerta = {
    _id: string; tipo: string; detalle?: string; debtor_nombre?: string;
    debtor_telefono?: string; numero_poliza?: string; area?: string;
    responsable?: string; created_at: string;
  };
  const ALERTA_TITULOS: Record<string, string> = {
    asesor_humano: 'Pide un asesor', consulta_fuera_alcance: 'Consulta fuera de alcance',
    oportunidad_comercial: 'Oportunidad comercial', pago_reportado: 'Reporta que ya pagó',
    solicitud_link_cupon: 'Pide link/cupón', opt_out: 'No desea más llamadas',
    numero_equivocado: 'Número equivocado', fecha_estimada_pago: 'Fecha estimada de pago',
    sin_contacto_agotado: 'Agotó intentos sin contacto',
  };
  const [alertasOpen, setAlertasOpen] = useState(false);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [alertasLoading, setAlertasLoading] = useState(false);
  const fetchAlertas = useCallback(async () => {
    setAlertasLoading(true);
    try {
      const r = await apiFetch('/api/cobranza/alertas?solo_pendientes=true');
      if (r.ok) setAlertas((await r.json()).items || []);
    } catch { /* keep prev */ }
    finally { setAlertasLoading(false); }
  }, []);
  useEffect(() => { fetchAlertas(); const id = window.setInterval(fetchAlertas, 60000); return () => window.clearInterval(id); }, [fetchAlertas]);
  const atenderAlerta = useCallback(async (a: Alerta) => {
    try {
      const r = await apiFetch(`/api/cobranza/alertas/${a._id}/atender`, { method: 'POST' });
      if (r.ok) {
        setAlertas(prev => prev.filter(x => x._id !== a._id));
        addToast({ id: `alerta-${a._id}`, message: 'Alerta marcada como atendida', ok: true });
      }
    } catch { /* noop */ }
  }, [addToast]);

  // ── Whole-cartera counts per estado (KPIs) ─────────────────────────────────
  const [funnel, setFunnel] = useState<{ counts: Record<string, number>; total: number } | null>(null);
  const fetchFunnel = useCallback(async () => {
    try {
      const r = await apiFetch('/api/cobranza/funnel');
      if (r.ok) setFunnel(await r.json());
    } catch { /* keep prev */ }
  }, []);
  useEffect(() => { fetchFunnel(); }, [fetchFunnel]);

  // ── SoftSeguros sync status (header pill) ──────────────────────────────────
  const [syncStatus, setSyncStatus] = useState<{ last_sync_at: string | null; is_syncing_now: boolean } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const fetchSyncStatus = useCallback(async () => {
    try {
      const r = await apiFetch('/api/debtors/sync-status');
      if (r.ok) {
        const d = await r.json();
        setSyncStatus({ last_sync_at: d.last_sync_at ?? null, is_syncing_now: !!d.is_syncing_now });
      }
    } catch { /* keep prev */ }
  }, []);
  useEffect(() => { fetchSyncStatus(); }, [fetchSyncStatus]);

  const handleSyncNow = useCallback(async () => {
    setSyncing(true);
    try {
      const r = await apiFetch('/api/debtors/sync-now', { method: 'POST' });
      if (r.ok) {
        addToast({ id: `sync-${Date.now()}`, message: 'Sincronización iniciada', ok: true });
        await fetchSyncStatus();
        await fetchDebtors();
        await fetchFunnel();
      } else {
        const data = await r.json().catch(() => ({}));
        addToast({ id: `sync-err-${Date.now()}`, message: (data as { detail?: string }).detail || `Error ${r.status}`, ok: false });
      }
    } catch {
      addToast({ id: `sync-err-${Date.now()}`, message: 'Error de conexión', ok: false });
    } finally {
      setSyncing(false);
    }
  }, [addToast, fetchSyncStatus, fetchDebtors]);

  const fmtSyncTime = (iso: string | null): string => {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }); }
    catch { return '—'; }
  };

  // ── Real-time WS updates ───────────────────────────────────────────────────
  const fetchDebtorById = useCallback(async (debtor_id: string) => {
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtor_id}`);
      if (!r.ok) return null;
      const data = await r.json() as { debtor: Debtor };
      return data.debtor ?? null;
    } catch { return null; }
  }, []);

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
  const quickAction = useCallback(async (debtorId: string, path: string, update: Partial<Debtor>) => {
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtorId}/${path}`, {
        method: 'POST',
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
  }, [addToast]);

  const handleLlamarAhora = async (debtorId: string) => {
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const path = isLocal ? 'llamar-ahora?test=true' : 'llamar-ahora';
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtorId}/${path}`, { method: 'POST' });
      if (r.ok) {
        addToast({ id: `call-${debtorId}`, message: 'Llamada iniciada', ok: true });
      } else if (r.status === 409) {
        setLey2300Confirm(debtorId);
      } else {
        const data = await r.json().catch(() => ({}));
        addToast({ id: `err-${Date.now()}`, message: (data as { detail?: string }).detail || `Error ${r.status}`, ok: false });
      }
    } catch {
      addToast({ id: `err-${Date.now()}`, message: 'Error de conexión', ok: false });
    }
  };
  // Keep a ref to the latest handleLlamarAhora so the stable row adapter
  // (onRowLlamar) can call it without taking it as a dependency.
  const handleLlamarAhoraRef = useRef(handleLlamarAhora);
  handleLlamarAhoraRef.current = handleLlamarAhora;

  const handleForceLlamar = async () => {
    if (!ley2300Confirm) return;
    const debtorId = ley2300Confirm;
    setLey2300Confirm(null);
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const path = isLocal ? 'llamar-ahora?test=true&force=true' : 'llamar-ahora?force=true';
    try {
      const r = await apiFetch(`/api/cobranza/debtors/${debtorId}/${path}`, { method: 'POST' });
      if (r.ok) {
        addToast({ id: `call-${debtorId}`, message: 'Llamada iniciada', ok: true });
      } else {
        const data = await r.json().catch(() => ({}));
        addToast({ id: `err-${Date.now()}`, message: (data as { detail?: string }).detail || `Error ${r.status}`, ok: false });
      }
    } catch {
      addToast({ id: `err-${Date.now()}`, message: 'Error de conexión', ok: false });
    }
  };

  const handleMarcarPagado = useCallback((debtorId: string) =>
    quickAction(debtorId, 'pagar', { estado: 'pagado' }).then(() =>
      addToast({ id: `paid-${debtorId}`, message: 'Marcado como pagado', ok: true })
    ), [quickAction, addToast]);

  const handlePausar = useCallback((d: Debtor) => {
    const isPausado = d.estado === 'pausado';
    quickAction(d._id, isPausado ? 'reactivar' : 'pausar', {
      estado: isPausado ? 'pendiente' : 'pausado',
    });
  }, [quickAction]);

  // Stable row adapters: DebtorRow passes the whole debtor; these extract the
  // id and stay referentially stable so memo(DebtorRow) actually skips renders.
  const onRowLlamar = useCallback((d: Debtor) => { void handleLlamarAhoraRef.current(d._id); }, []);
  const onRowPagar = useCallback((d: Debtor) => { void handleMarcarPagado(d._id); }, [handleMarcarPagado]);

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
  // Fallback "llamando" count from the current page (used until today-summary loads).
  const llamandoNow = debtors.filter(d => d.estado === 'llamando').length;

  // Whole-cartera KPIs from /funnel (counts) — fall back to the loaded page.
  const fc = funnel?.counts ?? {};
  const carteraCount = funnel?.total ?? total ?? debtors.length;
  const contactados = (fc.contactado ?? 0) + (fc.promesa_de_pago ?? 0) + (fc.pagado ?? 0);
  const promesasActivas = fc.promesa_de_pago ?? 0;
  const pagados = fc.pagado ?? 0;
  // No endpoint returns the cartera-wide monto sum for the mixed (manual + SS)
  // cartera, so this reflects the debtors currently loaded on screen.
  const carteraMontoPage = debtors.reduce((s, d) => s + (d.monto || 0), 0);

  // ── Filtered list ──────────────────────────────────────────────────────────
  // Filtering + pagination are server-side now; `debtors` is already the page.
  const visible = debtors;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // ── Show onboarding if strategy not yet configured ────────────────────────
  if (configured === null) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.muted, fontFamily: C.IN, fontSize: 13 }}>
      Cargando…
    </div>
  );
  if (!configured) return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'auto' }}>
      <div style={{ padding: '26px 28px 0' }}>
        <SoftSegurosSection />
      </div>
      <CobranzaOnboarding onDone={() => { setConfigured(true); fetchDebtors(); }} />
    </div>
  );

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px' }}>

        {/* hidden inputs */}
        <input ref={csvInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvUpload('create')} />
        <input ref={csvUpdateRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleCsvUpload('update')} />

        {/* Page heading (Panel) */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h1 style={{ fontFamily: C.SG, fontWeight: 800, fontSize: 26, letterSpacing: '-0.02em', color: C.ink, margin: 0 }}>
              Cobranza de Voz
            </h1>
            <p style={{ fontFamily: C.IN, fontSize: 14.5, color: C.muted, margin: '6px 0 0' }}>
              Agente IA activo · Ley 2300 — máx. 1 contacto por día
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* SoftSeguros sync pill — only when there is a sync to show */}
            {syncStatus?.last_sync_at && (
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '7px 12px', borderRadius: 999, background: C.tealBg, border: `1px solid ${C.tealBdr}` }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: C.teal, flexShrink: 0, ...(syncStatus.is_syncing_now ? { animation: 'cobr-pulse 1.5s infinite' } : {}) }} />
                <span style={{ fontFamily: C.SG, fontSize: 12, fontWeight: 700, color: C.teal }}>SoftSeguros</span>
                <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted }}>· sinc. {fmtSyncTime(syncStatus.last_sync_at)}</span>
                <ActionIcon onClick={handleSyncNow} disabled={syncing || syncStatus.is_syncing_now} title="Sincronizar ahora" variant="transparent" color="teal" size="sm" ml={2}>
                  <span style={{ display: 'inline-flex', animation: (syncing || syncStatus.is_syncing_now) ? 'cobr-spin 0.8s linear infinite' : 'none', fontSize: 14 }}>↻</span>
                </ActionIcon>
              </div>
            )}
            {/* Secondary CSV tools */}
            <Button
              onClick={() => csvInputRef.current?.click()}
              loading={uploadingCsv === 'create'}
              disabled={!!uploadingCsv}
              title="Agregar nuevos deudores desde CSV"
              variant="default"
              size="sm"
            >
              ↑ CSV
            </Button>
            <Button
              onClick={() => csvUpdateRef.current?.click()}
              loading={uploadingCsv === 'update'}
              disabled={!!uploadingCsv}
              title="Actualizar deudores existentes por teléfono"
              variant="default"
              size="sm"
            >
              ↕ CSV
            </Button>
            <ActionIcon
              onClick={() => { fetchDebtors(); fetchFunnel(); fetchTodaySummary(); }}
              title="Refrescar"
              variant="default"
              size="lg"
            >↺</ActionIcon>
            {/* Agregar deudor (primary) */}
            <Button
              onClick={() => setShowCreateModal(true)}
              title="Agregar deudor manualmente"
              color="indigo"
              size="sm"
            >+ Agregar deudor</Button>
          </div>
        </div>

        {/* KPIs (Panel) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
          {[
            // Solo 2 colores con significado real aquí: navy = la métrica insignia;
            // verde = dinero efectivamente cobrado. El resto son conteos de
            // actividad, no éxitos/alertas — quedan neutros.
            { label: 'Cartera total', value: formatCOP(carteraMontoPage), color: C.purple, big: false },
            { label: 'Contactados', value: `${contactados}/${carteraCount}`, color: C.ink, big: true },
            { label: 'Promesas activas', value: String(promesasActivas), color: C.ink, big: true },
            { label: 'Pagados', value: String(pagados), color: C.green, big: true },
          ].map(({ label, value, color, big }) => (
            <div key={label} className="card" style={{ padding: '16px 18px' }}>
              <div style={lbl(C.faint, 11)}>{label}</div>
              <div style={{ fontFamily: C.SG, fontWeight: 800, fontSize: big ? 28 : 18, color, marginTop: 8, lineHeight: 1.05 }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* Actividad de hoy (backend today-summary) — secondary strip */}
        <div style={{ ...lbl(C.faint, 10), marginBottom: 8 }}>ACTIVIDAD DE HOY</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10, marginBottom: 22 }}>
          {[
            {
              label: 'Minutos',
              value: minutos ? minutos.minutos_restantes.toLocaleString('es-CO') : '—',
              sub: minutos ? `de ${minutos.minutos_comprados.toLocaleString('es-CO')} del paquete` : '',
              // <15% restante = alerta real (ámbar); si no, es un saldo normal (neutro).
              color: minutos && minutos.minutos_restantes < 0.15 * (minutos.minutos_comprados || 1) ? C.orange : C.ink,
              pulse: false,
            },
            {
              label: 'Llamando ahora',
              value: String(todayKpis?.llamando_ahora ?? llamandoNow),
              sub: todayKpis?.llamando_ahora ? 'en vivo' : '',
              // Teal reservado para "en vivo" real — solo se enciende si hay una llamada activa.
              color: (todayKpis?.llamando_ahora ?? llamandoNow) > 0 ? C.teal : C.ink,
              pulse: (todayKpis?.llamando_ahora ?? 0) > 0,
            },
            { label: 'Contactados hoy', value: String(todayKpis?.contactados_hoy ?? '—'), sub: '', color: C.ink, pulse: false },
            { label: 'Promesas hoy', value: String(todayKpis?.promesas_hoy.count ?? '—'), sub: todayKpis ? formatCOP(todayKpis.promesas_hoy.monto) : '', color: C.green, pulse: false },
            { label: 'Pagado hoy', value: String(todayKpis?.pagado_hoy.count ?? '—'), sub: todayKpis ? formatCOP(todayKpis.pagado_hoy.monto) : '', color: C.green, pulse: false },
            { label: 'Sin contacto', value: String(todayKpis?.sin_contacto ?? '—'), sub: 'requiere atención', color: C.orange, pulse: false },
          ].map(({ label, value, sub, color, pulse }) => (
            <div key={label} className="card" style={{ padding: '12px 14px' }}>
              <div style={{ ...lbl(C.faint, 9), display: 'flex', alignItems: 'center', gap: 5 }}>
                {pulse && <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, animation: 'cobr-pulse 1.2s ease-in-out infinite' }} />}
                {label}
              </div>
              <div style={{ fontFamily: C.SG, fontWeight: 800, fontSize: 22, color, marginTop: 5, lineHeight: 1.05 }}>
                {value}
              </div>
              {sub && <div style={{ fontFamily: C.IN, fontSize: 11, color: C.muted, marginTop: 2 }}>{sub}</div>}
            </div>
          ))}
        </div>

        {/* Jornada de hoy (informe §2.1) — revisión previa + exclusión */}
        <div className="card" style={{ marginBottom: 18, overflow: 'hidden' }}>
          <UnstyledButton
            onClick={() => setJornadaOpen(o => !o)}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '13px 18px', cursor: 'pointer',
            }}
          >
            <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13.5, color: C.ink, display: 'flex', alignItems: 'center', gap: 8 }}>
              <ClipboardDocumentListIcon width={16} height={16} style={{ color: C.purple, flexShrink: 0 }} />
              Jornada de hoy
              {jornada && (
                <span style={{ fontFamily: C.IN, fontWeight: 500, fontSize: 12, color: C.muted }}>
                  {jornada.total} programados · cupo {jornada.cupo_diario}/día
                </span>
              )}
            </span>
            <span style={{ color: C.faint, fontSize: 12 }}>
              {jornadaOpen ? '▲ ocultar' : '▼ revisar y excluir antes de la jornada'}
            </span>
          </UnstyledButton>
          {jornadaOpen && (
            <div style={{ borderTop: `1px solid ${C.border}`, maxHeight: 380, overflowY: 'auto' }}>
              {jornadaLoading ? (
                <div style={{ padding: 18, fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>Calculando la jornada…</div>
              ) : !jornada || jornada.items.length === 0 ? (
                <div style={{ padding: 18, fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
                  No hay llamadas programadas para hoy.
                </div>
              ) : (
                jornada.items.map((it, idx) => {
                  const grupoBadge = it.grupo === 'vence_hoy'
                    ? { txt: 'VENCE HOY', color: C.orange, bg: C.orangeBg }
                    : it.grupo === 'preventiva'
                      ? { txt: 'PREVENTIVA', color: C.teal, bg: C.tealBg }
                      : { txt: `${it.dias_mora} D MORA`, color: C.pink, bg: C.pinkBg };
                  return (
                    <div key={it._id} style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '9px 18px',
                      borderBottom: `1px solid ${C.border}`,
                      opacity: it.dentro_cupo ? 1 : 0.45,
                    }}>
                      <span style={{ fontFamily: C.SG, fontSize: 11, color: C.faint, width: 26 }}>{idx + 1}.</span>
                      <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 10, color: grupoBadge.color, background: grupoBadge.bg, borderRadius: 5, padding: '2px 7px', whiteSpace: 'nowrap' }}>
                        {grupoBadge.txt}
                      </span>
                      <span style={{ fontFamily: C.SG, fontWeight: 600, fontSize: 12.5, color: C.ink, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {it.nombre}
                      </span>
                      <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, whiteSpace: 'nowrap' }}>
                        {it.telefono} · intento {it.intento} · {it.hora}
                        {!it.dentro_cupo && ' · fuera de cupo'}
                      </span>
                      <Button
                        size="xs"
                        variant="subtle"
                        color="red"
                        onClick={() => excluirDeJornada(it)}
                        title="Excluir de la jornada (pausa el deudor; se reactiva desde la tabla)"
                      >✕ Excluir</Button>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* Alertas tipadas (informe §7) — link/cupón, ya pagó, opt-out, número
            equivocado, fecha de pago, oportunidad comercial, agotó intentos */}
        <div className="card" style={{ marginBottom: 18, overflow: 'hidden' }}>
          <UnstyledButton
            onClick={() => setAlertasOpen(o => !o)}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '13px 18px', cursor: 'pointer',
            }}
          >
            <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13.5, color: C.ink, display: 'flex', alignItems: 'center', gap: 8 }}>
              🔔 Alertas
              {alertas.length > 0 && (
                <span style={{ fontFamily: C.SG, fontWeight: 800, fontSize: 11, color: '#fff', background: C.pink, borderRadius: 999, padding: '1px 8px' }}>
                  {alertas.length}
                </span>
              )}
            </span>
            <span style={{ color: C.faint, fontSize: 12 }}>
              {alertasOpen ? '▲ ocultar' : '▼ revisar y validar'}
            </span>
          </UnstyledButton>
          {alertasOpen && (
            <div style={{ borderTop: `1px solid ${C.border}`, maxHeight: 380, overflowY: 'auto' }}>
              {alertasLoading ? (
                <div style={{ padding: 18, fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>Cargando…</div>
              ) : alertas.length === 0 ? (
                <div style={{ padding: 18, fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
                  Sin alertas pendientes.
                </div>
              ) : (
                alertas.map(a => (
                  <div key={a._id} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '9px 18px',
                    borderBottom: `1px solid ${C.border}`,
                  }}>
                    <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 10, color: C.orange, background: C.orangeBg, borderRadius: 5, padding: '2px 7px', whiteSpace: 'nowrap' }}>
                      {ALERTA_TITULOS[a.tipo] || a.tipo}
                    </span>
                    <span style={{ fontFamily: C.SG, fontWeight: 600, fontSize: 12.5, color: C.ink, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {a.debtor_nombre || 'N/D'}
                    </span>
                    <span style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, whiteSpace: 'nowrap', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {a.detalle || (a.responsable ? `→ ${a.responsable}` : '')}
                    </span>
                    <Button size="xs" variant="subtle" color="green" onClick={() => atenderAlerta(a)}>
                      ✓ Atender
                    </Button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Filter pills (Panel) */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 18 }}>
          {FILTERS.map(({ value, label }) => {
            const active = estadoFilter === value;
            const count = value ? (funnel?.counts?.[value] ?? null) : (funnel?.total ?? null);
            return (
              <Button
                key={label}
                size="xs"
                radius="xl"
                variant={active ? 'filled' : 'outline'}
                color="indigo"
                onClick={() => setEstadoFilter(value)}
              >
                {label.charAt(0) + label.slice(1).toLowerCase()}
                {count !== null && <span style={{ opacity: 0.7 }}>&nbsp;({count})</span>}
              </Button>
            );
          })}
        </div>

        {/* Mora filter + sort — priorizar a los más morosos para llamar primero */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 18, alignItems: 'center' }}>
          <span style={{ ...lbl(C.faint, 10), marginRight: 2 }}>DÍAS DE MORA</span>
          {MORA_PRESETS.map(({ value, label }) => {
            const active = minMora === value;
            return (
              <Button
                key={label}
                size="xs"
                radius="xl"
                variant={active ? 'filled' : 'outline'}
                color="indigo"
                onClick={() => setMinMora(value)}
              >
                {label}
              </Button>
            );
          })}
          <div style={{ width: 1, height: 18, background: C.border, margin: '0 6px' }} />
          <Button
            size="xs"
            radius="xl"
            variant={sortMora ? 'filled' : 'outline'}
            color="indigo"
            onClick={() => setSortMora(s => !s)}
            title="Ordenar por antigüedad de mora (mayor primero)"
          >
            {sortMora ? '↓ Mayor mora primero' : 'Ordenar por mora'}
          </Button>
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
          <div className="card" style={{ padding: '52px 28px', textAlign: 'center' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>📋</div>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 15, color: C.ink, marginBottom: 6 }}>
              {estadoFilter ? `Sin deudores en estado "${estadoFilter}"` : 'No hay deudores en la campaña'}
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, lineHeight: 1.6 }}>
              {estadoFilter
                ? 'Prueba con otro filtro o carga deudores desde el panel de configuración.'
                : 'Carga una lista de deudores para iniciar la campaña de cobro.'}
            </div>
          </div>
        ) : (
          <div className="card" style={{ overflow: 'hidden' }}>
            {/* Table header */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1.9fr 1fr 1fr 0.9fr 0.9fr 0.7fr 96px',
              padding: '10px 20px',
              background: C.s2, gap: 12, borderBottom: `1px solid ${C.border}`,
            }}>
              {['DEUDOR', 'MONTO', 'VENCIMIENTO', 'MORA', 'ESTADO', 'INTENTOS', 'ACCIÓN'].map(h => (
                <div key={h} style={lbl(C.faint, 10.5)}>{h}</div>
              ))}
            </div>

            {/* Table rows */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {visible.map(d => (
                <DebtorRow
                  key={d._id}
                  debtor={d}
                  maxIntentos={maxIntentos}
                  onView={setSelectedDebtor}
                  onLlamar={onRowLlamar}
                  onPagar={onRowPagar}
                  onPausar={handlePausar}
                />
              ))}
            </div>
          </div>
        )}

        {/* Pagination */}
        {total > PAGE_SIZE && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, fontFamily: C.IN, fontSize: 12, color: C.muted, gap: 12, flexWrap: 'wrap' }}>
            <div>
              Mostrando {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} de {total.toLocaleString('es-CO')}
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <Button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} variant="default" size="xs">← Anterior</Button>
              <span style={{ padding: '6px 10px', fontFamily: C.SG, fontSize: 12, color: C.text }}>{page} / {totalPages}</span>
              <Button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} variant="default" size="xs">Siguiente →</Button>
            </div>
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selectedDebtor && (
        <DebtorModal
          debtor={selectedDebtor}

          onClose={() => setSelectedDebtor(null)}
          onAction={handleModalAction}
        />
      )}

      {/* Create debtor modal */}
      {showCreateModal && (
        <DebtorCreateModal

          onClose={() => setShowCreateModal(false)}
          onCreated={(debtor) => {
            setDebtors(prev => [debtor, ...prev]);
            addToast({ id: `new-${debtor._id}`, message: `${debtor.nombre} agregado`, ok: true });
          }}
        />
      )}

      {/* Ley 2300 confirmation modal (list view) */}
      {ley2300Confirm && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 500,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(50,50,90,0.40)', backdropFilter: 'blur(4px)',
        }}>
          <div style={{
            background: C.s1, border: `1px solid ${C.orange}`,
            padding: '28px 32px', maxWidth: 420, width: '90%',
            animation: 'cobr-fade-in 0.2s ease',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <span style={{ fontSize: 22 }}>&#9888;</span>
              <span style={{ fontFamily: C.SG, fontSize: 15, fontWeight: 600, color: C.orange }}>
                Ley 2300 — Contacto duplicado
              </span>
            </div>
            <p style={{ fontFamily: C.IN, fontSize: 13, color: C.text, lineHeight: 1.6, margin: '0 0 8px' }}>
              Este deudor <strong>ya fue contactado hoy</strong>. Volver a llamar puede constituir una
              infracción a la <strong>Ley 2300 de 2023</strong> (máximo 1 contacto por día).
            </p>
            <p style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, lineHeight: 1.5, margin: '0 0 20px' }}>
              Si decides continuar, la responsabilidad del contacto adicional recae sobre el operador.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <Button onClick={() => setLey2300Confirm(null)} variant="default" size="sm">
                Cancelar
              </Button>
              <Button onClick={handleForceLlamar} color="orange" variant="light" size="sm">
                Llamar de todos modos
              </Button>
            </div>
          </div>
        </div>
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
const DebtorRow = memo(function DebtorRow({
  debtor,
  maxIntentos,
  onView,
  onLlamar,
  onPagar,
  onPausar,
}: {
  debtor: Debtor;
  maxIntentos: number;
  // Handlers take the debtor so the parent can pass stable (useCallback)
  // references — no fresh inline arrow per row, so memo actually holds.
  onView: (d: Debtor) => void;
  onLlamar: (d: Debtor) => void;
  onPagar: (d: Debtor) => void;
  onPausar: (d: Debtor) => void;
}) {
  const [hover, setHover] = useState(false);
  const isSS = debtor.source === 'softseguros';

  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '1.9fr 1fr 1fr 0.9fr 0.9fr 0.7fr 96px',
        padding: '14px 20px', gap: 12, alignItems: 'center',
        background: hover ? C.s2 : 'transparent',
        borderBottom: `1px solid ${C.border}`,
        transition: 'background 0.15s', cursor: 'pointer',
      }}
      onClick={() => onView(debtor)}
    >
      {/* Deudor */}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 13.5, color: C.ink }}>
          {debtor.nombre}
        </div>
        <div style={{ fontFamily: C.IN, fontSize: 12, color: C.faint, marginTop: 2, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span>{debtor.telefono}</span>
          {isSS && debtor.ramo_nombre && (
            <span style={{ fontFamily: C.SG, fontSize: 10, fontWeight: 700, color: C.teal, background: C.tealBg, borderRadius: 5, padding: '1px 6px' }}>
              {debtor.ramo_nombre}
            </span>
          )}
          {debtor.no_llamar && (
            <span
              title="Entidad estatal / excluido — el bot no lo llama; gestión manual (informe §2). Se puede liberar desde el detalle."
              style={{ fontFamily: C.SG, fontSize: 10, fontWeight: 700, color: C.muted, background: C.s3, border: `1px solid ${C.border2}`, borderRadius: 5, padding: '1px 6px' }}
            >
              🏛 NO LLAMAR
            </span>
          )}
          {isSS && debtor.numero_poliza && <span>· {debtor.numero_poliza}</span>}
        </div>
      </div>

      {/* Monto */}
      <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.ink }}>
        {formatCOP(debtor.monto)}
      </div>

      {/* Vencimiento */}
      <div style={{ fontFamily: C.IN, fontSize: 13, color: C.text }}>
        {formatDate(debtor.vencimiento)}
      </div>

      {/* Mora — valor siempre visible: días en mora (rojo si alto), o cuánto */}
      {/* falta para vencer. El dato viene de edad_cartera del cURL. */}
      <div>
        {(() => {
          const mora = debtor.dias_mora ?? debtor.edad_cartera ?? 0;
          if (mora > 0) {
            const alto = mora >= 60;
            return (
              <span style={{ fontFamily: C.SG, fontWeight: 800, fontSize: 12.5, color: alto ? C.pink : C.orange, background: alto ? C.pinkBg : C.orangeBg, borderRadius: 6, padding: '2px 8px', whiteSpace: 'nowrap' }}>
                {mora} {mora === 1 ? 'día' : 'días'}
              </span>
            );
          }
          // Sin mora: cuánto falta para el vencimiento (próximo a vencer).
          const v = debtor.vencimiento ? new Date(debtor.vencimiento) : null;
          if (v && !isNaN(v.getTime())) {
            const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
            v.setHours(0, 0, 0, 0);
            const dias = Math.round((v.getTime() - hoy.getTime()) / 86400000);
            const txt = dias === 0 ? 'vence hoy' : dias > 0 ? `en ${dias} ${dias === 1 ? 'día' : 'días'}` : 'al día';
            return <span style={{ fontFamily: C.IN, fontSize: 12, color: C.muted, whiteSpace: 'nowrap' }}>{txt}</span>;
          }
          return <span style={{ fontFamily: C.IN, fontSize: 12, color: C.faint }}>—</span>;
        })()}
      </div>

      {/* Estado */}
      <div>
        <EstadoBadge estado={debtor.estado} />
      </div>

      {/* Intentos — máximo desde la config del tenant (informe §3 = 3) */}
      <div style={{ fontFamily: C.IN, fontSize: 13, color: C.muted }}>
        {debtor.intentos}/{maxIntentos}
      </div>

      {/* Acción — Llamar primary; pagar/pausar surface on hover */}
      <div onClick={e => e.stopPropagation()} style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 4 }}>
        {hover && (
          <>
            <ActionIcon
              variant="subtle"
              color="green"
              size="sm"
              title="Marcar pagado"
              onClick={() => onPagar(debtor)}
            >✓</ActionIcon>
            <ActionIcon
              variant="subtle"
              color="indigo"
              size="sm"
              title={debtor.estado === 'pausado' ? 'Reactivar' : 'Pausar'}
              onClick={() => onPausar(debtor)}
            >{debtor.estado === 'pausado' ? '▷' : '⏸'}</ActionIcon>
          </>
        )}
        <Button
          size="xs"
          radius="xl"
          variant="light"
          color="indigo"
          title="Llamar ahora"
          onClick={() => onLlamar(debtor)}
        >
          📞 Llamar
        </Button>
      </div>
    </div>
  );
});

export default CobranzaTab;
