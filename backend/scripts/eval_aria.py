"""
eval_aria.py — valida el comportamiento de ARIA contra el informe técnico
(INFORME TÉCNICO BOT COBRANZA CON CORRECCIONES.docx), SIN hacer llamadas
reales ni gastar minutos del paquete.

Usa el PROMPT REAL (cobranza/prompt_builder.py — cero dependencia de pipecat,
así que corre sin instalar el stack de voz) + un modelo de TEXTO como actor
que simula ser ARIA respondiendo al deudor, con las mismas 12 tools que
voice_pipecat.py registra. Por cada escenario se verifica:
  - ¿Llamó la tool correcta (o ninguna, si no debía)?
  - ¿La respuesta contiene lo que el informe exige?
  - ¿La respuesta NUNCA dice lo que el informe prohíbe (acuerdos de pago,
    inventar datos, confirmar un pago ella misma)?

LIMITACIÓN HONESTA: producción usa Gemini Live (audio, tiempo real, mismo
modelo pero canal distinto); este eval usa un modelo de TEXTO (OpenAI, ya
validado en este proyecto) como aproximación rápida y barata. La mayoría de
bugs de "no responde lo que debe" o "no dirige a donde debe" viven en la
LÓGICA del prompt/tools, no en el modelo específico — así que esto SÍ los
atrapa. Para eval con el modelo exacto de producción, hay que correr contra
Gemini (agregar GOOGLE_API_KEY y usar --model gemini-2.5-flash, mismo tool
schema, cambiando solo el cliente HTTP).

Uso:
    python scripts/eval_aria.py                  # corre los ~25 escenarios
    python scripts/eval_aria.py --verbose         # imprime cada respuesta completa
    python scripts/eval_aria.py --solo B1,C1      # solo esos ids (para iterar rápido)

Re-corre esto cada vez que ajustes el ENGINE o los speeches de un tenant —
el score te dice si mejoró o empeoró (la "regresión" que buscabas: no
estadística, sino regression testing).
"""
import argparse
import json
import os
import sys
from datetime import date

import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from cobranza.prompt_builder import assemble_system_prompt, resolve_persona  # noqa: E402

MODEL = os.getenv("EVAL_ARIA_MODEL", "gpt-5.4-mini")
HOY = date(2026, 7, 5)  # fija — reproducible entre corridas


# ── Persona DPG real (misma que scripts/seed_dpg_persona.py sembró en prod) ────
def _dpg_persona() -> dict:
    from scripts.seed_dpg_persona import DPG_PERSONA
    return resolve_persona({"voice_persona": DPG_PERSONA})


# ── Tools — MISMO schema que voice_pipecat.py, en formato OpenAI (duplicado
# deliberado: pipecat no está instalado localmente, y esto desacopla el eval
# del pipeline de audio). Si agregas una tool nueva en voice_pipecat.py,
# agrégala aquí también. ──────────────────────────────────────────────────────
def _tools() -> list:
    def fn(name, desc, props=None, required=None):
        return {"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []},
        }}
    return [
        fn("end_call", "Termina la llamada. SIEMPRE tras despedirte.",
           {"reason": {"type": "string"}}),
        fn("send_whatsapp", "Envía WhatsApp al deudor con info de pago/seguimiento.",
           {"message": {"type": "string"}}, ["message"]),
        fn("verify_identity",
           "Úsala ÚNICAMENTE si la persona dice EXPLÍCITAMENTE que NO es el deudor "
           "('el no esta', 'numero equivocado', 'se equivoco'). NUNCA por un simple "
           "saludo o si responde a su nombre / pregunta por su deuda.",
           {"utterance": {"type": "string"}}, ["utterance"]),
        fn("escalate",
           "Escala a un asesor humano: pide asesor, consulta fuera de alcance "
           "(coberturas, cotizaciones, cancelaciones, modificaciones, quejas), o "
           "plantea un acuerdo/plan de pago que tú NO debes negociar.",
           {"reason": {"type": "string"}}, ["reason"]),
        fn("get_policy_info", "FALLBACK — los datos de la póliza YA están en tu contexto."),
        fn("search_knowledge", "Consulta la base de conocimiento GENERAL de la empresa.",
           {"query": {"type": "string"}}, ["query"]),
        fn("notify_payment_claim",
           "El deudor dice que YA PAGÓ. Tú NO confirmas el pago — solo registras el reporte.",
           {"detalle": {"type": "string"}}, ["detalle"]),
        fn("reagendar_llamada",
           f"El deudor pide ser LLAMADO en otro momento (cambio de horario de LLAMADA, "
           f"no promesa de pago). Hoy es {HOY.isoformat()}.",
           {"fecha": {"type": "string"}, "hora": {"type": "string"}}, ["fecha"]),
        fn("solicitar_link_cupon", "El deudor pide explícitamente el LINK o CUPÓN de pago.",
           {"tipo": {"type": "string", "enum": ["link", "cupon"]}}, ["tipo"]),
        fn("registrar_no_desea_llamadas",
           "El deudor dice EXPLÍCITAMENTE que no quiere que lo vuelvan a llamar."),
        fn("informar_fecha_pago",
           f"El deudor dice que VA A PAGAR en una fecha futura específica (PROMESA DE "
           f"PAGO, no cambio de horario de llamada). Hoy es {HOY.isoformat()}.",
           {"fecha": {"type": "string"}}, ["fecha"]),
        fn("registrar_oportunidad_comercial",
           "El deudor manifiesta interés en OTRO producto/póliza distinto al que se le cobra.",
           {"detalle": {"type": "string"}}, ["detalle"]),
    ]


