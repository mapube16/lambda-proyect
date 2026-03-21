// Agent state types matching backend
export type AgentState = 'idle' | 'thinking' | 'tool_use' | 'waiting' | 'error';
export type AgentRole = 'coder' | 'researcher' | 'writer' | 'reviewer' | 'planner';

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  state: AgentState;
  current_tool: string | null;
  tool_status: string | null;
  palette: number;
  seat_id: string | null;
  is_subagent: boolean;
  parent_agent_id: string | null;
}

// Character types for rendering
export type CharacterState = 'idle' | 'walk' | 'type';
export type Direction = 0 | 1 | 2 | 3; // DOWN, LEFT, RIGHT, UP

export interface Character {
  id: string;
  agentId: string;
  state: CharacterState;
  dir: Direction;
  x: number;
  y: number;
  tileCol: number;
  tileRow: number;
  palette: number;
  frame: number;
  frameTimer: number;
  path: Array<{ col: number; row: number; dir?: Direction }>;
  moveProgress: number;
  currentTool: string | null;
  isActive: boolean;
  bubbleType: 'thinking' | 'tool' | 'waiting' | null;
  wanderTimer: number;
  wanderDelay: number;
}

// Sprite types
export type SpriteData = string[][];

export interface CharacterSprites {
  walk: Record<Direction, SpriteData[]>;
  typing: Record<Direction, SpriteData[]>;
  reading: Record<Direction, SpriteData[]>;
}

// Office layout types
export interface Seat {
  uid: string;
  seatCol: number;
  seatRow: number;
  facingDir: Direction;
  assigned: boolean;
}

export interface PlacedFurniture {
  uid: string;
  type: string;
  col: number;
  row: number;
}

export interface OfficeLayout {
  version: 1;
  cols: number;
  rows: number;
  tiles: number[];
  furniture: PlacedFurniture[];
}

// WebSocket message types
export interface WSMessage {
  type: string;
  [key: string]: unknown;
}

export interface AgentUpdateMessage extends WSMessage {
  type: 'agent_update';
  agent_id: string;
  state: AgentState;
  current_tool?: string;
  tool_status?: string;
}

export interface InitialStateMessage extends WSMessage {
  type: 'initial_state';
  agents: Agent[];
}
