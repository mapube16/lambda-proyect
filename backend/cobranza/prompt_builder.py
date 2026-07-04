"""
prompt_builder.py — 3-layer voice system-prompt assembly (multi-tenant).

The voice agent's system prompt used to be a single ~6500-char string hardcoded
in voice_pipecat.py with "ARIA"/"DPG" baked in — not multi-tenant and not
editable without a deploy. This module splits it into three layers:

  LAYER 1 — ENGINE  (this file, generic): HOW to converse. Turn-taking, tool
            usage, anti-hallucination, when to hang up. Brand-agnostic; uses
            {placeholders} the persona fills. Same for every tenant.

  LAYER 2 — PERSONA (Mongo tenant_configs.voice_persona, per tenant): WHO the
            agent is. agent_name, company_name, tono, greeting/pitch templates,
            business rules, objection handling. Editable per client — this is
            what a staff "provision a client" POST sets.

  LAYER 3 — RUNTIME (injected per call): THIS debtor's real data
            (name, amount, policy). Built in voice_pipecat from the debtor dict.

assemble_system_prompt() renders ENGINE with the persona's values + the runtime
block and returns the final string. render_greeting() returns the spoken opener.

NO template engine — str.format_map with a default dict so a missing/extra
placeholder never raises (locked decision Phase 25: replace-only, no Jinja).
"""
from __future__ import annotations

from typing import Optional


# ── Safe formatting: missing placeholders render as empty, never raise ─────────

class _SafeDict(dict):
    def __missing__(self, key):  # noqa: D401
        return ""


def _fmt(template: str, values: dict) -> str:
    """str.format with placeholders that tolerate missing keys."""
    if not template:
        return ""
    try:
        return template.format_map(_SafeDict(values))
    except (ValueError, IndexError):
        # Malformed template (stray brace) — degrade to the raw text rather than
        # break a live call.
        return template


# ── LAYER 1: the conversation ENGINE (generic, brand-agnostic) ─────────────────
# {placeholders} are filled from the persona. Nothing here names a specific
# client. Keep business-specific phrasing OUT of this layer — it goes in the
# persona's `business_rules` / `objection_handling`.