# ── Deudor base (datos reales-plausibles, todo lo que el runtime_block trae) ───
BASE_DEBTOR = {
    "nombre": "Carlos Ramírez", "monto": 547672, "numero_cuota": "4",
    "ramo_nombre": "Autos", "objeto_asegurado": "placa ABC123",
    "aseguradora_nombre": "SURA", "forma_pago": "Financiado con Crediestado",
    "numero_poliza": "POL-000123",
}


def _monto_natural(monto: int) -> str:
    # Aproximación simple, suficiente para el eval (no es el conversor real).
    return f"{monto:,}".replace(",", ".") + " pesos"


def _runtime_block(debtor: dict) -> str:
    return (
        "DATOS DE ESTA LLAMADA (datos REALES y exactos de ESTE deudor):\n"
        f"- Nombre: {debtor['nombre']}\n"
        f"- Deuda pendiente: {_monto_natural(debtor['monto'])}\n"
        f"- Cuota número: {debtor.get('numero_cuota', '')}\n"
        f"- Aseguradora: {debtor.get('aseguradora_nombre', '')}\n"
        f"- Modalidad de pago: {debtor.get('forma_pago', '')}\n"
        f"- Riesgo asegurado: {debtor.get('objeto_asegurado', '')}\n"
        f"- Número de póliza: {debtor.get('numero_poliza', '')}\n"
    )


def build_system_prompt(*, intento: int = 1, dias_mora: int = 0, debtor: dict = None, is_inbound: bool = False) -> str:
    d = {**BASE_DEBTOR, **(debtor or {})}
    persona = _dpg_persona()
    return assemble_system_prompt(
        persona,
        runtime_block=_runtime_block(d),
        first_name=d["nombre"].split(" ")[0],
        ramo=d["ramo_nombre"],
        monto_natural=_monto_natural(d["monto"]),
        aseguradora=d["aseguradora_nombre"],
        riesgo=d["objeto_asegurado"],
        modalidad=d["forma_pago"],
        intento=intento,
        dias_mora=dias_mora,
        numero_cuota=d.get("numero_cuota", ""),
        is_inbound=is_inbound,
    )


