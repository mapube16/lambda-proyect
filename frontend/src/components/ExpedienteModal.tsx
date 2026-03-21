import { useOfficeStore } from '../store/officeStore';

export function ExpedienteModal() {
  const { expediente, setExpediente } = useOfficeStore();
  if (!expediente) return null;

  const { status, markdown, json_payload, url } = expediente;
  const payload = json_payload as Record<string, unknown> | null;

  const copyEmail = () => {
    const body = (payload?.borradores as Record<string, unknown>)?.email_cuerpo as string;
    if (body) navigator.clipboard.writeText(body);
  };

  return (
    <div style={overlay} onClick={() => setExpediente(null)}>
      <div style={modal} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={header}>
          <div>
            <div style={badge(status === 'success' ? '#a9dc76' : '#ff6188')}>
              {status === 'success' ? '✅ APTO' : '❌ DESCALIFICADO'}
            </div>
            <div style={urlLabel}>{url}</div>
          </div>
          <button style={closeBtn} onClick={() => setExpediente(null)}>✕</button>
        </div>

        <div style={body}>
          {status === 'rejected' && payload && (
            <div style={rejectedBox}>
              <div style={sectionTitle}>Motivo de rechazo</div>
              <div style={rejectCode}>{String(payload.motivo_descalificacion ?? '')}</div>
              <div style={rejectEvidence}>{String(payload.evidencia_encontrada ?? '')}</div>
            </div>
          )}

          {status === 'success' && payload && (
            <>
              {/* Score */}
              <div style={scoreRow}>
                <div style={scoreBox}>
                  <div style={scoreBig}>{String(payload.score ?? '—')}</div>
                  <div style={scoreLabel}>/ 100</div>
                </div>
                <div style={scoreDetails}>
                  <div style={detailItem}>
                    <span style={detailKey}>Empresa</span>
                    <span style={detailVal}>{String(payload.empresa ?? '')}</span>
                  </div>
                  <div style={detailItem}>
                    <span style={detailKey}>Industria</span>
                    <span style={detailVal}>{String(payload.industria ?? '')}</span>
                  </div>
                  <div style={detailItem}>
                    <span style={detailKey}>Perfil</span>
                    <span style={detailVal}>{String((payload.datos_tecnicos as Record<string,unknown>)?.perfil ?? '')}</span>
                  </div>
                  <div style={detailItem}>
                    <span style={detailKey}>Tech Stack</span>
                    <span style={detailVal}>{String((payload.datos_tecnicos as Record<string,unknown>)?.tech_stack ?? 'No detectado')}</span>
                  </div>
                </div>
              </div>

              {/* Decisor */}
              {payload.decisor && (
                <div style={section}>
                  <div style={sectionTitle}>👤 Decisor clave</div>
                  <div style={decisorCard}>
                    <div style={decisorName}>{String((payload.decisor as Record<string,unknown>).nombre ?? '')}</div>
                    <div style={decisorRole}>{String((payload.decisor as Record<string,unknown>).cargo ?? '')}</div>
                    <div style={decisorEmail}>✉ {String((payload.decisor as Record<string,unknown>).email ?? '')}</div>
                  </div>
                </div>
              )}

              {/* Email */}
              {payload.borradores && (
                <div style={section}>
                  <div style={{ ...sectionTitle, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>✉️ Borrador de correo</span>
                    <button style={copyBtn} onClick={copyEmail}>📋 Copiar</button>
                  </div>
                  <div style={emailBox}>
                    {String((payload.borradores as Record<string,unknown>).email_cuerpo ?? '')
                      .split('\\n\\n')
                      .map((p, i) => <p key={i} style={{ margin: '0 0 10px 0' }}>{p}</p>)
                    }
                  </div>
                </div>
              )}
            </>
          )}

          {/* Markdown fallback */}
          {markdown && !payload && (
            <div style={markdownBox}>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: '13px', color: '#e5e5e5' }}>
                {markdown}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
};
const modal: React.CSSProperties = {
  background: '#1e1e2e', borderRadius: '16px', width: '640px', maxWidth: '95vw',
  maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden',
  border: '1px solid #3a3a5e', boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
};
const header: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  padding: '20px 24px 16px', borderBottom: '1px solid #2a2a4e',
};
const body: React.CSSProperties = {
  overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px',
};
const badge = (color: string): React.CSSProperties => ({
  display: 'inline-block', padding: '4px 12px', borderRadius: '20px',
  background: color, color: '#000', fontWeight: 700, fontSize: '13px', marginBottom: '6px',
});
const urlLabel: React.CSSProperties = { color: '#78dce8', fontSize: '13px', opacity: 0.8 };
const closeBtn: React.CSSProperties = {
  background: 'none', border: 'none', color: '#888', fontSize: '20px', cursor: 'pointer', padding: '4px',
};
const rejectedBox: React.CSSProperties = {
  background: '#2a1a1e', borderRadius: '10px', padding: '16px', border: '1px solid #ff618844',
};
const rejectCode: React.CSSProperties = {
  color: '#ff6188', fontWeight: 700, fontSize: '16px', marginBottom: '8px',
};
const rejectEvidence: React.CSSProperties = { color: '#ccc', fontSize: '14px' };
const scoreRow: React.CSSProperties = {
  display: 'flex', gap: '20px', background: '#252538', borderRadius: '12px', padding: '16px',
};
const scoreBox: React.CSSProperties = {
  display: 'flex', alignItems: 'baseline', gap: '4px', minWidth: '80px',
};
const scoreBig: React.CSSProperties = { fontSize: '52px', fontWeight: 800, color: '#a9dc76', lineHeight: 1 };
const scoreLabel: React.CSSProperties = { color: '#888', fontSize: '18px' };
const scoreDetails: React.CSSProperties = { flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' };
const detailItem: React.CSSProperties = { display: 'flex', gap: '8px' };
const detailKey: React.CSSProperties = { color: '#888', fontSize: '13px', minWidth: '80px' };
const detailVal: React.CSSProperties = { color: '#fff', fontSize: '13px', fontWeight: 500 };
const section: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '10px' };
const sectionTitle: React.CSSProperties = { color: '#ab9df2', fontWeight: 600, fontSize: '14px' };
const decisorCard: React.CSSProperties = {
  background: '#252538', borderRadius: '10px', padding: '14px',
};
const decisorName: React.CSSProperties = { color: '#fff', fontWeight: 600, fontSize: '16px' };
const decisorRole: React.CSSProperties = { color: '#aaa', fontSize: '13px', margin: '4px 0' };
const decisorEmail: React.CSSProperties = { color: '#78dce8', fontSize: '13px' };
const copyBtn: React.CSSProperties = {
  padding: '4px 12px', border: '1px solid #78dce8', borderRadius: '6px',
  background: 'transparent', color: '#78dce8', cursor: 'pointer', fontSize: '12px',
};
const emailBox: React.CSSProperties = {
  background: '#252538', borderRadius: '10px', padding: '16px',
  color: '#e5e5e5', fontSize: '14px', lineHeight: 1.6,
};
const markdownBox: React.CSSProperties = {
  background: '#252538', borderRadius: '10px', padding: '16px',
};