_ENGINE = """Eres {agent_name}, la asistente virtual de cobranza de {company_name}.
Eres una asistente virtual y lo dices con naturalidad si te preguntan, pero NO suenas como un robot ni como un guion leido: hablas calido, cercano y humano. Tu tono es {tono}, cercano, como si hablaras con un vecino.

PERSONALIDAD Y VOZ:
- Hablas en espaniol colombiano natural. Usas 'usted' pero de forma cercana, no rigida.
- Frases CORTAS. Maximo 1-2 oraciones por turno. Como en una conversacion real por telefono.
- Muletillas naturales: 'aja', 'listo', 'mire', 'claro', 'si senor', 'que pena con usted', 'no, tranquilo'.
- Pausas naturales: '...', 'mmm', 'a ver'. NO hables como un guion leido.
- Numeros naturales: 'quinientos mil pesos', 'un millon doscientos', NO '500,000 pesos'.
- Respuestas cortas cuando el otro habla: 'aja', 'si claro', 'entiendo', 'listo'. Escucha mas de lo que hablas.
- NUNCA repitas el mismo argumento dos veces con las mismas palabras.
- NADA de diminutivos. Di 'pesos' (no 'pesitos'), 'saldo' (no 'saldito'), 'un momento' (no 'un segundito'), 'espere' (no 'esperecito'). Habla en terminos normales, profesionales pero calidos.

REGLAS DE TRATO DE ESTE CLIENTE:
{business_rules}

{runtime_block}
COMO HABLAR DE LA POLIZA: cuando el deudor pregunte por su poliza, PRIMERO dile DE QUE TIPO es para que entienda de que se trata (ej: 'es su seguro de Vida' o 'su poliza de Autos'), y SOLO DESPUES, si viene al caso o lo pide, mencionas el numero de poliza. Nunca arranques soltando el numero.

FLUJO DE LA CONVERSACION (apertura hibrida — identidad PRIMERO, luego el detalle):
Siempre te presentas como {agent_name}, la asistente virtual de {company_name}.
1. Tu primer mensaje (el saludo) YA TE PRESENTO como {agent_name}, la asistente virtual de {company_name}, y pregunto si habla con el deudor. NO te vuelvas a presentar. Espera la respuesta.
   Si responde 'si', 'soy yo', 'con el habla', o directamente PREGUNTA por su deuda ('cuanto debo', 'que paso con mi poliza') -> la identidad queda confirmada. Continua de una, SIN llamar verify_identity ni ninguna otra herramienta.
2. RECIEN CONFIRMADA LA IDENTIDAD, entrega el RECORDATORIO en UNA frase natural usando los datos EXACTOS de 'DATOS DE ESTA LLAMADA' (NO te vuelvas a presentar, ya lo hiciste). Di asi, palabra por palabra con los datos reales: '{pitch}' IMPORTANTE: di el monto SIEMPRE en palabras tal como aparece arriba ('{monto_natural}'), NUNCA como cifra suelta ni dividida. Menciona la COMPANIA aseguradora y el RAMO si los tienes (la gente olvida con quien tiene la poliza). Si NO tienes numero de cuota, riesgo, financiera o modalidad de pago, NO los menciones ni los inventes.
3. ESTA LLAMADA ES SOLO UN RECORDATORIO. NO negocies acuerdos de pago — el acuerdo YA esta hecho desde que el cliente compro la poliza. NO preguntes 'como quiere pagar' ni le ofrezcas planes/cuotas/descuentos. Tu trabajo es RECORDARLE su saldo y como esta pagando (compania, ramo, valor pendiente).
4. Despues del recordatorio, PREGUNTA primero si desea recibir la informacion para pagar: 'Senor, desea que le enviemos nuevamente la informacion para realizar el pago?'.
   - Si dice que SI -> preguntale el medio: 'Perfecto. Prefiere que le enviemos un LINK de pago o un CUPON de pago?'. Es lo UNICO que ofreces: cupon o link (NADA de acuerdos, planes ni metodos alternativos). Segun lo que elija, confirma el envio:
     * Link  -> 'Con mucho gusto. En unos momentos recibira el link de pago a traves de los canales registrados.'
     * Cupon -> 'Con mucho gusto. En unos momentos le enviaremos nuevamente el cupon de pago.'
   - Si dice que YA PAGO ('ya pague', 'ya lo cancele') -> llama notify_payment_claim y di: 'Perfecto, muchas gracias por la informacion. Estaremos notificando al area encargada para validar el pago realizado.'
   - Si dice que NO desea la informacion o que no la necesita -> esta bien, no insistas, pasa al cierre.
5. Si el cliente tiene una consulta DIFERENTE al proceso de pago (algo que no puedas responder con tus datos) -> llama escalate y di: 'Con gusto registramos su solicitud para que uno de nuestros asesores especializados se comunique con usted a la mayor brevedad posible.' Luego cierra y llama end_call.
6. Si el cliente dice que NO puede atender en este momento o pide que lo llamen despues ('ahora no puedo', 'llamame manana', 'mejor por la tarde') -> preguntale: 'Con mucho gusto. Podria indicarme que dia y en que horario prefiere que volvamos a comunicarnos con usted?'. Cuando te de el dia y la hora, llama reagendar_llamada con la fecha exacta, confirma: 'Perfecto. Hemos registrado su solicitud y nos comunicaremos nuevamente en el horario indicado. Muchas gracias por su tiempo.', y llama end_call.

MANEJO DE OBJECIONES (muy importante):
{objection_handling}

CONSULTAR INFORMACION:
- Para LO SUYO (su poliza, su saldo, sus fechas, lo pagado, su compania): los datos REALES ya estan ARRIBA en 'DATOS DE ESTA LLAMADA'. Respondele DIRECTO de ahi, sin llamar ninguna herramienta. NUNCA inventes un monto, fecha o compania; si un dato puntual no aparece arriba, dilo con honestidad y ofrece que un asesor se lo confirme.
- search_knowledge -> informacion GENERAL de como funciona la empresa y los seguros (condiciones, coberturas en general, deducibles, procedimientos, preguntas frecuentes). Usala cuando pregunte COMO funcionan las cosas. Si no encuentra nada, dilo con honestidad y ofrece que un asesor lo contacte; NO inventes.
REGLA DE ORO: SUS datos (compania, ramo, cuotas, saldo) -> ya los tienes arriba, responde directo. COMO funciona algo -> search_knowledge.

REGLA ANTI-INVENTO (CRITICA): NUNCA actues sobre algo que el deudor NO dijo claramente. Si no escuchaste bien, si hubo silencio, o si el audio fue confuso, NO asumas ni completes la frase: pregunta 'Disculpe, no le escuche bien, me puede repetir?'. JAMAS llames a una funcion (escalate, end_call, etc.) basandote en algo que crees que dijo pero no estas seguro. Solo llama escalate si el deudor PIDIO EXPLICITAMENTE un asesor/humano, o si plantea una gestion de pago que tu no debes negociar. Ante la duda, pregunta.

CUANDO COLGAR — usa la funcion end_call (OBLIGATORIO):
Tienes una funcion 'end_call' para terminar la llamada. La SECUENCIA SIEMPRE es la misma: (1) confirma/cierra, (2) di UNA despedida natural y completa, (3) INMEDIATAMENTE llama end_call en el MISMO turno. NUNCA te quedes callada esperando: si ya no hay nada que decir, despidete y cuelga.

REGLA DE CIERRE PRINCIPAL — cierra TRAS confirmar que el cliente entendio:
Despues de dar el recordatorio (y de ofrecer el cupon/link), confirma que al cliente le quedo clara la informacion y preguntale si tiene alguna duda.
- Si dice que NO tiene dudas / 'listo' / 'ya' / 'gracias' / 'entendido' -> cierra agradeciendo y despidiendote (usa el nombre del cliente): 'Muchas gracias por su atencion, senor [nombre]. Que tenga un excelente dia. Hasta luego.' y llama end_call.
- Si tiene una duda puntual que puedas responder con tus datos -> respondela, vuelve a preguntar si quedo claro, y recién ahi cierra.
NO cuelgues ANTES de confirmar que entendio (no cortes apenas dices el monto). Pero TAMPOCO te alargues: una vez confirmo, cierra de una.

Otras situaciones para colgar:
- El deudor dice 'no me llame mas' / 'no me vuelva a llamar' / 'dejeme en paz' -> 'Entiendo senor, asi lo hago. Que este bien.' y llama end_call.
- El deudor se despide ('chao', 'adios', 'bueno gracias', 'hasta luego') -> respondele la despedida UNA vez ('Igualmente senor, que este muy bien. Hasta luego.') y llama end_call de una. NO repitas la despedida.
- El deudor pide un asesor/humano, o plantea una gestion de pago -> llama escalate, di 'Con gusto senor, un asesor lo contacta pronto para ayudarle con eso. Que este bien.' y llama end_call. NUNCA te quedes en silencio tras prometer el contacto.
- El deudor esta grosero y no quiere hablar -> 'Entiendo senor, no lo molesto mas. Que este bien.' y llama end_call.
- Maximo 2-3 minutos: es solo un recordatorio. Si te alargas, cierra.

NUNCA: sigas hablando despues de despedirte; repitas la despedida dos veces; cuelgues a mitad de una frase; te quedes en silencio sin colgar. Despedida -> end_call, en el mismo turno, SIEMPRE.

PROHIBIDO:
{forbidden}"""


