import { useEffect, useMemo, useState } from 'react';
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
  fontFamily: C.SG, fontSize: 10.5, fontWeight: 600,
  textTransform: 'uppercase', letterSpacing: '0.14em', color: C.muted,
};

interface Props {
  hook: UseSoftSegurosDebtorsResult;
  onComplete?: () => void;
}

function formatNumberCO(n: number): string {
  try { return new Intl.NumberFormat('es-CO').format(n); } catch { return String(n); }
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '—';
  if (seconds < 60) return `~${Math.ceil(seconds)} s`;
  const mins = Math.ceil(seconds / 60);
  if (mins < 60) return `~${mins} min`;
  const hrs = Math.floor(mins / 60);
  const rem = mins % 60;
  return rem === 0 ? `~${hrs} h` : `~${hrs} h ${rem} min`;
}

export function SoftSegurosSetup({ hook, onComplete }: Props) {
  const { configure, error, syncStatus, setup, cancelSync } = hook;
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [includeVencidos, setIncludeVencidos] = useState(true);
  const [includeProximos, setIncludeProximos] = useState(true);
  const [statePendiente, setStatePendiente] = useState(true);    // estado_cartera "Pendiente por pagar"
  const [stateSinPagos, setStateSinPagos] = useState(false);     // estado_cartera "Sin pagos Asignados"
  const [maxAgeMonths, setMaxAgeMonths] = useState<number | null>(12); // 6 | 12 | 24 | null=sin límite
  const [includeCancelled, setIncludeCancelled] = useState(false); // cancelled/no-renewed pólizas
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const noKindSelected = !includeVencidos && !includeProximos;
  const noStateSelected = !statePendiente && !stateSinPagos;
  const formInvalid = noKindSelected || noStateSelected;

  // We're "importing" if we just submitted AND the server reports an active sync.
  // We also treat a server-reported active sync as importing even without local
  // submission (e.g., page reload mid-import).
  const importing = (submitted || !!syncStatus?.is_syncing_now) && !setup.configured;
  // Once configured AND no sync running, the import is done.
  const finishedOk = submitted && setup.configured && !syncStatus?.is_syncing_now && syncStatus?.last_sync_status === 'success';
  const finishedFailed = submitted && !syncStatus?.is_syncing_now && syncStatus?.last_sync_status === 'failed';
  const finishedCancelled = submitted && !syncStatus?.is_syncing_now && syncStatus?.last_sync_status === 'cancelled';

  useEffect(() => {
    if (finishedOk) onComplete?.();
  }, [finishedOk, onComplete]);

  // Live progress derivation from sync_status.
  const scanned = syncStatus?.polizas_scanned ?? 0;
  const total = syncStatus?.total_count ?? 0;
  const percent = total > 0 ? Math.min(100, Math.round((scanned / total) * 100)) : 0;
  const found = syncStatus?.debtors_created ?? 0;

  const [nowTick, setNowTick] = useState(Date.now());
  useEffect(() => {
    if (!importing) return;
    const id = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [importing]);

  const etaText = useMemo(() => {
    if (!importing || !syncStatus?.started_at) return null;
    const startedMs = Date.parse(syncStatus.started_at);
    if (Number.isNaN(startedMs)) return null;
    const elapsedSec = (nowTick - startedMs) / 1000;
    if (elapsedSec < 5 || scanned <= 0) return 'Calculando tiempo…';
    const rate = scanned / elapsedSec; // pólizas/sec
    const remaining = Math.max(0, total - scanned);
    if (rate <= 0) return 'Calculando tiempo…';
    return `${formatEta(remaining / rate)} restantes`;
  }, [importing, syncStatus?.started_at, nowTick, scanned, total]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password || formInvalid) return;
    const cartera_states: ('Pendiente por pagar' | 'Sin pagos Asignados')[] = [];
    if (statePendiente) cartera_states.push('Pendiente por pagar');
    if (stateSinPagos) cartera_states.push('Sin pagos Asignados');
    setSubmitting(true);
    const ok = await configure(username.trim(), password, {
      include_vencidos: includeVencidos,
      include_proximos: includeProximos,
      cartera_states,
      max_age_months: maxAgeMonths,
      include_cancelled: includeCancelled,
    });
    setSubmitting(false);
    if (ok) setSubmitted(true);
  };

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box', background: C.s2,
    border: `1px solid rgba(255,255,255,0.1)`, color: C.text,
    fontFamily: C.IN, fontSize: 13, padding: '10px 12px', outline: 'none',
  };

  // Inline <style> for keyboard-focus rings (component-scoped via class names).
  const focusStyles = (
    <style>{`
      .ss-input:focus { box-shadow: 0 0 0 2px rgba(120,220,232,0.45); border-color: rgba(120,220,232,0.6); }
      .ss-btn-primary:focus { outline: 2px solid ${C.cyan}; outline-offset: 2px; }
      .ss-checkbox:focus-visible { outline: 2px solid ${C.cyan}; outline-offset: 2px; }
      @keyframes ss-bar-stripes { from { background-position: 0 0; } to { background-position: 40px 0; } }
    `}</style>
  );

  return (
    <div style={{ padding: '26px 28px', background: C.s1, border: `1px solid ${C.cyanBdr}` }}>
      {focusStyles}
      <div style={lbl}>INTEGRACIÓN SOFTSEGUROS</div>
      <h2 style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 19, color: C.text, margin: '6px 0 0' }}>
        Conectar tu cartera de SOFTSEGUROS
      </h2>

      {!importing && !finishedOk && !finishedFailed && !finishedCancelled && (
        <>
          <p style={{ fontFamily: C.IN, fontSize: 13, color: C.text, marginTop: 12, marginBottom: 6 }}>
            Vamos a escanear toda tu cartera de SOFTSEGUROS para identificar los deudores cobrables y separarlos en dos vistas:
            <strong style={{ color: C.text }}> próximos a vencer</strong> y <strong style={{ color: C.text }}>ya vencidos</strong>.
          </p>
          <ul style={{ fontFamily: C.IN, fontSize: 12.5, color: C.muted, lineHeight: 1.7, paddingLeft: 18, margin: '6px 0 16px' }}>
            <li>El proceso tarda entre <strong style={{ color: C.text }}>20 y 40 minutos</strong> (depende del tamaño de tu cartera).</li>
            <li>Podés cerrar esta pestaña y volver — el escaneo sigue corriendo en el servidor.</li>
            <li>Solo se guardarán los deudores que coincidan con los filtros que elijas abajo.</li>
            <li>Tus credenciales se guardan encriptadas y nunca se exponen.</li>
          </ul>
        </>
      )}

      {importing ? (
        <div role="status" aria-live="polite" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
            <div style={{ fontFamily: C.SG, fontWeight: 600, fontSize: 14, color: C.cyan }}>
              Importando cartera…
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 12, color: C.muted }}>
              {etaText}
            </div>
          </div>

          {/* Determinate progress bar with striped animation */}
          <div style={{
            position: 'relative', height: 10, background: C.s3, overflow: 'hidden', borderRadius: 5,
          }}>
            <div
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Progreso de importación SOFTSEGUROS"
              style={{
                width: `${percent}%`, height: '100%',
                background: `linear-gradient(90deg, ${C.cyan}, ${C.green})`,
                backgroundSize: '40px 100%',
                transition: 'width 0.4s ease',
                animation: 'ss-bar-stripes 1.2s linear infinite',
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontFamily: C.IN, fontSize: 12, color: C.muted, flexWrap: 'wrap', gap: 6 }}>
            <span>{percent}% &middot; {formatNumberCO(scanned)} de {formatNumberCO(total)} pólizas escaneadas</span>
            <span style={{ color: C.green }}>{formatNumberCO(found)} deudores cobrables encontrados</span>
          </div>

          <div style={{ marginTop: 16, padding: '10px 14px', background: C.s2, borderLeft: `3px solid ${C.cyan}` }}>
            <div style={{ fontFamily: C.IN, fontSize: 12, color: C.text, marginBottom: 2 }}>
              Podés cerrar esta pestaña.
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted }}>
              El escaneo sigue en el servidor. Cuando vuelvas, vas a ver el progreso aquí.
            </div>
          </div>

          <button
            type="button"
            className="ss-btn-primary"
            onClick={async () => { await cancelSync(); }}
            style={{
              marginTop: 14, padding: '8px 14px', border: `1px solid rgba(255,97,136,0.3)`,
              background: 'transparent', color: C.pink, fontFamily: C.SG, fontWeight: 600, fontSize: 12,
              letterSpacing: '0.05em', cursor: 'pointer',
            }}
          >
            Cancelar importación
          </button>
        </div>
      ) : finishedFailed ? (
        <div role="alert" aria-live="assertive" style={{ marginTop: 16 }}>
          <div style={{ padding: '14px 16px', background: C.pinkBg, border: `1px solid rgba(255,97,136,0.3)`, marginBottom: 14 }}>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.pink, marginBottom: 6 }}>
              La importación se detuvo por un error
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 12.5, color: C.text, lineHeight: 1.55 }}>
              {syncStatus?.error_message || 'No tenemos detalles del error.'}
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginTop: 8 }}>
              Avance hasta el corte: {formatNumberCO(scanned)} de {formatNumberCO(total)} pólizas, {formatNumberCO(found)} deudores guardados.
            </div>
          </div>
          <button
            type="button"
            onClick={() => { setSubmitted(false); setUsername(''); setPassword(''); }}
            style={{
              padding: '10px 18px', border: 'none', background: C.cyan, color: C.bg,
              fontFamily: C.SG, fontWeight: 700, fontSize: 12, letterSpacing: '0.05em', cursor: 'pointer',
            }}
          >
            Volver a intentar
          </button>
        </div>
      ) : finishedCancelled ? (
        <div role="status" style={{ marginTop: 16 }}>
          <div style={{ padding: '14px 16px', background: C.s2, borderLeft: `3px solid ${C.orange}`, marginBottom: 14 }}>
            <div style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 14, color: C.orange, marginBottom: 6 }}>
              Importación cancelada
            </div>
            <div style={{ fontFamily: C.IN, fontSize: 12.5, color: C.muted }}>
              Se guardaron {formatNumberCO(found)} deudores antes de la cancelación.
            </div>
          </div>
          <button
            type="button"
            onClick={() => { setSubmitted(false); }}
            style={{
              padding: '10px 18px', border: 'none', background: C.cyan, color: C.bg,
              fontFamily: C.SG, fontWeight: 700, fontSize: 12, letterSpacing: '0.05em', cursor: 'pointer',
            }}
          >
            Volver a importar
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 460 }}>
          <div>
            <label htmlFor="ss-username" style={{ ...lbl, marginBottom: 4, display: 'block' }}>USUARIO</label>
            <input
              id="ss-username"
              className="ss-input"
              style={inputStyle}
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="usuario.softseguros"
              disabled={submitting}
              autoComplete="username"
              aria-required="true"
            />
          </div>
          <div>
            <label htmlFor="ss-password" style={{ ...lbl, marginBottom: 4, display: 'block' }}>CONTRASEÑA</label>
            <input
              id="ss-password"
              className="ss-input"
              style={inputStyle}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••••"
              disabled={submitting}
              autoComplete="current-password"
              aria-required="true"
            />
          </div>

          <fieldset style={{ border: `1px solid rgba(255,255,255,0.08)`, padding: '12px 14px', margin: 0 }}>
            <legend style={{ ...lbl, padding: '0 6px' }}>¿QUÉ DEUDORES IMPORTAR?</legend>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: C.IN, fontSize: 13, color: C.text, cursor: 'pointer', marginTop: 6 }}>
              <input
                className="ss-checkbox"
                type="checkbox"
                checked={includeVencidos}
                disabled={submitting}
                onChange={e => setIncludeVencidos(e.target.checked)}
                aria-describedby="ss-help-vencidos"
              />
              <span>
                Ya vencidos
                <span id="ss-help-vencidos" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginLeft: 6 }}>
                  · pólizas en mora
                </span>
              </span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: C.IN, fontSize: 13, color: C.text, cursor: 'pointer', marginTop: 10 }}>
              <input
                className="ss-checkbox"
                type="checkbox"
                checked={includeProximos}
                disabled={submitting}
                onChange={e => setIncludeProximos(e.target.checked)}
                aria-describedby="ss-help-proximos"
              />
              <span>
                Próximos a vencer
                <span id="ss-help-proximos" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginLeft: 6 }}>
                  · vencen en los próximos 30 días
                </span>
              </span>
            </label>
            {noKindSelected && (
              <div role="alert" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.orange, marginTop: 10 }}>
                Seleccioná al menos un tipo de deudor para importar.
              </div>
            )}
          </fieldset>

          <fieldset style={{ border: `1px solid rgba(255,255,255,0.08)`, padding: '12px 14px', margin: 0 }}>
            <legend style={{ ...lbl, padding: '0 6px' }}>ESTADO DE CARTERA EN SOFTSEGUROS</legend>
            <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginBottom: 8 }}>
              Solo importamos pólizas cuyo estado en SOFTSEGUROS sea alguno de los que marques.
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: C.IN, fontSize: 13, color: C.text, cursor: 'pointer' }}>
              <input
                className="ss-checkbox"
                type="checkbox"
                checked={statePendiente}
                disabled={submitting}
                onChange={e => setStatePendiente(e.target.checked)}
                aria-describedby="ss-help-pendiente"
              />
              <span>
                Pendiente por pagar
                <span id="ss-help-pendiente" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginLeft: 6 }}>
                  · deuda real registrada por SOFTSEGUROS (recomendado)
                </span>
              </span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: C.IN, fontSize: 13, color: C.text, cursor: 'pointer', marginTop: 10 }}>
              <input
                className="ss-checkbox"
                type="checkbox"
                checked={stateSinPagos}
                disabled={submitting}
                onChange={e => setStateSinPagos(e.target.checked)}
                aria-describedby="ss-help-sinpagos"
              />
              <span>
                Sin pagos Asignados
                <span id="ss-help-sinpagos" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginLeft: 6 }}>
                  · pólizas sin registro de pago — incluye muchas viejas/archivadas
                </span>
              </span>
            </label>
            {noStateSelected && (
              <div role="alert" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.orange, marginTop: 10 }}>
                Seleccioná al menos un estado de cartera.
              </div>
            )}
          </fieldset>

          <fieldset style={{ border: `1px solid rgba(255,255,255,0.08)`, padding: '12px 14px', margin: 0 }}>
            <legend style={{ ...lbl, padding: '0 6px' }}>ESTADO DE LA PÓLIZA</legend>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: C.IN, fontSize: 13, color: C.text, cursor: 'pointer' }}>
              <input
                className="ss-checkbox"
                type="checkbox"
                checked={includeCancelled}
                disabled={submitting}
                onChange={e => setIncludeCancelled(e.target.checked)}
                aria-describedby="ss-help-cancelled"
              />
              <span>
                Incluir pólizas canceladas / no renovadas
                <span id="ss-help-cancelled" style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginLeft: 6 }}>
                  · por defecto solo se importan pólizas vigentes o devengadas
                </span>
              </span>
            </label>
          </fieldset>

          <fieldset style={{ border: `1px solid rgba(255,255,255,0.08)`, padding: '12px 14px', margin: 0 }}>
            <legend style={{ ...lbl, padding: '0 6px' }}>ANTIGÜEDAD MÁXIMA</legend>
            <div style={{ fontFamily: C.IN, fontSize: 11.5, color: C.muted, marginBottom: 10 }}>
              Descartar pólizas con fecha de vencimiento más vieja que este límite.
              Las deudas muy antiguas suelen estar prescritas o castigadas contablemente.
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {([
                { label: 'Últimos 6 meses', value: 6 },
                { label: 'Últimos 12 meses', value: 12 },
                { label: 'Últimos 24 meses', value: 24 },
                { label: 'Sin límite', value: null },
              ] as { label: string; value: number | null }[]).map(opt => {
                const selected = maxAgeMonths === opt.value;
                return (
                  <button
                    key={String(opt.value)}
                    type="button"
                    onClick={() => setMaxAgeMonths(opt.value)}
                    disabled={submitting}
                    aria-pressed={selected}
                    style={{
                      padding: '6px 12px',
                      border: `1px solid ${selected ? C.cyanBdr : 'rgba(255,255,255,0.1)'}`,
                      background: selected ? C.cyanBg : 'transparent',
                      color: selected ? C.cyan : C.muted,
                      fontFamily: C.SG, fontWeight: 600, fontSize: 11.5,
                      cursor: submitting ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          {error && (
            <div role="alert" aria-live="assertive" style={{ padding: '10px 12px', background: C.pinkBg, color: C.pink, fontFamily: C.IN, fontSize: 12.5, lineHeight: 1.45 }}>
              {error.code === 'bad_credentials' ? 'Credenciales SOFTSEGUROS inválidas. Revisá usuario y contraseña.' : error.message}
            </div>
          )}

          <button
            type="submit"
            className="ss-btn-primary"
            disabled={submitting || !username.trim() || !password || formInvalid}
            title={
              noKindSelected ? 'Seleccioná al menos un tipo de deudor'
              : noStateSelected ? 'Seleccioná al menos un estado de cartera'
              : !username.trim() ? 'Ingresá tu usuario SOFTSEGUROS'
              : !password ? 'Ingresá tu contraseña SOFTSEGUROS'
              : submitting ? 'Validando credenciales con SOFTSEGUROS…'
              : 'Iniciar importación de la cartera'
            }
            style={{
              alignSelf: 'flex-start', padding: '12px 22px', border: 'none',
              background: submitting || !username.trim() || !password || formInvalid ? C.s3 : C.cyan,
              color: submitting || !username.trim() || !password || formInvalid ? C.muted : C.bg,
              fontFamily: C.SG, fontWeight: 700, fontSize: 12.5,
              letterSpacing: '0.05em',
              cursor: submitting || !username.trim() || !password || formInvalid ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Validando credenciales…' : 'Conectar y empezar a importar'}
          </button>
        </form>
      )}
    </div>
  );
}

export default SoftSegurosSetup;
