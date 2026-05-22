import { useState, useEffect } from 'react';
import { useOfficeStore } from './store/officeStore';
import type { Agent } from './types/index';

// SVG Icons for sidebar
const HomeIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
const BarChartIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>;
const CheckIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>;
const UsersIcon = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>;

const _BACKEND = (import.meta as any).env?.VITE_BACKEND_URL || '';
import { apiFetch } from './lib/apiFetch';
import { LoginView } from './components/LoginView';
import { StaffDashboard } from './components/StaffDashboard';
import { ClientDashboard } from './components/ClientDashboard';
import { OfficeCanvas } from './components/OfficeCanvas';
import { AgentPanel } from './components/AgentPanel';
import { useWebSocket } from './hooks/useWebSocket';
import { useGameLoop } from './hooks/useGameLoop';

const C = {
  bg:      'linear-gradient(135deg, #0a0a14 0%, #0d0d18 50%, #0a0a14 100%)',
  bgSolid: '#0a0a14',
  s0:      'rgba(18,18,29,0.85)',
  s0Blur:  'blur(20px)',
  s1:      'rgba(27,26,38,0.7)',
  s3:      '#2c2b3a',
  s4:      '#343440',
  text:    '#f0eff8',
  textMid: '#d8d6e6',
  muted:   '#9b9aaa',
  cyan:    '#5dd9f5',
  cyanDim: 'rgba(93,217,245,0.08)',
  green:   '#7ee8a3',
  SG:      "'Space Grotesk', system-ui, sans-serif",
  IN:      "'Inter', system-ui, sans-serif",
};

function NavLink({ label, active = false, onClick }: { label: string; active?: boolean; onClick?: () => void }) {
  const [hov, setHov] = useState(false);
  return (
    <span
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        fontFamily: C.SG, fontSize: 13,
        fontWeight: active ? 700 : 400,
        color: active ? C.cyan : hov ? C.text : C.muted,
        letterSpacing: '-0.01em',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'color 0.15s',
      }}
    >
      {label}
    </span>
  );
}

function RailBtn({ icon, active = false, title, onClick }: {
  icon: React.ReactNode; active?: boolean; title?: string; onClick?: () => void;
}) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      title={title}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width: 44, height: 44, borderRadius: 10,
        cursor: onClick ? 'pointer' : 'default',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: active ? C.cyan : hov ? C.text : C.muted,
        background: active
          ? 'rgba(93,217,245,0.12)'
          : hov ? 'rgba(93,217,245,0.08)' : 'transparent',
        border: active ? '1px solid rgba(93,217,245,0.25)' : hov ? '1px solid rgba(93,217,245,0.15)' : '1px solid transparent',
        backdropFilter: active ? 'blur(6px)' : 'none',
        boxShadow: active ? '0 0 16px rgba(93,217,245,0.2), inset 0 1px 0 rgba(93,217,245,0.15)' : 'none',
        transition: 'all 0.25s ease-out',
        transform: hov ? 'scale(1.08)' : 'scale(1)',
      }}
    >
      {icon}
    </button>
  );
}

