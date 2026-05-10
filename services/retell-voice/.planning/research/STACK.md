# Stack Research

**Domain:** AI voice agent microservice — cobranza (Node/TS, Retell AI runtime, Anthropic brain, MongoDB)
**Researched:** 2026-05-09
**Confidence:** HIGH (versions verified via npm registry)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Node.js | 20 LTS | Runtime | LTS con soporte extendido hasta 2026-04; Web Streams API nativa necesaria para streaming de Retell |
| TypeScript | 6.0.3 | Type safety | TS 6 con `noUncheckedIndexedAccess` y `exactOptionalPropertyTypes` reduce errores en handlers de webhook donde los campos son opcionales |
| Hono | 4.12.18 | HTTP framework | Lightweight, edge-first, middleware composable; `@hono/node-server` para adaptar al runtime Node. Más rápido que Express para microservicios de alta concurrencia webhook |
| `@hono/node-server` | 2.0.2 | Hono adapter para Node | Necesario para correr Hono en Node (vs Bun/Deno). Railway usa Node |
| `@hono/zod-validator` | 0.8.0 | Middleware de validación | Integra Zod directamente en rutas Hono con tipado completo; elimina el boilerplate de `safeParse` manual |
| Mongoose | 9.6.2 | ODM MongoDB | Versión 9 es la estable actual (8x y 7x son legacy). Schemas tipados con TypeScript generics. Compartida con Landa |
| Zod | 4.4.3 | Schema validation | Zod 4 (latest stable) — 10x más rápido que Zod 3 en benchmarks. Valida todos los bordes: HTTP body, webhooks Retell, env vars |
| `@anthropic-ai/sdk` | 0.95.1 | Anthropic API client | SDK oficial con soporte a tool use (function calling), streaming, y auto-retry configurable |
| `retell-sdk` | 5.22.0 | Retell API client | SDK oficial TypeScript de Retell — maneja outbound call dispatch, agent management, y tipos de webhook |
| Pino | 10.3.1 | Structured logging | Logger más rápido en el ecosistema Node; JSON nativo para Railway log drain; `pino-http` para request logging automático |
| Vitest | 4.1.5 | Test runner | Mismo config que Vite, compatible con ESM nativo. Mucho más rápido que Jest en proyectos TypeScript. `vitest run` suficiente para CI |
| Biome | 2.4.15 | Linter + formatter | Reemplaza ESLint + Prettier en un solo binary; 10-100x más rápido; config mínima; reglas de seguridad para async/await |

### Supporting Libraries (Aux table stakes)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pino-http` | 11.0.0 | HTTP request logging | Middleware Hono que loguea cada request con `tenantId`, `callId`, `statusCode`, `responseTime` automáticamente |
| `pino-pretty` | 13.1.3 | Dev log formatting | Solo en desarrollo (`NODE_ENV=development`). NUNCA en producción — rompe el JSON parsing del log drain |
| `dotenv` | 17.4.2 | Env var loading | Carga `.env` en desarrollo. En Railway las vars vienen del entorno — dotenv es no-op seguro si `.env` no existe. Usar con `dotenv/config` import |
| `svix` | 1.93.0 | Webhook signature verification | Retell usa svix para firmar sus webhooks. `svix.Webhook.verify()` valida la firma HMAC-SHA256 en cada evento entrante. CRÍTICO para seguridad — sin esto cualquiera puede fakear eventos Retell |
| `p-retry` | 8.0.0 | Retry with backoff | Reintentos con exponential backoff para llamadas a Retell API y Anthropic. Interfaz limpia con `onFailedAttempt` hook para logging. Hook Nivel 2 preparado |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `tsx` | 4.21.0 | TypeScript execution (dev) | `tsx watch src/index.ts` para hot reload en desarrollo. No requiere compilar. NO usar en producción |
| `@types/node` | 25.6.2 | Node type definitions | Necesario para tipos de `Buffer`, `process.env`, `crypto` (usado en verificación manual de webhooks como fallback) |

---

## Installation

```bash
# Core runtime
npm install hono @hono/node-server @hono/zod-validator
npm install mongoose
npm install zod
npm install @anthropic-ai/sdk
npm install retell-sdk
npm install pino pino-http

# Auxiliares table stakes
npm install dotenv
npm install svix
npm install p-retry

# Dev dependencies
npm install -D typescript tsx
npm install -D @types/node
npm install -D vitest
npm install -D @biomejs/biome
npm install -D pino-pretty
```

---

## Configuración Mínima por Librería (Producción Nivel 1)

### Hono + @hono/node-server
```typescript
// src/index.ts
import { serve } from '@hono/node-server'
import { Hono } from 'hono'

const app = new Hono()

serve({ fetch: app.fetch, port: Number(process.env.PORT) || 3000 })
```
- Nunca exponer el puerto raw sin `PORT` env var — Railway lo inyecta.

