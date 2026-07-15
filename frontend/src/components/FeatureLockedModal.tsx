interface FeatureLockedModalProps {
  featureName: string;
  description?: string;
  features?: string[];
  onClose: () => void;
}

// Modal de "función no incluida en tu plan". DPG es un tenant cobranza-only:
// todo lo demás (prospección B2B) queda bloqueado con este modal.
const TEAL = '#0F6B64';
const TEAL_D = '#0B534E';

export function FeatureLockedModal({ featureName, description, features = [], onClose }: FeatureLockedModalProps) {
  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        {/* Cabecera teal */}
        <div style={header}>
          <button style={closeBtn} onClick={onClose} aria-label="Cerrar">✕</button>
          <div style={badge}>◆ FUNCIÓN PREMIUM</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 12 }}>
            <div style={iconBox}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </div>
            <div>
              <div style={titleStyle}>{featureName}</div>
              <div style={subtitleStyle}>No incluida en tu plan actual</div>
            </div>
          </div>
        </div>

        {/* Cuerpo */}
        <div style={bodyStyle}>
          {description && <div style={message}>{description}</div>}
          {features.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 4 }}>
              {features.map((f, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                  <span style={checkDot}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={TEAL} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  </span>
                  <span style={featItem}>{f}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={footer}>
          <button style={ghostBtn} onClick={onClose}>Ahora no</button>
          <a href="mailto:innovaciondpg@gmail.com?subject=Solicitud%20de%20acceso%20a%20funcion%20Landa%20Tech" style={ctaBtn}>
            Solicitar acceso
          </a>
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(22,22,40,0.55)', backdropFilter: 'blur(6px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 400, padding: 20,
};
const modal: React.CSSProperties = {
  background: '#fff', borderRadius: 20, maxWidth: 440, width: '100%',
  display: 'flex', flexDirection: 'column', overflow: 'hidden',
  boxShadow: '0 30px 80px rgba(15,107,100,0.30)',
};
const header: React.CSSProperties = {
  position: 'relative', padding: '22px 26px 24px',
  background: `linear-gradient(135deg, ${TEAL} 0%, ${TEAL_D} 100%)`, color: '#fff',
};
const badge: React.CSSProperties = {
  display: 'inline-block', background: 'rgba(255,255,255,0.18)', color: '#fff',
  borderRadius: 999, padding: '5px 12px', fontSize: 11, fontWeight: 800, letterSpacing: '0.08em',
};
const closeBtn: React.CSSProperties = {
  position: 'absolute', top: 16, right: 16, width: 30, height: 30, borderRadius: 999,
  background: 'rgba(255,255,255,0.18)', border: 'none', color: '#fff', fontSize: 14, cursor: 'pointer',
};
const iconBox: React.CSSProperties = {
  width: 46, height: 46, borderRadius: 13, background: 'rgba(255,255,255,0.16)',
  display: 'grid', placeItems: 'center', flexShrink: 0,
};
const titleStyle: React.CSSProperties = { fontSize: 20, fontWeight: 800, letterSpacing: '-0.01em', fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" };
const subtitleStyle: React.CSSProperties = { fontSize: 12.5, opacity: 0.85, marginTop: 2, fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" };
const bodyStyle: React.CSSProperties = { padding: '22px 26px', display: 'flex', flexDirection: 'column', gap: 14, fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" };
const message: React.CSSProperties = { color: '#34343F', fontSize: 14, lineHeight: 1.6 };
const checkDot: React.CSSProperties = { width: 22, height: 22, borderRadius: 999, background: 'rgba(15,107,100,0.10)', display: 'grid', placeItems: 'center', flexShrink: 0 };
const featItem: React.CSSProperties = { color: '#34343F', fontSize: 13.5 };
const footer: React.CSSProperties = { display: 'flex', gap: 12, padding: '18px 26px 24px' };
const ghostBtn: React.CSSProperties = {
  flex: 1, padding: '11px 0', borderRadius: 11, cursor: 'pointer', fontSize: 14, fontWeight: 700,
  background: '#fff', border: '1px solid #E3E3EC', color: '#6B6B7A', fontFamily: 'inherit',
};
const ctaBtn: React.CSSProperties = {
  flex: 2, padding: '11px 0', borderRadius: 11, cursor: 'pointer', fontSize: 14, fontWeight: 800,
  background: TEAL, border: 'none', color: '#fff', fontFamily: 'inherit',
  textAlign: 'center', textDecoration: 'none', display: 'block',
};
