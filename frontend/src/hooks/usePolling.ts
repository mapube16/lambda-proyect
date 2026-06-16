import { useEffect, useRef, useCallback } from 'react';
import { useOfficeStore } from '../store/officeStore';
import type { Lead, LandaCheckpointLead } from '../store/officeStore';
import type { Agent } from '../types';
import { apiFetch } from '../lib/apiFetch';

const BACKEND = (import.meta as any).env?.VITE_BACKEND_URL || '';
const API_URL = BACKEND;

const PIPELINE_AGENTS: Agent[] = [
  { id: 'buscador-001', name: 'Buscador',    role: 'researcher', state: 'idle', current_tool: null, tool_status: null, palette: 0, seat_id: null, is_subagent: false, parent_agent_id: null },
  { id: 'scraper-001',  name: 'Scraper',      role: 'planner',    state: 'idle', current_tool: null, tool_status: null, palette: 1, seat_id: null, is_subagent: false, parent_agent_id: null },
  { id: 'analista-001', name: 'Analista B2B', role: 'reviewer',   state: 'idle', current_tool: null, tool_status: null, palette: 2, seat_id: null, is_subagent: false, parent_agent_id: null },
  { id: 'redactor-001', name: 'Redactor',     role: 'writer',     state: 'idle', current_tool: null, tool_status: null, palette: 3, seat_id: null, is_subagent: false, parent_agent_id: null },
];

const POLL_INTERVAL_MS = 3000;

