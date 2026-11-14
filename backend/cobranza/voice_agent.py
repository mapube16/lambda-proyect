"""voice_agent.py — motor de voz sobre el Deepgram Voice Agent API (produccion).

Pivote (09-ago): en vez de orquestar STT+LLM+TTS a mano en pipecat (turnos, eco
y barge-in nos rompian llamada tras llamada), se delega ese plumbing al Voice
Agent de Deepgram, que lo hace nativo. Deepgram escucha (nova-2 es + keyterms),
Gemini piensa (el mismo prompt de 3 capas), celeste (rola) pronuncia.

Este modulo es SOLO el puente + el cableado de las 12 tools reales a nuestros
handlers (crear_alerta + CobranzaOrchestrator) y la construccion del CallResult
para el post-call. Toda la capa de Twilio (AMD, ring timeout, ledger de minutos,
scheduling) es independiente y sigue igual.

Se monta detras del flag tenant_config.cobranza.voz_engine == "deepgram_agent"
(o COBRANZA_VOZ_ENGINE); default: el pipeline de pipecat intacto.
"""
import asyncio
import base64
import json
import logging
import os
import random
import re
import time
from datetime import date, datetime, time as dtime, timezone

import websockets

from cobranza.voz_comun import CallResult

logger = logging.getLogger("cobranza.voice_agent")

DG_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
# flash-lite: 0.66 s de think medidos vs 1.49-1.9 s de 3.5-flash (sonda
# check_deepgram_agent.py, 30-ago) — el turno completo baja de ~1.8 s a ~0.96 s.
# Si en llamada real cede terreno en el guion, se revierte con la env sin deploy.
THINK_MODEL = os.getenv("COBRANZA_AGENT_THINK_MODEL", "gemini-3.1-flash-lite")


# ── Esquemas de las tools (formato Voice Agent) ────────────────────────────────
# Las 12 de produccion (send_whatsapp, get_policy_info y search_knowledge
# se portaron el 30-sep; antes faltaban y el docstring mentia). El destinatario/ids sensibles NO los elige el modelo:
# se resuelven server-side contra el deudor en curso (igual que en pipecat).

def _tool_schemas(modo_recepcion: bool) -> list:
    end_call = {"name": "end_call",
                "description": "Termina la llamada. Usa esta funcion SIEMPRE que la conversacion "
                               "deba finalizar: cuando el deudor dice que no quiere hablar mas, "
                               "cuando ya se llego a un acuerdo, cuando te despides, cuando pide "
                               "que no lo llamen mas, cuando pide hablar con un humano (despues "
                               "de llamar escalate), o cuando la conversacion se vuelve "
                               "improductiva o el deudor se enoja. DESPIDETE ANTES de llamarla, "
                               "en el MISMO turno.",
                "parameters": {"type": "object",
                               "properties": {"reason": {"type": "string"}},
                               "required": ["reason"]}}
    if modo_recepcion:
        return [
            {"name": "identificar_cliente",
             "description": "Busca al cliente por el numero de documento que MARCO en el "
                            "teclado (te llega como '[TECLADO] <digitos>') o que dijo. "
                            "Devuelve sus polizas pendientes o 'no_encontrado'.",
             "parameters": {"type": "object",
                            "properties": {"documento": {"type": "string"}},
                            "required": ["documento"]}},
            end_call,
        ]
    return [
        end_call,
        {"name": "solicitar_link_cupon",
         "description": "El deudor pide el LINK o el CUPON de pago. Genera alerta a cartera "
                        "para enviarlo por WhatsApp. Confirma el envio.",
         "parameters": {"type": "object",
                        "properties": {"tipo": {"type": "string", "enum": ["link", "cupon"]}},
                        "required": ["tipo"]}},
        {"name": "informar_fecha_pago",
         "description": "El deudor promete pagar en una fecha futura ('pago el viernes'). "
                        "Registra la promesa (hoy es " + date.today().isoformat() + ").",
         "parameters": {"type": "object",
                        "properties": {"fecha": {"type": "string", "description": "YYYY-MM-DD"}},
                        "required": ["fecha"]}},
        {"name": "reagendar_llamada",
         "description": "El deudor pide que lo llamen en OTRO momento. Pregunta dia y hora "
                        "ANTES de llamarla. Reprograma la llamada.",
         "parameters": {"type": "object",
                        "properties": {"fecha": {"type": "string", "description": "YYYY-MM-DD"},
                                       "hora": {"type": "string", "description": "HH:MM 24h"}},
                        "required": ["fecha"]}},
        {"name": "notify_payment_claim",
         "description": "El deudor dice que YA PAGO. Notifica al equipo para verificar el "
                        "comprobante. Tu NO confirmas el pago, solo registras el reporte.",
         "parameters": {"type": "object",
                        "properties": {"detalle": {"type": "string"}},
                        "required": ["detalle"]}},
        {"name": "escalate",
         "description": "Escala a un asesor humano: el deudor lo pide, o hay disputa del "
                        "monto, reclamo, o pregunta por coberturas de su poliza. Confirma "
                        "que un asesor lo contactara, despidete y llama end_call.",
         "parameters": {"type": "object",
                        "properties": {"reason": {"type": "string"}},
                        "required": ["reason"]}},
        {"name": "registrar_no_desea_llamadas",
         "description": "El deudor pide EXPLICITAMENTE no ser llamado mas ('no me llame'). "
                        "Detiene todas las llamadas futuras. Despidete y llama end_call.",
         "parameters": {"type": "object", "properties": {}}},
        {"name": "verify_identity",
         "description": "USO RARO. Solo si la persona dice EXPLICITAMENTE que NO es el deudor "
                        "('numero equivocado', 'el no vive aqui') o da otro nombre. Nunca por "
                        "un simple 'alo'/'si'.",
         "parameters": {"type": "object",
                        "properties": {"utterance": {"type": "string"}},
                        "required": ["utterance"]}},
        {"name": "registrar_oportunidad_comercial",
         "description": "El deudor muestra interes en OTRO producto/seguro. Alerta al asesor "
                        "comercial. No interrumpe el flujo de cobranza.",
         "parameters": {"type": "object",
                        "properties": {"detalle": {"type": "string"}},
                        "required": ["detalle"]}},
        # ── Portadas del motor pipecat (migracion incompleta, 30-sep) ──────────
        # SEGURIDAD: el destinatario NO lo elige el modelo. Siempre va al telefono
        # del deudor en Mongo — una vez alucino un +573001234567.
        {"name": "send_whatsapp",
         "description": "Envia un WhatsApp AL DEUDOR (a su numero registrado) con "
                        "informacion de pago o seguimiento. El destinatario es siempre "
                        "el deudor; tu solo escribes el contenido del mensaje.",
         "parameters": {"type": "object",
                        "properties": {"message": {"type": "string",
                                       "description": "Contenido del mensaje para el deudor"}},
                        "required": ["message"]}},
        {"name": "get_policy_info",
         "description": "FALLBACK SOLAMENTE. Los datos de la poliza de ESTE deudor ya estan "
                        "en tu contexto — responde DIRECTO de ahi. Usa esta funcion UNICAMENTE "
                        "si el deudor pide un dato puntual que NO aparece en ese bloque "
                        "(numero de poliza, vigencia, prima, estado de cartera, asesor).",
         "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "search_knowledge",
         "description": "Consulta la base de conocimiento de la empresa (polizas, condiciones, "
                        "preguntas frecuentes, procedimientos) para responder con informacion "
                        "REAL y no inventada. Usala SIEMPRE que el deudor pregunte algo "
                        "especifico sobre su producto, cobertura, deducibles o condiciones.",
         "parameters": {"type": "object",
                        "properties": {"query": {"type": "string",
                                       "description": "La pregunta o tema, en lenguaje natural"}},
                        "required": ["query"]}},
    ]


