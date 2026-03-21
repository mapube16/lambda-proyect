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

B) **Prompt del Analista** (el más crítico): instrucciones detalladas para evaluar prospectos específicas para el sector, criterios de scoring, qué buscar en el scraping, jerarquía de decisores, umbrales de rechazo.

C) **Variables de campaña** (TODAS derivadas de los documentos, ninguna inventada):
   - nombre_remitente: nombre del contacto principal del cliente
   - empresa_remitente: nombre de la empresa del cliente
   - industria_objetivo: sector de empresas a prospectar
   - ciudad_objetivo: ciudad(es) objetivo
   - dolor_operativo: problema principal que resuelve el cliente
   - solucion_ofrecida: qué vende/ofrece el cliente
   - software_clave: software que usan las empresas objetivo (señal de presupuesto)
   - jerarquia_decisores: quién toma la decisión de compra (de más a menos relevante)

D) **Resumen del negocio** (2-3 oraciones): qué hace el cliente y a quién le vende.

REGLAS:
- Usa información EXCLUSIVAMENTE de los documentos. No inventes datos.
- Si un dato no está en los documentos, usa "[Por confirmar]"
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
    "industria_objetivo": "...",
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

    user_msg = PROPOSAL_USER_TEMPLATE.format(knowledge_text=knowledge_text)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROPOSAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=3000,
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