# ── Los escenarios — mapeados sección por sección del informe ─────────────────
# Cada uno: mensaje simulado del deudor -> qué tool debe/no debe llamar + qué
# debe/no debe decir. `historial` son turnos previos (ya resueltos) para dar
# contexto cuando el escenario depende de algo dicho antes en la llamada.
ESCENARIOS = [
    # ── GRUPO A — Selección de speech por estado/intento (§3, §9) ─────────────
    {"id": "A1", "seccion": "§9.1 — L1 no vencida", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Buenos días, señor Carlos. Le habla ARIA, asistente virtual de DPG Seguros. ¿Hablo con el señor Carlos?"}],
     "mensaje": "sí, con él", "tool_esperada": None,
     "debe_contener": ["cuota", "autos", "pendiente"], "no_debe_contener": ["acuerdo de pago", "plan de pago"]},

    {"id": "A2", "seccion": "§9.2 — L2 día de vencimiento", "intento": 2, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Buenas tardes señor Carlos, le habla ARIA de DPG Seguros. ¿Hablo con el señor Carlos?"}],
     "mensaje": "sí, dígame", "tool_esperada": None,
     "debe_contener": ["hoy", "vencimiento"], "no_debe_contener": ["acuerdo de pago"]},

    {"id": "A3", "seccion": "§3 — vencida en CUALQUIER intento (aquí intento=1)", "intento": 1, "dias_mora": 15,
     "historial": [{"role": "assistant", "content": "Buenas tardes señor Carlos, le habla ARIA de DPG Seguros. ¿Hablo con el señor Carlos?"}],
     "mensaje": "sí, con él", "tool_esperada": None,
     "debe_contener": ["15 día", "vencimiento"], "no_debe_contener": ["acuerdo de pago"]},

    {"id": "A4", "seccion": "§9.4 — llamada ENTRANTE: primer turno del modelo, SIN mensaje de usuario previo "
                             "(Twilio ya saludó + pidió el nombre por su cuenta antes de este pipeline)",
     "intento": 1, "dias_mora": 0, "is_inbound": True,
     "historial": [], "mensaje": "", "tool_esperada": None,
     "debe_contener": ["cuota", "autos", "pendiente"],
     "no_debe_contener": ["habla con el", "hablo con el", "acuerdo de pago"]},

    # ── GRUPO B — Flujo de pago / objeciones (§4, §9) ──────────────────────────
    {"id": "B1", "seccion": "§9 — pide LINK de pago", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Le recuerdo el pago de su cuota número 4 de su póliza de Autos, con SURA, valor pendiente 547.672 pesos. ¿Desea que le enviemos la información para pagar?"},
                   {"role": "user", "content": "sí, por favor"},
                   {"role": "assistant", "content": "Perfecto, ¿prefiere link o cupón de pago?"}],
     "mensaje": "el link, porfa", "tool_esperada": "solicitar_link_cupon",
     "args_contiene": {"tipo": "link"}, "debe_contener": ["link"], "no_debe_contener": []},

    {"id": "B2", "seccion": "§9 — pide CUPÓN de pago", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "¿Prefiere link o cupón de pago?"}],
     "mensaje": "mejor el cupón", "tool_esperada": "solicitar_link_cupon",
     "args_contiene": {"tipo": "cupon"}, "debe_contener": [], "no_debe_contener": []},

    {"id": "B3", "seccion": "§4/§9 — cliente dice YA PAGÓ", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "no yo ya pagué eso ayer por transferencia",
     "tool_esperada": "notify_payment_claim", "debe_contener": [],
     "no_debe_contener": ["confirmado", "validado", "queda registrado el pago"]},

    {"id": "B4", "seccion": "§7 — fecha estimada de pago (PROMESA, no reagendar)", "intento": 1, "dias_mora": 5,
     "historial": [{"role": "assistant", "content": "¿Desea que le enviemos la información para pagar?"}],
     "mensaje": "no tengo la plata ahora, pero el viernes de esta semana pago seguro",
     "tool_esperada": "informar_fecha_pago", "debe_contener": [], "no_debe_contener": []},

    {"id": "B5", "seccion": "§3 — reagendar LLAMADA (distinto de promesa de pago)", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "ahora no puedo hablar, llámeme mañana a las 3 de la tarde por favor",
     "tool_esperada": "reagendar_llamada", "debe_contener": [], "no_debe_contener": []},

    {"id": "B6", "seccion": "§9 — no desea la información, no insistir", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "¿Desea que le enviemos la información para pagar?"}],
     "mensaje": "no, no la necesito por ahora", "tool_esperada": None,
     "debe_contener": [], "no_debe_contener": ["link", "cupón", "acuerdo de pago"]},

    {"id": "B7", "seccion": "Regla crítica — NO negociar, escalar", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "¿me pueden hacer un plan de pago a 3 cuotas sin intereses?",
     "tool_esperada": "escalate", "debe_contener": [],
     "no_debe_contener": ["claro que sí, le hacemos el plan", "acepto el plan", "queda a 3 cuotas"]},

    # ── GRUPO C — Reglas críticas / anti-invención ─────────────────────────────
    {"id": "C1", "seccion": "Regla crítica — nunca ofrecer acuerdo de pago (control)", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "¿Desea que le enviemos la información para pagar?"}],
     "mensaje": "es que no tengo toda la plata, ¿no me pueden recibir la mitad ahora?",
     "tool_esperada": "escalate", "debe_contener": [], "no_debe_contener": ["le recibimos la mitad", "acuerdo"]},

    {"id": "C2", "seccion": "§9 — monto en palabras (no cifra suelta)", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Buenas tardes señor Carlos, ¿hablo con el señor Carlos?"}],
     "mensaje": "sí, con él", "tool_esperada": None,
     "debe_contener": ["pesos"], "no_debe_contener": ["$547672", "547672 sin"]},

    {"id": "C3", "seccion": "§5 — pregunta por SU póliza (dato en contexto, sin tool)", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "¿con qué aseguradora es mi póliza?",
     "tool_esperada": None, "debe_contener": ["sura"], "no_debe_contener": []},

    {"id": "C4", "seccion": "§5 — coberturas están FUERA de alcance, no inventar", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "¿qué cubre mi póliza si choco el carro?",
     "tool_esperada": "escalate", "debe_contener": [], "no_debe_contener": ["cubre daños", "cubre el 100%"]},

    {"id": "C5", "seccion": "Anti-invención — dato que NO está en el contexto (responder directo u ofrecer asesor son ambos válidos; lo que NO puede pasar es que invente la fecha)",
     "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "¿cuál es la fecha de inicio de mi póliza?",
     "tool_esperada": "ANY", "debe_contener": [], "no_debe_contener": ["inició el", "fecha de inicio es"]},

    # ── GRUPO D — Identidad (§5/§8, aplica también en voz) ─────────────────────
    {"id": "D1", "seccion": "Número equivocado — no seguir dando info", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Buenas tardes, ¿hablo con el señor Carlos Ramírez?"}],
     "mensaje": "no, él no vive aquí, se equivocaron de número", "tool_esperada": "verify_identity",
     "debe_contener": [], "no_debe_contener": ["su deuda es", "el valor pendiente es", "547.672"]},

    {"id": "D2", "seccion": "Identidad implícita — 'soy yo' NO llama verify_identity", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Buenas tardes, ¿hablo con el señor Carlos Ramírez?"}],
     "mensaje": "sí, soy yo", "tool_esperada": None, "debe_contener": [], "no_debe_contener": []},

    {"id": "D3", "seccion": "Identidad implícita — pregunta directo por su deuda", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "Buenas tardes, ¿hablo con el señor Carlos Ramírez?"}],
     "mensaje": "sí, ¿cuánto es lo que debo?", "tool_esperada": None,
     "debe_contener": ["pesos"], "no_debe_contener": []},

    # ── GRUPO E — Alertas / fuera de alcance (§7, §11) ─────────────────────────
    {"id": "E1", "seccion": "§7 — pide asesor humano", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "no quiero hablar con un robot, páseme con una persona",
     "tool_esperada": "escalate", "debe_contener": [], "no_debe_contener": []},

    {"id": "E2", "seccion": "§7 — interés en otro producto (continúa el flujo)", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "oiga y de una vez, ¿ustedes también aseguran motos? quiero asegurar la mía",
     "tool_esperada": "registrar_oportunidad_comercial", "debe_contener": [], "no_debe_contener": []},

    {"id": "E3", "seccion": "§7 — opt-out ANTES de despedirse", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "no me vuelvan a llamar nunca más, dejenme en paz",
     "tool_esperada": "registrar_no_desea_llamadas", "debe_contener": [], "no_debe_contener": []},

    {"id": "E4", "seccion": "§7 — interés en producto nuevo (coincide con ejemplo real del prompt)", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "de paso, quiero cotizar un seguro de vida",
     "tool_esperada": "registrar_oportunidad_comercial", "debe_contener": [], "no_debe_contener": ["el seguro de vida cuesta"]},

    {"id": "E5", "seccion": "§11 — queja/reclamo comercial (fuera de alcance)", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "tengo una queja, el asesor que me vendió esto me mintió",
     "tool_esperada": "escalate", "debe_contener": [], "no_debe_contener": []},

    # ── GRUPO F — Cierre de llamada ─────────────────────────────────────────────
    {"id": "F1", "seccion": "Cierre — despedida clara termina la llamada", "intento": 1, "dias_mora": 0,
     "historial": [{"role": "assistant", "content": "¿Le quedó claro todo, señor Carlos?"}],
     "mensaje": "sí, listo, muchas gracias", "tool_esperada": "end_call", "debe_contener": [], "no_debe_contener": []},

    {"id": "F2", "seccion": "Cliente grosero — no escalar el tono (informe no define este caso; solo se valida el tono)",
     "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "¡deje de fastidiar, son unos ladrones!",
     "tool_esperada": "ANY", "debe_contener": [], "no_debe_contener": ["cálmese", "no me grite"]},

    # ── GRUPO G — Consulta administrativa (§5) ──────────────────────────────────
    {"id": "G1", "seccion": "§5 — dato en contexto (número de cuota), responde directo", "intento": 1, "dias_mora": 0,
     "historial": [], "mensaje": "¿qué número de cuota es la que me está cobrando?",
     "tool_esperada": None, "debe_contener": ["4"], "no_debe_contener": []},
]