def _debe_empujar(*, ahora: float, esperando_respuesta: bool, t_turno_cliente: float,
                  fin_audio: float, empujones: int, espera: float, maximo: int,
                  saludo_pendiente: bool) -> bool:
    """¿Toca empujar a ARIA a pedir aclaracion? Funcion pura: testeable sin llamada.

    La señal NO es "hay silencio" — un cliente pensando 7 s es normal y empujarlo
    ahi es grosero. La señal es ESPECIFICA: el cliente YA HABLO y ARIA no ha
    emitido NADA desde entonces. Eso es ARIA trabada, que es el bug reportado.

    - saludo_pendiente: el saludo aun no sale; nada que empujar.
    - esperando_respuesta: False si ARIA ya hablo despues del ultimo turno del
      cliente (o si el cliente no ha hablado todavia — ahi manda el watchdog de
      no-speech, que cuelga).
    - fin_audio: epoch en que Twilio termina de reproducir lo encolado. Si todavia
      suena, ARIA no esta trabada: esta hablando.
    """
    if saludo_pendiente or not esperando_respuesta:
        return False
    if empujones >= maximo:
        return False
    if ahora < fin_audio + 0.3:
        return False
    return (ahora - t_turno_cliente) >= espera


def _dias_mora_vivo(debtor: dict) -> int:
    """Recalcula los dias de mora contra HOY en Bogota.

    Portado de voice_pipecat:398-415. El `dias_mora` del sync de Softseguros
    puede tener un dia de rezago; ademas alimenta select_pitch_template, asi que
    un valor viejo hace elegir el pitch equivocado.
    """
    import pytz
    hoy = datetime.now(pytz.timezone("America/Bogota")).date()
    raw = debtor.get("fecha_pago") or debtor.get("vencimiento")
    venc = None
    if isinstance(raw, datetime):
        venc = raw.date()
    elif isinstance(raw, date):
        venc = raw
    elif raw:
        try:
            venc = date.fromisoformat(str(raw)[:10])
        except ValueError:
            venc = None
    if venc is not None:
        dias = max(0, (hoy - venc).days)
        # Tope de cordura: una poliza con >5 anios de mora es dato corrupto, no
        # cartera real. Sin esto ARIA dice "nueve mil ochocientos cuarenta y seis
        # dias" en voz alta (visto con un deudor de prueba con fecha de 1999).
        # Se cae al dias_mora de la DB, y si tampoco sirve, a 0.
        if dias > 1825:
            logger.warning("[agent] dias_mora absurdo (%d) para deudor %s — uso el de la DB",
                           dias, debtor.get("_id"))
            return min(1825, max(0, int(debtor.get("dias_mora") or 0)))
        return dias
    return max(0, int(debtor.get("dias_mora") or 0))


def _policy_info(debtor: dict) -> dict:
    """Datos de poliza de ESTE deudor, formateados para que el agente los hable.

    Solo campos del propio `debtor` (sin fuga entre tenants). Portado de
    voice_pipecat._handle_get_policy_info — el motor nuevo solo lleva 6 campos en
    el prompt, asi que los otros ~9 eran inalcanzables sin esto.
    """
    def _money(v):
        try:
            return f"${int(float(v)):,}".replace(",", ".") if v is not None else None
        except (TypeError, ValueError):
            return None

    def _date(v):
        return str(v)[:10] if v else None

    info = {
        "nombre": debtor.get("nombre"),
        "numero_poliza": debtor.get("numero_poliza"),
        "ramo": debtor.get("ramo_global_nombre") or debtor.get("ramo_nombre"),
        "tipo_poliza": debtor.get("ramo_nombre"),
        "saldo_pendiente": _money(debtor.get("monto") or debtor.get("total")),
        "prima": _money(debtor.get("prima")),
        "total_pagado": _money(debtor.get("total_pagado")),
        "vencimiento": _date(debtor.get("vencimiento")),
        "fecha_limite_pago": _date(debtor.get("fecha_limite_pago")),
        "vigencia_fin": _date(debtor.get("fecha_fin")),
        "estado_cartera": debtor.get("estado_cartera"),
        "estado_poliza": debtor.get("estado_poliza_nombre"),
        "periodicidad": debtor.get("periodicidad"),
        "asesor": debtor.get("vendedores_nombre"),
    }
    return {k: v for k, v in info.items() if v not in (None, "", [])}


# Tools que exponen datos del deudor (poliza, saldo, deuda) o actuan sobre su
# cuenta. Bloqueadas mientras el llamante no este identificado en modo recepcion.
_TOOLS_CON_DATOS = frozenset({
    "get_policy_info", "search_knowledge", "send_whatsapp", "solicitar_link_cupon",
    "informar_fecha_pago", "reagendar_llamada", "notify_payment_claim",
    "registrar_no_desea_llamadas", "registrar_oportunidad_comercial", "escalate",
})


_AFIRMA_PAGO = re.compile(
    r"ya (lo )?(pagu|cancel|consign|transfer|abon)|"
    r"\bpagu[eé]\b|\bcancel[eé]\b|"
    r"\bconsign[eé]\b|\btransfer[ií]\b|"
    r"hice (el|la) (pago|consignacion|transferencia)|esta pagad[oa]",
    re.IGNORECASE)


# Tools que pegan a servicios externos y tardan lo suficiente para que se note
# el silencio. Las que solo tocan Mongo (alertas, update_debtor) son instantaneas
# y un filler ahi solo haria la conversacion mas lenta.
_TOOLS_LENTAS = frozenset({"search_knowledge", "identificar_cliente", "send_whatsapp"})
_FILLERS = (
    "Permitame un momento que reviso eso...",
    "Dejeme verlo un momento...",
    "A ver, dejeme consultar eso...",
)


# Filtros de alerta para verify_identity (portados de voice_pipecat:1207-1236).
# _NEGACION_EXPLICITA: la persona dice claramente que no es el deudor.
# _ES_MAQUINA: es un buzon/contestador, no una persona negando.
_NEGACION_EXPLICITA = re.compile(
    r"equivoc[oóa]|n[uú]mero (incorrecto|errado|nuevo)|no (lo|la) conozco|"
    r"no conozco a|no vive|no trabaja|ya no (vive|trabaja|usa)|"
    r"no es (el|mi|su) (n[uú]mero|tel[eé]fono)|qui[eé]n es .{0,15}\?|"
    r"vendi[oó]? (el|la|este)|cambi[oó] de n[uú]mero",
    re.IGNORECASE)
_ES_MAQUINA = re.compile(
    r"buz[oó]n|contestador|mensaje autom|dej[ae] (su|tu) mensaje|"
    r"despu[eé]s del tono|no contest[oó] directamente",
    re.IGNORECASE)


# ── Dispatch de tools → handlers reales ────────────────────────────────────────

