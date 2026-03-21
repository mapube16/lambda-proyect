import { useState, useEffect } from 'react';
import type { CharacterSprites, Direction, SpriteData } from '../types';

const SPRITE_SIZE = 32;
const CHAR_COUNT = 6;

// Sprite sheet layout for Isomorph Office characters
// Each character sprite sheet contains:
// - Walk animations (4 frames x 4 directions)
// - Typing animations (2 frames x 4 directions)  
// - Reading animations (2 frames x 4 directions)

interface SpriteSheetConfig {
  walkRow: number;
  typeRow: number;
  readRow: number;
  framesPerDir: { walk: number; type: number; read: number };
}

const _SPRITE_CONFIG: SpriteSheetConfig = {
  walkRow: 0,
  typeRow: 4,
  readRow: 6,
  framesPerDir: { walk: 4, type: 2, read: 2 }
};
void _SPRITE_CONFIG; // retained for reference

export function useCharacterSprites() {
  const [sprites, setSprites] = useState<Map<number, CharacterSprites>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAllSprites();
  }, []);

  async function loadAllSprites() {
    try {
      const spriteMap = new Map<number, CharacterSprites>();
      
      // Try to load character sprites, but don't fail if they don't exist
      for (let i = 0; i < CHAR_COUNT; i++) {
        try {
          const charSprites = await loadCharacterSprite(i);
          spriteMap.set(i, charSprites);
        } catch (e) {
          console.warn(`Failed to load sprite for character ${i}:`, e);
          // Continue anyway with empty sprites
        }
      }
      
      setSprites(spriteMap);
      setLoading(false);
    } catch (e) {
      console.error('Failed to load sprites:', e);
      setLoading(false);
    }
  }

  async function loadCharacterSprite(charIndex: number): Promise<CharacterSprites> {
    const img = await loadImage(`/assets/characters/char_${charIndex}.png`);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d')!;
    
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
    
    const imageData = ctx.getImageData(0, 0, img.width, img.height);
    
    // Extract sprite frames
    const walk: Record<Direction, SpriteData[]> = { 0: [], 1: [], 2: [], 3: [] };
    const typing: Record<Direction, SpriteData[]> = { 0: [], 1: [], 2: [], 3: [] };
    const reading: Record<Direction, SpriteData[]> = { 0: [], 1: [], 2: [], 3: [] };
    
    // Extract walk frames (rows 0-3, 4 frames each)
    for (let dir = 0; dir < 4; dir++) {
      for (let frame = 0; frame < 4; frame++) {
        const sprite = extractSprite(imageData, frame, dir, img.width);
        walk[dir as Direction].push(sprite);
      }
    }
    
    // Extract typing frames (rows 4-7, 2 frames each)
    for (let dir = 0; dir < 4; dir++) {
      for (let frame = 0; frame < 2; frame++) {
        const sprite = extractSprite(imageData, frame, 4 + dir, img.width);
        typing[dir as Direction].push(sprite);
      }
    }
    
    // Extract reading frames (rows 8-11, 2 frames each)
    // If not present, use typing frames as fallback
    const hasReadingFrames = img.height >= SPRITE_SIZE * 12;
    for (let dir = 0; dir < 4; dir++) {
      for (let frame = 0; frame < 2; frame++) {
        if (hasReadingFrames) {
          const sprite = extractSprite(imageData, frame, 8 + dir, img.width);
          reading[dir as Direction].push(sprite);
        } else {
          // Fallback to typing frames
          reading[dir as Direction].push(typing[dir as Direction][frame]);
        }
      }
    }
    
    return { walk, typing, reading };
  }

  function extractSprite(imageData: ImageData, col: number, row: number, imgWidth: number): SpriteData {
    const sprite: SpriteData = [];
    const startX = col * SPRITE_SIZE;
    const startY = row * SPRITE_SIZE;
    
    for (let y = 0; y < SPRITE_SIZE; y++) {
      const rowData: string[] = [];
      for (let x = 0; x < SPRITE_SIZE; x++) {
        const px = startX + x;
        const py = startY + y;
        const idx = (py * imgWidth + px) * 4;
        
        const r = imageData.data[idx];
        const g = imageData.data[idx + 1];
        const b = imageData.data[idx + 2];
        const a = imageData.data[idx + 3];
        
        if (a === 0) {
          rowData.push('');
        } else if (a < 255) {
          rowData.push(`#${hex(r)}${hex(g)}${hex(b)}${hex(a)}`);
        } else {
          rowData.push(`#${hex(r)}${hex(g)}${hex(b)}`);
        }
      }
      sprite.push(rowData);
    }
    
    return sprite;
  }

  function hex(n: number): string {
    return n.toString(16).padStart(2, '0');
  }

  async function loadImage(src: string): Promise<HTMLImageElement> {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }

  return { sprites, loading };
}
