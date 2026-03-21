# Contexto del Proyecto: Plataforma AaaS de Prospección B2B

## Basado en Framework Hive (aden-hive)

> **Repositorio Base**: https://github.com/aden-hive/hive
> **Licencia**: Apache 2.0
> **Versión de Referencia**: v0.6.0

---

## Visión General

Plataforma SaaS multiusuario de **Agentes como Servicio (AaaS)** para prospección B2B, reciclando la lógica del framework **Hive** para crear agentes de prospección mediante lenguaje natural.

### Filosofía Core (Heredada de Hive)

| Concepto | Descripción |
|----------|-------------|
| **Goal-Driven Development** | El usuario define objetivos en lenguaje natural, el sistema genera el grafo de agentes |
| **Self-Improving** | Captura fallos, evoluciona el grafo, redespliega automáticamente |
| **SDK-Wrapped Nodes** | Cada nodo recibe contexto (memoria, LLM, herramientas) automáticamente |
| **Human-in-the-Loop** | Nodos de intervención que pausan para input humano |

---

## Arquitectura Hive a Reciclar

### Estructura del Repositorio Hive

```
hive/
├── core/                           # Framework principal
│   └── framework/
│       ├── runner/                 # AgentRunner, CLI
│       ├── executor/               # GraphExecutor, NodeContext
│       ├── llm/                    # LiteLLMProvider (100+ modelos)
│       ├── tools/                  # ToolRegistry, MCPClient
│       ├── memory/                 # SharedMemory (STM/LTM/RLM)
│       ├── runtime/                # Runtime, BuilderQuery
│       ├── graph/                  # Goal, GraphSpec
│       └── mcp/                    # agent_builder_server, BuildSession
│
├── tools/                          # Paquete aden_tools
│   └── src/aden_tools/
│       ├── tools/                  # 19 herramientas MCP incluidas
│       └── mcp_server.py           # Servidor MCP (HTTP/STDIO)
│
├── exports/                        # Paquetes de agentes exportados
│   └── {agent_name}/
│       ├── agent.json              # GraphSpec (definición del grafo)
│       ├── tools.py                # Herramientas personalizadas
│       ├── __main__.py             # Entry point CLI
│       └── tests/                  # Tests del agente
│
└── .claude/skills/                 # Skills para Claude Code
```

### Componentes Core a Reutilizar

| Componente | Clase/Archivo | Propósito en Nuestro Proyecto |
|------------|---------------|-------------------------------|
| `AgentRunner` | `core/framework/runner/` | Cargar y ejecutar agentes de prospección |
| `GraphExecutor` | `core/framework/executor/` | Ejecutar el grafo de nodos del prospector |
| `NodeContext` | `core/framework/executor/node_context.py` | Dar contexto (memoria, LLM, tools) a cada nodo |
| `LiteLLMProvider` | `core/framework/llm/` | Integrar 100+ LLMs (OpenAI, Claude, Gemini) |
| `ToolRegistry` | `core/framework/tools/` | Registrar herramientas de scraping, CRM, email |
| `SharedMemory` | `core/framework/memory/` | Estado compartido entre nodos |
| `BuildSession` | `core/framework/mcp/build_session.py` | Sesiones de construcción de agentes |
| `Goal` | `core/framework/graph/goal.py` | Definir objetivos y criterios de éxito |
| `GraphSpec` | `core/framework/graph/graph.py` | Especificación del grafo (nodos + edges) |

---

## Flujo de Desarrollo Hive

### Ciclo Goal → Graph → Execute → Evolve

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  DEFINE GOAL    │────▶│  AUTO-GENERATE   │────▶│ EXECUTE AGENTS  │
│  (Lenguaje      │     │  GRAPH           │     │                 │
│   Natural)      │     │  (NodeSpec +     │     │ GraphExecutor   │
│                 │     │   EdgeSpec)      │     │                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  DELIVER        │◀────│  EVOLVE GRAPH    │◀────│ MONITOR &       │
│  RESULT         │     │  (Si falla)      │     │ OBSERVE         │
│                 │     │                  │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

### Estructura de un Agente (agent.json)

