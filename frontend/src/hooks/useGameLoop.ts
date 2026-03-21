import { useEffect, useRef, useCallback } from 'react';
import { useOfficeStore } from '../store/officeStore';
import type { Character, Direction } from '../types';

const TILE_SIZE = 16;
const WALK_SPEED = 32; // pixels per second
const WALK_FRAME_DURATION = 0.15; // seconds per frame
const TYPE_FRAME_DURATION = 0.3;  // seconds per frame

// Open floor positions for idle wandering (verified against layout tiles)
// Left room: cols 1-9, rows 11-20  |  Right room: cols 11-18, rows 11-20
const WANDER_SPOTS = [
  // Left room — central open areas, away from desks (cols 2-4 rows 12-14) and furniture col 1
  { col: 5, row: 12 }, { col: 5, row: 15 }, { col: 5, row: 19 },
  { col: 8, row: 13 }, { col: 8, row: 17 }, { col: 8, row: 20 },
  { col: 2, row: 20 }, { col: 5, row: 20 },
  // Right room — away from sofa cluster (cols 13-16, rows 13-16)
  { col: 12, row: 12 }, { col: 17, row: 12 },
  { col: 12, row: 18 }, { col: 17, row: 18 },
  { col: 15, row: 20 }, { col: 12, row: 20 },
  // Doorway corridor between rooms
  { col: 10, row: 15 },
];

export function useGameLoop() {
  const lastTimeRef = useRef<number>(0);
  const animationFrameRef = useRef<number>(0);

  const { characters, updateCharacter } = useOfficeStore();

  const update = useCallback((timestamp: number) => {
    if (!lastTimeRef.current) {
      lastTimeRef.current = timestamp;
    }
    const dt = Math.min((timestamp - lastTimeRef.current) / 1000, 0.1); // cap at 100ms
    lastTimeRef.current = timestamp;

    characters.forEach((char, id) => {
      const updates = updateCharacterState(char, dt);
      if (Object.keys(updates).length > 0) {
        updateCharacter(id, updates);
      }
    });

    animationFrameRef.current = requestAnimationFrame(update);
  }, [characters, updateCharacter]);

  useEffect(() => {
    animationFrameRef.current = requestAnimationFrame(update);
    return () => cancelAnimationFrame(animationFrameRef.current);
  }, [update]);
}

function updateCharacterState(char: Character, dt: number): Partial<Character> {
  const updates: Partial<Character> = {};
  let newFrameTimer = char.frameTimer + dt;

  switch (char.state) {
    case 'type': {
      if (newFrameTimer >= TYPE_FRAME_DURATION) {
        newFrameTimer -= TYPE_FRAME_DURATION;
        updates.frame = (char.frame + 1) % 2;
      }
      updates.frameTimer = newFrameTimer;
      break;
    }

    case 'walk': {
      if (newFrameTimer >= WALK_FRAME_DURATION) {
        newFrameTimer -= WALK_FRAME_DURATION;
        updates.frame = (char.frame + 1) % 4;
      }
      updates.frameTimer = newFrameTimer;

      if (char.path.length > 0) {
        const nextTile = char.path[0];
        const targetX = nextTile.col * TILE_SIZE + TILE_SIZE / 2;
        const targetY = nextTile.row * TILE_SIZE + TILE_SIZE / 2;

        const dx = targetX - char.x;
        const dy = targetY - char.y;
        updates.dir = getDirection(dx, dy);

        const dist = Math.sqrt(dx * dx + dy * dy);
        const moveAmount = WALK_SPEED * dt;

        if (moveAmount >= dist) {
          updates.x = targetX;
          updates.y = targetY;
          updates.tileCol = nextTile.col;
          updates.tileRow = nextTile.row;
          updates.path = char.path.slice(1);

          if (updates.path.length === 0) {
            // Path complete — apply seat facing direction if specified
            if (nextTile.dir !== undefined) {
              updates.dir = nextTile.dir as Direction;
            }
            updates.state = char.isActive ? 'type' : 'idle';
            updates.frame = 0;
            updates.frameTimer = 0;
            if (!char.isActive) {
              updates.wanderTimer = 0;
              updates.wanderDelay = 3 + Math.random() * 5;
            }
          }
        } else {
          const ratio = moveAmount / dist;
          updates.x = char.x + dx * ratio;
          updates.y = char.y + dy * ratio;
        }
      } else {
        // No path — settle into idle/type
        updates.state = char.isActive ? 'type' : 'idle';
        updates.frame = 0;
        updates.frameTimer = 0;
      }
      break;
    }

    case 'idle': {
      updates.frame = 0;

      if (char.isActive) {
        // Agent became active mid-idle — game loop will let store handle walk start
        updates.frameTimer = 0;
      } else {
        // Count down wander timer, then walk to a random open spot
        const newWanderTimer = char.wanderTimer + dt;
        if (newWanderTimer >= char.wanderDelay) {
          const spot = WANDER_SPOTS[Math.floor(Math.random() * WANDER_SPOTS.length)];
          updates.path = [spot];
          updates.state = 'walk';
          updates.frame = 0;
          updates.frameTimer = 0;
          updates.wanderTimer = 0;
          updates.wanderDelay = 4 + Math.random() * 6;
        } else {
          updates.wanderTimer = newWanderTimer;
        }
      }
      break;
    }
  }

  return updates;
}

function getDirection(dx: number, dy: number): Direction {
  if (Math.abs(dx) > Math.abs(dy)) {
    return dx > 0 ? 2 : 1; // RIGHT or LEFT
  } else {
    return dy > 0 ? 0 : 3; // DOWN or UP
  }
}
