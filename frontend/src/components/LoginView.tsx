import { useEffect } from 'react';
import { useState } from 'react';
import { useOfficeStore } from '../store/officeStore';
import { apiFetch } from '../lib/apiFetch';

const API_URL = '';

// Inject global styles for animations
function injectGlobalStyles() {
  if (document.getElementById('login-styles')) return;
  const style = document.createElement('style');
  style.id = 'login-styles';
  style.textContent = `
    @keyframes pulseGlow {
      0%, 100% { box-shadow: 0 0 20px 0 rgba(120, 220, 232, 0.3), inset 0 0 20px 0 rgba(120, 220, 232, 0.1); }
      50% { box-shadow: 0 0 40px 4px rgba(120, 220, 232, 0.5), inset 0 0 30px 2px rgba(120, 220, 232, 0.15); }
    }
    @keyframes syncPulse {
      0%, 100% { opacity: 0.4; }
      50% { opacity: 1; }
    }
    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    input::placeholder {
      color: #6b6b7d;
    }
    input:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    input:focus {
      outline: none;
    }
    button:hover:not(:disabled) {
      opacity: 0.9;
    }
    button:focus-visible {
      outline: 2px solid rgba(120,220,232,0.5);
      outline-offset: 2px;
    }
    .landa-input-wrapper:focus-within {
      border-color: rgba(120, 220, 232, 0.5) !important;
      box-shadow: 0 2px 12px rgba(120, 220, 232, 0.12) !important;
    }
    select {
      color-scheme: dark;
      background-color: rgba(18, 18, 29, 0.8);
      color: #e0e0e0;
    }
    select option {
      background-color: #1a1a2e;
      color: #e0e0e0;
    }
  `;
  document.head.appendChild(style);
}

