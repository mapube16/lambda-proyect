"""voz_comun.py — piezas de voz SIN dependencias de pipecat.

CallResult, el regex de buzon en vivo, documento_base y keyterms_llamada
las comparten el pipeline pipecat y el motor Deepgram Voice Agent. Viven
aqui para que voice_agent.py (y sus scripts de chequeo) no arrastren el
import de pipecat/google.genai solo por un dataclass.
"""
import re
import time
from dataclasses import dataclass, field


@dataclass
class CallResult:
    """Data collected during the call for post-call processing."""
    call_sid: str = ""
    duration_seconds: int = 0
    transcript: list = field(default_factory=list)  # [(timestamp, speaker, text)]
    started_at: float = 0.0
    ended_at: float = 0.0
    engine: str = "pipecat-telnyx-gemini-live"   # etiqueta en historial_llamadas
    end_reason: str = ""                          # por que colgo (end_call/watchdog)
    _bot_buffer: str = field(default="", repr=False)
    _bot_buffer_ts: float = field(default=0.0, repr=False)

    def flush_bot_buffer(self):
        """Flush accumulated bot tokens into a single transcript entry."""
        if self._bot_buffer.strip():
            self.transcript.append((self._bot_buffer_ts, "ARIA", self._bot_buffer.strip()))
            self._bot_buffer = ""

    @property
    def full_transcript(self) -> str:
        self.flush_bot_buffer()
        lines = []
        for _, speaker, text in sorted(self.transcript, key=lambda x: x[0]):
            lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    @property
    def user_turn_count(self) -> int:
        return sum(1 for _, speaker, _ in self.transcript if speaker == "Deudor")


# Frases INEQUIVOCAS de contestador/buzon (lo que dice la MAQUINA al contestar).
_VOICEMAIL_LIVE_RE = re.compile(
    r"buz[oó]n de voz|correo de voz|contestador|"
    r"dej[ae] (su|tu) mensaje|dejar (su|tu) mensaje|grab[ae]r? (su|el) mensaje|"
    r"despu[eé]s (del|de escuchar el) tono|al (escuchar|o[ií]r) el tono|"
    r"tecla numeral|lleg[oó] al tiempo l[ií]mite|"
    r"para [a-záéíóúü ]{2,30}marque|"
    # Minado de 372 transcripts reales (09-ago): las familias que se escapaban.
    # Los menus con "presiona X" (52 apariciones) solo cubriamos con "marque";
    # "excedido el tiempo de grabacion" = ARIA ya le grabo un mensaje entero.
    r"presion[ae] (uno|dos|tres|cuatro|cinco|numeral|la tecla)|"
    r"excedido el tiempo|servicio de contestador|"
    r"dej[ae]s? (tu|su) nombre|responde despu[eé]s del tono|"
    r"no se encuentra disponible|no est[aá] disponible en este momento|"
    r"el n[uú]mero que (usted )?marc[oó]",
    re.IGNORECASE,
)


def documento_base(stored) -> str:
    """Parte comparable de un documento: digitos ANTES del guion. ~40% de los
    documentos DPG son NITs con digito de verificacion ('801001470-9') y el
    cliente no lo dice/marca — se compara solo la base. Cedulas sin guion se
    comparan completas. (Compartido por el IVR DTMF y identificar_cliente.)"""
    s = str(stored or "")
    s = s.split("-")[0] if "-" in s else s
    return "".join(c for c in s if c.isdigit())

def keyterms_llamada(debtor: dict) -> list:
    """Vocabulario a reforzar en el STT para ESTA llamada: nombre del deudor,
    aseguradora, y el vocabulario minado de 372 transcripts reales. Anclar
    estos terminos reduce los inventos del STT en audio telefonico ruidoso."""
    base = [
        "alo", "si", "no", "bueno", "senora", "senor", "gracias", "cupon",
        "link", "poliza", "pago", "cuota", "pesos", "ya pague", "ya lo pague",
        "no tengo plata", "no puedo pagar", "manana", "mas tarde", "asesor",
        "numero equivocado", "de una", "hasta luego", "buenos dias",
    ]
    for campo in ("nombre", "aseguradora_nombre"):
        for w in str(debtor.get(campo) or "").split():
            w = "".join(c for c in w if c.isalpha())
            if len(w) > 2:
                base.append(w)
    # dedup preservando orden
    vistos, out = set(), []
    for t in base:
        k = t.lower()
        if k not in vistos:
            vistos.add(k)
            out.append(t)
    return out
