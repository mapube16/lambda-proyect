import { heroui } from "@heroui/react";

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    // HeroUI v2 monolítico: el theme está ANIDADO (@heroui/react/node_modules/
    // @heroui/theme) y las clases viven en archivos .mjs. Este glob amplio cubre
    // ambas cosas — sin él, Tailwind no genera las clases de color (bg-primary…)
    // y los botones salen sin relleno.
    "./node_modules/@heroui/**/dist/**/*.{js,mjs}",
  ],
  // CLAVE: sin preflight. El proyecto ya tiene su reset (index.css) y su sistema
  // de diseño Landa (landa.css + estilos inline). Activar el preflight de
  // Tailwind pisaría todo eso. HeroUI estila sus propios componentes, así que
  // no lo necesita.
  corePlugins: {
    preflight: false,
  },
  darkMode: "class",
  theme: { extend: {} },
  plugins: [
    heroui({
      themes: {
        light: {
          colors: {
            // Paleta Landa (mismos tokens que landa.css / C)
            primary: {
              DEFAULT: "#4F46E5",
              foreground: "#FFFFFF",
              50: "#F5F4FE",
              100: "#EEEDFC",
              200: "#DAD8F9",
              300: "#B9B5F2",
              400: "#8B84E9",
              500: "#4F46E5",
              600: "#4338CA",
              700: "#3730A3",
              800: "#2A2680",
              900: "#1E1B5E",
            },
            secondary: { DEFAULT: "#1FA89E", foreground: "#FFFFFF" },
            success: { DEFAULT: "#15A56A", foreground: "#FFFFFF" },
            warning: { DEFAULT: "#D97A06", foreground: "#FFFFFF" },
            danger: { DEFAULT: "#E03E4C", foreground: "#FFFFFF" },
          },
        },
      },
    }),
  ],
};