export function LoginView() {
  useEffect(() => {
    injectGlobalStyles();
  }, []);

  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  // Register fields
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [phone, setPhone] = useState('');
  const [country, setCountry] = useState('');
  const [agreeTerms, setAgreeTerms] = useState(false);
  
  const { setAuth } = useOfficeStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    if (tab === 'register' && !agreeTerms) {
      setError('Debes aceptar los términos y condiciones');
      return;
    }
    
    setLoading(true);
    try {
      if (tab === 'register') {
        const res = await apiFetch(`${API_URL}/auth/register-request`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            email, 
            full_name: fullName,
            company_name: companyName,
            phone,
            country,
            role: 'user'
          }),
        });
        if (!res.ok) {
          const d = await res.json();
          throw new Error(d.detail || 'Error al enviar solicitud');
        }
        // Success - show message
        setTimeout(() => {
          setError('');
          alert('¡Solicitud enviada! Nuestro equipo se pondrá en contacto pronto.');
          setFullName('');
          setCompanyName('');
          setEmail('');
          setPhone('');
          setCountry('');
          setAgreeTerms(false);
          setTab('login');
        }, 500);
        return;
      }
      
      // Login flow
      const res = await apiFetch(`${API_URL}/auth/login`, {
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

  const handleGoogleAuth = async () => {
    // Load Google SDK
    if (!(window as any).google) {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
      
      script.onload = () => {
        (window as any).google.accounts.id.initialize({
          client_id: (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID || 'YOUR_GOOGLE_CLIENT_ID',
          callback: handleGoogleCallback,
        });
        (window as any).google.accounts.id.renderButton(
          document.getElementById('google-sign-in-btn'),
          { theme: 'dark', size: 'large' }
        );
      };
    }
  };

  const handleGoogleCallback = async (response: any) => {
    const token = response.credential;
    setLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/auth/google-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || 'Error al autenticar con Google');
      }
      
      const data = await res.json();
      setAuth(data.access_token, data.email, data.role);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error en autenticación con Google');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={s.page}>
      {/* Background Circuit Pattern */}
      <div style={s.circuitBg} />
      
      {/* Gradient Blobs */}
      <div style={s.blobCyan} />
      <div style={s.blobPurple} />

      {/* Main Container */}
      <main style={s.mainContainer}>
        {/* Brand / Logo Section */}
        <div style={s.brandSection}>
          <div style={s.logoContainer}>
            <div style={s.logoPulse} />
            <div style={s.logoInner}>
              <img src="/assets/logo.svg" alt="Landa AI" style={s.logoImg} />
              <div style={s.logoCorner} />
            </div>
          </div>
          <div style={s.brandText}>
            <h1 style={s.brandTitle}>
              LANDA <span style={s.brandHighlight}>AI</span>
            </h1>
            <p style={s.brandSub}>Portal de Acceso al Sistema</p>
          </div>
        </div>

        {/* Auth Card */}
        <div style={s.authCard}>
          <div style={s.cornerTop} /><div style={s.cornerRight} />

          {/* Tabs */}
          <div style={s.tabsContainer}>
            <button
              style={{ ...s.tabButton, ...(tab === 'login' ? s.tabActive : s.tabInactive) }}
              onClick={() => setTab('login')}
            >
              Entrar
            </button>
            <button
              style={{ ...s.tabButton, ...(tab === 'register' ? s.tabActive : s.tabInactive) }}
              onClick={() => setTab('register')}
            >
              Crear cuenta
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} style={s.form}>
            {tab === 'login' ? (
              <>
                {/* LOGIN FORM */}
                {/* Email Field */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Email_Address</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type="email"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      placeholder="tu@email.com"
                      required
                      disabled={loading}
                    />
                  </div>
                </div>

                {/* Password Field */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Contraseña</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      required
                      disabled={loading}
                    />
                    <button
                      type="button"
                      style={s.visibilityBtn}
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? '👁️' : '👁️‍🗨️'}
                    </button>
                  </div>
                  <div style={s.fieldFooter}>
                    <a style={s.forgotLink} href="#">¿Olvidaste tu contraseña?</a>
                  </div>
                </div>
              </>
            ) : (
              <>
                {/* REGISTER FORM */}
                {/* Full Name */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Nombre Completo</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type="text"
                      value={fullName}
                      onChange={e => setFullName(e.target.value)}
                      placeholder="Tu nombre completo"
                      required
                      disabled={loading}
                    />
                  </div>
                </div>

                {/* Company Name */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Empresa</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type="text"
                      value={companyName}
                      onChange={e => setCompanyName(e.target.value)}
                      placeholder="Tu Empresa S.A."
                      required
                      disabled={loading}
                    />
                  </div>
                </div>

                {/* Email Field */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Email_Address</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type="email"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      placeholder="contacto@empresa.com"
                      required
                      disabled={loading}
                    />
                  </div>
                </div>

                {/* Phone */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Teléfono</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type="tel"
                      value={phone}
                      onChange={e => setPhone(e.target.value)}
                      placeholder="+57 3XX XXX XXXX"
                      disabled={loading}
                    />
                  </div>
                </div>

                {/* Country */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>País</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <select
                      style={{ ...s.input, ...s.select }}
                      value={country}
                      onChange={e => setCountry(e.target.value)}
                      required
                      disabled={loading}
                    >
                      <option value="">Seleccionar país</option>
                      <option value="AR">Argentina</option>
                      <option value="MX">México</option>
                      <option value="ES">España</option>
                      <option value="CO">Colombia</option>
                      <option value="CL">Chile</option>
                      <option value="PE">Perú</option>
                      <option value="BR">Brasil</option>
                    </select>
                  </div>
                </div>

                {/* Password Field */}
                <div style={s.fieldGroup}>
                  <label style={s.fieldLabel}>Contraseña</label>
                  <div className="landa-input-wrapper" style={s.inputWrapper}>
                    <input
                      style={s.input}
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      required
                      disabled={loading}
                    />
                    <button
                      type="button"
                      style={s.visibilityBtn}
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? '👁️' : '👁️‍🗨️'}
                    </button>
                  </div>
                </div>

                {/* Agree Terms */}
                <div style={s.checkboxGroup}>
                  <input
                    type="checkbox"
                    id="terms"
                    checked={agreeTerms}
                    onChange={e => setAgreeTerms(e.target.checked)}
                    disabled={loading}
                    style={s.checkbox}
                  />
                  <label htmlFor="terms" style={s.checkboxLabel}>
                    Acepto los{' '}
                    <a href="#" style={s.termsLink}>
                      términos y condiciones
                    </a>
                  </label>
                </div>
              </>
            )}

            {error && <div style={s.errorBox}>{error}</div>}

            {/* Submit Button */}
            <button
              style={{ ...s.submitBtn, ...(loading ? s.submitBtnLoading : {}) }}
              type="submit"
              disabled={loading}
            >
              {loading ? 'PROCESSING...' : tab === 'login' ? 'AUTHORIZE ACCESS' : 'CREATE ACCOUNT'}
            </button>
          </form>

          {/* Google Auth */}
          <div style={s.biometricSection}>
            <p style={s.biometricLabel}>Or auth via Google</p>
            <button 
              style={s.googleBtn} 
              type="button" 
              onClick={handleGoogleAuth}
              disabled={loading}
            >
              <svg style={{width: 20, height: 20, marginRight: 8}} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              GOOGLE
            </button>
          </div>
        </div>

        {/* Footer */}
        <footer style={s.footer}>
          <div style={s.footerStats}>
            <div style={s.statItem}>
              <span style={s.statusDot} />
              SISTEMA: ACTIVO
            </div>
            <div style={s.statItem}>ACCESO: SEGURO</div>
          </div>
          <p style={s.footerCopy}>© 2026 Landa AI</p>
        </footer>
      </main>

      {/* Corner Decorators (Desktop) */}
      <div style={s.cornerDecoratorLeft}>
        <div style={s.decoratorText}>
          <div>LAT: 4.7110° N</div>
          <div>LONG: 74.0721° W</div>
          <div style={s.decoratorEncrypt}>ENCRYPTION: AES-256-GCM</div>
        </div>
      </div>

      <div style={s.cornerDecoratorRight}>
        <div style={s.decoratorTextRight}>
          <div style={s.syncPulse}>CONECTANDO <span style={s.syncDot} /></div>
          <div>UPTIME: 99.98%</div>
        </div>
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  page: {
    position: 'relative',
    width: '100%',
    height: '100vh',
    background: '#12121d',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    fontFamily: 'Inter, system-ui, sans-serif',
  },

  /* Background & Decorations */
  circuitBg: {
    position: 'absolute',
    inset: 0,
    backgroundImage: `
      linear-gradient(0deg, rgba(120, 220, 232, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(120, 220, 232, 0.03) 1px, transparent 1px)
    `,
    backgroundSize: '24px 24px',
    pointerEvents: 'none',
    zIndex: 1,
  },
  blobCyan: {
    position: 'absolute',
    top: '-10%',
    left: '-5%',
    width: 600,
    height: 600,
    background: 'radial-gradient(circle, rgba(120, 220, 232, 0.15) 0%, transparent 70%)',
    borderRadius: '50%',
    filter: 'blur(80px)',
    pointerEvents: 'none',
    zIndex: 1,
  },
  blobPurple: {
    position: 'absolute',
    bottom: '-5%',
    right: '-10%',
    width: 700,
    height: 700,
    background: 'radial-gradient(circle, rgba(171, 157, 242, 0.12) 0%, transparent 70%)',
    borderRadius: '50%',
    filter: 'blur(100px)',
    pointerEvents: 'none',
    zIndex: 1,
  },

  /* Main Container */
  mainContainer: {
    position: 'relative',
    zIndex: 10,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 32,
    maxWidth: 440,
    width: '100%',
    padding: '0 20px',
  } as React.CSSProperties,

  /* Brand Section */
  brandSection: {
    display: 'flex',
    alignItems: 'center',
    gap: 20,
    marginBottom: 12,
  },
  logoContainer: {
    position: 'relative',
    width: 72,
    height: 72,
  },
  logoPulse: {
    position: 'absolute',
    inset: 0,
    borderRadius: '50%',
    background: 'rgba(120, 220, 232, 0.2)',
    animation: 'pulseGlow 3s ease-in-out infinite',
  },
  logoInner: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, rgba(120, 220, 232, 0.1) 0%, rgba(169, 220, 118, 0.05) 100%)',
    borderRadius: '12px',
    border: '1px solid rgba(120, 220, 232, 0.2)',
    backdropFilter: 'blur(8px)',
  },
  logoImg: {
    width: 54,
    height: 54,
    display: 'block',
  },
  logoCorner: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 8,
    height: 8,
    border: '2px solid #78dce8',
  },
  brandText: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  brandTitle: {
    margin: 0,
    fontSize: 28,
    fontWeight: 700,
    letterSpacing: '-0.5px',
    color: '#b0b1b9',
    fontFamily: "'Space Grotesk', system-ui, sans-serif",
  },
  brandHighlight: {
    background: 'linear-gradient(90deg, #78dce8 0%, #a9dc76 100%)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  brandSub: {
    margin: 0,
    fontSize: 12,
    color: '#6b6b7d',
    letterSpacing: '0.5px',
    fontFamily: 'Inter, system-ui, sans-serif',
  },

  /* Auth Card */
  authCard: {
    position: 'relative',
    width: '100%',
    background: 'linear-gradient(135deg, rgba(25, 25, 42, 0.8) 0%, rgba(30, 30, 50, 0.8) 100%)',
    border: '1px solid rgba(120, 220, 232, 0.1)',
    borderRadius: 16,
    backdropFilter: 'blur(10px)',
    padding: 36,
    display: 'flex',
    flexDirection: 'column',
    gap: 24,
    boxShadow: `
      0 8px 32px rgba(0, 0, 0, 0.3),
      inset 0 1px 1px rgba(120, 220, 232, 0.1)
    `,
  },
  cornerTop: {
    position: 'absolute',
    top: 12,
    left: 12,
    width: 16,
    height: 16,
    border: '2px solid #78dce8',
    borderRight: 'none',
    borderBottom: 'none',
  },
  cornerRight: {
    position: 'absolute',
    top: 12,
    right: 12,
    width: 16,
    height: 16,
    border: '2px solid #ab9df2',
    borderLeft: 'none',
    borderBottom: 'none',
  },

  /* Tabs */
  tabsContainer: {
    display: 'flex',
    gap: 8,
    background: 'rgba(18, 18, 29, 0.6)',
    borderRadius: 10,
    padding: 6,
    border: '1px solid rgba(120, 220, 232, 0.05)',
  },
  tabButton: {
    flex: 1,
    padding: '10px 16px',
    border: 'none',
    borderRadius: 8,
    background: 'transparent',
    color: '#6b6b7d',
    fontSize: 14,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    fontFamily: 'Inter, system-ui, sans-serif',
    letterSpacing: '0.3px',
  },
  tabActive: {
    background: 'linear-gradient(135deg, rgba(120, 220, 232, 0.15) 0%, rgba(169, 220, 118, 0.08) 100%)',
    color: '#78dce8',
    border: '1px solid rgba(120, 220, 232, 0.2)',
    boxShadow: '0 4px 16px rgba(120, 220, 232, 0.15)',
  },
  tabInactive: {
    color: '#ffffff',
  },

  /* Form */
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },

  /* Field Group */
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  twoColumns: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 12,
  },
  fieldLabel: {
    fontSize: 12,
    fontWeight: 800,
    color: '#78dce8',
    letterSpacing: '0.8px',
    textTransform: 'uppercase',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  inputWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    background: 'rgba(18, 18, 29, 0.6)',
    border: '1px solid rgba(120, 220, 232, 0.1)',
    borderRadius: 10,
    padding: '0 12px',
    transition: 'all 0.2s ease',
  },
  inputIcon: {
    display: 'flex',
    alignItems: 'center',
    marginRight: 10,
    fontSize: 16,
    color: '#78dce8',
  },
  input: {
    flex: 1,
    padding: '12px 0',
    background: 'transparent',
    border: 'none',
    color: '#e0e0e0',
    fontSize: 14,
    fontFamily: 'Inter, system-ui, sans-serif',
    outline: 'none',
    transition: 'color 0.2s ease',
  },
  select: {
    cursor: 'pointer',
    width: '100%',
  },
  visibilityBtn: {
    background: 'transparent',
    border: 'none',
    color: '#78dce8',
    fontSize: 16,
    cursor: 'pointer',
    padding: '6px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'transform 0.15s ease',
  },
  fieldFooter: {
    display: 'flex',
    justifyContent: 'flex-end',
    paddingTop: 4,
  },
  forgotLink: {
    fontSize: 12,
    color: '#ab9df2',
    textDecoration: 'none',
    cursor: 'pointer',
    transition: 'color 0.2s ease',
  },
  checkboxGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 0',
  },
  checkbox: {
    width: 18,
    height: 18,
    cursor: 'pointer',
    accentColor: '#78dce8',
  },
  checkboxLabel: {
    fontSize: 13,
    color: '#b0b1b9',
    fontFamily: 'Inter, system-ui, sans-serif',
    cursor: 'pointer',
  },
  termsLink: {
    color: '#78dce8',
    textDecoration: 'none',
    transition: 'color 0.2s ease',
  },

  /* Error Box */
  errorBox: {
    padding: '12px 14px',
    background: 'rgba(255, 97, 136, 0.12)',
    border: '1px solid rgba(255, 97, 136, 0.3)',
    borderRadius: 8,
    color: '#ff6188',
    fontSize: 13,
    fontFamily: 'Inter, system-ui, sans-serif',
    lineHeight: 1.4,
  },

  /* Submit Button */
  submitBtn: {
    padding: '14px 20px',
    marginTop: 8,
    background: 'linear-gradient(90deg, #78dce8 0%, #a9dc76 100%)',
    border: 'none',
    borderRadius: 10,
    color: '#12121d',
    fontWeight: 700,
    fontSize: 14,
    letterSpacing: '0.5px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    fontFamily: 'Inter, system-ui, sans-serif',
    boxShadow: '0 8px 24px rgba(120, 220, 232, 0.2)',
  },
  submitBtnLoading: {
    opacity: 0.8,
    transform: 'scale(0.98)',
  },

  /* Biometric Section */
  biometricSection: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 12,
    paddingTop: 12,
    borderTop: '1px solid rgba(120, 220, 232, 0.1)',
  },
  biometricLabel: {
    margin: 0,
    fontSize: 12,
    color: '#6b6b7d',
    fontFamily: 'Inter, system-ui, sans-serif',
  },
  biometricButtons: {
    display: 'flex',
    gap: 12,
  },
  biometricBtn: {
    width: 48,
    height: 48,
    borderRadius: 10,
    border: '1px solid rgba(120, 220, 232, 0.15)',
    background: 'rgba(120, 220, 232, 0.08)',
    fontSize: 20,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  googleBtn: {
    padding: '12px 24px',
    borderRadius: 10,
    border: '1px solid rgba(120, 220, 232, 0.2)',
    background: 'rgba(66, 133, 244, 0.1)',
    color: '#4285f4',
    fontWeight: 600,
    fontSize: 14,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'Inter, system-ui, sans-serif',
  } as React.CSSProperties,

  /* Footer */
  footer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 8,
    marginTop: 12,
  },
  footerStats: {
    display: 'flex',
    gap: 24,
    fontSize: 11,
    color: '#6b6b7d',
    fontFamily: 'Space Grotesk, system-ui, sans-serif',
    letterSpacing: '0.5px',
  },
  statItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#a9dc76',
    display: 'inline-block',
    animation: 'syncPulse 2s ease-in-out infinite',
  },
  footerCopy: {
    margin: 0,
    fontSize: 10,
    color: '#4a4a5e',
    fontFamily: 'Inter, system-ui, sans-serif',
    letterSpacing: '0.3px',
  },

  /* Decorators */
  cornerDecoratorLeft: {
    position: 'absolute',
    bottom: 32,
    left: 32,
    fontSize: 11,
    color: '#6b6b7d',
    fontFamily: 'Space Grotesk, system-ui, sans-serif',
    letterSpacing: '0.5px',
    lineHeight: 1.6,
    display: 'none',
  } as React.CSSProperties,
  decoratorText: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    padding: '12px 16px',
    background: 'rgba(18, 18, 29, 0.6)',
    border: '1px solid rgba(120, 220, 232, 0.1)',
    borderRadius: 8,
    backdropFilter: 'blur(8px)',
  },
  decoratorEncrypt: {
    color: '#78dce8',
    fontWeight: 600,
  },
  cornerDecoratorRight: {
    position: 'absolute',
    bottom: 32,
    right: 32,
    fontSize: 11,
    color: '#6b6b7d',
    fontFamily: 'Space Grotesk, system-ui, sans-serif',
    letterSpacing: '0.5px',
    lineHeight: 1.6,
    display: 'none',
  } as React.CSSProperties,
  decoratorTextRight: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    padding: '12px 16px',
    background: 'rgba(18, 18, 29, 0.6)',
    border: '1px solid rgba(171, 157, 242, 0.1)',
    borderRadius: 8,
    backdropFilter: 'blur(8px)',
  },
  syncPulse: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    color: '#a9dc76',
    fontWeight: 600,
  },
  syncDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: '#a9dc76',
    display: 'inline-block',
    animation: 'blink 1.5s ease-in-out infinite',
  },
};
