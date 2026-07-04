interface FeatureLockedModalProps {
  featureName: string;
  onClose: () => void;
}

export function FeatureLockedModal({ featureName, onClose }: FeatureLockedModalProps) {
  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={header}>
          <div style={lockBadge}>🔒 No disponible en tu plan</div>
          <button style={closeBtn} onClick={onClose}>✕</button>
        </div>

        <div style={bodyStyle}>
          <div style={featureTitle}>{featureName}</div>
          <div style={message}>
            Esta función todavía no está habilitada para tu cuenta. Si tu operación
            necesita este servicio, contacta a tu ejecutivo de cuenta en Landa Tech
            para activarlo.
          </div>
        </div>

        <div style={footer}>
          <button style={cerrarBtn} onClick={onClose}>Entendido</button>
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
};

const modal: React.CSSProperties = {
  background: '#1e1e2e', border: '1px solid #3a3a5e', borderRadius: 12,
  maxWidth: 420, width: '90%',
  display: 'flex', flexDirection: 'column', overflow: 'hidden',
  boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
};

const header: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  padding: '18px 20px 14px', borderBottom: '1px solid #2a2a4e',
};

const lockBadge: React.CSSProperties = {
  background: '#ffd86622', border: '1px solid #ffd866', color: '#ffd866',
  borderRadius: 4, padding: '3px 10px', fontSize: 12, fontWeight: 700,
};

const closeBtn: React.CSSProperties = {
  background: 'none', border: 'none', color: '#888', fontSize: 18, cursor: 'pointer', padding: 4,
};

const bodyStyle: React.CSSProperties = {
  padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10,
};

const featureTitle: React.CSSProperties = {
  color: '#fff', fontSize: 16, fontWeight: 700,
};

const message: React.CSSProperties = {
  color: '#ccc', fontSize: 13, lineHeight: 1.6,
};

const footer: React.CSSProperties = {
  display: 'flex', gap: 10, padding: '14px 20px', borderTop: '1px solid #2a2a4e', justifyContent: 'flex-end',
};

const cerrarBtn: React.CSSProperties = {
  padding: '8px 18px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
  background: '#78dce822', border: '1px solid #78dce8', color: '#78dce8',
  fontWeight: 700, fontFamily: 'inherit',
};
