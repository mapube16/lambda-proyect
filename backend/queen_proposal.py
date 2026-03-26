"""
queen_proposal.py — Queen intelligence for client onboarding.

Reads all uploaded client documentation via RAG and produces a structured
proposal: agent names/personas, system prompt for the Analista, and all
8 campaign variables — derived exclusively from the documents.
"""

import json
import logging

logger = logging.getLogger("queen_proposal")

PROPOSAL_SYSTEM_PROMPT = """Eres la Abeja Reina de Isomorph, una IA estratégica especializada en construir equipos de agentes de prospección B2B personalizados.

Tu misión: analizar la documentación de un cliente nuevo y proponer la configuración ÓPTIMA para su equipo de prospección automatizada.

El equipo siempre incluye los 4 roles base, pero puede tener agentes adicionales si el negocio lo requiere:
1. **Buscador** (researcher): Descubre empresas objetivo via búsqueda web
2. **Scraper** (planner): Extrae datos clave de cada web empresarial
3. **Analista** (reviewer): Evalúa si la empresa califica como prospecto
4. **Redactor** (writer): Redacta el mensaje de outreach personalizado

Si el negocio necesita más agentes (ej. un agente de seguimiento, un calificador adicional, un agente de WhatsApp), agrégalos. No hay límite en el número de agentes.

**Canales de comunicación:**
- Por defecto, los agentes usan email (`"channel": "email"`)
- Si un agente se comunica con prospectos por **WhatsApp**, usa `"channel": "whatsapp"` e incluye `"whatsapp_config": {"phone_number": "[Por confirmar]", "template_name": "outreach_inicial"}`
- Si hay un agente dedicado a WhatsApp, asígnale `"role": "whatsapp_sender"`

Tu propuesta debe incluir:

A) **Identidad de cada agente** adaptada al sector del cliente:
   - Nombre (puede ser creativo, ej. "Cazador de Flotas" para logística)
   - Breve descripción del rol desde la perspectiva del negocio del cliente
   - Canal de comunicación (email o whatsapp)

B) **Prompt del Analista** (el más crítico): instrucciones detalladas para evaluar prospectos específicas para el sector, criterios de scoring, qué buscar en el scraping, jerarquía de decisores, umbrales de rechazo. IMPORTANTE: el sistema inyectará automáticamente el contenido del sitio web. Tu prompt solo debe contener los criterios de evaluación — NO incluyas placeholders ni instrucciones de formato JSON.

C) **Variables de campaña** (TODAS derivadas de los documentos, ninguna inventada):
   - nombre_remitente: nombre del contacto principal del cliente
   - empresa_remitente: nombre de la empresa del cliente
   - sector_propio_cliente: sector/industria DEL CLIENTE (el que vende). Ej: si el cliente es una agencia de seguros → "seguros, corretaje de seguros". Si es empresa de software → "desarrollo de software, software factory". Estas empresas son COMPETIDORES y serán excluidas automáticamente de la prospección.
   - industria_objetivo: 2 o 3 industrias CONCRETAS y CORTAS separadas por coma, que sean los mejores mercados para el cliente. REGLAS ESTRICTAS:
     * Deben ser términos de búsqueda reales (ej: "logística y transporte, construcción, clínicas médicas") — NO frases descriptivas largas.
     * NUNCA pongas el mismo sector del cliente ni sinónimos de él.
     * Elige las industrias donde el dolor que resuelve el cliente sea más agudo y el presupuesto para comprar exista. Si los documentos no especifican industrias objetivo, INFIERE las 2-3 más probables basándote en la solución ofrecida.
     * Ejemplo para seguros corporativos: "logística y transporte, construcción, manufactura"
     * Ejemplo para software a medida: "agencias de marketing digital, empresas de logística, clínicas médicas"
     * Ejemplo para consultoría financiera: "pymes manufactura, sector retail, empresas de construcción"
   - ciudad_objetivo: ciudad(es) objetivo
   - dolor_operativo: problema principal que resuelve el cliente
   - solucion_ofrecida: qué vende/ofrece el cliente
   - software_clave: software que usan las empresas objetivo (señal de presupuesto)
   - jerarquia_decisores: quién toma la decisión de compra (de más a menos relevante)

D) **Resumen del negocio** (2-3 oraciones): qué hace el cliente y a quién le vende.

REGLAS:
- MAXIMIZAR CONVERSIONES es el objetivo principal. Cuando la información sea escasa, INFIERE y EXPANDE usando conocimiento del sector. Es mejor una propuesta razonada que una incompleta.
- Para industria_objetivo: si los documentos no especifican a quién vender, razona desde la solución ofrecida y el dolor → infiere los 2-3 sectores donde ese dolor es más común y el presupuesto existe.
- Usa información de los documentos como base, pero si falta algo crítico para maximizar resultados, infiere con criterio de negocio. Márcalo como "[Inferido]" solo si es muy incierto.
- El prompt del Analista debe ser específico al sector, no genérico
- Las variables deben estar en español, usando la terminología del cliente
- Si el negocio opera por WhatsApp, incluye un agente con canal whatsapp
- Cuando veas bloques etiquetados como [COMPETENCIA], úsalos como benchmark comparativo (mensajería, posicionamiento, diferenciadores), NO como fuente de identidad del cliente.
- Cuando veas bloques [EMPRESA_CLIENTE] o [DOCUMENTO_CLIENTE], trátalos como fuente principal para propuesta, personalidad y campaña.
- Jerarquía obligatoria de decisión:
  1) PRIORIDAD_1_EMPRESA_CLIENTE
  2) PRIORIDAD_2_OTRAS_FUENTES
  3) PRIORIDAD_3_COMPETENCIA
- Si hay conflicto entre empresa y competencia, SIEMPRE gana empresa.
- Nunca copies texto o claims de competencia como si fueran del cliente.

Responde ÚNICAMENTE con JSON válido, sin texto adicional, sin markdown:"""