class _Dispatcher:
    """Ejecuta las tools contra la DB real. Reusa crear_alerta + orchestrator +
    la logica de identificar_cliente. `identificado` se comparte con el firewall
    conceptual de recepcion (aqui: si no esta identificado, solo corre
    identificar_cliente)."""

    def __init__(self, db, user_id: str, debtor: dict, orchestrator, call_sid: str,
                 transcript_ref: list, identificado: dict):
        self.db = db
        self.user_id = user_id
        self.debtor = debtor
        self.orch = orchestrator
        self.call_sid = call_sid
        self._transcript = transcript_ref
        self.identificado = identificado
        self._alertas = set()   # dedupe por tipo

    async def _alerta(self, tipo: str, *, detalle: str = "", extra: dict = None) -> dict:
        if not self.user_id or tipo in self._alertas:
            return {"ok": True, "dedupe": True}
        self._alertas.add(tipo)
        try:
            from cobranza.alerts import crear_alerta
            doc = await crear_alerta(self.db, self.user_id, self.debtor, tipo,
                                     detalle=detalle, extra=extra)
            return {"ok": True, "alerta_id": str(doc.get("_id"))}
        except Exception:
            logger.exception("[agent] crear_alerta(%s) fallo", tipo)
            return {"ok": False}

    async def __call__(self, name: str, args: dict) -> dict:
        d = self.debtor
        # Firewall de recepcion (portado en espiritu de voice_pipecat:1088-1091).
        # El viejo filtraba el TEXTO antes del TTS; aqui el audio lo sintetiza
        # Deepgram y ese filtro no es portable. Lo que SI se puede cerrar es la
        # puerta de datos: mientras el llamante no este identificado, ninguna
        # tool que exponga poliza/saldo puede correr. Incidente CA2573a3: el
        # modelo fabrico una poliza de Equidad y se la dijo a un desconocido.
        if not self.identificado.get("ok") and name in _TOOLS_CON_DATOS:
            logger.warning("[agent] firewall recepcion: bloqueada %s (sin identificar)", name)
            return {"ok": False,
                    "bloqueado": True,
                    "instruccion": "AUN NO ha confirmado su identidad. NO des ningun dato "
                                   "de poliza, saldo ni deuda. Pidele el numero de documento "
                                   "y llama identificar_cliente."}
        try:
            if name == "solicitar_link_cupon":
                tipo = args.get("tipo", "link")
                r = await self._alerta("solicitud_link_cupon",
                                       detalle=f"Solicito {tipo} de pago", extra={"tipo": tipo})
                return {**r, "confirmar": f"En breve le enviamos el {tipo} de pago por WhatsApp."}

            if name == "informar_fecha_pago":
                dd = date.fromisoformat(str(args.get("fecha", ""))[:10])
                if self.orch:
                    await self.orch.update_debtor(str(d["_id"]),
                        {"estado": "promesa_de_pago", "fecha_promesa": dd.isoformat()})
                return await self._alerta("fecha_estimada_pago", detalle=f"Pagaria el {dd.isoformat()}")

            if name == "reagendar_llamada":
                dd = date.fromisoformat(str(args.get("fecha", ""))[:10])
                if dd < datetime.now(timezone.utc).date():
                    return {"ok": False, "error": "fecha en el pasado"}
                try:
                    hh, mm = str(args.get("hora") or "09:00").split(":")[:2]
                    t = dtime(int(hh), int(mm))
                except Exception:
                    t = dtime(9, 0)   # sin hora -> inicio de jornada
                # CRITICO: datetime tz-aware en UTC, NO string naive.
                # sequence_engine hace isinstance(raw, datetime): con un string
                # cae a _to_date(), trunca a [:10] y pierde la hora que pidio el
                # cliente (pedia 3pm, lo llamaban a las 8am).
                import pytz
                local = pytz.timezone("America/Bogota").localize(datetime.combine(dd, t))
                at_utc = local.astimezone(pytz.utc)
                if self.orch:
                    upd = await self.orch.update_debtor(str(d["_id"]), {
                        "estado": "reagendado",
                        "fecha_reagendada": at_utc,
                        "proximo_intento_at": at_utc,
                        "reagendado_solicitado_por": "cliente",
                        "reagendado_en_llamada": self.call_sid,
                    })
                    if not upd.get("ok"):
                        return upd
                return {"ok": True,
                        "reagendado_para": f"{dd.isoformat()} {t.strftime('%H:%M')}",
                        "confirmar": "Listo, reprogramamos la llamada."}

            if name == "notify_payment_claim":
                # Anti-falso-positivo (portado de voice_pipecat:1297-1317): exige
                # que el deudor haya afirmado el pago EN PASADO en el transcript
                # real. Un STT que oye "pague" donde dijo "no pague" generaba
                # alertas falsas a cartera.
                # transcript son 3-tuplas (ts, speaker, texto) y el speaker
                # del cliente es "Deudor". Desempacar en 2 lanzaba ValueError y
                # el except de abajo lo tragaba: la tool NUNCA funcionaba.
                dicho = " ".join(x[2] for x in self._transcript if x[1] != "ARIA")
                if not _AFIRMA_PAGO.search(dicho):
                    logger.warning("[agent] notify_payment_claim RECHAZADO — sin afirmacion en pasado")
                    return {"ok": False,
                            "instruccion": "No quedo claro que ya pago. Preguntale explicitamente: "
                                           "'Para confirmar, ¿usted ya realizo el pago?' antes de registrarlo."}
                # SOLO alerta a cartera para que un HUMANO verifique el comprobante.
                # NO cambia el estado del deudor: un "pague" mal transcrito por el
                # STT (paso 09-ago: se marco pago_reportado sin que el cliente lo
                # dijera) no puede frenar la cobranza. El humano revisa y decide.
                r = await self._alerta("pago_reportado",
                                       detalle=args.get("detalle", "el cliente dice que ya pago"))
                # Mensaje 2 (portado de voice_pipecat:1327-1347): el prompt le
                # PROMETE al cliente un WhatsApp para mandar el comprobante. Sin
                # esto ARIA promete algo que nunca sale.
                tel = str(d.get("telefono", "")).strip()
                if self.orch and tel:
                    try:
                        await self.orch.send_whatsapp(tel,
                            "Hola, gracias por informarnos sobre su pago. Para actualizar "
                            "nuestros registros, ¿nos puede compartir por aqui el comprobante? "
                            "Con gusto lo validamos.")
                    except Exception as exc:
                        logger.error("[agent] WhatsApp de comprobante fallo: %s", exc)
                return r

            if name == "escalate":
                if self.orch:
                    try:
                        await self.orch.escalate(args.get("reason", "escalado"), str(d.get("_id")))
                    except Exception:
                        logger.exception("[agent] escalate orch fallo")
                return await self._alerta("consulta_fuera_alcance", detalle=args.get("reason", ""))

            if name == "registrar_no_desea_llamadas":
                if self.orch:
                    await self.orch.update_debtor(str(d["_id"]),
                        {"no_llamar": True, "no_llamar_motivo": "opt_out", "clasificado_por": "manual"})
                return await self._alerta("opt_out")

            if name == "verify_identity":
                utterance = args.get("utterance", "")
                if self.orch:
                    try:
                        r = await self.orch.verify_identity(utterance, d.get("nombre"))
                        if r.get("confirmed") is False and r.get("confidence") == "high":
                            # Alerta SOLO con negacion explicita (portado de
                            # voice_pipecat:1207-1236). Sin estos filtros, un "No."
                            # seco, ruido de STT o un contestador generaban alertas
                            # basura a cartera: 10 en un dia el 17-jul.
                            if _NEGACION_EXPLICITA.search(utterance) and                                not _ES_MAQUINA.search(utterance):
                                await self._alerta("numero_equivocado",
                                                   detalle=utterance[:200])
                            # Guion de cierre: es la ruta donde la conversacion se
                            # muere si ARIA no sabe que decir. Sin mencionar la deuda.
                            r["instruccion"] = (
                                "La persona NO es el deudor (numero equivocado). Discúlpate "
                                "brevemente y despídete SIN mencionar la deuda ni ningun dato: "
                                "'Ah, disculpe la molestia, debe haber un error con el numero. "
                                "Que tenga un buen dia, hasta luego.' y llama end_call en el "
                                "mismo turno."
                            )
                        return r
                    except Exception:
                        logger.exception("[agent] verify_identity fallo")
                return {"confirmed": False}

            if name == "registrar_oportunidad_comercial":
                return await self._alerta("oportunidad_comercial", detalle=args.get("detalle", ""))

            if name == "identificar_cliente":
                return await self._identificar(args.get("documento", ""))

            # ── Portadas del motor pipecat (migracion incompleta, 30-sep) ──────
            if name == "send_whatsapp":
                # SEGURIDAD: el telefono sale de Mongo, NUNCA del modelo.
                phone = str(d.get("telefono", "")).strip()
                msg = args.get("message", "")
                if not phone:
                    return {"ok": False, "error": "el deudor no tiene telefono registrado"}
                if not (self.orch and msg):
                    return {"ok": False, "error": "orchestrator no disponible"}
                try:
                    return await self.orch.send_whatsapp(phone, msg)
                except Exception as exc:
                    logger.error("[agent] send_whatsapp fallo: %s", exc)
                    return {"ok": False, "error": str(exc)[:100]}

            if name == "get_policy_info":
                return {"found": bool(_policy_info(d)), "poliza": _policy_info(d)}

            if name == "search_knowledge":
                return await self._buscar_kb(args.get("query", ""))

        except Exception:
            logger.exception("[agent] tool %s fallo", name)
            return {"ok": False, "error": "fallo interno"}
        return {"ok": True}

    async def _buscar_kb(self, query: str) -> dict:
        """search_knowledge: RAG por tenant (Pinecone, namespace=user_id).

        Portado de voice_pipecat._handle_search_knowledge. Mantiene el timeout
        duro de 4s: una consulta lenta no puede dejar la llamada en aire muerto.
        El filler hablado del motor viejo NO se porta — aqui el audio lo genera
        Deepgram y no hay cola de TTS propia donde encolarlo.
        """
        if not (self.user_id and query):
            return {"found": False, "message": "No hay informacion sobre eso."}
        try:
            from cobranza.rag_service import search_knowledge
            matches = await asyncio.wait_for(
                search_knowledge(self.user_id, query, top_k=3), timeout=4.0
            )
        except asyncio.TimeoutError:
            logger.warning("[agent] search_knowledge timeout (>4s) — degradando")
            return {"found": False, "message": "No pude consultar eso a tiempo."}
        except Exception as exc:
            logger.error("[agent] search_knowledge fallo: %s", exc)
            return {"found": False, "error": str(exc)[:100]}
        if not matches:
            return {"found": False,
                    "message": "No hay informacion sobre eso en la base de conocimiento."}
        return {"found": True,
                "results": [{"text": m.get("text", "")[:600], "title": m.get("title", "")}
                            for m in matches]}

    async def _identificar(self, crudo: str) -> dict:
        from cobranza.voz_comun import documento_base
        from cobranza.es_numbers import pesos_en_palabras
        digits = "".join(c for c in str(crudo) if c.isdigit())
        cands = []
        if len(digits) >= 5:
            async for x in self.db.debtors.find(
                {"user_id": self.user_id, "is_active": {"$ne": False},
                 "cliente_documento": {"$nin": [None, ""]}},
                {"cliente_documento": 1, "nombre": 1, "numero_poliza": 1, "ramo_nombre": 1,
                 "aseguradora_nombre": 1, "monto": 1, "vencimiento": 1, "fecha_pago": 1,
                 "numero_cuota": 1, "dias_mora": 1}):
                if documento_base(x.get("cliente_documento")) == digits:
                    cands.append(x)
        if not cands:
            await self._alerta("llamada_entrante_no_identificada",
                               detalle=f"Documento '{digits}' sin match en cartera.")
            return {"resultado": "no_encontrado",
                    "instruccion": "Disculpate, di que un asesor puede ayudarle, NO reveles "
                                   "ningun dato, y despidete."}
        principal = max(cands, key=lambda x: int(x.get("dias_mora") or 0))
        self.debtor = principal
        self.identificado["ok"] = True
        await self.db.cobranza_calls_in_progress.update_one(
            {"call_sid": self.call_sid},
            {"$set": {"debtor_id": str(principal["_id"]), "debtor_name": principal.get("nombre")}})
        pol = [{"tipo": x.get("ramo_nombre"), "aseguradora": x.get("aseguradora_nombre"),
                "valor": pesos_en_palabras(float(x.get("monto") or 0)),
                "vence": str(x.get("fecha_pago") or x.get("vencimiento"))[:10],
                "dias_mora": int(x.get("dias_mora") or 0),
                 "poliza": x.get("numero_poliza"),
                 "cuota": x.get("numero_cuota")} for x in cands]
        return {"resultado": "encontrado", "nombre": principal.get("nombre"),
                "polizas_pendientes": pol,
                "instruccion": "Identidad confirmada. Saludalo por su nombre y gestiona el "
                               "recordatorio con estos datos."}


