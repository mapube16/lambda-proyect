import { useRef, useEffect, useCallback, useState } from 'react';
import { useOfficeStore } from '../store/officeStore';
import type { Character, Agent } from '../types';

const TILE_SIZE = 16;
const SCALE = 2;
// Sprite sheet: 7 cols × 3 rows, each frame is 16×32 px
// Row 0 = down, Row 1 = up, Row 2 = side (mirror for left)
// Cols 0-3 = walk/idle frames, Cols 4-5 = type frames
const SPRITE_W = 16;
const SPRITE_H = 32;
const CHAR_COUNT = 6;
const FLOOR_COUNT = 9;

interface TileColor {
  h: number;
  s: number;
  b: number;
  c: number;
}

interface FurnitureItem {
  uid: string;
  type: string;
  col: number;
  row: number;
}

interface LayoutData {
  version: number;
  cols: number;
  rows: number;
  tiles: number[];
  tileColors: (TileColor | null)[];
  furniture: FurnitureItem[];
}

interface Assets {
  floors: (HTMLImageElement | null)[];
  furniture: Map<string, HTMLImageElement>;
  chars: (HTMLImageElement | null)[];
}

interface Bounds {
  minCol: number;
  minRow: number;
  maxCol: number;
  maxRow: number;
}

function computeBounds(layout: LayoutData): Bounds {
  let minRow = layout.rows, maxRow = 0;
  let minCol = layout.cols, maxCol = 0;

  // Include tile positions
  for (let i = 0; i < layout.tiles.length; i++) {
    if (layout.tiles[i] === 255) continue;
    const col = i % layout.cols;
    const row = Math.floor(i / layout.cols);
    if (row < minRow) minRow = row;
    if (row > maxRow) maxRow = row;
    if (col < minCol) minCol = col;
    if (col > maxCol) maxCol = col;
  }

  // Also include furniture positions (wall furniture sits on empty tile rows)
  for (const f of layout.furniture) {
    if (f.row < minRow) minRow = f.row;
    if (f.row > maxRow) maxRow = f.row;
    if (f.col < minCol) minCol = f.col;
    if (f.col > maxCol) maxCol = f.col;
  }

  return { minCol, minRow, maxCol, maxRow };
}

// Maps compound IDs like DESK_FRONT → parent folder DESK
const FOLDER_MAP: Record<string, string> = {
  DESK_FRONT: 'DESK', DESK_SIDE: 'DESK',
  SOFA_FRONT: 'SOFA', SOFA_BACK: 'SOFA', SOFA_SIDE: 'SOFA',
  WOODEN_CHAIR_FRONT: 'WOODEN_CHAIR', WOODEN_CHAIR_BACK: 'WOODEN_CHAIR', WOODEN_CHAIR_SIDE: 'WOODEN_CHAIR',
  PC_FRONT_OFF: 'PC', PC_FRONT_ON_1: 'PC', PC_FRONT_ON_2: 'PC', PC_SIDE: 'PC', PC_BACK: 'PC',
  SMALL_TABLE_FRONT: 'SMALL_TABLE', SMALL_TABLE_SIDE: 'SMALL_TABLE',
  CUSHIONED_CHAIR_FRONT: 'CUSHIONED_CHAIR', CUSHIONED_CHAIR_BACK: 'CUSHIONED_CHAIR', CUSHIONED_CHAIR_SIDE: 'CUSHIONED_CHAIR',
};

function getFurniturePath(id: string): string {
  const folder = FOLDER_MAP[id] ?? id;
  return `/assets/furniture/${folder}/${id}.png`;
}

function loadImg(src: string): Promise<HTMLImageElement | null> {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => { console.warn(`Missing asset: ${src}`); resolve(null); };
    img.src = src;
  });
}

async function loadAssets(layout: LayoutData): Promise<Assets> {
  const floors = await Promise.all(
    Array.from({ length: FLOOR_COUNT }, (_, i) => loadImg(`/assets/floors/floor_${i}.png`))
  );

  const uniqueIds = new Set(layout.furniture.map(f => f.type.replace(/:left$/, '')));
  const furnitureEntries = await Promise.all(
    Array.from(uniqueIds).map(async id => {
      const img = await loadImg(getFurniturePath(id));
      return img ? ([id, img] as [string, HTMLImageElement]) : null;
    })
  );
  const furniture = new Map(furnitureEntries.filter((e): e is [string, HTMLImageElement] => e !== null));

  const chars = await Promise.all(
    Array.from({ length: CHAR_COUNT }, (_, i) => loadImg(`/assets/characters/char_${i}.png`))
  );

  return { floors, furniture, chars };
}