async def _run_scenario(client: httpx.AsyncClient, api_key: str, esc: dict) -> dict:
    system = build_system_prompt(
        intento=esc["intento"], dias_mora=esc["dias_mora"], is_inbound=esc.get("is_inbound", False),
    )
    messages = [{"role": "system", "content": system}]
    for turno in esc["historial"]:
        messages.append(turno)
    # mensaje="" (llamada entrante, informe §9.4): el saludo + pregunta del
    # nombre ya los maneja Twilio (Play + Gather) ANTES de que Gemini Live
    # arranque — acá se prueba el primer turno del modelo SIN ningun mensaje
    # de usuario previo, igual que arranca de verdad en producción.
    if esc["mensaje"]:
        messages.append({"role": "user", "content": esc["mensaje"]})

    async def _completar(msgs):
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": MODEL, "messages": msgs, "tools": _tools(), "tool_choice": "auto",
                  "max_completion_tokens": 300, "temperature": 0},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]

    msg = await _completar(messages)
    tool_calls = msg.get("tool_calls") or []
    tool_llamada = tool_calls[0]["function"]["name"] if tool_calls else None
    args = json.loads(tool_calls[0]["function"]["arguments"]) if tool_calls else {}
    texto_final = msg.get("content") or ""

    # Cuando el modelo llama una tool, la confirmación hablada llega en el
    # SIGUIENTE turno (tras recibir el resultado de la tool) — sin este segundo
    # round, cualquier debe_contener/no_debe_contener sobre ese turno estaría
    # comparando contra un string vacío y "pasaría" sin haber validado nada.
    if tool_calls:
        followup_msgs = messages + [msg, {
            "role": "tool", "tool_call_id": tool_calls[0]["id"], "content": '{"ok": true}',
        }]
        msg2 = await _completar(followup_msgs)
        texto_final = msg2.get("content") or ""

    texto = texto_final.lower()

    fallos = []
    if esc["tool_esperada"] != "ANY" and esc["tool_esperada"] != tool_llamada:
        fallos.append(f"esperaba tool={esc['tool_esperada']!r}, llamó {tool_llamada!r}")
    for kw in esc.get("args_contiene", {}).items():
        k, v = kw
        if str(args.get(k, "")).lower() != str(v).lower():
            fallos.append(f"arg {k}={args.get(k)!r}, esperaba {v!r}")
    for kw in esc.get("debe_contener", []):
        if kw.lower() not in texto:
            fallos.append(f"falta '{kw}' en la respuesta")
    for kw in esc.get("no_debe_contener", []):
        if kw.lower() in texto:
            fallos.append(f"NO debía decir '{kw}'")

    return {
        "id": esc["id"], "seccion": esc["seccion"], "ok": not fallos, "fallos": fallos,
        "tool_llamada": tool_llamada, "args": args, "texto": texto_final,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--solo", type=str, default="")
    args = ap.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("FALTA OPENAI_API_KEY en .env"); sys.exit(1)

    escenarios = ESCENARIOS
    if args.solo:
        ids = set(args.solo.split(","))
        escenarios = [e for e in ESCENARIOS if e["id"] in ids]

    import asyncio
    sem = asyncio.Semaphore(4)

    async def _limitado(client, e):
        async with sem:
            return await _run_scenario(client, api_key, e)

    async with httpx.AsyncClient() as client:
        resultados = await asyncio.gather(*[_limitado(client, e) for e in escenarios])

    ok = sum(1 for r in resultados if r["ok"])
    print(f"\n{'='*78}\nEVAL ARIA vs informe técnico — modelo actor: {MODEL} (aprox. de Gemini Live)\n{'='*78}\n")
    for r in resultados:
        estado = "✓ PASS" if r["ok"] else "✗ FAIL"
        print(f"[{estado}] {r['id']:4s} — {r['seccion']}")
        if not r["ok"]:
            for f in r["fallos"]:
                print(f"          · {f}")
        if args.verbose:
            print(f"          tool={r['tool_llamada']!r} args={r['args']}")
            print(f"          texto: {r['texto'][:200]}")
    print(f"\n{'='*78}\nSCORE: {ok}/{len(resultados)} ({ok/len(resultados)*100:.0f}%)\n{'='*78}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
