import { useState, useEffect } from 'react';
import { apiFetch } from '../lib/apiFetch';

// ─── Tokens (same palette as CobranzaTab) ──────────────────────────────────────
const C = {
  bg: '#F6F6FB', s0: '#FFFFFF', s2: '#FAFAFC', s3: '#F2F2F8', s4: '#E3E3EC',
  text: '#34343F', muted: '#6B6B7A', faint: '#9696A6',
  cyan: '#0EA5E9', cyanBg: 'rgba(14,165,233,0.08)',
  green: '#15A56A', greenBg: '#E6F6EE', pink: '#E03E4C', pinkBg: '#FCE9EA',
  orange: '#D97A06', orangeBg: '#FCF1E0', purple: '#4F46E5', purpleBg: '#EEEDFC',
  border: '#ECECF3',
  SG: "'Plus Jakarta Sans', system-ui, sans-serif",
};

const lbl: React.CSSProperties = {
  fontFamily: C.SG, fontSize: 10.5, fontWeight: 700, letterSpacing: '0.06em',
  textTransform: 'uppercase', color: C.faint,
};
const inputStyle: React.CSSProperties = {
  width: '100%', boxSizing: 'border-box', background: C.s0,
  border: `1px solid ${C.border}`, borderRadius: 8, color: C.text,
  fontFamily: C.SG, fontSize: 13, padding: '9px 11px', outline: 'none',
};

type Block = Record<string, any>;
interface Cfg {
  softseguros_cartera?: Block;
  timings?: Block;
  horarios?: Block;
  volumen?: Block;
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ background: C.s0, border: `1px solid ${C.border}`, borderRadius: 14, padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <div style={{ fontFamily: C.SG, fontSize: 14.5, fontWeight: 700, color: C.text }}>{title}</div>
        {hint && <div style={{ fontFamily: C.SG, fontSize: 12, color: C.muted, marginTop: 2 }}>{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <label style={{ ...lbl }}>{label}</label>
      {children}
      {hint && <div style={{ fontFamily: C.SG, fontSize: 11, color: C.faint }}>{hint}</div>}
    </div>
  );
}

const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 };