_ENRICHER_SYSTEM_PROMPT = """Eres un analista de negocios B2B. Tu tarea: leer la información disponible de un cliente y producir un perfil de negocio completo y estructurado, expandiendo activamente lo que no esté explícito usando tu conocimiento del sector.

Regla crítica: INFIERE sin miedo. Si el cliente vende CRM → sus clientes ideales son empresas con muchos contactos (agencias, inmobiliarias, aseguradoras). Si vende automatización → empresas con procesos manuales. Una inferencia razonada vale más que dejar un campo vacío.

Genera el perfil en texto estructurado (no JSON), con estas secciones:

## EMPRESA
Nombre: [nombre o "Por confirmar"]
Sector propio: [sector/industria de la empresa — ej: "desarrollo de software", "seguros corporativos". Esto se usará para EXCLUIR a sus propios competidores]
Descripción: [qué hace en 1-2 oraciones]

## PRODUCTO / SERVICIO
Qué ofrece: [descripción concreta]
Diferenciadores: [qué los distingue]
Casos de uso: [2-3 situaciones reales]

## MERCADO OBJETIVO
Industrias objetivo: [2-3 industrias CONCRETAS y cortas donde hay más demanda — NUNCA el sector propio del cliente — ej: "logística y transporte, manufactura, clínicas médicas"]
Perfil del cliente ideal: [tipo de empresa, tamaño, características]
Ciudad/región: [si se menciona, o infiere desde el contexto]

## DOLOR QUE RESUELVE
Problema principal: [dolor operativo específico]
Consecuencias: [qué le pasa al cliente si no lo resuelve]

## CAMPAÑA B2B
Jerarquía de decisores: [quién decide la compra — de más a menos relevante]
Software señal de presupuesto: [herramientas que usa el cliente objetivo como señal de que puede pagar]
Contacto principal: [nombre del fundador/CEO si se menciona, o "Por confirmar"]"""

_SPARSE_CHARS = 2500  # below this, trigger enrichment