export function usePolling() {
  const {
    setAgents,
    setConnected,
    setProspecting,
    setLeads,
    addLead,
    clearLeads,
    setCampaignSummary,
    setActiveTab,
    setActiveCampaign,
    addCheckpointLead,
    setCurrentRunId,
    setAgentLogs,
    isAuthenticated,
    currentRunId,
    prospecting,
    approveLead: approveLeadLocal,
    discardLead: discardLeadLocal,
  } = useOfficeStore();

  const pollRef = useRef<number | null>(null);
  const seenLeadIds = useRef<Set<string>>(new Set());

  // ── Initial hydration ────────────────────────────────────────────────────────
  const hydrateFromDB = useCallback(async () => {
    try {
      const [leadsRes, campaignRes, agentsRes] = await Promise.all([
        apiFetch(`${API_URL}/api/leads`),
        apiFetch(`${API_URL}/api/campaigns/active`),
        apiFetch(`${API_URL}/api/agents`),
      ]);
      if (leadsRes.ok) {
        const rawLeads = await leadsRes.json() as Array<Record<string, unknown>>;
        const leads: Lead[] = rawLeads.map((l, i) => ({
          id: String(l._id ?? ''),
          leadId: String(l._id ?? '') || undefined,
          title: String(l.company_name ?? l.url ?? ''),
          url: String(l.url ?? ''),
          status: String(l.system_state) === 'SUCCESS_READY_FOR_REVIEW' ? 'success'
                : String(l.system_state) === 'REJECTED_BY_AI' ? 'rejected' : 'error',
          markdown: (l.expediente_markdown as string) ?? null,
          json_payload: (l.expediente_json as Record<string, unknown>) ?? null,
          approved: l.hitl_status === 'approved' ? true : l.hitl_status === 'rejected' ? false : null,
          index: i,
          total: rawLeads.length,
          phone: l.phone as string | undefined,
          address: l.address as string | undefined,
          rating: (l.expediente_json as Record<string, unknown> | null)?.score as number | null | undefined,
        }));
        setLeads(leads);
        leads.forEach(l => seenLeadIds.current.add(l.id));
        if (leads.length > 0) setActiveTab('results');
      }
      if (agentsRes.ok) {
        const agents = await agentsRes.json() as Agent[];
        setAgents(agents.length > 0 ? agents : PIPELINE_AGENTS);
      } else {
        setAgents(PIPELINE_AGENTS);
      }
      if (campaignRes.ok) {
        const campaign = await campaignRes.json() as Record<string, unknown> | null;
        const clean: Record<string, string> = {};
        for (const [k, v] of Object.entries(campaign ?? {})) {
          if (!['_id', 'user_id', 'is_active', 'created_at'].includes(k))
            clean[k] = String(v);
        }
        setActiveCampaign(clean);
      }
    } catch (e) {
      console.error('[hydrate] error:', e);
    }
  }, [setLeads, setActiveTab, setActiveCampaign, setAgents]);

  // ── Polling loop ──────────────────────────────────────────────────────────────
  const pollRunStatus = useCallback(async (runId: string) => {
    try {
      const res = await apiFetch(`${API_URL}/api/runs/${runId}/status`);
      if (!res.ok) return;
      const data = await res.json() as {
        run_id: string;
        status: string;
        leads: Lead[];
        agent_logs: Record<string, string[]>;
        checkpoint_leads: LandaCheckpointLead[];
        total_analyzed: number;
        total_approved: number;
      };

      // Surface new leads incrementally
      for (const lead of data.leads) {
        if (!seenLeadIds.current.has(lead.id)) {
          seenLeadIds.current.add(lead.id);
          addLead(lead);
          setActiveTab('results');
        }
      }

      // Surface new checkpoint leads
      for (const cp of data.checkpoint_leads ?? []) {
        addCheckpointLead(cp);
      }

      // Agent logs
      if (data.agent_logs && Object.keys(data.agent_logs).length > 0) {
        setAgentLogs(data.agent_logs);
      }

      // Animate pipeline agents based on run state
      const runDone = data.status === 'complete' || data.status === 'error';
      const leadCount = data.leads.length;
      PIPELINE_AGENTS.forEach((a, i) => {
        const agentState = runDone ? 'idle'
          : leadCount === 0 && i === 0 ? 'thinking'
          : leadCount > 0 && i <= 2 ? 'tool_use'
          : 'waiting';
        useOfficeStore.getState().updateAgent(a.id, { state: agentState });
      });

      if (runDone) {
        setCampaignSummary({
          total_analyzed: data.total_analyzed,
          total_approved: data.total_approved,
          total_rejected: data.total_analyzed - data.total_approved,
        });
        setProspecting(false);
        setCurrentRunId(null);
      }
    } catch (e) {
      console.error('[poll] error:', e);
    }
  }, [addLead, setActiveTab, addCheckpointLead, setAgentLogs, setCampaignSummary, setProspecting, setCurrentRunId]);

  // Start/stop polling when run is active
  useEffect(() => {
    if (!prospecting || !currentRunId) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRunStatus(currentRunId); // immediate first poll
    pollRef.current = window.setInterval(() => pollRunStatus(currentRunId), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [prospecting, currentRunId, pollRunStatus]);

  // Hydrate on auth
  useEffect(() => {
    if (!isAuthenticated) return;
    setConnected(true);
    hydrateFromDB();
  }, [isAuthenticated, hydrateFromDB, setConnected]);

  // ── Actions (same interface as useWebSocket) ──────────────────────────────────
  const approveLead = useCallback(async (leadId: string | undefined, url: string) => {
    approveLeadLocal(leadId, url);
    if (!leadId) return;
    apiFetch(`${API_URL}/api/leads/${leadId}/approve`, { method: 'PATCH' })
      .catch(e => console.error('[approveLead]', e));
  }, [approveLeadLocal]);

  const rejectLead = useCallback(async (leadId: string | undefined, url: string) => {
    discardLeadLocal(leadId, url);
    if (!leadId) return;
    apiFetch(`${API_URL}/api/leads/${leadId}/reject`, { method: 'PATCH' })
      .catch(e => console.error('[rejectLead]', e));
  }, [discardLeadLocal]);

  const startProspect = useCallback(async (
    campaign: Record<string, string> = {},
    max_results: number = 20,
  ) => {
    clearLeads();
    seenLeadIds.current.clear();
    setAgentLogs({});
    setCurrentRunId(null);
    setProspecting(true);
    setAgents(PIPELINE_AGENTS);
    try {
      const res = await apiFetch(`${API_URL}/api/prospect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaign, max_results }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.run_id) setCurrentRunId(data.run_id);
      } else {
        setProspecting(false);
      }
    } catch (e) {
      console.error('Prospect error:', e);
      setProspecting(false);
    }
  }, [setProspecting, clearLeads, setCurrentRunId, setAgentLogs, setAgents]);

  // Legacy stubs — no longer needed but kept for interface compatibility
  const createAgent = useCallback((_name: string, _role: string) => {}, []);
  const runTask = useCallback((_agentId: string, _task: string) => {}, []);
  const sendMessage = useCallback((_msg: object) => {}, []);

  return { createAgent, runTask, sendMessage, startProspect, approveLead, rejectLead };
}