```json
{
  "goal": {
    "objective": "Prospectar empresas del sector {industria} en {ciudad}",
    "success_criteria": [
      {
        "description": "Identificar al menos 10 leads con Score >= 70",
        "measurable": true,
        "threshold": 10
      }
    ],
    "constraints": [
      {
        "description": "No contactar empresas B2C",
        "type": "hard"
      },
      {
        "description": "Respetar límite de 100 consultas por hora",
        "type": "soft"
      }
    ],
    "input_schema": {
      "industria_objetivo": "string",
      "ciudad_objetivo": "string",
      "dolor_operativo": "string"
    },
    "output_schema": {
      "leads_calificados": "array",
      "expedientes_md": "array",
      "correos_draft": "array"
    }
  },
  "nodes": [...],
  "edges": [...]
}
```

---

## Mapeo: Hive → Prospección B2B

### Los 10 Variables del Nodo V12 como Input Schema

```python
# core/framework/graph/goal.py → Adaptación

class ProspectorGoal(Goal):
    input_schema = {
        "nombre_remitente": str,
        "empresa_remitente": str,
        "industria_objetivo": str,
        "ciudad_objetivo": str,
        "dolor_operativo": str,
        "solucion_ofrecida": str,
        "software_clave": List[str],
        "jerarquia_decisores": List[str],
        "contenido_scrapeado": str,  # Se llena dinámicamente
        "identidad_remitente": str
    }
```

### Nodos del Agente Prospector

| Nodo | Tipo Hive | Descripción |
|------|-----------|-------------|
| `sourcing_node` | `llm_node` | Busca empresas usando web_search_tool |
| `scraping_node` | `function_node` | Extrae datos con web_scrape_tool |
| `scoring_node` | `llm_node` | Califica leads con Score 0-100 |
| `veto_router` | `router_node` | Aplica Kill Switches (B2C, competidores, etc.) |
| `spiced_analyzer` | `llm_node` | Analiza Situación, Dolor, Impacto, Evento, Decisión |
| `jtbd_deducer` | `llm_node` | Deduce el "Job to be Done" de la empresa |
| `email_composer` | `llm_node` | Genera correo hiper-personalizado (≤80 palabras) |
| `expediente_generator` | `function_node` | Genera expediente Markdown |
| `crm_pusher` | `function_node` | Envía JSON a HubSpot/Salesforce |
| `human_review` | `hitl_node` | Pausa para revisión humana (Handoff) |

### Edges (Conexiones entre Nodos)

```json
{
  "edges": [
    {
      "from": "sourcing_node",
      "to": "scraping_node",
      "condition": "on_success"
    },
    {
      "from": "scraping_node",
      "to": "scoring_node",
      "condition": "always"
    },
    {
      "from": "scoring_node",
      "to": "veto_router",
      "condition": "on_success"
    },
    {
      "from": "veto_router",
      "to": "spiced_analyzer",
      "condition": "conditional",
      "condition_code": "output['score'] >= 70 and not output['is_vetoed']"
    },
    {
      "from": "veto_router",
      "to": "end_rejected",
      "condition": "conditional",
      "condition_code": "output['score'] < 70 or output['is_vetoed']"
    },
    {
      "from": "spiced_analyzer",
      "to": "jtbd_deducer",
      "condition": "on_success"
    },
    {
      "from": "jtbd_deducer",
      "to": "email_composer",
      "condition": "on_success"
    },
    {
      "from": "email_composer",
      "to": "expediente_generator",
      "condition": "on_success"
    },
    {
      "from": "expediente_generator",
      "to": "human_review",
      "condition": "always"
    },
    {
      "from": "human_review",
      "to": "crm_pusher",
      "condition": "on_approve"
    }
  ]
}
```

---

## Sistema de Memoria (SharedMemory)

Hive provee 3 capas de memoria que usaremos:

| Capa | Uso en Prospección |
|------|-------------------|
| **STM (Short-Term)** | Datos del prospecto actual en proceso |
| **LTM (Long-Term)** | Historial de todos los prospectos procesados |
| **RLM (Retrieval)** | Búsqueda semántica de prospectos similares |

### Acceso desde NodeContext