async def _enrich_if_sparse(client, knowledge_text: str) -> str:
    """If the uploaded docs are thin, run a dedicated enricher LLM first."""
    raw_len = len(knowledge_text.strip())
    if raw_len >= _SPARSE_CHARS:
        return knowledge_text

    logger.info("[queen_proposal] docs sparse (%d chars) — enriching with business analyst LLM", raw_len)
    resp = await client.chat.completions.create(
        model="gpt-5.4-2026-03-05",
        messages=[
            {"role": "system", "content": _ENRICHER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Información disponible del cliente:\n\n{knowledge_text}\n\nExpande y completa el perfil de negocio."},
        ],
        temperature=0.4,
        extra_body={"max_completion_tokens": 1200},
    )
    enriched = (resp.choices[0].message.content or "").strip()
    logger.info("[queen_proposal] enriched to %d chars", len(enriched))
    return (
        "### PRIORIDAD_1_EMPRESA_CLIENTE (perfil expandido por analista IA)\n"
        f"{enriched}\n\n"
        "### INFORMACIÓN ORIGINAL DEL CLIENTE\n"
        f"{knowledge_text}"
    )


PROPOSAL_USER_TEMPLATE = """Documentación del cliente:

{knowledge_text}

IMPORTANTE: La documentación ya viene ordenada por prioridad (empresa → otras fuentes → competencia). Respeta ese orden para inferir identidad, propuesta de valor y variables de campaña.

Genera la propuesta de configuración completa en este formato JSON exacto:

{{
  "resumen_negocio": "...",
  "agents": [
    {{"id": "buscador-001", "name": "...", "role": "researcher", "persona": "...", "channel": "email"}},
    {{"id": "scraper-001", "name": "...", "role": "planner", "persona": "...", "channel": "email"}},
    {{"id": "analista-001", "name": "...", "role": "reviewer", "persona": "...", "channel": "email"}},
    {{"id": "redactor-001", "name": "...", "role": "writer", "persona": "...", "channel": "email"}}
  ],
  "system_prompt_analista": "...",
  "campaign": {{
    "nombre_remitente": "...",
    "empresa_remitente": "...",
    "sector_propio_cliente": "sector del cliente (para excluir competidores)",
    "industria_objetivo": "sector de empresas a prospectar (DISTINTO al sector del cliente)",
    "ciudad_objetivo": "...",
    "dolor_operativo": "...",
    "solucion_ofrecida": "...",
    "software_clave": "...",
    "jerarquia_decisores": "..."
  }}
}}

Nota: puedes agregar más agentes al array si el negocio lo requiere. Si algún agente usa WhatsApp, agrega el campo "whatsapp_config": {{"phone_number": "[Por confirmar]", "template_name": "outreach_inicial"}}"""


async def generate_proposal(user_id: str, openai_api_key: str) -> dict:
    """
    Read all uploaded docs for user_id and have the Queen generate a
    full onboarding proposal.  Returns the parsed JSON dict.
    """
    from rag import get_all_knowledge_text
    from openai import AsyncOpenAI

    knowledge_text = await get_all_knowledge_text(user_id)
    if not knowledge_text:
        raise ValueError("No hay documentación cargada para este cliente.")

    client = AsyncOpenAI(api_key=openai_api_key)

    # If the client uploaded very little, enrich before sending to the Queen
    knowledge_text = await _enrich_if_sparse(client, knowledge_text)

    user_msg = PROPOSAL_USER_TEMPLATE.format(knowledge_text=knowledge_text)

    response = await client.chat.completions.create(
        model="gpt-5.4-2026-03-05",
        messages=[
            {"role": "system", "content": PROPOSAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        extra_body={"max_completion_tokens": 3000},
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[queen_proposal] JSON parse error: {e}\nRaw: {raw[:500]}")
        raise ValueError(f"Queen devolvió JSON inválido: {e}")

    logger.info(f"[queen_proposal] Proposal generated for user {user_id} with {len(proposal.get('agents', []))} agents")
    return proposal
