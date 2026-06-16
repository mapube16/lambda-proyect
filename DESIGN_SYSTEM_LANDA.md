# Landa Office — Design System

## Filosofía
**Limpio, corporativo-amable, accesible para todas las edades.** Inspirado en Apollo pero con personalidad propia. Base clara (blanco), primario índigo, tipografía Plus Jakarta Sans.

---

## Paleta de Colores

### Surfaces
- `--bg`: #F6F6FB (fondo app)
- `--surface`: #FFFFFF (cards, modales)
- `--surface-2`: #FAFAFC (hover, alt background)
- `--surface-3`: #F2F2F8 (disabled, muted)
- `--border`: #ECECF3 (líneas sutiles)
- `--border-2`: #E3E3EC (líneas más prominentes)

### Brand
- `--primary`: #4F46E5 (índigo — botones, acciones)
- `--primary-600`: #4338CA (hover primario)
- `--primary-700`: #3730A3 (active primario)
- `--primary-soft`: #EEEDFC (background soft)
- `--primary-softer`: #F5F4FE (muy soft)

### Role Accents (Agentes)
- `--r-buscador`: #6366F1 (índigo)
- `--r-scraper`: #0EA5E9 (cyan)
- `--r-analista`: #10B981 (green)
- `--r-redactor`: #F59E0B (amber)
- Cada uno tiene `..-soft` para backgrounds suaves

### Semantic
- `--green`: #15A56A (aprobado, éxito)
- `--amber`: #D97A06 (advertencia, neutral)
- `--red`: #E03E4C (error, descartar)
- Cada uno tiene `..-soft`

### Typography
- `--ink`: #16161D (texto más oscuro)
- `--text`: #34343F (cuerpo principal)
- `--text-muted`: #6B6B7A (secundario)
- `--text-faint`: #9696A6 (muy tenue, labels)

---

## Tipografía

**Font familia**: Plus Jakarta Sans (400, 500, 600, 700, 800)
- Profesional pero cálida
- Excelente legibilidad
- Peso 700 para títulos (h1, h2, h3)
- Peso 600 para CTA buttons
- Peso 400 para cuerpo

### Escalas
- **h1** (títulos página): 26px, weight 700, letter-spacing -0.02em
- **h2** (subtítulos): 20px, weight 700
- **h3** (secciones): 16px, weight 700
- **body**: 14.5px, weight 400, line-height 1.5
- **small**: 13px, weight 500
- **label**: 11px, weight 700, uppercase, letter-spacing 0.07em, color --text-faint
- **mono/num**: tabular-nums (números alineados)

---

## Componentes Base

### Botones
- `.btn-primary`: índigo, blanco text, shadow glow
- `.btn-ghost`: surface + border, hover surface-2
- `.btn-soft`: primary-soft background, primary-700 text
- `.btn-approve`: green-soft background
- `.btn-discard`: convertirse a red-soft en hover
- `.btn-icon`: padding compacto para iconos solos
- Tamaño estándar: 10px vertical, 16px horizontal

### Cards
- background: `--surface`
- border: 1px `--border`
- border-radius: `--r-lg` (16px)
- box-shadow: `--sh-sm`
- padding: 18–20px

### Chips / Pills
- padding: 5px 10px
- border-radius: 999px
- font-size: 12px, weight 600
- .dot: 7px × 7px círculo

### Layout
- Sidebar: 248px width
- Topbar: 70px height
- Main content: padding 24px
- Grid gap: 16px (estándar)

### Animations
- Transiciones: .12s–.2s ease
- Hover lift: transform translateY(-1px)
- Live pulse: @keyframes lc-pulse 1.8s infinite

---

## Estructura de Vistas

1. **Inicio** — KPIs + campaña activa + equipo en vivo
2. **Campañas** — Grid 3-col de campañas, click → detalles
3. **Aprobados** — Tabla de leads ready-to-send, editar + enviar (Email/WhatsApp)
4. **Chat** — Asistente que guía campañas + reportes en vivo
5. **Resultados** — Métricas: open rate, click rate, reply rate
6. **Aprendizaje** — Patrones, sector insights, recomendaciones

---

## Flujo de Negocio

### Nueva Campaña
- **Modal conversacional** (wizard):
  1. Nombre campaña
  2. Sector(es)
  3. Ciudad(es)
  4. Perfil cliente ideal
  5. Leads estimados
  6. Resumen → Lanzar

### En Aprobados
- Editar correo (copiar, personalización)
- Elegir canal: Email / WhatsApp / Ambos
- Enviar → trackear métricas (open, click, reply)

### Chat Inteligente
- Preguntas sobre campaña → respuestas del equipo
- Reportes en vivo (empresas nuevas por sector)
- Integración con datos históricos del cliente

---

## Botón de Ayuda (Persistente)
- FAB circular (56×56px) abajo derecha
- Primario gradient, blanco ícono
- onClick → WhatsApp a equipo Landa
- z-index: 999 (siempre visible)

---

## Qué NO Hacer
❌ Oscuro / pixel-art / HUD de juego
❌ Colores inventados fuera de la paleta
❌ Tipografía diversa (solo Plus Jakarta Sans)
❌ Bordes gruesos / sombras pesadas
❌ Espacios inconsistentes
❌ Breakpoints complejos (desktop-first, 1440px)

---

## Siguiente Paso
Reconstruir **landa-app-final.jsx** respetando 100% este sistema.
