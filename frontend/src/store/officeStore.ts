import { create } from 'zustand';
import type { Agent, Character, AgentState, Direction, Seat } from '../types';

const TILE_SIZE = 16;

// Work seats: only PC desk positions (with facing direction)
// dir: 0=down, 1=left, 2=right, 3=up
const WORK_SEATS: Array<{ col: number; row: number; dir: Direction }> = [
  { col: 3, row: 14, dir: 3 }, // CUSHIONED_BENCH left  → face UP toward PC at row 12
  { col: 7, row: 14, dir: 3 }, // CUSHIONED_BENCH right → face UP toward PC at row 12
  { col: 3, row: 16, dir: 2 }, // WOODEN_CHAIR_SIDE     → face RIGHT toward PC_SIDE col 4
  { col: 7, row: 16, dir: 1 }, // WOODEN_CHAIR_SIDE:left→ face LEFT toward PC_SIDE col 6
  { col: 3, row: 18, dir: 2 }, // WOODEN_CHAIR_SIDE     → face RIGHT toward PC_SIDE col 4
  { col: 7, row: 18, dir: 1 }, // WOODEN_CHAIR_SIDE:left→ face LEFT toward PC_SIDE col 6
  // Overflow seats on verified open floor (left room + corridor + right room)
  { col: 5, row: 12, dir: 3 },
  { col: 8, row: 13, dir: 1 },
  { col: 5, row: 15, dir: 2 },
  { col: 8, row: 17, dir: 1 },
  { col: 5, row: 19, dir: 2 },
  { col: 8, row: 20, dir: 3 },
  { col: 10, row: 15, dir: 2 },
  { col: 12, row: 12, dir: 3 },
  { col: 17, row: 12, dir: 3 },
  { col: 12, row: 18, dir: 2 },
  { col: 17, row: 18, dir: 1 },
  { col: 12, row: 20, dir: 2 },
  { col: 15, row: 20, dir: 3 },
];

// Seat assignments: agentId → seat (persists across renders)
const seatAssignments = new Map<string, { col: number; row: number; dir: Direction }>();

function isSeatTaken(agentId: string, seat: { col: number; row: number }): boolean {
  return Array.from(seatAssignments.entries())
    .some(([id, s]) => id !== agentId && s.col === seat.col && s.row === seat.row);
}

function getFreeSeat(agentId: string): { col: number; row: number; dir: Direction } {
  for (const seat of WORK_SEATS) {
    if (!isSeatTaken(agentId, seat)) return seat;
  }

  // Final fallback: reuse seats deterministically only if all defined seats are occupied.
  return WORK_SEATS[seatAssignments.size % WORK_SEATS.length];
}

export interface Expediente {
  status: 'success' | 'rejected';
  markdown: string | null;
  json_payload: Record<string, unknown> | null;
  url: string;
}

export interface Lead {
  id: string;           // stable local key (prefer leadId/_id)
  leadId?: string;      // MongoDB _id — used for HITL API calls
  title: string;
  url: string;
  status: 'success' | 'rejected' | 'error';
  markdown: string | null;
  json_payload: Record<string, unknown> | null;
  approved: boolean | null;  // null = pending, true = approved, false = discarded
  index: number;
  total: number;
  phone?: string;
  address?: string;
  rating?: number | null;
}

export interface CampaignSummary {
  total_analyzed: number;
  total_approved: number;
  total_rejected: number;
}

export interface LandaCheckpointLead {
  leadId: string;
  empresa: string;
  puntaje: number;
}

export interface LandaHandoverLead {
  leadId: string;
  empresa: string;
  canal: string;
}

interface OfficeStore {
  agents: Map<string, Agent>;
  characters: Map<string, Character>;
  seats: Map<string, Seat>;
  ws: WebSocket | null;
  connected: boolean;
  expediente: Expediente | null;
  prospecting: boolean;
  leads: Lead[];
  campaignSummary: CampaignSummary | null;
  activeTab: 'campaign' | 'results' | 'approved' | 'chat';
  activeCampaign: Record<string, string> | null;
  currentRunId: string | null;
  agentLogs: Record<string, string[]> | null;
  isAuthenticated: boolean;
  userEmail: string | null;
  userRole: 'staff' | 'client' | null;
  authToken: string | null;