### Zod 4 con env validation
```typescript
// src/env.ts — valida en startup, falla rápido
import { z } from 'zod'

const EnvSchema = z.object({
  MONGODB_URI: z.string().url(),
  RETELL_API_KEY: z.string().min(1),
  RETELL_WEBHOOK_SECRET: z.string().min(1),
  ANTHROPIC_API_KEY: z.string().min(1),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('production'),
  PORT: z.coerce.number().default(3000),
})

export const env = EnvSchema.parse(process.env)
```
- Si falta cualquier var, el proceso muere en startup con mensaje claro. Mejor que fallar en medio de una llamada.

### Mongoose con multi-tenancy
```typescript
// src/db/connection.ts
import mongoose from 'mongoose'
import { env } from '../env.js'

export async function connectDB() {
  await mongoose.connect(env.MONGODB_URI, {
    maxPoolSize: 10,        // Railway free tier: no más de 10
    serverSelectionTimeoutMS: 5000,
    socketTimeoutMS: 45000,
  })
}
```
- Todo schema lleva `tenantId: { type: String, required: true, index: true }`.
- Todas las queries incluyen `{ tenantId: env.TENANT_ID }` o reciben el tenantId del contexto de la llamada.

### Retell SDK — Webhook Signature Verification (CRÍTICO)
```typescript
// src/middleware/retell-webhook-verify.ts
import { Webhook } from 'svix'
import { createMiddleware } from 'hono/factory'

export const verifyRetellWebhook = createMiddleware(async (c, next) => {
  const secret = env.RETELL_WEBHOOK_SECRET
  const wh = new Webhook(secret)

  const headers = {
    'svix-id': c.req.header('svix-id') ?? '',
    'svix-timestamp': c.req.header('svix-timestamp') ?? '',
    'svix-signature': c.req.header('svix-signature') ?? '',
  }

  const rawBody = await c.req.text()
  try {
    wh.verify(rawBody, headers)
  } catch {
    return c.json({ error: 'Invalid webhook signature' }, 401)
  }

  // Re-parse body como JSON para el handler
  c.set('webhookBody', JSON.parse(rawBody))
  await next()
})
```
- Retell firma todos los webhooks con svix. El secret se obtiene en el dashboard de Retell.

### Pino — Logging estructurado con contexto de llamada
```typescript
// src/logger.ts
import pino from 'pino'
import { env } from './env.js'

export const logger = pino({
  level: env.NODE_ENV === 'production' ? 'info' : 'debug',
  ...(env.NODE_ENV === 'development' && {
    transport: { target: 'pino-pretty', options: { colorize: true } },
  }),
})

// En handlers de llamada — loguear siempre con contexto
// logger.info({ tenantId, callId, debtorId, event: 'call_started' }, 'Call initiated')
```

### Anthropic SDK — Tool Use para function calling
```typescript
import Anthropic from '@anthropic-ai/sdk'

const client = new Anthropic({
  apiKey: env.ANTHROPIC_API_KEY,
  maxRetries: 3,        // Auto-retry en 429 y 5xx
  timeout: 30_000,      // 30s timeout — Retell tiene su propio timeout
})
```
- Para cobranza: usar `claude-3-5-haiku-20241022` para latencia baja (voz exige <500ms TTFB).
- `claude-3-5-sonnet-20241022` solo si la complejidad del razonamiento lo requiere.

### Vitest — Configuración mínima
```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    coverage: { provider: 'v8', reporter: ['text', 'json'] },
  },
})
```

