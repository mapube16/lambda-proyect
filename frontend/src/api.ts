/**
 * API Service — Frontend ↔ Backend communication
 * Handles all HTTP calls to http://localhost:8001
 */

const API_BASE = "https://my.landatech.org";
let ACCESS_TOKEN = "";

// Initialize token. In dev, use the dev-token endpoint (no rate limiting).
export async function initAuth(_email?: string, _password?: string) {
  const res = await fetch(`${API_BASE}/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await res.json();
  if (data.access_token) {
    ACCESS_TOKEN = data.access_token;
    localStorage.setItem("token", ACCESS_TOKEN);
    console.log("Dev token obtained");
    return data;
  }
  throw new Error("Failed to obtain dev token");
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

// Helper: make authenticated requests
async function apiCall(endpoint: string, options: RequestInit = {}) {
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
    localStorage.removeItem("token");
    ACCESS_TOKEN = "";
    throw new Error("Unauthorized — token inválido o expirado");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return data;
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

// ============ LEADS (all nested under campaign) ============
// Map backend lead shape → UI shape used by the views.
function mapLead(l: any) {
  return {
    id: l.id,
    name: l.company_name || l.name || "",
    sector: l.sector || "",
    ciudad: l.city || "",
    score: l.score || 0,
    decisor: l.decision_maker || "",
    cargo: l.cargo || l.title || "",
    email: l.email || "",
    phone: l.phone || "",
    reason: l.reason || "",
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
}
