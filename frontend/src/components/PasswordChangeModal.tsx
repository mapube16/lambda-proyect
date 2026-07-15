import { useState } from 'react';
import { changePassword } from '../api';

// Cambio de contraseña. forced=true cuando el login trajo contraseña temporal
// (must_change_pw): el modal no se puede cerrar hasta cambiarla.
export function PasswordChangeModal({ forced, onClose }: { forced: boolean; onClose: () => void }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (next.length < 8) { setError('La nueva contraseña debe tener al menos 8 caracteres.'); return; }
    if (next !== confirm) { setError('Las contraseñas no coinciden.'); return; }
    setBusy(true);
    try {
      await changePassword(current, next);
      setDone(true);
      setTimeout(onClose, 1400);
    } catch (err: any) {
      setError(err?.message || 'No se pudo cambiar la contraseña');
    } finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={forced ? undefined : onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={header}>
          <div style={iconBox}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
          </div>
          <div>
            <div style={titleStyle}>{forced ? 'Crea tu nueva contraseña' : 'Cambiar contraseña'}</div>
            <div style={subStyle}>{forced ? 'Tu cuenta tiene una contraseña temporal' : 'Actualiza tu contraseña de acceso'}</div>
          </div>
        </div>

        <div style={{ padding: '22px 26px 26px' }}>
          {done ? (
            <div style={{ textAlign: 'center', padding: '14px 0', color: '#157F5B', fontWeight: 700, fontSize: 15 }}>
              ✓ Contraseña actualizada
            </div>
          ) : (
            <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <input type="password" placeholder={forced ? 'Contraseña temporal (la del correo)' : 'Contraseña actual'} value={current} onChange={e => setCurrent(e.target.value)} style={input} autoFocus />
              <input type="password" placeholder="Nueva contraseña (mínimo 8 caracteres)" value={next} onChange={e => setNext(e.target.value)} style={input} />
              <input type="password" placeholder="Confirmar nueva contraseña" value={confirm} onChange={e => setConfirm(e.target.value)} style={input} />
              {error && <div style={{ color: '#B91C3C', fontSize: 12.5 }}>{error}</div>}
              <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                {!forced && <button type="button" onClick={onClose} style={ghostBtn}>Cancelar</button>}
                <button type="submit" disabled={busy} style={{ ...primaryBtn, opacity: busy ? 0.7 : 1, flex: forced ? 1 : 2 }}>
                  {busy ? 'Guardando…' : 'Guardar contraseña'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

const F = "'Plus Jakarta Sans', system-ui, sans-serif";
const NAVY = '#234876';
const overlay: React.CSSProperties = { position: 'fixed', inset: 0, background: 'rgba(22,22,40,0.55)', backdropFilter: 'blur(6px)', display: 'grid', placeItems: 'center', zIndex: 500, padding: 20, fontFamily: F };
const modal: React.CSSProperties = { background: '#fff', borderRadius: 18, maxWidth: 420, width: '100%', overflow: 'hidden', boxShadow: '0 28px 70px rgba(35,72,118,0.30)' };
const header: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 14, padding: '22px 26px', background: NAVY, color: '#fff' };
const iconBox: React.CSSProperties = { width: 44, height: 44, borderRadius: 12, background: 'rgba(255,255,255,0.16)', display: 'grid', placeItems: 'center', flexShrink: 0 };
const titleStyle: React.CSSProperties = { fontSize: 17, fontWeight: 800, letterSpacing: '-0.01em' };
const subStyle: React.CSSProperties = { fontSize: 12, opacity: 0.85, marginTop: 2 };
const input: React.CSSProperties = { width: '100%', padding: '11px 13px', borderRadius: 10, border: '1px solid #E3E3EC', background: '#FAFAFC', color: '#34343F', fontFamily: F, fontSize: 13.5, outline: 'none', boxSizing: 'border-box' };
const ghostBtn: React.CSSProperties = { flex: 1, padding: '11px 0', borderRadius: 10, border: '1px solid #E3E3EC', background: '#fff', color: '#6B6B7A', fontFamily: F, fontSize: 13.5, fontWeight: 700, cursor: 'pointer' };
const primaryBtn: React.CSSProperties = { padding: '11px 0', borderRadius: 10, border: 'none', background: NAVY, color: '#fff', fontFamily: F, fontSize: 13.5, fontWeight: 800, cursor: 'pointer' };
