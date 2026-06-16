const COLORS = {
  bg: '#FFFFFF',
  surface: '#FFFFFF',
  border: '#ECECF3',
  primary: '#4F46E5',
  primarySoft: '#EEEDFC',
  text: '#34343F',
  textMuted: '#6B6B7A',
  textFaint: '#9696A6',
};

interface SidebarProps {
  view: string;
  setView: (view: any) => void;
}

export function Sidebar({ view, setView }: SidebarProps) {
  const nav = [
    ['inicio', 'home', 'Inicio'],
    ['campanas', 'rocket', 'Campañas'],
    ['resultados', 'list', 'Resultados'],
    ['aprobados', 'check', 'Aprobados'],
    ['chat', 'chat', 'Chat'],
    ['aprendizaje', 'spark', 'Aprendizaje'],
  ];

  return (
    <aside
      style={{
        width: 248,
        flex: 'none',
        background: COLORS.surface,
        borderRight: `1px solid ${COLORS.border}`,
        display: 'flex',
        flexDirection: 'column',
        padding: 16,
      }}
    >
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '6px 8px 18px' }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 10,
            background: `linear-gradient(135deg, ${COLORS.primary}, #7C74F0)`,
            display: 'grid',
            placeItems: 'center',
            boxShadow: `0 4px 12px -4px rgba(79,70,229,.6)`,
          }}
        >
          <div style={{ width: 13, height: 13, borderRadius: 4, background: '#fff' }} />
        </div>
        <div>
          <div style={{ fontWeight: 800, fontSize: 17, color: '#16161D', letterSpacing: '-0.02em' }}>
            Landa
          </div>
          <div style={{ fontSize: 11, color: COLORS.textFaint, fontWeight: 600 }}>
            Prospección B2B
          </div>
        </div>
      </div>

      {/* Nav Items */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {nav.map(([key, , label]) => (
          <div
            key={key}
            onClick={() => setView(key)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 11,
              padding: '9px 12px',
              borderRadius: 10,
              color: view === key ? COLORS.primary : COLORS.textMuted,
              fontWeight: view === key ? 700 : 600,
              fontSize: 14,
              cursor: 'pointer',
              background: view === key ? COLORS.primarySoft : 'transparent',
              transition: 'all .12s',
            }}
          >
            <IconPlaceholder />
            <span>{label}</span>
            {key === 'resultados' && (
              <span
                style={{
                  marginLeft: 'auto',
                  fontSize: 11,
                  fontWeight: 700,
                  color: '#fff',
                  background: COLORS.primary,
                  borderRadius: 999,
                  padding: '2px 8px',
                }}
              >
                8
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Bottom Section */}
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div
          style={{
            background: '#FAFAFC',
            border: `1px solid ${COLORS.border}`,
            borderRadius: 14,
            padding: 14,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: COLORS.textFaint }}>
              Plan Pro
            </span>
            <span style={{ fontSize: 12, fontWeight: 700, color: COLORS.textMuted }}>62%</span>
          </div>
          <div style={{ height: 7, background: '#E9E9F1', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: '62%', height: '100%', background: COLORS.primary, borderRadius: 999 }} />
          </div>
          <div style={{ fontSize: 12, color: COLORS.textFaint, marginTop: 8 }}>
            8.420 / 13.500 créditos
          </div>
        </div>

        {/* User Card */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 8, borderRadius: 12, cursor: 'pointer' }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: 'linear-gradient(135deg,#F59E0B,#EF6C5A)',
              display: 'grid',
              placeItems: 'center',
              color: '#fff',
              fontWeight: 800,
              fontSize: 14,
            }}
          >
            DP
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 13.5, color: '#16161D' }}>
              DPG Seguros
            </div>
            <div
              style={{
                fontSize: 11.5,
                color: COLORS.textFaint,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              dpg.seguros@gmail.com
            </div>
          </div>
          <IconPlaceholder size={16} />
        </div>
      </div>
    </aside>
  );
}

function IconPlaceholder({ size = 19 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="1" />
    </svg>
  );
}
