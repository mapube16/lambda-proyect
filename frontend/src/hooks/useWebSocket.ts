import { useEffect, useRef, useCallback } from 'react';
import { useOfficeStore } from '../store/officeStore';
import type { Lead } from '../store/officeStore';
import type { WSMessage, AgentUpdateMessage, InitialStateMessage, Agent } from '../types';

const API_URL = 'http://localhost:8001';
const WS_URL_BASE = 'ws://localhost:8001/ws';

const MAX_RECONNECT_DELAY = 30_000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectDelayRef = useRef<number>(3000);

  const {
    setAgents,
    updateAgent,
    addAgent,
    removeAgent,
    setWebSocket,
    setConnected,
    setExpediente,
    setProspecting,
    addLead,
    setLeads,
    approveLead: approveLeadLocal,
    discardLead: discardLeadLocal,
    clearLeads,
    setCampaignSummary,
    setActiveTab,
    setActiveCampaign,
    isAuthenticated,
    authToken,
  } = useOfficeStore();

  // Load leads + active campaign from MongoDB after connect
  const hydrateFromDB = useCallback(async (token: string) => {
    const headers = { 'Authorization': `Bearer ${token}` };
    try {
      const [leadsRes, campaignRes] = await Promise.all([
        fetch(`${API_URL}/api/leads`, { headers }),
        fetch(`${API_URL}/api/campaigns/active`, { headers }),
      ]);
      if (leadsRes.ok) {
        const rawLeads = await leadsRes.json() as Array<Record<string, unknown>>;
        const leads: Lead[] = rawLeads.map((l, i) => {
          const sysState = String(l.system_state ?? '');
          const status: Lead['status'] = sysState === 'SUCCESS_READY_FOR_REVIEW' ? 'success'
            : sysState === 'REJECTED_BY_AI' ? 'rejected' : 'error';
          const leadId = String(l._id ?? '');
          return {
            id: leadId || `${String(l.url ?? '')}#${i}`,
            leadId: leadId || undefined,
            title: String(l.company_name ?? l.url ?? ''),
            url: String(l.url ?? ''),
            status,
            markdown: (l.expediente_markdown as string) ?? null,
            json_payload: (l.expediente_json as Record<string, unknown>) ?? null,
            approved: l.hitl_status === 'approved' ? true : l.hitl_status === 'rejected' ? false : null,
            index: i,
            total: rawLeads.length,
            phone: l.phone as string | undefined,
            address: l.address as string | undefined,
            rating: (l.expediente_json as Record<string, unknown> | null)?.score as number | null | undefined,
          };
        });
        setLeads(leads);
        if (leads.length > 0) setActiveTab('results');
      }
      if (campaignRes.ok) {
        const campaign = await campaignRes.json() as Record<string, unknown>;
        const clean: Record<string, string> = {};
        for (const [k, v] of Object.entries(campaign)) {
          if (!['_id', 'user_id', 'is_active', 'created_at'].includes(k)) {
            clean[k] = String(v);
          }
        }
        setActiveCampaign(clean);
      }
    } catch (e) {
      console.error('[hydrate] error:', e);
    }
  }, [setLeads, setActiveTab, setActiveCampaign]);

  const approveLead = useCallback(async (leadId: string | undefined, url: string) => {
    approveLeadLocal(leadId, url);
    if (!leadId) return;
    const token = useOfficeStore.getState().authToken;
    if (!token) return;
    fetch(`${API_URL}/api/leads/${leadId}/approve`, {
      method: 'PATCH',
      headers: { 'Authorization': `Bearer ${token}` },
    }).catch(e => console.error('[approveLead]', e));
  }, [approveLeadLocal]);

  const rejectLead = useCallback(async (leadId: string | undefined, url: string) => {
    discardLeadLocal(leadId, url);
    if (!leadId) return;
    const token = useOfficeStore.getState().authToken;
    if (!token) return;
    fetch(`${API_URL}/api/leads/${leadId}/reject`, {
      method: 'PATCH',
      headers: { 'Authorization': `Bearer ${token}` },
    }).catch(e => console.error('[rejectLead]', e));
  }, [discardLeadLocal]);

  const sendMessage = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const createAgent = useCallback((name: string, role: string) => {
    sendMessage({ type: 'create_agent', name, role });
  }, [sendMessage]);

  const runTask = useCallback((agentId: string, task: string) => {
    sendMessage({ type: 'run_task', agent_id: agentId, task });
  }, [sendMessage]);

  const handleMessage = useCallback((data: WSMessage) => {
    switch (data.type) {
      case 'initial_state': {
        const msg = data as InitialStateMessage;
        console.log('📦 Received initial state:', msg.agents.length, 'agents');
        setAgents(msg.agents);
        break;
      }
      case 'agent_update': {
        const msg = data as AgentUpdateMessage;
        updateAgent(msg.agent_id, {
          state: msg.state,
          current_tool: msg.current_tool || null,
          tool_status: msg.tool_status || null,
        });
        break;
      }
      case 'agent_created': {
        const agent = (data as unknown as { agent: Agent }).agent;
        addAgent(agent);
        break;
      }
      case 'agent_removed': {
        const agentId = (data as unknown as { agent_id: string }).agent_id;
        removeAgent(agentId);
        break;
      }
      case 'lead_result': {
        const lead = data as unknown as Lead & { type: string; phone?: string; address?: string; rating?: number; lead_id?: string };
        addLead({
          id: lead.lead_id ?? lead.url,
          leadId: lead.lead_id,
          title: lead.title || lead.url,
          url: lead.url,
          status: lead.status,
          markdown: lead.markdown ?? null,
          json_payload: lead.json_payload ?? null,
          index: lead.index,
          total: lead.total,
          phone: lead.phone,
          address: lead.address,
          rating: lead.rating,
        });
        setActiveTab('results');
        break;
      }
      case 'campaign_complete': {
        const msg = data as unknown as {
          total_analyzed: number; total_approved: number; total_rejected: number;
        };
        setCampaignSummary({
          total_analyzed: msg.total_analyzed,
          total_approved: msg.total_approved,
          total_rejected: msg.total_rejected,
        });
        setProspecting(false);
        break;
      }
      case 'discovery_complete': {
        console.log('🔍 Discovery:', (data as unknown as { count: number }).count, 'companies found');
        break;
      }
      case 'pong':
        break;
      default:
        console.log('Unknown message type:', data.type);
    }
  }, [setAgents, updateAgent, addAgent, removeAgent, setExpediente, setProspecting,
      addLead, clearLeads, setCampaignSummary, setActiveTab]);

  useEffect(() => {
    // Don't connect if not authenticated
    if (!isAuthenticated || !authToken) {
      wsRef.current?.close();
      return;
    }

    let mounted = true;

    const connectAsync = () => {
      if (!mounted) return;
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      if (wsRef.current?.readyState === WebSocket.CONNECTING) return;

      const token = useOfficeStore.getState().authToken;
      if (!token) return;

      const wsUrl = `${WS_URL_BASE}?token=${token}`;
      console.log('🔌 Connecting to WebSocket...');
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (mounted) {
          console.log('✅ WebSocket connected');
          reconnectDelayRef.current = 3000;
          setConnected(true);
          setWebSocket(ws);
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
          }
          hydrateFromDB(token);
        }
      };

      ws.onmessage = (event) => {
        try {
          const data: WSMessage = JSON.parse(event.data);
          handleMessage(data);
        } catch (e) {
          console.error('Failed to parse WS message:', e);
        }
      };

      ws.onclose = (event) => {
        if (mounted) {
          setConnected(false);
          setWebSocket(null);
          // Only reconnect if still authenticated
          if (!useOfficeStore.getState().isAuthenticated) return;
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 1.5, MAX_RECONNECT_DELAY);
          const delay = reconnectDelayRef.current;
          console.log(`🔌 WS closed (${event.code}) — retrying in ${Math.round(delay / 1000)}s`);
          reconnectTimeoutRef.current = window.setTimeout(connectAsync, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      wsRef.current = ws;
    };

    connectAsync();

    const heartbeat = setInterval(() => {
      sendMessage({ type: 'ping' });
    }, 30000);

    return () => {
      mounted = false;
      clearInterval(heartbeat);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
    };
  }, [isAuthenticated, authToken, handleMessage, sendMessage, hydrateFromDB]);

  const startProspect = useCallback(async (
    campaign: Record<string, string> = {},
    max_results: number = 20,
  ) => {
    const token = useOfficeStore.getState().authToken;
    if (!token) return;
    clearLeads();
    setProspecting(true);
    try {
      await fetch(`${API_URL}/api/prospect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ campaign, max_results }),
      });
    } catch (e) {
      console.error('Prospect error:', e);
      setProspecting(false);
    }
  }, [setProspecting, clearLeads]);

  return { createAgent, runTask, sendMessage, startProspect, approveLead, rejectLead };
}
