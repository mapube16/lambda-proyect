const fs = require('fs');
const layout = require('./public/assets/default-layout-1.json');

// Expand from 21x22 to 32x24
const newCols = 32;
const newRows = 24;
const oldCols = layout.cols;
const oldRows = layout.rows;

// Create new tiles array (32x24 = 768 tiles)
const newTiles = new Array(newCols * newRows).fill(255);

// Copy old tiles to new array (top-left)
for (let i = 0; i < layout.tiles.length; i++) {
  const oldCol = i % oldCols;
  const oldRow = Math.floor(i / oldCols);
  const newIdx = oldRow * newCols + oldCol;
  newTiles[newIdx] = layout.tiles[i];
}

// Add break room area (cols 18-31, rows 10-20): floor tile 7 (cream)
for (let row = 10; row <= 20; row++) {
  for (let col = 18; col <= 30; col++) {
    const idx = row * newCols + col;
    newTiles[idx] = 7;
  }
}

// Wall separating (col 17 is wall, col 18 is new area)
for (let row = 10; row <= 20; row++) {
  const idx = row * newCols + 17;
  newTiles[idx] = 0; // wall
}

// Create new tileColors array
const newTileColors = new Array(newCols * newRows).fill(null);
for (let i = 0; i < layout.tileColors.length; i++) {
  const oldCol = i % oldCols;
  const oldRow = Math.floor(i / oldCols);
  const newIdx = oldRow * newCols + oldCol;
  newTileColors[newIdx] = layout.tileColors[i];
}

// Add color to break room
const breakRoomColor = { h: 25, s: 48, b: -43, c: -88 };
for (let row = 10; row <= 20; row++) {
  for (let col = 18; col <= 30; col++) {
    const idx = row * newCols + col;
    newTileColors[idx] = breakRoomColor;
  }
}

// Add new furniture for break room
const newFurniture = [
  ...layout.furniture,
  // Coffee area (col 20-22, row 12-13)
  { uid: "f-break-coffee-table", type: "COFFEE_TABLE", col: 20, row: 12 },
  { uid: "f-break-coffee", type: "COFFEE", col: 21, row: 13 },
  { uid: "f-break-coffee-2", type: "COFFEE", col: 22, row: 13 },
  // Lounge area (col 24-28, row 13-17)
  { uid: "f-break-sofa-front", type: "SOFA_FRONT", col: 25, row: 14 },
  { uid: "f-break-sofa-back", type: "SOFA_BACK", col: 25, row: 16 },
  { uid: "f-break-sofa-side", type: "SOFA_SIDE", col: 24, row: 15 },
  { uid: "f-break-sofa-side-left", type: "SOFA_SIDE:left", col: 27, row: 15 },
  { uid: "f-break-table", type: "SMALL_TABLE_FRONT", col: 26, row: 14 },
  // Decorative plants
  { uid: "f-break-plant1", type: "PLANT_2", col: 19, row: 11 },
  { uid: "f-break-plant2", type: "CACTUS", col: 29, row: 11 },
];

const newLayout = {
  ...layout,
  cols: newCols,
  rows: newRows,
  tiles: newTiles,
  tileColors: newTileColors,
  furniture: newFurniture,
};

fs.writeFileSync('./public/assets/default-layout-1.json', JSON.stringify(newLayout, null, 2));
console.log('Layout expanded from 21x22 to 32x24 with break room added');
