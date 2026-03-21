// Tile and grid settings
export const TILE_SIZE = 32;
export const DEFAULT_COLS = 16;
export const DEFAULT_ROWS = 12;

// Animation timing (in seconds)
export const WALK_FRAME_DURATION = 0.15;
export const TYPE_FRAME_DURATION = 0.3;
export const WALK_SPEED_PX_PER_SEC = 64;

// Character settings
export const CHARACTER_PALETTES = 6;

// Colors
export const COLORS = {
  floor: '#3d3846',
  floorAlt: '#4a4458',
  wall: '#1e1e2e',
  grid: 'rgba(255, 255, 255, 0.05)',
  
  // UI colors
  primary: '#7c3aed',
  secondary: '#06b6d4',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  
  // State colors
  idle: '#6b7280',
  thinking: '#7c3aed',
  toolUse: '#06b6d4',
  waiting: '#f59e0b',
  
  // Text
  text: '#e5e5e5',
  textMuted: '#9ca3af',
  
  // Background
  bgDark: '#1a1a2e',
  bgCard: '#2a2a3e',
  bgHover: '#3a3a4e',
};

// Bubble settings
export const BUBBLE_OFFSET_Y = -40;
export const BUBBLE_BOB_AMPLITUDE = 2;
export const BUBBLE_BOB_SPEED = 3;

// Tool icons (emoji fallbacks)
export const TOOL_ICONS: Record<string, string> = {
  read_file: '📖',
  write_file: '✍️',
  search_web: '🔍',
  run_code: '▶️',
  delegate_task: '👥',
  default: '🔧',
};

// State icons
export const STATE_ICONS: Record<string, string> = {
  thinking: '💭',
  tool_use: '⚡',
  waiting: '⏳',
  error: '❌',
  idle: '💤',
};