  setAgents: (agents: Agent[]) => void;
  updateAgent: (agentId: string, updates: Partial<Agent>) => void;
  addAgent: (agent: Agent) => void;
  removeAgent: (agentId: string) => void;
  updateCharacter: (charId: string, updates: Partial<Character>) => void;
  setWebSocket: (ws: WebSocket | null) => void;
  setConnected: (connected: boolean) => void;
  assignSeat: (agentId: string, seatId: string) => void;
  setExpediente: (e: Expediente | null) => void;
  setProspecting: (v: boolean) => void;
  addLead: (lead: Omit<Lead, 'approved'>) => void;
  setLeads: (leads: Lead[]) => void;
  approveLead: (leadId?: string, url?: string) => void;
  discardLead: (leadId?: string, url?: string) => void;
  clearLeads: () => void;
  setCampaignSummary: (s: CampaignSummary) => void;
  setActiveTab: (tab: 'campaign' | 'results' | 'approved' | 'chat') => void;
  setActiveCampaign: (campaign: Record<string, string> | null) => void;
  setCurrentRunId: (id: string | null) => void;
  setAgentLogs: (logs: Record<string, string[]>) => void;
  checkpointLeads: LandaCheckpointLead[];
  handoverLead: LandaHandoverLead | null;
  addCheckpointLead: (lead: LandaCheckpointLead) => void;
  clearCheckpointLead: (leadId: string) => void;
  setHandoverLead: (lead: LandaHandoverLead | null) => void;

  setAuth: (token: string, email: string, role: 'staff' | 'client') => void;
  clearAuth: () => void;
}

function createCharacterFromAgent(agent: Agent, seatIndex: number): Character {
  const col = 2 + (seatIndex % 4) * 2;
  const row = 13 + Math.floor(seatIndex / 4) * 3;

  return {
    id: `char-${agent.id}`,
    agentId: agent.id,
    state: 'idle',
    dir: 0 as Direction,
    x: col * TILE_SIZE + TILE_SIZE / 2,
    y: row * TILE_SIZE + TILE_SIZE / 2,
    tileCol: col,
    tileRow: row,
    palette: agent.palette,
    frame: 0,
    frameTimer: 0,
    path: [],
    moveProgress: 0,
    currentTool: agent.current_tool,
    isActive: agent.state === 'thinking' || agent.state === 'tool_use',
    bubbleType: getBubbleType(agent.state),
    wanderTimer: 0,
    wanderDelay: 3 + Math.random() * 5,
  };
}

function getBubbleType(state: AgentState): 'thinking' | 'tool' | 'waiting' | null {
  switch (state) {
    case 'thinking': return 'thinking';
    case 'tool_use': return 'tool';
    case 'waiting':  return 'waiting';
    default:         return null;
  }
}