```python
# Dentro de cualquier nodo
async def execute(self, ctx: NodeContext) -> dict:
    # Leer de memoria
    prospecto_actual = await ctx.memory.get("current_prospect")
    
    # Escribir resultado
    await ctx.memory.set("lead_score", 85)
    
    # Acceder a LLM
    response = await ctx.llm.complete(
        messages=[{"role": "user", "content": prompt}],
        model="claude-3-5-sonnet-20241022"
    )
    
    # Usar herramientas
    search_results = await ctx.tools.execute(
        "web_search_tool",
        {"query": f"empresas {industria} {ciudad}"}
    )
    
    return {"score": 85, "analysis": response}
```

---

## Herramientas MCP para Prospección

### Herramientas Built-in de Hive (aden_tools)

| Herramienta | Uso |
|-------------|-----|
| `web_search_tool` | Búsqueda de empresas (Brave Search) |
| `web_scrape_tool` | Extracción de contenido web |
| `file_system_toolkits` | Guardar expedientes |

### Herramientas Custom a Desarrollar

```python
# tools.py del agente prospector

from core.framework.tools import tool

@tool("clay_enrichment")
async def clay_enrichment(company_domain: str) -> dict:
    """Enriquece datos de empresa via Clay API"""
    # Integración con Clay para datos de empresa
    pass

@tool("hubspot_push")
async def hubspot_push(lead_data: dict) -> dict:
    """Envía lead calificado a HubSpot"""
    # Integración CRM
    pass

@tool("email_sender")
async def email_sender(to: str, subject: str, body: str) -> dict:
    """Envía correo via SendGrid/Mailgun"""
    # Requiere calentamiento previo
    pass

@tool("linkedin_scraper")
async def linkedin_scraper(profile_url: str) -> dict:
    """Extrae datos de perfil LinkedIn"""
    # Usar Firecrawl o similar
    pass
```

### Configuración MCP (mcp_servers.json)

```json
{
  "servers": [
    {
      "name": "aden_tools",
      "type": "stdio",
      "command": "uv run python -m aden_tools.mcp_server"
    },
    {
      "name": "clay_enrichment",
      "type": "http",
      "url": "https://api.clay.com/mcp"
    },
    {
      "name": "hubspot_crm",
      "type": "http", 
      "url": "https://mcp.hubspot.com/sse"
    }
  ]
}
```

---

## Plataforma Multiusuario

### Roles y Vistas (Sobre Hive)

```
┌────────────────────────────────────────────────────────────────┐
│                    PLATAFORMA AaaS B2B                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────┐        ┌──────────────────┐              │
│  │  ADMIN PANEL     │        │  USER DASHBOARD  │              │
│  │                  │        │                  │              │
│  │ • Ver todos los  │        │ • Login/Auth     │              │
│  │   agentes        │        │ • Crear agentes  │              │
│  │ • Crear agentes  │        │   (10 variables) │              │
│  │   para usuarios  │        │ • Ver leads      │              │
│  │ • Monitorear     │        │   calificados    │              │
│  │   ejecuciones    │        │ • Revisar        │              │
│  │ • Calibrar       │        │   expedientes    │              │
│  │   prompts        │        │ • Aprobar/       │              │
│  │                  │        │   Rechazar       │              │
│  └────────┬─────────┘        └────────┬─────────┘              │
│           │                           │                        │
│           ▼                           ▼                        │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              HIVE CORE (Backend)                    │       │
│  │                                                     │       │
│  │  AgentRunner → GraphExecutor → NodeContext          │       │
│  │       ↓              ↓             ↓                │       │
│  │  BuildSession   SharedMemory   ToolRegistry         │       │
│  │       ↓              ↓             ↓                │       │
│  │  agent.json      STM/LTM/RLM    MCP Servers         │       │
│  │                                                     │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### Base de Datos de Usuarios y Agentes

```
users/
├── user_001/
│   ├── profile.json
│   └── agents/
│       ├── prospector_clinicas/
│       │   ├── agent.json
│       │   ├── tools.py
│       │   └── runs/
│       │       ├── run_20260317_001/
│       │       │   ├── state.json
│       │       │   ├── decisions.json
│       │       │   └── outputs/
│       │       └── ...
│       └── prospector_software/
│           └── ...
└── user_002/
    └── ...
```

---

## Modelo de Negocio Integrado

### Flujo Comercial con Hive

```
1. REUNIÓN DE DIAGNÓSTICO
   └── Extraer las 10 variables (SPICED + JTBD)
   └── Definir Goal con success_criteria y constraints