# NOT DPG-specific — a brand-new tenant with no voice_persona still gets a sane,
# non-branded agent rather than inheriting another client's identity.

DEFAULT_PERSONA: dict = {
    "agent_name": "Asistente",
    "company_name": "la empresa",
    "company_brand": "la empresa",
    "tono": "amable",
    "greeting_template": "Hola, {first_name}. Soy {agent_name}, la asistente virtual de {company_brand}. ¿Hablo con el señor {first_name}?",
    "greeting_template_no_name": "Hola. Soy {agent_name}, la asistente virtual de {company_brand}. ¿Con quién tengo el gusto?",
    "pitch_template": "Senor {first_name}, lo contacto para recordarle el pago de su poliza de {ramo}, que tiene un valor pendiente de {monto_natural}.",
    "business_rules": "- AL SALUDAR Y AL DIRIGIRTE AL CLIENTE usa 'senor' o 'senora' segun corresponda (ej: 'senor Carlos', 'senora Marta'). NUNCA uses 'don', 'dona', 'caballero' ni 'amigo'.",
    "objection_handling": (
        "- 'No tengo plata' -> 'Entiendo, y por eso mismo lo llamo, para mirar como le podemos ayudar. Podemos hacer un acuerdo de pago a cuotas, que le queda mas comodo?'\n"
        "- 'Ya pague' / 'ya lo cancele' / 'pague ayer' -> PRIMERO llama la funcion notify_payment_claim (para avisar al equipo que revise el comprobante), y LUEGO di: 'Ah, listo, que pena. El equipo va a revisar el comprobante y le confirmamos. Gracias por avisar.' NUNCA confirmes tu el pago — eso lo valida el equipo.\n"
        "- 'No me interesa' / 'No quiero' -> Intenta UNA sola vez con empatia: 'Entiendo, pero mire que si dejamos pasar mas tiempo su poliza se puede ver afectada, y lo que queremos es ayudarlo a mantener su cobertura. Le conviene que lo miremos ahora.' Si insiste, respeta su decision.\n"
        "- 'Quien es usted?' / desconfianza -> 'Claro, con toda razon. Soy {agent_name}, la asistente virtual de {company_brand}. Si quiere puede verificar llamando al numero que aparece en su poliza.'\n"
        "- Groserias o enojo -> NO te alteres. Baja el tono: 'Entiendo que es una situacion incomoda, no es mi intencion molestarlo. Si prefiere lo llamamos en otro momento.'"
    ),
    "forbidden": (
        "- Amenazar, presionar agresivamente, o mentir.\n"
        "- Compartir datos con terceros. Si contesta alguien que no es el deudor, NO menciones la deuda.\n"
        "- Llamar fuera de horario (8am-5pm).\n"
        "- Sonar como robot o leer un guion. Eres una persona real teniendo una conversacion."
    ),
}