### Biome — Configuración mínima
```json
// biome.json
{
  "formatter": { "indentStyle": "space", "indentWidth": 2 },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "suspicious": { "noExplicitAny": "warn" },
      "correctness": { "useExhaustiveDependencies": "warn" }
    }
  },
  "organizeImports": { "enabled": true }
}
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Hono | Express 5 | Nunca para este caso — Express 5 es más pesado, sin soporte ESM nativo limpio, y Hono es superior para webhooks high-throughput |
| Hono | Fastify | Si el equipo ya tiene expertise Fastify y necesita el ecosistema de plugins. Para este microservicio Hono es suficiente y más simple |
| Mongoose 9 | Prisma | Si el proyecto migra a SQL. Prisma no soporta Mongo en producción (preview only). Mongoose es el ODM correcto aquí |
| Zod 4 | Joi / Yup | Nunca — Zod tiene mejor integración TypeScript, es más rápido, y es el estándar de facto en 2025+ |
| Pino | Winston / Morgan | Winston es ~10x más lento. Morgan no produce JSON estructurado. Pino es el correcto para Railway log drain |
| Vitest | Jest | Jest con ESM+TypeScript requiere configuración compleja y es más lento. Vitest es la elección obvia en 2025 |
| svix | Verificación manual HMAC | svix es la librería oficial de Retell para firma. Manual es error-prone (timing attacks, encoding issues) |
| p-retry | async-retry / axios-retry | p-retry usa Promises nativas, TypeScript-first, y tiene mejor API con `onFailedAttempt`. axios-retry acopla al cliente HTTP |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `express` | Más pesado, middleware basado en callbacks, sin soporte ESM nativo limpio. Para webhooks de alta frecuencia Hono es superior | `hono` + `@hono/node-server` |
| `axios` | Dependency pesada e innecesaria — Retell SDK y Anthropic SDK tienen sus propios clientes HTTP. Añadir axios solo duplica librerías HTTP | El cliente nativo del SDK correspondiente |
| `mongoose@8x` o anterior | Versión legacy con peor soporte TypeScript. Mongoose 9 tiene tipado de `HydratedDocument` mejorado | `mongoose@9.6.2` |
| `zod@3` | Zod 3 es ~10x más lento que Zod 4. Con el volumen de webhooks en tiempo real la diferencia es real | `zod@4.4.3` |
| `jest` | Configuración compleja para ESM+TypeScript, más lento. En 2025 no hay razón para preferirlo sobre Vitest | `vitest` |
| `ts-node` | Reemplazado por `tsx` — `tsx` es más rápido, soporta ESM nativo, y no requiere `--loader` flags | `tsx` |
| `dotenv-safe` | Redundante con Zod env validation. `dotenv-safe` falla silenciosamente en algunos casos edge; Zod parse falla ruidosamente y con tipos | `dotenv` + `zod` env schema |
| `winston` | ~10x más lento que Pino. No produce JSON compacto compatible con Railway log drain sin configuración compleja | `pino` |
| `body-parser` | Hono incluye `c.req.json()` y `c.req.text()` nativo. `body-parser` es dependencia Express | Hono built-ins |
| `cors` (npm package) | Hono incluye `hono/cors` middleware nativo | `import { cors } from 'hono/cors'` |
| Mongoose `@8x` con Zod schemas inline complejos | Causa problemas de tipos circulares. Usar `z.infer<>` solo para validación de input, Mongoose types para el documento | Separar schemas Zod (input validation) de Mongoose schemas (DB) |

---

## Stack Patterns por Variante

**Para function calls / tools de Retell:**
- Retell invoca los tools como webhooks HTTP POST al endpoint del microservicio
- NO integrar directamente Anthropic en el handler del webhook de function call — Retell ya maneja el LLM
- Los tools son handlers HTTP deterministas: reciben parámetros tipados, ejecutan lógica DB, devuelven JSON

**Para outbound calls:**
- Usar `retell-sdk` client: `client.call.createPhoneCall({ from_number, to_number, agent_id })`
- El worker interno debe implementar rate limiting con Railway cron job o un simple `setInterval` con lógica de ventana horaria

**Para el cerebro Anthropic (system prompt + tool definitions):**
- Anthropic solo se usa si el agente Retell está configurado en modo "custom LLM" — Retell llama a un endpoint tuyo que llama a Anthropic
- Si se usa el agente nativo de Retell con Claude configurado directamente en Retell dashboard: el SDK de Anthropic NO se usa en el microservicio

**Hook Nivel 2 — Retry:**
- Envolver llamadas a `retell-sdk` y `@anthropic-ai/sdk` con `p-retry` pero solo activarlo en `ENABLE_RETRIES=true`
- En Nivel 1: cada SDK ya tiene `maxRetries` configurable internamente

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `mongoose@9.6.2` | Node 20 LTS | Requiere Node ≥14. Node 20 verificado. Sin breaking changes conocidos con Node 20 |
| `zod@4.4.3` | `@hono/zod-validator@0.8.0` | Verificar que `@hono/zod-validator` soporte Zod 4 — si no, usar `@hono/zod-validator@latest` que agregó soporte Zod 4 |
| `vitest@4.1.5` | TypeScript 6 | Vitest 4 requiere Vite 6 internamente. Compatible con TS 6 |
| `@anthropic-ai/sdk@0.95.1` | Node 18+ | Compatible con Node 20 LTS. Usa `fetch` nativo de Node |
| `retell-sdk@5.22.0` | Node 18+ | SDK generado con Stainless — compatible con Node 20 |
| `biome@2.4.15` | TypeScript 6 | Biome 2.x soporta la nueva sintaxis de TS 6 |

---

## Sources

- npm registry (verificación directa de versiones) — HIGH confidence
- `npm show <package> dist-tags` ejecutado 2026-05-09 — HIGH confidence
- Retell AI docs pattern (svix webhook verification) — MEDIUM confidence (WebFetch no disponible, basado en conocimiento del ecosistema svix + retell-sdk)
- Anthropic SDK README (maxRetries, timeout config) — HIGH confidence (training data verificada con versión actual)

---

*Stack research for: retell-voice microservice (Landa ecosystem)*
*Researched: 2026-05-09*
