import { useOfficeStore } from './store/officeStore';
import { LoginView } from './components/LoginView';
import { StaffDashboard } from './components/StaffDashboard';
import { OfficeCanvas } from './components/OfficeCanvas';
import { AgentPanel } from './components/AgentPanel';
import { useWebSocket } from './hooks/useWebSocket';
import { useGameLoop } from './hooks/useGameLoop';

function OfficeView() {
  const { createAgent, runTask, startProspect, approveLead, rejectLead } = useWebSocket();
  useGameLoop();
  const { userEmail, clearAuth } = useOfficeStore();

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}>🐝</span>
          <h1 style={styles.logoText}>Isomorph Office</h1>
        </div>
        <div style={styles.headerActions}>
          {userEmail && <span style={styles.userBadge}>{userEmail}</span>}
          <button style={styles.logoutBtn} onClick={clearAuth}>Salir</button>
        </div>
      </header>
      <main style={styles.main}>
        <div style={styles.canvasContainer}>
          <OfficeCanvas />
        </div>
        <div style={styles.panelContainer}>
          <AgentPanel createAgent={createAgent} runTask={runTask} startProspect={startProspect} approveLead={approveLead} rejectLead={rejectLead} />
        </div>
      </main>
    </div>
  );
}

export default function App() {
  const { isAuthenticated, userRole } = useOfficeStore();

  if (!isAuthenticated) return <LoginView />;
  if (userRole === 'staff') return <StaffDashboard />;
  return <OfficeView />;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    height: '100vh',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    background: 'linear-gradient(180deg, #1a1a2e 0%, #16162a 100%)',
    color: '#fff',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px 24px',
    borderBottom: '1px solid #2a2a4a',
  },
  logo: { display: 'flex', alignItems: 'center', gap: '12px' },
  logoIcon: { fontSize: '32px' },
  logoText: {
    margin: 0,
    fontSize: '24px',
    fontWeight: 600,
    background: 'linear-gradient(90deg, #78dce8, #a9dc76)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  headerActions: { display: 'flex', alignItems: 'center', gap: '12px' },
  userBadge: { fontSize: 13, color: '#888' },
  logoutBtn: {
    padding: '6px 14px',
    borderRadius: 6,
    border: '1px solid #2a2a4a',
    background: 'transparent',
    color: '#888',
    cursor: 'pointer',
    fontSize: 13,
    fontFamily: "'Segoe UI', system-ui, sans-serif",
  },
  main: {
    flex: 1,
    minHeight: 0,
    display: 'flex',
    gap: '24px',
    padding: '24px',
    alignItems: 'stretch',
    overflow: 'hidden',
  },
  canvasContainer: {
    flexShrink: 0,
    overflowY: 'auto',
    alignSelf: 'flex-start',
    maxHeight: '100%',
  },
  panelContainer: {
    flex: 1,
    minWidth: '280px',
    maxWidth: '360px',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
  },
};