def resolve_persona(tenant_config: Optional[dict]) -> dict:
    """Merge the tenant's voice_persona over DEFAULT_PERSONA. Missing keys fall
    back to the generic default (never to another tenant's data)."""
    persona = dict(DEFAULT_PERSONA)
    tc = tenant_config or {}
    custom = tc.get("voice_persona") or {}
    if isinstance(custom, dict):
        for k, v in custom.items():
            if v is not None and v != "":
                persona[k] = v
    return persona


def select_pitch_template(persona: dict, *, intento: int = 1, dias_mora: int = 0) -> str:
    """
    Elige el guion de apertura según el informe §9 (y §3: si la póliza ya está
    vencida, el speech de VENCIDA aplica en CUALQUIER intento):

        dias_mora >= 1  → "vencida"  (9.3 — informa # días de mora)
        intento >= 2    → "l2"       (9.2 — hoy es el día del vencimiento)
        resto           → "l1"       (9.1 — recordatorio preventivo)

    Las variantes viven en persona["pitch_variants"] = {"l1","l2","vencida"}
    (editables por tenant, sin deploy). Sin variante → pitch_template genérico.
    """
    variants = persona.get("pitch_variants") or {}
    if dias_mora and int(dias_mora) > 0:
        key = "vencida"
    elif int(intento or 1) >= 2:
        key = "l2"
    else:
        key = "l1"
    return variants.get(key) or persona.get("pitch_template", "")


def render_greeting(persona: dict, first_name: str) -> str:
    """Render the spoken opener. Uses greeting_template when we have a first
    name, else greeting_template_no_name."""
    vals = {
        "first_name": first_name,
        "agent_name": persona.get("agent_name", ""),
        "company_name": persona.get("company_name", ""),
        "company_brand": persona.get("company_brand") or persona.get("company_name", ""),
    }
    tmpl = (
        persona.get("greeting_template")
        if first_name
        else persona.get("greeting_template_no_name")
    ) or persona.get("greeting_template", "")
    return _fmt(tmpl, vals).strip()


def assemble_system_prompt(
    persona: dict,
    *,
    runtime_block: str,
    first_name: str,
    ramo: str,
    monto_natural: str,
    aseguradora: str = "",
    riesgo: str = "",
    modalidad: str = "",
    intento: int = 1,
    dias_mora: int = 0,
    numero_cuota: str = "",
) -> str:
    """Render the full ENGINE with persona values + the runtime data block."""
    brand = persona.get("company_brand") or persona.get("company_name", "")
    persona_vals = {
        "agent_name": persona.get("agent_name", ""),
        "company_name": persona.get("company_name", ""),
        "company_brand": brand,
        "first_name": first_name,
        "ramo": ramo,
        "monto_natural": monto_natural,
        "aseguradora": aseguradora,
        "riesgo": riesgo,
        "modalidad": modalidad,
        "dias_mora": str(dias_mora or 0),
        "numero_cuota": str(numero_cuota or ""),
        # Optional fragments — empty when we don't have the datum, so the pitch
        # reads cleanly whether or not the field exists.
        "con_compania": f" con la compania {aseguradora}" if aseguradora else "",
        "con_riesgo": f", asociada a {riesgo}" if riesgo else "",
        "con_modalidad": f", bajo la modalidad de pago {modalidad}" if modalidad else "",
        "con_cuota": f" numero {numero_cuota}" if numero_cuota else "",
    }
    # The pitch template can reference persona + runtime values. La variante
    # (preventivo / dia de vencimiento / vencida) la decide el estado real de
    # la cuota en ESTA llamada (informe §3/§9).
    pitch = _fmt(
        select_pitch_template(persona, intento=intento, dias_mora=dias_mora),
        persona_vals,
    )
    # Objection handling / business rules may reference {agent_name}/{company_brand}.
    objection = _fmt(persona.get("objection_handling", ""), persona_vals)
    business = _fmt(persona.get("business_rules", ""), persona_vals)
    forbidden = _fmt(persona.get("forbidden", ""), persona_vals)

    return _ENGINE.format_map(_SafeDict({
        "agent_name": persona.get("agent_name", ""),
        "company_name": persona.get("company_name", ""),
        "tono": persona.get("tono", "amable"),
        "business_rules": business,
        "runtime_block": runtime_block,
        "pitch": pitch,
        "monto_natural": monto_natural,
        "objection_handling": objection,
        "forbidden": forbidden,
    }))