function tileFilter(color: TileColor | null): string {
  if (!color) return 'none';
  const { h, s, b, c } = color;
  return `hue-rotate(${h}deg) saturate(${Math.max(0, 100 + s)}%) brightness(${Math.max(0, 100 + b)}%) contrast(${Math.max(0, 100 + c)}%)`;
}

// Map direction to sprite row: 0=down→0, 3=up→1, 1/2=side→2
function getDirRow(dir: number): number {
  if (dir === 3) return 1; // up
  if (dir === 0) return 0; // down
  return 2;               // left or right (mirror left)
}

// Get column in sprite sheet for a given state+frame
function getFrameCol(state: 'idle' | 'walk' | 'type', frame: number): number {
  if (state === 'type') return 4 + (frame % 2);
  if (state === 'walk') return frame % 4;
  return 0; // idle
}

export function OfficeCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [layout, setLayout] = useState<LayoutData | null>(null);
  const [assets, setAssets] = useState<Assets | null>(null);
  const { characters, agents } = useOfficeStore();

  useEffect(() => {
    fetch('/assets/default-layout-1.json')
      .then(r => r.json())
      .then(setLayout)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!layout) return;
    loadAssets(layout).then(setAssets).catch(console.error);
  }, [layout]);

  const bounds: Bounds | null = layout ? computeBounds(layout) : null;

  const canvasW = bounds
    ? (bounds.maxCol - bounds.minCol + 1) * TILE_SIZE * SCALE
    : 672;
  const canvasH = bounds
    ? (bounds.maxRow - bounds.minRow + 1) * TILE_SIZE * SCALE
    : 384;

  // Offset so world coords map to cropped canvas (ox/oy in world-pixels at base scale)
  const ox = bounds ? bounds.minCol * TILE_SIZE : 0;
  const oy = bounds ? bounds.minRow * TILE_SIZE : 0;

  const render = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !layout || !assets || !bounds) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvasW, canvasH);
    ctx.save();
    ctx.scale(SCALE, SCALE);
    ctx.translate(-ox, -oy); // shift world so minCol/minRow lands at 0,0

    // 1. Draw floor/wall tiles
    for (let i = 0; i < layout.tiles.length; i++) {
      const tIdx = layout.tiles[i];
      if (tIdx === 255) continue;
      const col = i % layout.cols;
      const row = Math.floor(i / layout.cols);
      const img = assets.floors[tIdx];
      if (!img) continue;
      const filter = tileFilter(layout.tileColors?.[i] ?? null);
      if (filter !== 'none') ctx.filter = filter;
      ctx.drawImage(img, col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE);
      if (filter !== 'none') ctx.filter = 'none';
    }

    // 2. Draw furniture sorted by row for depth
    const sortedFurniture = [...layout.furniture].sort((a, b) => a.row - b.row || a.col - b.col);
    for (const f of sortedFurniture) {
      drawFurniture(ctx, f, assets.furniture);
    }

    // 3. Draw characters sorted by Y for depth
    const sortedChars = Array.from(characters.values()).sort((a, b) => a.y - b.y);
    for (const char of sortedChars) {
      drawCharacter(ctx, char, assets.chars, agents.get(char.agentId));
    }

    ctx.restore();
  }, [layout, assets, bounds, characters, agents, canvasW, canvasH, ox, oy]);

  useEffect(() => {
    let id: number;
    const loop = () => { render(); id = requestAnimationFrame(loop); };
    id = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(id);
  }, [render]);

  if (!layout || !assets) {
    return (
      <div style={{
        width: canvasW, height: canvasH,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0a0a14', color: '#666', fontFamily: 'monospace',
        fontSize: '13px', borderRadius: '8px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
      }}>
        Loading office...
      </div>
    );
  }

  return (
    <canvas
      ref={canvasRef}
      width={canvasW}
      height={canvasH}
      style={{
        background: '#0a0a14',
        borderRadius: '8px',
        boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
        display: 'block',
      }}
    />
  );
}