# ── Settings del Voice Agent ───────────────────────────────────────────────────

def _env_json(name: str) -> dict:
    try:
        return json.loads(os.getenv(name, "") or "{}") or {}
    except json.JSONDecodeError:
        logger.warning("[agent] %s no es JSON valido — ignorado", name)
        return {}


def _listen_provider(keyterms: list, cfg: dict) -> dict:
    """Oido del agente. cfg = tenant_configs.cobranza.deepgram_listen (o env
    COBRANZA_AGENT_LISTEN como JSON). Default: nova-3 es (doc oficial
    Twilio+Deepgram). Con model "flux-general-multi" se usa el end-of-turn
    INTEGRADO de Flux (eot_threshold / eager_eot_threshold / eot_timeout_ms):
    decide que el cliente termino por el modelo, no por un silencio fijo — es
    la palanca grande de latencia STT→LLM. Se valida sin llamada real con
    scripts/check_deepgram_agent.py."""
    model = str(cfg.get("model") or "nova-3")
    p = {"type": "deepgram", "model": model, "keyterms": keyterms}
    if model.startswith("flux"):
        p["version"] = "v2"
        p["language_hints"] = list(cfg.get("language_hints") or ["es"])
        for k in ("eot_threshold", "eager_eot_threshold", "eot_timeout_ms"):
            if cfg.get(k) is not None:
                p[k] = cfg[k]
    else:
        p["language"] = str(cfg.get("language") or "es")
    if cfg.get("smart_format") is not None:
        p["smart_format"] = bool(cfg["smart_format"])
    return p


def _settings(prompt: str, greeting: str, voz: str, keyterms: list,
              modo_recepcion: bool, listen_cfg: dict = None,
              temperature: float = 0.5) -> dict:
    return {
        "type": "Settings",
        "audio": {
            "input": {"encoding": "mulaw", "sample_rate": 8000},
            "output": {"encoding": "mulaw", "sample_rate": 8000, "container": "none"},
        },
        "agent": {
            "listen": {"provider": _listen_provider(keyterms, listen_cfg or {})},
            # temperature 0.5 (misma que el pipeline pipecat): menos deliberacion
            # de muestreo = respuesta un poco antes; cobranza quiere guion, no
            # creatividad.
            "think": {"provider": {"type": "google", "model": THINK_MODEL,
                                   "temperature": temperature},
                      "prompt": prompt, "functions": _tool_schemas(modo_recepcion)},
            "speak": {"provider": {"type": "deepgram", "model": voz}},
            "greeting": greeting,
        },
    }


# ── Prompt de 3 capas + saludo (mismo prompt_builder de produccion) ────────────