function OfficeView() {
  const { createAgent, runTask, startProspect, approveLead, rejectLead } = useWebSocket();
  useGameLoop();
  const { userEmail, clearAuth, agents, setAgents } = useOfficeStore();

  // Hard fetch on mount — bypasses all store/WS timing issues
  useEffect(() => {
    apiFetch(`${_BACKEND}/api/agents`)
      .then(r => r.ok ? r.json() : [])
      .then((data: Agent[]) => { if (data?.length) setAgents(data); })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [view, setView] = useState<'office' | 'dashboard'>('office');
  const [dashboardInitialSection, setDashboardInitialSection] = useState<
    'leads' | 'cobranza' | 'email' | 'canales' | undefined
  >(undefined);
  const agentCount = agents.size;
  const activeAgents = Array.from(agents.values()).filter(a => a.state !== 'idle').length;

  if (view === 'dashboard') {
    return (
      <ClientDashboard
        onBack={() => setView('office')}
        initialSection={dashboardInitialSection}
      />
    );
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh',
      background: C.bg as string, color: C.text, fontFamily: C.IN, overflow: 'hidden',
    }}>

      {/* ── Fixed top nav ── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 50,
        height: 64, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', padding: '0 24px',
        background: C.s0 as string,
        backdropFilter: C.s0Blur,
        borderBottom: '1px solid rgba(93,217,245,0.08)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 36 }}>
          <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 20, color: C.cyan, letterSpacing: '-0.03em' }}>
            Landa
          </span>
          <div style={{ display: 'flex', gap: 24 }}>
            <NavLink label="Oficina" active />
            <NavLink label="Pipeline" onClick={() => setView('dashboard')} />
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {userEmail && (
            <span style={{ fontFamily: C.SG, fontSize: 11, color: C.muted }}>
              {userEmail}
            </span>
          )}
          <button
            onClick={clearAuth}
            style={{
              padding: '4px 12px', borderRadius: 2,
              border: '1px solid rgba(120,220,232,0.2)',
              background: 'transparent', color: C.cyan,
              fontFamily: C.SG, fontSize: 11, letterSpacing: '0.04em',
              cursor: 'pointer', transition: 'background 0.15s',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = C.cyanDim; }}
            onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
          >
            logout
          </button>
        </div>

        {/* gradient separator line */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 1,
          background: 'linear-gradient(to right, transparent, rgba(120,220,232,0.2), transparent)',
          pointerEvents: 'none',
        }} />
      </nav>

      {/* ── Body (below fixed nav) ── */}
      <div style={{ display: 'flex', flex: 1, paddingTop: 64, overflow: 'hidden' }}>

        {/* ── Left icon rail ── */}
        <div style={{
          width: 64, flexShrink: 0,
          background: 'rgba(18,18,29,0.85)', backdropFilter: 'blur(20px)',
          borderRight: '1px solid rgba(93,217,245,0.08)',
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          paddingTop: 24, gap: 8,
        }}>
          <RailBtn icon={<HomeIcon />} active title="Oficina" />
          <RailBtn icon={<BarChartIcon />} title="Pipeline" onClick={() => setView('dashboard')} />
          <RailBtn icon={<CheckIcon />} title="Aprobados" onClick={() => setView('dashboard')} />
          <RailBtn
            icon={<UsersIcon />}
            title="Cobros"
            onClick={() => {
              setDashboardInitialSection('cobranza');
              setView('dashboard');
            }}
          />
        </div>

        {/* ── Canvas section ── */}
        <section style={{
          flex: 1, minWidth: 0, position: 'relative',
          background: C.bgSolid, overflow: 'auto',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
          padding: 32,
        }}>
          {/* Dot grid */}
          <div style={{
            position: 'absolute', inset: 0, pointerEvents: 'none', opacity: 0.08,
            backgroundImage: 'radial-gradient(#78dce8 0.5px, transparent 0.5px)',
            backgroundSize: '24px 24px',
          }} />

          {/* SYSTEM_LIVE chip */}
          <div style={{
            position: 'absolute', top: 16, left: 72, zIndex: 10,
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'rgba(31,30,42,0.85)', backdropFilter: 'blur(8px)',
            padding: '6px 14px', borderRadius: 8,
            border: '1px solid rgba(120,220,232,0.18)',
            pointerEvents: 'none',
          }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: C.green, boxShadow: `0 0 6px ${C.green}`,
              display: 'inline-block',
            }} />
            <span style={{
              fontFamily: C.SG, fontSize: 10, fontWeight: 600,
              color: C.text, textTransform: 'uppercase', letterSpacing: '0.15em',
            }}>
              System_Live
            </span>
          </div>

          {/* Stats overlay */}
          <div style={{
            position: 'absolute', bottom: 24, left: 72, zIndex: 10,
            background: 'rgba(18,18,29,0.8)', backdropFilter: 'blur(10px)',
            padding: '12px 18px', borderRadius: 12,
            border: '1px solid rgba(62,73,74,0.25)',
            display: 'flex', gap: 18, alignItems: 'center',
            pointerEvents: 'none',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontFamily: C.SG, fontSize: 9, color: C.cyan, textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                Agentes
              </span>
              <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 22, color: C.text, lineHeight: 1.2 }}>
                {String(agentCount).padStart(2, '0')}
              </span>
            </div>
            <div style={{ width: 1, height: 32, background: 'rgba(62,73,74,0.4)' }} />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontFamily: C.SG, fontSize: 9, color: C.cyan, textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                Activos
              </span>
              <span style={{ fontFamily: C.SG, fontWeight: 700, fontSize: 22, color: activeAgents > 0 ? C.green : C.text, lineHeight: 1.2 }}>
                {String(activeAgents).padStart(2, '0')}
              </span>
            </div>
          </div>

          {/* Pixel office canvas — untouched */}
          <OfficeCanvas />
        </section>

        {/* ── Right panel (AgentPanel) ── */}
        <aside style={{
          width: 440, flexShrink: 0,
          background: C.s1,
          display: 'flex', flexDirection: 'column',
          height: '100%', overflow: 'hidden',
          boxShadow: '-8px 0 28px rgba(0,0,0,0.35)',
        }}>
          <AgentPanel
            createAgent={createAgent}
            runTask={runTask}
            startProspect={startProspect}
            approveLead={approveLead}
            rejectLead={rejectLead}
          />
        </aside>
      </div>
    </div>
  );
}

export default function App() {
  const { isAuthenticated, userRole, setAuth } = useOfficeStore();
  // On load the Zustand store starts isAuthenticated=false, but the session may
  // still be valid via the httpOnly cookie. Ask the backend who we are; if the
  // cookie is good, rehydrate the store so a reload doesn't bounce to login.
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await apiFetch(`${_BACKEND}/auth/me`);
        if (alive && r.ok) {
          const me = await r.json();
          if (me?.authenticated) setAuth(me.email ?? '', me.role ?? 'client');
        }
      } catch {
        /* not authenticated — stay on login */
      } finally {
        if (alive) setCheckingSession(false);
      }
    })();
    return () => { alive = false; };
  }, [setAuth]);

  if (checkingSession && !isAuthenticated) {
    return (
      <div style={{
        height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0d0d18', color: '#8a8a9a', fontFamily: "'Inter', system-ui, sans-serif", fontSize: 13,
      }}>
        Cargando…
      </div>
    );
  }

  if (!isAuthenticated) return <LoginView />;
  if (userRole === 'staff') return <StaffDashboard />;
  return <OfficeView />;
}
