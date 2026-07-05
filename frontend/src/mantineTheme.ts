import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Genera una escala Mantine de 10 tonos (índice 6 = el color base, igual que
// Tailwind X-600) mezclando hacia blanco (más claros) y hacia negro (más
// oscuros). Sin dependencias nuevas — Mantine no trae un generador propio sin
// instalar @mantine/colors-generator.
function mixHex(hex: string, target: string, t: number): string {
  const h = (s: string) => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
  const [r1, g1, b1] = h(hex);
  const [r2, g2, b2] = h(target);
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `#${[mix(r1, r2), mix(g1, g2), mix(b1, b2)].map(v => v.toString(16).padStart(2, '0')).join('')}`;
}

function shades(hex: string): MantineColorsTuple {
  return [
    mixHex(hex, '#ffffff', 0.95),
    mixHex(hex, '#ffffff', 0.85),
    mixHex(hex, '#ffffff', 0.70),
    mixHex(hex, '#ffffff', 0.50),
    mixHex(hex, '#ffffff', 0.30),
    mixHex(hex, '#ffffff', 0.15),
    hex,
    mixHex(hex, '#000000', 0.15),
    mixHex(hex, '#000000', 0.30),
    mixHex(hex, '#000000', 0.45),
  ] as MantineColorsTuple;
}

// Paleta corporativa "Ledger Navy + Deep Teal" — MISMOS hex que la constante
// `C` en CobranzaTab.tsx (un solo lugar de verdad). Navy = único acento de
// marca (botones primarios, pills activas). Teal queda reservado para señales
// de "en vivo/sincronización" (no compite como segundo color de marca).
// Verde/ámbar/rojo = semántica de estado, nunca el acento.
export const theme = createTheme({
  primaryColor: 'indigo',
  primaryShade: 6,
  colors: {
    indigo: shades('#234876'), // C.purple — Ledger Navy
    teal: shades('#0F6B64'),   // C.teal — reservado: en vivo/sincronización
    orange: shades('#B7791E'), // C.orange — advertencia
    red: shades('#B91C3C'),    // C.pink — peligro
    green: shades('#157F5B'),  // C.green — éxito
    cyan: shades('#3B6EA5'),   // C.cyan — informativo (familia del navy)
  },
  fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
  defaultRadius: 'md',
});
