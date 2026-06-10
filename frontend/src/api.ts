/**
 * API Service — Frontend ↔ Backend communication
 * Handles all HTTP calls to http://localhost:8001
 */

// En `npm run dev` (import.meta.env.DEV) apunta al backend local; en build de
// producción usa el dominio real. Antes estaba hardcodeado a prod, lo que
// impedía probar en localhost (prod tiene /auth/dev-token deshabilitado → 405).
export const API_BASE = import.meta.env.DEV
  ? "http://localhost:8001"
  : "https://my.landatech.org";
let ACCESS_TOKEN = "";

// Request deduplication: if the same request is in-flight, return the existing promise
const inflightRequests = new Map<string, Promise<any>>();

export interface AuthUser { user_id?: string; email: string; role: string; }

function persistAuth(data: any) {
  if (data.access_token) {
    ACCESS_TOKEN = data.access_token;
    localStorage.setItem("token", ACCESS_TOKEN);
  }
  const user: AuthUser = { user_id: data.user_id, email: data.email, role: data.role || "client" };
  localStorage.setItem("landa_user", JSON.stringify(user));
  return user;
}

// Login real con email/password.
export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Email o contraseña incorrectos");
  if (!data.access_token) throw new Error("El servidor no devolvió token");
  return persistAuth(data);
}

export async function register(email: string, password: string, extra: Partial<{ full_name: string; company_name: string; phone: string; country: string }> = {}) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, ...extra }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "No se pudo registrar");
  return data;
}

// Bypass de desarrollo (dpg.seguros). Útil para entrar sin credenciales en local.
export async function initAuth(_email?: string, _password?: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await res.json();
  if (data.access_token) {
    return persistAuth(data);
  }
  throw new Error("Failed to obtain dev token");
}