export const useOfficeStore = create<OfficeStore>((set, get) => ({
  agents: new Map(),
  characters: new Map(),
  seats: new Map(),
  ws: null,
  connected: false,
  expediente: null,
  prospecting: false,
  leads: [],
  campaignSummary: null,
  activeTab: 'campaign',
  activeCampaign: null,
  currentRunId: null,
  agentLogs: null,
  isAuthenticated: false, // Cookies are handled automatically by browser (httpOnly)
  userEmail: null,
  userRole: null,
  authToken: null, // Token is stored in httpOnly cookie, not accessible to JS
  checkpointLeads: [],
  handoverLead: null,

  setAgents: (agents) => {
    // Full reset: clear all seat assignments
    seatAssignments.clear();

    const agentMap = new Map<string, Agent>();
    const charMap = new Map<string, Character>();

    agents.forEach((agent, index) => {
      agentMap.set(agent.id, agent);
      const char = createCharacterFromAgent(agent, index);
      const isActive = agent.state === 'thinking' || agent.state === 'tool_use';
      if (isActive) {
        const seat = getFreeSeat(agent.id);
        seatAssignments.set(agent.id, seat);
        char.path = [seat];
        char.state = 'walk';
      }
      charMap.set(agent.id, char);
    });

    set({ agents: agentMap, characters: charMap });
  },

  updateAgent: (agentId, updates) => {
    const { agents, characters } = get();
    const agent = agents.get(agentId);
    if (!agent) return;

    const updatedAgent = { ...agent, ...updates };
    const newAgents = new Map(agents);
    newAgents.set(agentId, updatedAgent);

    const char = characters.get(agentId);
    if (!char) { set({ agents: newAgents }); return; }

    const isNowActive = updatedAgent.state === 'thinking' || updatedAgent.state === 'tool_use';

    // Assign a seat the first time this agent becomes active
    let seat = seatAssignments.get(agentId);
    if (isNowActive && !seat) {
      seat = getFreeSeat(agentId);
      seatAssignments.set(agentId, seat);
    }

    // Walk to seat whenever active and not already there
    // (includes chars that are mid-wander so they get redirected)
    const atSeat = seat && char.tileCol === seat.col && char.tileRow === seat.row;
    const shouldWalk = isNowActive && seat && !atSeat;

    const newChars = new Map(characters);
    newChars.set(agentId, {
      ...char,
      state: shouldWalk ? 'walk' : isNowActive ? 'type' : 'idle',
      path: shouldWalk ? [seat!] : char.path,
      dir: !shouldWalk && !isNowActive ? 0 as Direction : char.dir,
      currentTool: updatedAgent.current_tool,
      isActive: isNowActive,
      bubbleType: getBubbleType(updatedAgent.state),
      // Reset wander timer when going inactive so they start wandering fresh
      wanderTimer: isNowActive ? char.wanderTimer : 0,
      wanderDelay: isNowActive ? char.wanderDelay : 3 + Math.random() * 5,
    });
    set({ agents: newAgents, characters: newChars });
  },

  addAgent: (agent) => {
    const { agents, characters } = get();
    const newAgents = new Map(agents);
    newAgents.set(agent.id, agent);
    const newChars = new Map(characters);
    newChars.set(agent.id, createCharacterFromAgent(agent, newAgents.size - 1));
    set({ agents: newAgents, characters: newChars });
  },

  removeAgent: (agentId) => {
    // Free the seat so others can claim it
    seatAssignments.delete(agentId);

    const { agents, characters } = get();
    const newAgents = new Map(agents);
    newAgents.delete(agentId);
    const newChars = new Map(characters);
    newChars.delete(agentId);
    set({ agents: newAgents, characters: newChars });
  },

  updateCharacter: (charId, updates) => {
    const { characters } = get();
    const char = characters.get(charId);
    if (char) {
      const newChars = new Map(characters);
      newChars.set(charId, { ...char, ...updates });
      set({ characters: newChars });
    }
  },

  setWebSocket: (ws) => set({ ws }),
  setConnected: (connected) => set({ connected }),
  setExpediente: (expediente) => set({ expediente }),
  setProspecting: (prospecting) => set({ prospecting }),
  addLead: (lead) => set((state) => {
    const key = lead.leadId || lead.url;
    return {
      leads: [
        ...state.leads.filter(l => (l.leadId || l.url) !== key),
        { ...lead, approved: null },
      ],
    };
  }),
  setLeads: (leads) => set({ leads }),
  approveLead: (leadId, url) => set((state) => ({
    leads: state.leads.map(l => {
      const matches = leadId ? l.leadId === leadId : l.url === url;
      return matches ? { ...l, approved: true } : l;
    })
  })),
  discardLead: (leadId, url) => set((state) => ({
    leads: state.leads.map(l => {
      const matches = leadId ? l.leadId === leadId : l.url === url;
      return matches ? { ...l, approved: false } : l;
    })
  })),
  clearLeads: () => set({ leads: [], campaignSummary: null }),
  setCampaignSummary: (campaignSummary) => set({ campaignSummary }),
  setCurrentRunId: (currentRunId) => set({ currentRunId }),
  setAgentLogs: (agentLogs) => set({ agentLogs }),
  setActiveTab: (activeTab) => set({ activeTab }),
  setActiveCampaign: (activeCampaign) => set({ activeCampaign }),

  addCheckpointLead: (lead) =>
    set((s) => ({ checkpointLeads: [...s.checkpointLeads.filter(l => l.leadId !== lead.leadId), lead] })),
  clearCheckpointLead: (leadId) =>
    set((s) => ({ checkpointLeads: s.checkpointLeads.filter(l => l.leadId !== leadId) })),
  setHandoverLead: (lead) => set({ handoverLead: lead }),

  setAuth: (token, email, role) => {
    // SECURITY: Tokens are now stored in httpOnly cookies (set by backend)
    // This function updates Zustand state only for UI purposes
    // The actual JWT token is NOT accessible to JavaScript
    set({ isAuthenticated: true, userEmail: email, userRole: role });
  },
  clearAuth: () => {
    // SECURITY: httpOnly cookie will be cleared by backend on logout
    // Here we just clear Zustand state
    set({ isAuthenticated: false, authToken: null, userEmail: null, userRole: null });
  },

  assignSeat: (agentId, seatId) => {
    const { agents, seats } = get();
    const agent = agents.get(agentId);
    const seat = seats.get(seatId);
    if (agent && seat) {
      const newAgents = new Map(agents);
      newAgents.set(agentId, { ...agent, seat_id: seatId });
      const newSeats = new Map(seats);
      newSeats.set(seatId, { ...seat, assigned: true });
      set({ agents: newAgents, seats: newSeats });
    }
  },
}));