export function CobranzaSettings() {
  const [cfg, setCfg] = useState<Cfg>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ t: string; ok: boolean } | null>(null);
  const [manualDesde, setManualDesde] = useState('');

  useEffect(() => { void load(); }, []);
  async function load() {
    setLoading(true);
    try {
      const r = await apiFetch('/api/cobranza/config');
      if (r.ok) setCfg((await r.json()) || {});
    } finally { setLoading(false); }
  }

  const cartera = cfg.softseguros_cartera || {};
  const timings = cfg.timings || {};
  const horarios = cfg.horarios || {};
  const volumen = cfg.volumen || {};
  const franjas: string[][] = horarios.franjas || [];

  function setBlock(block: keyof Cfg, patch: Block) {
    setCfg(c => ({ ...c, [block]: { ...(c[block] || {}), ...patch } }));
  }
  function setFranjas(next: string[][]) { setBlock('horarios', { franjas: next }); }

  async function save() {
    setSaving(true); setMsg(null);
    // offsets viene como texto "−1, 0, 2" -> list[int]
    const offsetsRaw = (timings as any)._offsets_text;
    const offsets = offsetsRaw != null
      ? String(offsetsRaw).split(',').map(s => parseInt(s.trim(), 10)).filter(n => !Number.isNaN(n))
      : timings.offsets_intentos_dias_habiles;
    const body: Cfg = {
      softseguros_cartera: cartera.sede ? cartera : undefined,
      timings: { ...timings, offsets_intentos_dias_habiles: offsets, _offsets_text: undefined },
      horarios,
      volumen,
    };
    // limpiar undefined/_helpers
    Object.keys(body).forEach(k => { if (body[k as keyof Cfg] == null) delete body[k as keyof Cfg]; });
    if (body.timings) delete (body.timings as any)._offsets_text;
    try {
      const r = await apiFetch('/api/cobranza/config', {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      if (r.ok) { const d = await r.json(); setCfg(d.cobranza || cfg); setMsg({ t: 'Configuración guardada ✓', ok: true }); }
      else { const d = await r.json().catch(() => ({})); setMsg({ t: (d as any).detail || 'Error al guardar', ok: false }); }
    } catch { setMsg({ t: 'Error de conexión', ok: false }); }
    finally { setSaving(false); }
  }

  async function sincronizar(override: Block | null) {
    setMsg({ t: override ? 'Carga manual iniciada…' : 'Sincronizando…', ok: true });
    try {
      const r = await apiFetch('/api/cobranza/sincronizar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override_filters: override }),
      });
      if (r.ok) setMsg({ t: override ? 'Carga manual iniciada — se está trayendo la cartera.' : 'Sync iniciado — actualizando la cola.', ok: true });
      else setMsg({ t: 'Error al sincronizar', ok: false });
    } catch { setMsg({ t: 'Error de conexión', ok: false }); }
  }

  const num = (v: any) => (v === '' || v == null ? '' : v);
  const btn = (bg: string): React.CSSProperties => ({
    padding: '10px 18px', border: 'none', borderRadius: 9, background: bg, color: '#fff',
    fontFamily: C.SG, fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
  });

  if (loading) return <div style={{ padding: 24, fontFamily: C.SG, color: C.muted }}>Cargando configuración…</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 780 }}>
      {/* Header + acciones */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontFamily: C.SG, fontSize: 18, fontWeight: 800, color: C.text }}>Configuración de cobranza</div>
          <div style={{ fontFamily: C.SG, fontSize: 12.5, color: C.muted }}>Ajusta los parámetros de tu operación. Un sync corre solo cada día detrás.</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => sincronizar(null)} style={{ ...btn(C.cyan) }}>Sincronizar ahora</button>
          <button onClick={save} disabled={saving} style={{ ...btn(C.purple), opacity: saving ? 0.6 : 1 }}>{saving ? 'Guardando…' : 'Guardar cambios'}</button>
        </div>
      </div>

      {msg && (
        <div style={{ padding: '10px 14px', borderRadius: 9, fontFamily: C.SG, fontSize: 13,
          background: msg.ok ? C.greenBg : C.pinkBg, color: msg.ok ? C.green : C.pink }}>{msg.t}</div>
      )}

      {/* Ingesta / cartera */}
      <Section title="Ingesta de cartera (Softseguros)" hint="De qué deuda se arma la cola. La ventana de fecha define cuánta mora se cobra.">
        <div style={grid2}>
          <Field label="Sede" hint="Obligatorio (identificador de la sucursal en Softseguros)">
            <input style={inputStyle} type="number" value={num(cartera.sede)} onChange={e => setBlock('softseguros_cartera', { sede: e.target.value ? Number(e.target.value) : '' })} />
          </Field>
          <Field label="Anticipación (días)" hint="Llamada preventiva antes del vencimiento">
            <input style={inputStyle} type="number" value={num(cartera.ventana_proximos_dias)} onChange={e => setBlock('softseguros_cartera', { ventana_proximos_dias: Number(e.target.value) })} />
          </Field>
          <Field label="Cartera vencida desde" hint="Vencimientos a partir de esta fecha">
            <input style={inputStyle} type="date" value={cartera.fecha_desde || ''} onChange={e => setBlock('softseguros_cartera', { fecha_desde: e.target.value })} />
          </Field>
          <Field label="Hasta (fija — solo arranque)" hint="Techo fijo de compromisos. Déjala solo durante la evacuación inicial.">
            <input style={inputStyle} type="date" value={cartera.fecha_hasta || ''} onChange={e => setBlock('softseguros_cartera', { fecha_hasta: e.target.value })} />
          </Field>
          <Field label="Hasta rodante (días hábiles)" hint="Régimen: hoy + N hábiles, se recalcula cada sync y la cola se rellena sola. Si se define, manda sobre la fija.">
            <input style={inputStyle} type="number" min={0} max={30} placeholder="ej: 1"
              value={cartera.fecha_hasta_rodante_dias ?? ''}
              onChange={e => setBlock('softseguros_cartera', { fecha_hasta_rodante_dias: e.target.value === '' ? null : Number(e.target.value) })} />
          </Field>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: C.SG, fontSize: 13, color: C.text, cursor: 'pointer' }}>
          <input type="checkbox" checked={cartera.solo_no_recaudadas !== false} onChange={e => setBlock('softseguros_cartera', { solo_no_recaudadas: e.target.checked })} />
          Solo deuda no pagada (cola viva)
        </label>
      </Section>

      {/* Secuencia de intentos */}
      <Section title="Secuencia de llamadas" hint="Cuántos intentos, en qué días hábiles relativos al vencimiento, y por qué fecha se agenda.">
        <div style={grid2}>
          <Field label="Días hábiles de los 3 intentos" hint="Ej: −1, 0, 2  (día antes, día de vencimiento, +2)">
            <input style={inputStyle} type="text"
              value={(timings as any)._offsets_text ?? (timings.offsets_intentos_dias_habiles || [-1, 0, 2]).join(', ')}
              onChange={e => setBlock('timings', { _offsets_text: e.target.value })} />
          </Field>
          <Field label="Máx. intentos">
            <input style={inputStyle} type="number" value={num(timings.max_intentos ?? 3)} onChange={e => setBlock('timings', { max_intentos: Number(e.target.value) })} />
          </Field>
          <Field label="Frecuencia (días entre reintentos)">
            <input style={inputStyle} type="number" value={num(timings.frecuencia_dias ?? 1)} onChange={e => setBlock('timings', { frecuencia_dias: Number(e.target.value) })} />
          </Field>
          <Field label="Agendar por">
            <select style={inputStyle} value={timings.agendar_por || 'fecha_compromiso'} onChange={e => setBlock('timings', { agendar_por: e.target.value })}>
              <option value="fecha_compromiso">Fecha de compromiso</option>
              <option value="fecha_pago">Fecha de pago (vencimiento)</option>
            </select>
          </Field>
        </div>
      </Section>

      {/* Horarios */}
      <Section title="Horarios de llamada" hint="Franjas permitidas (Lun–Vie). Nunca puede exceder el límite legal Ley 2300 (07:00–19:00).">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(franjas.length ? franjas : [['09:00', '12:00']]).map((fr, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input style={{ ...inputStyle, width: 130 }} type="time" value={fr[0] || ''} onChange={e => { const n = [...franjas]; n[i] = [e.target.value, fr[1] || '']; setFranjas(n); }} />
              <span style={{ color: C.muted, fontFamily: C.SG }}>a</span>
              <input style={{ ...inputStyle, width: 130 }} type="time" value={fr[1] || ''} onChange={e => { const n = [...franjas]; n[i] = [fr[0] || '', e.target.value]; setFranjas(n); }} />
              <button onClick={() => setFranjas(franjas.filter((_, j) => j !== i))} style={{ border: 'none', background: C.pinkBg, color: C.pink, borderRadius: 8, padding: '8px 12px', fontFamily: C.SG, fontWeight: 700, cursor: 'pointer' }}>Quitar</button>
            </div>
          ))}
          <button onClick={() => setFranjas([...(franjas.length ? franjas : [['09:00', '12:00']]), ['14:00', '16:00']])}
            style={{ alignSelf: 'flex-start', border: `1px dashed ${C.s4}`, background: C.s2, color: C.text, borderRadius: 8, padding: '8px 14px', fontFamily: C.SG, fontWeight: 600, fontSize: 12.5, cursor: 'pointer' }}>+ Agregar franja</button>
        </div>
        <div style={grid2}>
          <Field label="Máx. contactos por día (por cliente)">
            <input style={inputStyle} type="number" value={num(horarios.max_contactos_dia ?? 1)} onChange={e => setBlock('horarios', { max_contactos_dia: Number(e.target.value) })} />
          </Field>
          <Field label="Llamadas por día (cupo)">
            <input style={inputStyle} type="number" value={num(volumen.llamadas_por_dia ?? 30)} onChange={e => setBlock('volumen', { llamadas_por_dia: Number(e.target.value) })} />
          </Field>
        </div>
      </Section>

      {/* Carga manual — solo para el arranque */}
      <Section title="Carga manual — evacuación de arranque" hint="Solo para las primeras semanas de operación.">
        <div style={{ padding: '11px 14px', borderRadius: 9, background: C.orangeBg, color: C.orange, fontFamily: C.SG, fontSize: 12.5, lineHeight: 1.5 }}>
          ⚠️ <strong>Esto es temporal.</strong> Sirve para evacuar la <strong>cartera vencida acumulada</strong> (mora vieja) durante los primeros días de arranque.
          En operación normal <strong>NO lo necesitas</strong>: el sync diario mantiene la cola sola. Estos deudores quedan <em>fijados</em> (el sync diario no los borra).
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
          <Field label="Cargar cartera vencida desde">
            <input style={{ ...inputStyle, width: 180 }} type="date" value={manualDesde} onChange={e => setManualDesde(e.target.value)} />
          </Field>
          <button onClick={() => manualDesde && sincronizar({ fecha_desde: manualDesde, fecha_hasta: '2027-12-31' })}
            disabled={!manualDesde} style={{ ...btn(C.orange), opacity: manualDesde ? 1 : 0.5 }}>Traer esta cartera</button>
        </div>
      </Section>
    </div>
  );
}