def armar_prompt(debtor: dict, tenant_config: dict, *, modo_recepcion: bool,
                 is_inbound: bool = False) -> tuple:
    """Devuelve (prompt, greeting, keyterms). Reusa prompt_builder para que el
    guion sea IDENTICO al del pipeline pipecat."""
    from cobranza.prompt_builder import (
        assemble_system_prompt, nombre_dos, render_greeting, resolve_persona,
    )
    from cobranza.es_numbers import pesos_en_palabras
    from cobranza.voz_comun import keyterms_llamada
    persona = resolve_persona(tenant_config)
    brand = persona.get("company_brand") or persona.get("company_name", "")
    agente = str(persona.get("agent_name") or "Aria").title()

    # Saludo segun la franja real en Bogota: "buenos dias" fijo sonaba mal
    # en llamadas de la tarde (bug compartido con voice_pipecat:976).
    import pytz
    _h = datetime.now(pytz.timezone("America/Bogota")).hour
    saludo_hora = ("muy buenos dias" if _h < 12 else
                   "muy buenas tardes" if _h < 19 else "muy buenas noches")

    if modo_recepcion:
        greeting = f"{brand}, {saludo_hora}, le habla {agente}. ¿Con quien tengo el gusto?"
        prompt = (
            f"Eres {agente}, la asistente virtual de {brand} (seguros, Colombia). "
            "Contestaste una llamada ENTRANTE; aun no sabes quien llama.\n"
            "OBJETIVO: identificarlo por su documento (cedula o NIT). Pidele que lo MARQUE "
            "en el teclado y termine con numeral; te llega como '[TECLADO] <digitos>'. Apenas "
            "lo tengas, llama identificar_cliente. Si insiste en decirlo de viva voz, "
            "aceptalo. NUNCA reveles datos de polizas/saldos ni confirmes si un documento "
            "existe hasta que identificar_cliente confirme. Espanol colombiano, de usted, "
            "frases cortas, numeros digito por digito. Al terminar, despidete y llama end_call."
        )
        return prompt, greeting, keyterms_llamada(debtor or {})

    first_name = nombre_dos(debtor.get("nombre") or "")
    monto_natural = pesos_en_palabras(float(debtor.get("monto") or 0))
    runtime_block = (
        "DATOS DE ESTA LLAMADA (reales y exactos de ESTE deudor — usalos directo):\n"
        f"- Nombre: {debtor.get('nombre')}\n"
        f"- Dirigete por su nombre: '{first_name}'. NUNCA 'senor/senora/don/dona'.\n"
        f"- Deuda pendiente: {monto_natural}\n"
        # Campos opcionales: si falta el dato se OMITE la linea. Antes se
        # interpolaba el None y el modelo lo leia en voz alta ("expedida por Non").
        + "".join(
            f"- {etq}: {val}\n"
            for etq, val in (
                ("Vencimiento", str(debtor.get("vencimiento") or debtor.get("fecha_pago") or "")[:10] or None),
                ("Tipo de poliza", debtor.get("ramo_nombre")),
                ("Aseguradora", debtor.get("aseguradora_nombre")),
            ) if val
        )
        # Campos extra (portados de voice_pipecat:306-346): sin esto el modelo
        # tenia que llamar get_policy_info para datos que ya estan a mano.
        + "".join(
            f"- {etq}: {val}\n"
            for etq, val in (
                ("Numero de poliza", debtor.get("numero_poliza")),
                ("Riesgo asegurado", debtor.get("objeto_asegurado")),
                ("Estado de cartera", debtor.get("estado_cartera")),
                ("Estado de la poliza", debtor.get("estado_poliza_nombre")),
                ("Vigencia hasta", str(debtor.get("fecha_fin") or "")[:10] or None),
                ("Fecha limite de pago", str(debtor.get("fecha_limite_pago") or "")[:10] or None),
                ("Asesor asignado", debtor.get("vendedores_nombre")),
            ) if val
        )
        # Desambiguacion anti-invento (portado de voice_pipecat:376-386). Los
        # keyterms son el "oido"; esto es el "cerebro".
        + "\nAUDIO TELEFONICO RUIDOSO — VOCABULARIO PROBABLE DEL CLIENTE (usalo para "
          "desambiguar lo que oigas; lo que NO se parezca a nada de esto ni al "
          "contexto, NO lo completes — pide repetir): "
        + f"'{first_name}', '{str(debtor.get('aseguradora_nombre') or '').strip()}', "
        + "'alo', 'si', 'si por favor', 'si claro', 'no', 'no gracias', 'bueno', "
          "'con ella habla', 'con el habla', 'soy yo', 'un link', 'link de pago', "
          "'un cupon de pago', 'ya pague', 'ya lo cancele', 'no tengo plata', "
          "'no puedo pagar', 'llamame manana', 'mas tarde', 'un asesor', "
          "'numero equivocado', 'gracias', 'hasta luego'.\n\n"
    )
    prompt = assemble_system_prompt(
        persona, runtime_block=runtime_block, first_name=first_name,
        ramo=debtor.get("ramo_nombre") or "seguros", monto_natural=monto_natural,
        aseguradora=debtor.get("aseguradora_nombre") or "",
        riesgo=str(debtor.get("objeto_asegurado") or "").strip(),
        modalidad=str(debtor.get("forma_pago") or debtor.get("forma_pago_texto") or "").strip(),
        intento=int(debtor.get("proximo_intento_numero") or (debtor.get("intentos") or 0) + 1),
        dias_mora=_dias_mora_vivo(debtor),
        numero_cuota=str(debtor.get("numero_cuota") or ""),
        is_inbound=is_inbound,
    ).replace("ARIA", "Aria")
    if is_inbound and first_name:
        # Entrante de un deudor ya identificado: NO le preguntes quien es, el
        # acaba de llamar (portado de voice_pipecat:908-919).
        agente = persona.get("agent_name", "Aria")
        brand = persona.get("company_brand", "")
        greeting = (f"Gracias por comunicarse con {brand}. Le habla {agente}. "
                    f"{first_name}, con mucho gusto le ayudo. ¿En que le puedo servir?")
    else:
        greeting = render_greeting(persona, first_name)
    greeting = greeting.replace("ARIA", "Aria")
    return prompt, greeting, keyterms_llamada(debtor or {})


# ── Bridge Twilio ↔ Voice Agent ────────────────────────────────────────────────

_MULAW_BPS = 8000.0          # bytes/segundo de mulaw 8k = segundos que suena
_TRAMA = 160                 # 20 ms — la trama que Twilio espera