2. DESARROLLO DEL AGENTE
   └── Usar BuildSession de Hive
   └── Generar agent.json con el grafo de nodos
   └── Configurar tools.py y mcp_servers.json

3. TESTING Y CALIBRACIÓN
   └── Ejecutar con hive run exports/prospector_cliente
   └── Monitorear con hive tui
   └── Ajustar prompts según resultados

4. ENTREGA AL CLIENTE
   └── Demo del expediente generado sobre ellos mismos
   └── Acceso a su dashboard de usuario

5. SUSCRIPCIÓN MENSUAL
   └── Mantenimiento de entregabilidad (SPF, DKIM, DMARC)
   └── Rituales de Prompt Engineering semanales
   └── Evolución automática del grafo (self-improving)
```

---

## Fases de Desarrollo

### Fase 1: Setup de Hive (Semana 1-2)

- [ ] Clonar repositorio Hive
- [ ] Ejecutar `./quickstart.sh`
- [ ] Configurar credenciales LLM
- [ ] Verificar ejecución con `hive tui`

### Fase 2: Agente Prospector MVP (Semana 3-4)

- [ ] Crear `exports/prospector_b2b/`
- [ ] Definir Goal con las 10 variables
- [ ] Implementar nodos core (sourcing, scoring, veto)
- [ ] Configurar herramientas MCP (web_search, scraper)

### Fase 3: Sistema de Scoring y Veto (Semana 5-6)

- [ ] Implementar lógica SPICED en nodo dedicado
- [ ] Crear router de veto (Kill Switches)
- [ ] Configurar umbrales (Score >= 70)
- [ ] Testing con empresas reales

### Fase 4: Generación de Outputs (Semana 7-8)

- [ ] Nodo de composición de email (≤80 palabras)
- [ ] Generador de expedientes Markdown
- [ ] Schema JSON para CRM
- [ ] Nodo HITL para revisión humana

### Fase 5: Plataforma Web (Semana 9-12)

- [ ] Autenticación (Auth0/Clerk/Supabase)
- [ ] Dashboard de usuario
- [ ] Panel de administración
- [ ] API para crear agentes desde UI

### Fase 6: Integraciones (Semana 13-14)

- [ ] MCP Server para HubSpot
- [ ] MCP Server para SendGrid
- [ ] Webhooks para Slack/Teams
- [ ] Clay integration para enriquecimiento

### Fase 7: MVP Validation (Semana 15-16)

- [ ] Prospectar clientes propios con el sistema
- [ ] Demostrar expediente auto-generado
- [ ] Cerrar primeros clientes piloto
- [ ] Iterar basado en feedback

---

## Comandos Hive Esenciales

```bash
# Setup inicial
git clone https://github.com/aden-hive/hive.git
cd hive
./quickstart.sh

# Crear agente con Claude Code
claude> /hive

# Probar agente interactivamente
hive tui

# Ejecutar agente directamente
hive run exports/prospector_b2b --input '{"industria_objetivo": "clinicas", "ciudad_objetivo": "Bogota"}'

# Debug del agente
claude> /hive-debugger

# Shell interactivo
hive shell
```

---

## Stack Tecnológico Final

| Capa | Tecnología |
|------|------------|
| **Framework Core** | Hive (Python 3.11+) |
| **LLM** | LiteLLM → Claude, GPT-4, Gemini |
| **Herramientas** | MCP Protocol (aden_tools + custom) |
| **Orquestación** | GraphExecutor + EventBus |
| **Memoria** | SharedMemory (STM/LTM/RLM) |
| **Observabilidad** | hive tui + OutcomeAggregator |
| **Auth** | Supabase Auth / Auth0 |
| **Frontend** | Next.js + Tailwind |
| **CRM** | HubSpot / Salesforce (via MCP) |
| **Email** | SendGrid + warm-up service |
| **Datos** | Clay + Firecrawl |

---

## Referencias

- **Hive Repository**: https://github.com/aden-hive/hive
- **Hive Documentation**: https://docs.adenhq.com
- **DeepWiki Analysis**: https://deepwiki.com/adenhq/hive
- **MCP Protocol**: https://modelcontextprotocol.io

---

*Documento actualizado para integrar lógica de Hive Framework*
*Versión: 2.0 | Fecha: Marzo 2026*