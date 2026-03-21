import { useState } from 'react';
import { useOfficeStore } from '../store/officeStore';

const API_URL = 'http://localhost:8001';

export function LoginView() {
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useOfficeStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (tab === 'register') {
        const res = await fetch(`${API_URL}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const d = await res.json();
          throw new Error(d.detail || 'Error al registrar');
        }
        // Auto-login after register
      }
      const res = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || 'Credenciales incorrectas');
      }
      const data = await res.json();
      setAuth(data.access_token, data.email, data.role);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error de conexión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.page}>
      <div style={s.card}>
        {/* Logo */}
        <div style={s.logoRow}>
          <span style={s.bee}>🐝</span>
          <div>
            <div style={s.logoText}>Isomorph Office</div>
            <div style={s.logoSub}>B2B Prospecting Platform</div>
          </div>
        </div>

        {/* Tabs */}
        <div style={s.tabs}>
          <button style={{ ...s.tab, ...(tab === 'login' ? s.tabActive : {}) }} onClick={() => setTab('login')}>
            Entrar
          </button>
          <button style={{ ...s.tab, ...(tab === 'register' ? s.tabActive : {}) }} onClick={() => setTab('register')}>
            Crear cuenta
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={s.form}>
          <label style={s.label}>Email</label>
          <input
            style={s.input}
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="tu@email.com"
            autoFocus
            required
          />
          <label style={s.label}>Contraseña</label>
          <input
            style={s.input}
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="••••••••"
            required
          />
          {error && <div style={s.error}>{error}</div>}
          <button style={s.btn} type="submit" disabled={loading}>
            {loading ? 'Cargando...' : tab === 'login' ? 'Entrar' : 'Crear cuenta'}
          </button>
        </form>
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    height: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(180deg, #1a1a2e 0%, #16162a 100%)',
  },
  card: {
    background: '#1e1e32',
    border: '1px solid #2a2a4a',
    borderRadius: 16,
    padding: '40px 36px',
    width: 360,
    display: 'flex',
    flexDirection: 'column',
    gap: 20,
  },
  logoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    marginBottom: 4,
  },
  bee: { fontSize: 40 },
  logoText: {
    fontSize: 20,
    fontWeight: 700,
    background: 'linear-gradient(90deg, #78dce8, #a9dc76)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
  },
  logoSub: {
    fontSize: 12,
    color: '#888',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
  },
  tabs: {
    display: 'flex',
    gap: 4,
    background: '#16162a',
    borderRadius: 8,
    padding: 4,
  },
  tab: {
    flex: 1,
    padding: '8px 0',
    border: 'none',
    borderRadius: 6,
    background: 'transparent',
    color: '#888',
    cursor: 'pointer',
    fontSize: 14,
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    transition: 'all 0.15s',
  },
  tabActive: {
    background: '#2a2a4a',
    color: '#e0e0e0',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  label: {
    fontSize: 12,
    color: '#888',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    marginBottom: -4,
  },
  input: {
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #2a2a4a',
    background: '#16162a',
    color: '#e0e0e0',
    fontSize: 14,
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    outline: 'none',
  },
  error: {
    fontSize: 13,
    color: '#ff6188',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    padding: '6px 0',
  },
  btn: {
    marginTop: 6,
    padding: '12px',
    borderRadius: 8,
    border: 'none',
    background: 'linear-gradient(90deg, #78dce8, #a9dc76)',
    color: '#1a1a2e',
    fontWeight: 700,
    fontSize: 15,
    cursor: 'pointer',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    transition: 'opacity 0.15s',
  },
};