// Usuario cacheado (email/role) tras login. null si no hay sesión.
export function getCachedUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem("landa_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// Load token from localStorage on app start
export function loadToken() {
  const token = localStorage.getItem("token");
  if (token) {
    ACCESS_TOKEN = token;
    return true;
  }
  return false;
}

// Helper: make authenticated requests with deduplication for GET requests
async function apiCall(endpoint: string, options: RequestInit = {}) {
  const method = (options.method || "GET").toUpperCase();
  const cacheKey = `${method}:${endpoint}`;

  // Only dedupe GET requests (safe for read operations)
  if (method === "GET" && inflightRequests.has(cacheKey)) {
    return inflightRequests.get(cacheKey)!;
  }

  const requestPromise = (async () => {
    const url = `${API_BASE}${endpoint}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (typeof options.headers === 'object' && options.headers !== null) {
      Object.assign(headers, options.headers);
    }
    if (ACCESS_TOKEN) {
      headers["Authorization"] = `Bearer ${ACCESS_TOKEN}`;
    }
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      // Sesión expirada/ inválida → limpiar todo y avisar a la app para volver al login.
      ACCESS_TOKEN = "";
      localStorage.removeItem("token");
      localStorage.removeItem("landa_user");
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("landa:unauthorized"));
      }
      throw new Error("Unauthorized — token inválido o expirado");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `HTTP ${res.status}`);
    }
    return data;
  })();

  if (method === "GET") {
    inflightRequests.set(cacheKey, requestPromise);
    requestPromise.finally(() => {
      inflightRequests.delete(cacheKey);
    });
  }

  return requestPromise;
}

// ============ CAMPAIGNS ============
export async function getCampaigns(limit = 50, offset = 0) {
  return apiCall(`/api/campaigns?limit=${limit}&offset=${offset}`);
}

export async function createCampaign(data: any) {
  return apiCall("/api/campaigns", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getCampaign(campaignId: string) {
  return apiCall(`/api/campaigns/${campaignId}`);
}

export async function updateCampaign(campaignId: string, data: any) {
  return apiCall(`/api/campaigns/${campaignId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteCampaign(campaignId: string) {
  return apiCall(`/api/campaigns/${campaignId}`, {
    method: "DELETE",
  });
}

export async function launchCampaign(campaignId: string) {
  return apiCall(`/api/campaigns/${campaignId}/launch`, {
    method: "POST",
  });
}

export async function getCampaignRuns(campaignId: string) {
  return apiCall(`/api/campaigns/${campaignId}/runs`);
}

// Estado de un run de prospección (polling). Devuelve { status, leads[], total_analyzed, total_approved, ... }
export async function getRunStatus(runId: string) {
  return apiCall(`/api/runs/${runId}/status`);
}

// ============ LEADS (all nested under campaign) ============
// Map backend lead shape → UI shape used by the views.
function mapLead(l: any) {
  return {
    id: l.id,
    name: l.company_name || l.name || "",
    sector: l.sector || "",
    ciudad: l.city || "",
    score: l.score || 0,
    qualified: !!l.qualified,
    decisor: l.decision_maker || "",
    cargo: l.cargo || l.title || "",
    email: l.email || "",
    phone: l.phone || "",
    reason: l.reason || "",
    resumen: l.resumen || "",
    motivo: l.motivo || "",
    nit: l.nit || "",
    url: l.url || "",
    contratos_secop: l.contratos_secop,
    valor_total: l.valor_total,
    fecha_matricula: l.fecha_matricula,
    opens: l.opens || 0,
    clicks: l.clicks || 0,
    replies: l.replies || 0,
    status: l.status === "approved" ? "opened" : l.status || "pending",
  };
}

export async function getLeads(campaignId: string, limit = 50, offset = 0) {
  const data = await apiCall(`/api/campaigns/${campaignId}/leads?limit=${limit}&offset=${offset}`);
  return { ...data, leads: (data.leads || []).map(mapLead) };
}

export async function approveLead(campaignId: string, leadId: string, notes?: string) {
  return apiCall(`/api/campaigns/${campaignId}/leads/${leadId}/approve`, {
    method: "POST",
    body: JSON.stringify({ notes }),
  });
}

export async function sendLead(campaignId: string, leadId: string, channel: string, body: string, subject?: string) {
  return apiCall(`/api/campaigns/${campaignId}/leads/${leadId}/send`, {
    method: "POST",
    body: JSON.stringify({ channel, body, subject }),
  });
}

export async function editLead(campaignId: string, leadId: string, data: any) {
  return apiCall(`/api/campaigns/${campaignId}/leads/${leadId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteLead(campaignId: string, leadId: string) {
  return apiCall(`/api/campaigns/${campaignId}/leads/${leadId}`, {
    method: "DELETE",
  });
}

// ============ KPIs & METRICS ============
// Backend returns {leads_qualified, leads_approved, approval_rate, ...}.
// The Inicio view renders an array of KPI cards, so map it here.
export async function getKPIs(campaignId: string) {
  const k = await apiCall(`/api/campaigns/${campaignId}/kpis`);
  return {
    raw: k,
    kpis: [
      { label: "Leads calificados", value: k.leads_qualified ?? 0, trend: "—", spark: [0, k.leads_qualified ?? 0], color: "var(--primary)" },
      { label: "Aprobados por ti", value: k.leads_approved ?? 0, trend: "—", spark: [0, k.leads_approved ?? 0], color: "var(--green)" },
      { label: "Tasa de aprobación", value: Math.round((k.approval_rate ?? 0) * 100) + "%", trend: "—", spark: [0, (k.approval_rate ?? 0) * 100], color: "var(--r-buscador)" },
      { label: "Enviados", value: k.leads_sent ?? 0, trend: "—", spark: [0, k.leads_sent ?? 0], color: "var(--r-scraper)" },
    ],
  };
}

export async function getMetrics(campaignId: string) {
  return apiCall(`/api/campaigns/${campaignId}/metrics`);
}

export async function getQuota() {
  return apiCall(`/api/tenant/quota`);
}

// ============ CHAT (la Reina) ============
// POST /api/chat/prospect → single-turn NL. Returns either
// { status: "extracted", campaign } or { status: "needs_clarification", reply }.
export async function sendChatMessage(message: string) {
  return apiCall(`/api/chat/prospect`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

// ============ EMAIL (conexión de buzón del cliente) ============
export async function getEmailStatus() {
  // { connected, provider, email }
  return apiCall(`/api/me/email-status`);
}

export async function getSmtpStatus() {
  return apiCall(`/api/me/smtp-status`);
}

export async function saveSmtpConfig(data: { email: string; password: string; smtp_host: string; smtp_port: number }) {
  return apiCall(`/api/me/smtp-config`, { method: "POST", body: JSON.stringify(data) });
}

export async function disconnectEmail() {
  return apiCall(`/api/me/email-disconnect`, { method: "DELETE" });
}

export async function disconnectSmtp() {
  return apiCall(`/api/me/smtp-disconnect`, { method: "DELETE" });
}

export async function getEmailTemplate() {
  return apiCall(`/api/me/email-template`);
}

export async function saveEmailTemplate(template: any) {
  return apiCall(`/api/me/email-template`, { method: "POST", body: JSON.stringify({ template }) });
}

export async function sendTestEmail(to?: string) {
  return apiCall(`/api/me/email-test`, { method: "POST", body: JSON.stringify({ to: to || null }) });
}

// OAuth: navegación top-level. El token va por query porque un redirect del
// navegador no lleva el header Authorization (el backend lo acepta como fallback).
export function emailConnectUrl(provider: "gmail" | "outlook") {
  return `${API_BASE}/auth/${provider}/connect?token=${encodeURIComponent(ACCESS_TOKEN)}`;
}

// ============ COBRANZA ============
// { enabled, configured } — usado para gatear la pestaña Cobranza en el sidebar.
export async function getCobranzaStatus() {
  return apiCall(`/api/cobranza/status`);
}

// ============ KNOWLEDGE / ONBOARDING ============
export async function saveKnowledge(data: { product_description?: string; icp_summary?: string }) {
  return apiCall(`/api/knowledge`, { method: "POST", body: JSON.stringify(data) });
}

export async function getKnowledge() {
  return apiCall(`/api/knowledge`);
}

// ============ LEARNING (Aprendizaje) ============
export async function getLearningStats() {
  // { ideal_count, rejected_count, ready_for_patterns }
  return apiCall(`/api/learning/stats`);
}

export async function getLearningPatterns() {
  // { patterns: [...] } — shape depende del detector LLM
  return apiCall(`/api/learning/patterns`);
}

// ============ Helper ============
export function setToken(token: string) {
  ACCESS_TOKEN = token;
  localStorage.setItem("token", ACCESS_TOKEN);
}

export function getToken() {
  return ACCESS_TOKEN;
}

export function logout() {
  ACCESS_TOKEN = "";
  localStorage.removeItem("token");
  localStorage.removeItem("landa_user");
}