async def run_voice_agent(*, websocket, call_sid: str, debtor: dict, user_id: str,
                          stream_id: str, tenant_config: dict,
                          is_inbound: bool = False, modo_recepcion: bool = False,
                          captions: bool = False) -> CallResult:
    """Puentea el media-stream de Twilio (ya aceptado) con el Voice Agent de
    Deepgram y devuelve el CallResult para el post-call. Nunca lanza hacia
    afuera: cualquier fallo cierra limpio con lo que se haya recolectado."""
    result = CallResult(call_sid=call_sid, started_at=time.time(), engine="deepgram_agent")
    from database import get_db
    db = get_db()
    key = os.getenv("DEEPGRAM_API_KEY", "")

    # Kill-switch por tenant (portado de voice_pipecat:271-274). Va ANTES de
    # conectar a Deepgram: si el modulo de voz esta apagado, el tenant no debe
    # consumir ni minutos ni cuota del Voice Agent.
    if not tenant_config.get("modules", {}).get("voice", True):
        logger.info("[agent] modules.voice=false user=%s — cerrando socket (1008)", user_id)
        try:
            await websocket.close(1008, "Voice module disabled")
        except Exception:
            pass
        result.end_reason = "voice_module_disabled"
        return result

    # 1) Conectar a Deepgram YA, en paralelo con armar prompt/orchestrator: el
    #    handshake TLS+WS (~300-600 ms) deja de sumarse al silencio pre-saludo.
    t_conn = time.time()

    async def _abrir():   # websockets.connect es awaitable pero NO corutina
        return await websockets.connect(
            DG_AGENT_URL, additional_headers={"Authorization": f"Token {key}"},
            close_timeout=1)  # si Twilio muere primero, close() esperaba 10s el handshake

    conectar = asyncio.create_task(_abrir())

    # Ruido de oficina de fondo (call center feel). Apagable por tenant con
    # office_ambience_enabled=false; volumen con office_ambience_volume.
    try:
        from cobranza.office_mixer_mulaw import crear as _crear_ambiente
        ambiente = _crear_ambiente(tenant_config)
    except Exception as _amb_err:
        logger.warning("[agent] ambiente de oficina no disponible: %s", _amb_err)
        ambiente = None

    cobr = tenant_config.get("cobranza") or {}
    prompt, greeting, keyterms = armar_prompt(debtor or {}, tenant_config,
                                              modo_recepcion=modo_recepcion,
                                              is_inbound=is_inbound)
    voz = str(cobr.get("deepgram_voice") or tenant_config.get("deepgram_voice")
              or os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-celeste-es"))
    listen_cfg = cobr.get("deepgram_listen") or _env_json("COBRANZA_AGENT_LISTEN")
    temperature = float(cobr.get("voice_temperature") or tenant_config.get("voice_temperature")
                        or os.getenv("COBRANZA_AGENT_TEMPERATURE", "0.5"))
    logger.info("[agent] call=%s recepcion=%s voz=%s think=%s listen=%s keyterms=%d prompt=%d chars",
                call_sid, modo_recepcion, voz, THINK_MODEL,
                listen_cfg.get("model") or "nova-3", len(keyterms), len(prompt))
    from cobranza.cobranza_orchestrator import CobranzaOrchestrator
    orch = CobranzaOrchestrator(user_id, tenant_config) if user_id else None
    identificado = {"ok": not modo_recepcion}
    dispatch = _Dispatcher(db, user_id, debtor or {}, orch, call_sid,
                           result.transcript, identificado)

    # ── Reloj de reproduccion ─────────────────────────────────────────────────
    # Deepgram entrega el audio del agente en RAFAGA (mucho mas rapido que tiempo
    # real) y Twilio lo reproduce a 8000 B/s. Todo lo que dependa de "ARIA ya
    # termino de hablar" (anti-eco, colgar tras la despedida) se calcula sobre
    # CUANDO TERMINA DE SONAR, no sobre cuando llego el ultimo chunk. (Bug
    # anterior: a los 0.5 s del ultimo chunk se reabria el microfono con ARIA
    # aun a mitad de frase → su propio eco entraba como turno del cliente.)
    play = {"fin": 0.0}                       # epoch en que Twilio termina de sonar
    # Cola anti-eco: mientras ARIA habla +N s se manda silencio al STT en vez
    # del audio del cliente. A 0.5 s se comia el final de lo que el cliente
    # decia solapado con ARIA (el motor viejo NO interrumpia pero SI escuchaba:
    # voice_pipecat:876-878). 0.15 s basta para el eco de la linea.
    # 0.15 s se probo en llamada real (01-oct) y METE ECO: ARIA se oia a si
    # misma, repetia frases y el STT le inventaba nombres ("Martina", "Marco"
    # donde el cliente es "Maxi"). 0.5 s es el valor que venia de fabrica y no
    # mostro ese problema. Si hace falta que ARIA oiga mas al cliente, el
    # camino es apagar half-duplex, no acortar la cola.
    _COLA_ANTIECO = float(os.getenv("COBRANZA_AGENT_ECHO_TAIL_S", "0.5"))
    _SILENCIO = b"\xff" * _TRAMA
    # Half-duplex apagable por tenant/env: su costo real es que lo que el
    # cliente diga MIENTRAS ARIA habla se pierde (y el se siente ignorado). En
    # telefono al oido casi no hay eco; full-duplex deja que Deepgram maneje
    # eco/barge-in nativo. Default: on (el caso ALTAVOZ inventaba turnos).
    _half_duplex = str(cobr.get("agent_half_duplex",
                                os.getenv("COBRANZA_AGENT_HALF_DUPLEX", "true"))).lower() != "false"

    # El SALUDO manda: hasta que el primer byte de audio de ARIA llegue, TODO lo
    # del cliente se silencia hacia Deepgram. Sin esto habia una carrera fatal:
    # el "alo" al contestar entraba ANTES del saludo, Deepgram disparaba
    # UserStartedSpeaking / barge-in sobre un saludo apenas encolado, y el
    # cliente oia a ARIA arrancando A MITAD de frase (queja 30-ago).
    saludo_pendiente = {"v": True}

    def aria_habla() -> bool:
        # Half-duplex anti-eco (doc Deepgram audio-preprocessing): mientras ARIA
        # suena (+cola), lo que vuelve por la linea es su eco (grave en ALTAVOZ);
        # a Deepgram se le manda silencio. Costo: sin barge-in ese ratito.
        return _half_duplex and (saludo_pendiente["v"]
                                 or time.time() < play["fin"] + _COLA_ANTIECO)

    # ── Latencia por turno (lo que el cliente percibe) ────────────────────────
    lat = {"t_eot": 0.0, "turno": 0}

    # ── Colgado coordinado ───────────────────────────────────────────────────
    colgar = asyncio.Event()
    motivo = {"v": ""}

    def pedir_colgar(m: str):
        if not colgar.is_set():
            motivo["v"] = m
            result.end_reason = result.end_reason or m
            colgar.set()

    vm_acum = {"t": ""}           # texto del cliente acumulado, para cazar buzones
    # Ultimo momento en que ALGUIEN hablo (ARIA o el cliente). Si pasa mucho
    # sin nada, ARIA se quedo muda sin entender y hay que empujarla a pedir
    # que le repitan — antes el cliente tenia que decir "alo" para despertarla.
    # "esperando": el cliente hablo y ARIA no ha emitido nada desde entonces.
    # Esa es la señal de ARIA trabada — no el silencio a secas (un cliente
    # pensando 7 s es normal y empujarlo ahi es grosero).
    espera_resp = {"on": False, "t_turno": 0.0, "empujones": 0}
    marca_eco = asyncio.Event()   # Twilio devolvio el mark: lo encolado ya SONO

    async def _subtitulo(role: str, texto: str):
        # Solo para la demo web (captions=True): Twilio no entiende este evento.
        if not captions:
            return
        try:
            await websocket.send_json({"event": "transcript", "role": role, "text": texto})
        except Exception:
            pass

    async def _enviar_marca():
        try:
            await websocket.send_json({"event": "mark", "streamSid": stream_id,
                                       "mark": {"name": "fin-despedida"}})
        except Exception:
            pass

    async def colgar_tras_despedida(max_espera: float = 8.0):
        # end_call: colgar cuando la despedida SONO de verdad. El mark de Twilio
        # se encola detras del audio ya enviado y vuelve como eco cuando ese
        # audio se reprodujo — senal exacta, sin estimar red/buffers. Si llega
        # MAS audio despues del mark, se manda otro. Fallback: el reloj de
        # reproduccion +1s si el eco no vuelve; tope duro de max_espera.
        limite = time.time() + max_espera
        # La despedida AUN NO LLEGO: end_call entra como JSON antes que el audio
        # (cientos de ms a 1-2 s). play["fin"] todavia apunta al turno ANTERIOR,
        # asi que el fallback de abajo se cumpliria en la iteracion 0 y
        # colgariamos antes de que ARIA diga una sola palabra. Esperamos a que
        # el reloj de reproduccion CREZCA (= llego audio nuevo) o a que venza la
        # ventana de arranque. El motor viejo lo resolvia con un sleep(0.6)
        # incondicional (voice_pipecat:1160); esto es lo mismo pero medido.
        fin_previo = play["fin"]
        arranque = time.time() + 2.5
        while time.time() < arranque and play["fin"] <= fin_previo + 0.05:
            if colgar.is_set():
                return
            await asyncio.sleep(0.05)
        await _enviar_marca()
        while time.time() < limite:
            if marca_eco.is_set():
                if time.time() >= play["fin"] - 0.05:
                    break                     # eco recibido y nada mas por sonar
                marca_eco.clear()             # llego mas despedida tras el mark
                await _enviar_marca()
            elif time.time() >= play["fin"] + 1.0:
                break                         # fallback estimado: eco perdido
            await asyncio.sleep(0.15)
        pedir_colgar("end_call")

    tareas_bg: set = set()

    def _bg(coro):
        t = asyncio.create_task(coro)
        tareas_bg.add(t)
        t.add_done_callback(tareas_bg.discard)
        return t

    async def ejecutar_tool(dg, f: dict):
        # Corre como task: mientras la tool pega a Mongo/alertas, el audio que
        # el agente ya mando sigue fluyendo a Twilio (antes el loop se frenaba).
        name = f.get("name", "")
        _a = f.get("arguments")
        if isinstance(_a, str):            # el Voice Agent manda arguments como STRING JSON
            try:
                _a = json.loads(_a) if _a.strip() else {}
            except json.JSONDecodeError:
                _a = {}
        # Filler hablado para las tools lentas (portado de voice_pipecat:1421-1430).
        # Sin esto el cliente escucha aire muerto mientras corre la consulta.
        # behavior=queue: se encola detras de lo que el agente este diciendo y
        # NO interrumpe; si el cliente habla, Deepgram lo rechaza solo.
        if name in _TOOLS_LENTAS:
            try:
                await dg.send(json.dumps({
                    "type": "InjectAgentMessage",
                    "message": random.choice(_FILLERS),
                    "behavior": "queue"}))
            except Exception:
                pass   # un filler que no sale nunca puede tumbar la tool

        t0 = time.time()
        content = await dispatch(name, _a or {})
        logger.info("[agent][lat] tool %s: %.0f ms", name, (time.time() - t0) * 1000)
        await dg.send(json.dumps({"type": "FunctionCallResponse", "id": f.get("id"),
                                  "name": name,
                                  "content": json.dumps(content, ensure_ascii=False)}))
        if name == "end_call":
            result.end_reason = str((_a or {}).get("reason") or "end_call")
            _bg(colgar_tras_despedida())

    async def watchdogs():
        # Mismos guardas que el pipeline pipecat (el motor nuevo no los tenia):
        # sin voz humana en N s = buzon mudo/aire muerto → colgar; tope duro de
        # duracion pase lo que pase.
        no_speech = int(os.getenv("COBRANZA_NO_SPEECH_HANGUP_SECS", "20"))
        max_s = int(os.getenv("COBRANZA_MAX_CALL_SECS", "240"))
        await asyncio.sleep(no_speech)
        if result.user_turn_count == 0:
            pedir_colgar(f"sin voz humana tras {no_speech}s")
            return
        await asyncio.sleep(max(0, max_s - no_speech))
        # Pide la despedida antes de cortar: el viejo encolaba un EndFrame
        # que pipecat drenaba DETRAS del audio pendiente. Aqui avisamos al
        # modelo y le damos un respiro para cerrar; si no lo hace, se corta.
        try:
            await dg_box["ws"].send(json.dumps({
                "type": "InjectAgentMessage",
                "message": "Disculpe, debo finalizar la llamada. Que tenga un buen dia.",
                "behavior": "interrupt"}))
            await asyncio.sleep(4.0)
        except Exception:
            pass
        pedir_colgar(f"tope de {max_s}s")

    async def empujar_si_mudo():
        """Si nadie habla por N s, ARIA pide que le repitan en vez de quedarse muda.

        El problema real observado (01-oct): cuando ARIA no entiende, no produce
        nada y la llamada queda en silencio hasta que el cliente dice "alo" para
        despertarla. Ningun motor tenia esto — ni el viejo ni el nuevo: el unico
        guarda de silencio CUELGA, no reengancha.

        behavior="default": Deepgram solo lo dice si NADIE esta hablando; si el
        cliente arranco justo en ese momento, lo rechaza solo y no pisa su turno.
        Tope de 2 empujones: al tercero la conversacion esta muerta y es mejor
        dejar que el watchdog de duracion cierre con una despedida.
        """
        espera = float(os.getenv("COBRANZA_SILENCIO_EMPUJON_S", "7"))
        maximo = int(os.getenv("COBRANZA_MAX_EMPUJONES", "2"))
        frases = (
            "Disculpe, no le escuche bien. ¿Me puede repetir, por favor?",
            "¿Sigue usted ahi? Si prefiere, podemos continuar en otro momento.",
        )
        await listo.wait()
        while not colgar.is_set():
            await asyncio.sleep(1.0)
            if colgar.is_set():
                continue
            if not _debe_empujar(
                ahora=time.time(),
                esperando_respuesta=espera_resp["on"],
                t_turno_cliente=espera_resp["t_turno"],
                fin_audio=play["fin"],
                empujones=espera_resp["empujones"],
                espera=espera, maximo=maximo,
                saludo_pendiente=saludo_pendiente["v"],
            ):
                continue
            i = espera_resp["empujones"]
            espera_resp["empujones"] += 1
            espera_resp["t_turno"] = time.time()   # reinicia la ventana
            logger.info("[agent] ARIA trabada tras turno del cliente — empujon %d/%d",
                        i + 1, maximo)
            try:
                await dg_box["ws"].send(json.dumps({
                    "type": "InjectAgentMessage",
                    "message": frases[min(i, len(frases) - 1)],
                    "behavior": "default"}))
            except Exception:
                logger.warning("[agent] no pude mandar el empujon")

    dg_box = {"ws": None}      # la bomba arranca ANTES de tener la sesion
    listo = asyncio.Event()    # Settings ya enviados: se puede reenviar audio
    descartado = {"frames": 0}

    # ── Acumulador DTMF (portado de voice_pipecat.CapturaDTMF) ────────────────
    dtmf_buf: list = []
    dtmf_timer = {"t": None}

    async def _dtmf_flush():
        """Manda los digitos acumulados como UN solo mensaje y limpia."""
        if dtmf_timer["t"]:
            dtmf_timer["t"].cancel()
            dtmf_timer["t"] = None
        if not dtmf_buf:
            return
        digitos = "".join(dtmf_buf)
        dtmf_buf.clear()
        logger.info("[agent] DTMF -> %s digitos", len(digitos))
        # 3-tupla con speaker "Deudor": una 2-tupla revienta full_transcript
        # (desempaca 3) y el sorted compara str con float. Ademas asi SI cuenta
        # en user_turn_count y el watchdog de no-speech no cuelga a quien solo teclea.
        result.transcript.append((time.time(), "Deudor", f"[TECLADO] {digitos}"))
        try:
            await dg_box["ws"].send(json.dumps({"type": "InjectUserMessage",
                                                "content": f"[TECLADO] {digitos}"}))
        except Exception:
            logger.warning("[agent] no pude inyectar DTMF")

    async def _dtmf_timeout():
        """Cierra el bloque si pasan 3s sin teclear (no todos marcan '#')."""
        try:
            await asyncio.sleep(3.0)
            await _dtmf_flush()
        except asyncio.CancelledError:
            pass

    async def twilio_a_dg():
        async for raw in websocket.iter_text():
            m = json.loads(raw)
            ev = m.get("event")
            if ev == "media":
                if not listo.is_set():
                    # Audio ANTERIOR a la sesion con Deepgram (los "alo, alo?"
                    # mientras conectabamos). Antes se acumulaba en el buffer y
                    # al conectar entraba EN RAFAGA: el STT arrancaba esos
                    # segundos atrasado y ARIA respondia a turnos viejos toda la
                    # llamada (visto: stt_latency 6.8s drenando a 0.2s/s). Se
                    # DESCARTA: el saludo lo dice ella primero igual.
                    descartado["frames"] += 1
                    continue
                await dg_box["ws"].send(
                    _SILENCIO if aria_habla() else base64.b64decode(m["media"]["payload"]))
            elif ev == "dtmf":
                # Acumulador (portado de voice_pipecat.CapturaDTMF:106-167). Antes
                # se inyectaba UNA tecla por mensaje: una cedula de 10 digitos
                # generaba 10 inyecciones sueltas y el modelo tenia que
                # reconstruir el numero. Ahora se cierra con '#' o tras 3s sin
                # teclear, y se manda el bloque completo de una.
                tecla = (m.get("dtmf") or {}).get("digit", "")
                if not listo.is_set():
                    continue
                if tecla == "#":
                    await _dtmf_flush()
                elif tecla.isdigit():
                    dtmf_buf.append(tecla)
                    if dtmf_timer["t"]:
                        dtmf_timer["t"].cancel()
                    dtmf_timer["t"] = asyncio.create_task(_dtmf_timeout())
            elif ev == "mark":
                if (m.get("mark") or {}).get("name") == "fin-despedida":
                    marca_eco.set()
            elif ev == "stop":
                pedir_colgar("twilio stop")
                return

    async def dg_a_twilio(dg):
        from cobranza.voz_comun import _VOICEMAIL_LIVE_RE
        async for msg in dg:
            if isinstance(msg, bytes):
                now = time.time()
                saludo_pendiente["v"] = False   # ya esta sonando: manda el reloj
                if lat["t_eot"]:
                    logger.info("[agent][lat] turno %d: fin-de-turno → primer audio %.0f ms",
                                lat["turno"], (now - lat["t_eot"]) * 1000)
                    lat["t_eot"] = 0.0
                if play["fin"] < now:
                    play["fin"] = now          # cola vacia: empieza a sonar ya
                play["fin"] += len(msg) / _MULAW_BPS
                espera_resp["on"] = False      # ARIA respondio: no esta trabada
                # Re-chunk a tramas de 20 ms: Deepgram manda bloques grandes e
                # irregulares y Twilio glitchea al reproducirlos ("se traba").
                for i in range(0, len(msg), _TRAMA):
                    trama = msg[i:i + _TRAMA]
                    if ambiente is not None:
                        trama = ambiente.mezclar(trama)
                    await websocket.send_json({
                        "event": "media", "streamSid": stream_id,
                        "media": {"payload": base64.b64encode(trama).decode()}})
                continue
            ev = json.loads(msg)
            t = ev.get("type")
            if t == "UserStartedSpeaking":
                # barge-in SOLO en full-duplex: vaciar lo encolado en Twilio.
                # En half-duplex no hay barge-in — y este clear era el que
                # BOTABA el saludo recien encolado cuando el "alo" inicial
                # disparaba UserStartedSpeaking (saludo cortado a la mitad).
                if not _half_duplex:
                    await websocket.send_json({"event": "clear", "streamSid": stream_id})
                    play["fin"] = 0.0
            elif t == "ConversationText":
                texto = ev.get("content", "")
                if ev.get("role") == "user":
                    result.transcript.append((time.time(), "Deudor", texto))
                    await _subtitulo("user", texto)
                    espera_resp["on"] = True
                    espera_resp["t_turno"] = time.time()
                    espera_resp["empujones"] = 0   # hubo dialogo: contador a cero
                    lat["turno"] += 1
                    lat["t_eot"] = time.time()
                    # Acumulado, no por turno suelto (portado de
                    # voice_pipecat:88-96): una locucion de buzon partida en dos
                    # transcripciones ("deje su mensaje" / "despues del tono") no
                    # matcheaba evaluando cada una por separado.
                    vm_acum["t"] = (vm_acum["t"] + " " + texto)[-400:]
                    if _VOICEMAIL_LIVE_RE.search(vm_acum["t"]):
                        pedir_colgar(f"buzon en vivo: {texto[:60]!r}")
                else:
                    result.transcript.append((time.time(), "ARIA", texto))
                    await _subtitulo("agent", texto)
            elif t == "FunctionCallRequest":
                for f in ev.get("functions", []):
                    if f.get("client_side", True):
                        _bg(ejecutar_tool(dg, f))
            elif t == "LatencyReport":
                # Desglose oficial por turno (segundos): stt / ttt_* (LLM) / tts.
                logger.info("[agent][lat] deepgram %s",
                            {k: v for k, v in ev.items() if k != "type"})
            elif t == "SettingsApplied":
                logger.info("[agent] SettingsApplied a +%.0f ms del arranque del bridge",
                            (time.time() - t_conn) * 1000)
            elif t in ("Error", "Warning", "InjectionRefused"):
                logger.log(logging.ERROR if t == "Error" else logging.WARNING,
                           "[agent] Deepgram %s: %s", t, ev)
                if t == "Error":
                    pedir_colgar("deepgram error")
                    return

    dg = None
    tareas = [asyncio.create_task(twilio_a_dg())]   # leer YA: que nada se encole
    try:
        dg = await conectar
        logger.info("[agent] conectado a Deepgram en %.0f ms", (time.time() - t_conn) * 1000)
        await dg.send(json.dumps(_settings(prompt, greeting, voz, keyterms, modo_recepcion,
                                           listen_cfg, temperature)))
        dg_box["ws"] = dg
        listo.set()
        if descartado["frames"]:
            logger.info("[agent][lat] descartados %d ms de audio pre-sesion (no envenenan el STT)",
                        descartado["frames"] * 20)
        tareas += [asyncio.create_task(dg_a_twilio(dg)),
                   asyncio.create_task(watchdogs()),
                   asyncio.create_task(empujar_si_mudo()),
                   asyncio.create_task(colgar.wait())]
        await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        if colgar.is_set():
            logger.info("[agent] colgando call=%s motivo=%s", call_sid, motivo["v"])
    except Exception:
        logger.exception("[agent] bridge fallo call=%s", call_sid)
    finally:
        if dtmf_timer.get("t"):
            dtmf_timer["t"].cancel()
        for x in list(tareas) + list(tareas_bg):
            x.cancel()
        if dg is not None:
            try:
                await dg.close()
            except Exception:
                pass
        # Colgado garantizado: cerrar el stream termina la llamada con el TwiML
        # actual, pero el update REST la mata aunque el TwiML cambie o el WS
        # quede zombie — y corta la facturacion ya. Solo cuando decidimos
        # nosotros (si colgo el cliente, la llamada ya esta completed).
        if colgar.is_set() and motivo["v"] != "twilio stop" and call_sid.startswith("CA"):
            def _rest_hangup():
                try:
                    from twilio.rest import Client
                    Client(os.getenv("TWILIO_ACCOUNT_SID", ""),
                           os.getenv("TWILIO_AUTH_TOKEN", "")).calls(call_sid).update(status="completed")
                except Exception:
                    logger.info("[agent] REST hangup no aplico (llamada ya terminada)")
            try:
                await asyncio.get_event_loop().run_in_executor(None, _rest_hangup)
            except Exception:
                pass

    result.ended_at = time.time()
    result.duration_seconds = int(result.ended_at - result.started_at)
    # En recepcion, identificar_cliente ya actualizo el mapping en Mongo con el
    # debtor_id — el ws handler relee el mapping en el post-call.
    return result