function drawFurniture(
  ctx: CanvasRenderingContext2D,
  item: FurnitureItem,
  furnitureMap: Map<string, HTMLImageElement>
) {
  const mirror = item.type.endsWith(':left');
  const id = item.type.replace(/:left$/, '');
  const img = furnitureMap.get(id);
  if (!img) return;

  const x = item.col * TILE_SIZE;
  const y = item.row * TILE_SIZE;

  if (mirror) {
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(img, -(x + img.width), y, img.width, img.height);
    ctx.restore();
  } else {
    ctx.drawImage(img, x, y, img.width, img.height);
  }
}

function drawCharacter(
  ctx: CanvasRenderingContext2D,
  char: Character,
  charSprites: (HTMLImageElement | null)[],
  agent?: Agent
) {
  const img = charSprites[char.palette % charSprites.length];
  if (!img) {
    ctx.fillStyle = '#ff6b6b';
    ctx.beginPath();
    ctx.arc(char.x, char.y, 8, 0, Math.PI * 2);
    ctx.fill();
    return;
  }

  const col = getFrameCol(char.state, char.frame);
  const row = getDirRow(char.dir);
  const srcX = col * SPRITE_W;
  const srcY = row * SPRITE_H;
  const destX = Math.floor(char.x) - SPRITE_W / 2;
  const destY = Math.floor(char.y) - SPRITE_H + TILE_SIZE / 2;
  const mirrorLeft = char.dir === 1; // flip sprite horizontally for left

  if (mirrorLeft) {
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(img, srcX, srcY, SPRITE_W, SPRITE_H, -(destX + SPRITE_W), destY, SPRITE_W, SPRITE_H);
    ctx.restore();
  } else {
    ctx.drawImage(img, srcX, srcY, SPRITE_W, SPRITE_H, destX, destY, SPRITE_W, SPRITE_H);
  }

  if (agent) {
    drawNameTag(ctx, char.x, destY - 2, agent.name);
  }

  if (char.bubbleType) {
    const bubbleText = agent?.tool_status || (agent?.current_tool?.replace(/_/g, ' ')) || null;
    drawBubble(ctx, char.x, destY - 10, char.bubbleType, bubbleText);
  }
}

function drawNameTag(ctx: CanvasRenderingContext2D, x: number, y: number, name: string) {
  ctx.save();
  ctx.font = '6px monospace';
  ctx.textAlign = 'center';
  const w = ctx.measureText(name).width + 4;
  ctx.fillStyle = 'rgba(0,0,0,0.75)';
  ctx.fillRect(x - w / 2, y - 8, w, 8);
  ctx.fillStyle = '#ffffff';
  ctx.fillText(name, x, y - 2);
  ctx.restore();
}

function bubbleRoundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function drawBubble(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  type: 'thinking' | 'tool' | 'waiting',
  text?: string | null
) {
  const COLORS = { thinking: '#ffd866', tool: '#78dce8', waiting: '#a9dc76' };
  const DEFAULTS = { thinking: 'Thinking...', tool: 'Working...', waiting: 'Done!' };
  const label = (text && text.length > 0 ? text : DEFAULTS[type]).slice(0, 22);

  ctx.save();
  ctx.font = '6px monospace';
  const tw = ctx.measureText(label).width;
  const padX = 4, padY = 3;
  const bw = tw + padX * 2;
  const bh = 8 + padY * 2;
  const bx = x - bw / 2;
  const by = y - bh - 4;

  // Background
  ctx.fillStyle = COLORS[type];
  bubbleRoundRect(ctx, bx, by, bw, bh, 2);
  ctx.fill();

  // Border
  ctx.strokeStyle = 'rgba(0,0,0,0.25)';
  ctx.lineWidth = 0.5;
  ctx.stroke();

  // Tail
  ctx.fillStyle = COLORS[type];
  ctx.beginPath();
  ctx.moveTo(x - 3, by + bh);
  ctx.lineTo(x + 3, by + bh);
  ctx.lineTo(x, by + bh + 4);
  ctx.closePath();
  ctx.fill();

  // Text
  ctx.fillStyle = '#111';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x, by + bh / 2);
  ctx.textBaseline = 'alphabetic';
  ctx.restore();
}
