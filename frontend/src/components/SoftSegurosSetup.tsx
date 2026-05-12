import { useEffect, useState } from 'react';
import type { UseSoftSegurosDebtorsResult } from '../hooks/useSoftSegurosDebtors';

// Shared visual tokens (mirrors CobranzaTab / ClientDashboard).
const C = {
  bg: '#0d0d18', s0: '#12121d', s1: '#1b1a26', s2: '#22212e', s3: '#2c2b3a',
  text: '#e3e0f1', muted: '#8a8a9a',
  cyan: '#78dce8', cyanBg: 'rgba(120,220,232,0.08)', cyanBdr: 'rgba(120,220,232,0.25)',
  green: '#a9dc76', greenBg: 'rgba(169,220,118,0.08)',
  pink: '#ff6188', pinkBg: 'rgba(255,97,136,0.1)',
  orange: '#fc9867',
  SG: "'Space Grotesk', system-ui, sans-serif",
  IN: "'Inter', system-ui, sans-serif",
};

const lbl: React.CSSProperties = {
  fontFamily: C.SG, fontSize: 9, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.14em', color: C.muted,
};

interface Props {
  hook: UseSoftSegurosDebtorsResult;
  /** Called once the onboarding sync completes (setup.configured becomes true and no sync running). */
  onComplete?: () => void;
}

/**
 * SOFTSEGUROS onboarding form: collects username + password, calls hook.configure,
 * then shows an indeterminate "Importando pólizas..." progress until the onboarding
 * sync completes.
 */
export function SoftSegurosSetup({ hook, onComplete }: Props) {
  const { configure, error, syncStatus, setup } = hook;
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const importing = submitted && (!!syncStatus?.is_syncing_now || !setup.configured);

  // Fire onComplete once the onboarding sync settles.
  useEffect(() => {
    if (submitted && setup.configured && syncStatus && !syncStatus.is_syncing_now) {
      onComplete?.();
    }
  }, [submitted, setup.configured, syncStatus, onComplete]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setSubmitting(true);
    const ok = await configure(username.trim(), password);
    setSubmitting(false);
    if (ok) setSubmitted(true);
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', background: C.s2,
    border: `1px solid rgba(255,255,255,0.1)`, color: C.text,
    fontFamily: C.IN, fontSize: 13, padding: '10px 12px', outline: 'none',
  };

  return (
    <div style={{ padding: '20px 24px', background: C.s1, border: `1px solid ${C.cyanBdr}` }}>
      <div style={lbl}>INTEGRACIÓN SOFTSEGUROS</div>
      <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 17, color: C.text, marginTop: 4 }}>
        Conectar SOFTSEGUROS
      </div>
      <p style={{ fontFamily: C.IN, fontSize: 12.5, color: C.muted, marginTop: 6, marginBottom: 16, lineHeight: 1.5 }}>
        Ingresa tus credenciales de SOFTSEGUROS para importar automáticamente tus pólizas
        y separarlas en deudores próximos a vencer y ya vencidos.
      </p>

      {importing ? (
        <div>
          <div style={{ fontFamily: C.SG, fontSize: 13, color: C.cyan, marginBottom: 10 }}>
            Importando pólizas…
          </div>
          {/* Indeterminate progress bar */}
          <div style={{ position: 'relative', height: 6, background: C.s3, overflow: 'hidden', borderRadius: 3 }}>
            <div style={{
              position: 'absolute', top: 0, bottom: 0, width: '35%',
              background: `linear-gradient(90deg, ${C.cyan}, ${C.green})`,
              animation: 'cobr-spin 1.4s linear infinite',
              // reuse a slide-ish feel; cobr-spin keyframe exists. Fallback to left animation:
              left: 0,
            }} />
          </div>
          <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginTop: 8 }}>
            Esto puede tardar varios minutos. Puedes cerrar esta pestaña y volver más tarde.
            {syncStatus && typeof syncStatus.debtors_created === 'number' && (
              <> {' '}Deudores importados hasta ahora: {syncStatus.debtors_created}.</>
            )}
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 420 }}>
          <div>
            <div style={{ ...lbl, marginBottom: 4 }}>USUARIO</div>
            <input
              style={inputStyle}
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="usuario.softseguros"
              disabled={submitting}
              autoComplete="username"
            />
          </div>
          <div>
            <div style={{ ...lbl, marginBottom: 4 }}>CONTRASEÑA</div>
            <input
              style={inputStyle}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••••"
              disabled={submitting}
              autoComplete="current-password"
            />
          </div>
          {error && (
            <div style={{ padding: '8px 12px', background: C.pinkBg, color: C.pink, fontFamily: C.IN, fontSize: 12 }}>
              {error.code === 'bad_credentials' ? 'Credenciales inválidas' : error.message}
            </div>
          )}
          <button
            type="submit"
            disabled={submitting || !username.trim() || !password}
            style={{
              alignSelf: 'flex-start', padding: '10px 18px', border: 'none',
              background: submitting || !username.trim() || !password ? C.s3 : C.cyan,
              color: C.bg, fontFamily: C.SG, fontWeight: 700, fontSize: 12,
              letterSpacing: '0.05em',
              cursor: submitting || !username.trim() || !password ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Validando…' : 'Conectar SOFTSEGUROS'}
          </button>
        </form>
      )}
    </div>
  );
}

export default SoftSegurosSetup;
