const COLORS = {
  primary: '#4F46E5',
  surface: '#FFFFFF',
  surfaceHover: '#FAFAFC',
  border: '#E3E3EC',
  text: '#34343F',
  textMuted: '#6B6B7A',
  textFaint: '#9696A6',
};

interface TopbarProps {
  onLaunch?: () => void;
}

export function Topbar({ onLaunch }: TopbarProps) {
  return (
    <header
      style={{
        height: 70,
        flex: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '0 28px',
        borderBottom: `1px solid ${COLORS.border}`,
        background: 'rgba(255,255,255,.8)',
        backdropFilter: 'blur(8px)',
        zIndex: 5,
      }}
    >
      {/* Search */}
      <div style={{ position: 'relative', width: 320, maxWidth: '32%' }}>
        <span
          style={{
            position: 'absolute',
            left: 12,
            top: '50%',
            transform: 'translateY(-50%)',
            color: COLORS.textFaint,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 17,
            height: 17,
          }}
        >
          🔍
        </span>
        <input
          placeholder="Buscar empresas, leads, decisores…"
          style={{
            width: '100%',
            border: `1px solid ${COLORS.border}`,
            background: COLORS.surfaceHover,
            borderRadius: 10,
            padding: '10px 12px 10px 36px',
            fontFamily: 'inherit',
            fontSize: 13.5,
            color: COLORS.text,
            outline: 'none',
          }}
        />
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Notifications Button */}
      <button
        style={{
          position: 'relative',
          width: 40,
          height: 40,
          borderRadius: 10,
          border: `1px solid ${COLORS.border}`,
          background: COLORS.surface,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: COLORS.text,
          fontSize: 19,
        }}
        title="Notificaciones"
      >
        🔔
        <span
          style={{
            position: 'absolute',
            top: 7,
            right: 7,
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: '#E03E4C',
            border: '1.5px solid #fff',
          }}
        />
      </button>

      {/* Launch Campaign Button */}
      <button
        onClick={onLaunch}
        style={{
          fontFamily: 'inherit',
          fontWeight: 600,
          fontSize: 14,
          border: 'none',
          borderRadius: 10,
          padding: '10px 16px',
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          color: '#fff',
          background: COLORS.primary,
          boxShadow: `0 1px 2px rgba(79,70,229,.3), 0 4px 12px -4px rgba(79,70,229,.5)`,
          transition: 'all .14s ease',
        }}
        onMouseOver={(e) => {
          e.currentTarget.style.background = '#4338CA';
          e.currentTarget.style.transform = 'translateY(-1px)';
          e.currentTarget.style.boxShadow = `0 2px 4px rgba(79,70,229,.3), 0 8px 18px -6px rgba(79,70,229,.55)`;
        }}
        onMouseOut={(e) => {
          e.currentTarget.style.background = COLORS.primary;
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = `0 1px 2px rgba(79,70,229,.3), 0 4px 12px -4px rgba(79,70,229,.5)`;
        }}
      >
        🚀 Lanzar campaña
      </button>
    </header>
  );
}
