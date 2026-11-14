"""office_mixer_mulaw.py — ruido de oficina para el motor Deepgram (mulaw 8k).

El mixer original (office_mixer.py) suma PCM lineal a 24 kHz, que es lo que
emitia el pipeline de pipecat. El Voice Agent de Deepgram entrega mulaw 8 kHz
ya comprimido, asi que no se puede sumar directo: hay que decodificar, mezclar
y recodificar. Esto hace exactamente eso, trama por trama (20 ms).

El lecho de ambiente (static/voice/office_ambience.pcm) esta grabado a 24 kHz,
asi que se diezma 3:1 una sola vez al arrancar y queda cacheado a 8 kHz.

Config por tenant (igual que el viejo):
  office_ambience_enabled  bool, default True
  office_ambience_volume   0..1, default 0.35. A 0.15 (el default del mixer
                           viejo de 24 kHz) no se oye en la linea telefonica.
"""
import audioop
import logging
import os

logger = logging.getLogger("cobranza.office_mixer_mulaw")

_RUTA = os.path.join(os.path.dirname(__file__), "..", "static", "voice", "office_ambience.pcm")


class AmbienteMulaw:
    """Mezcla un lecho de ambiente bajo la voz, en mulaw 8 kHz."""

    def __init__(self, volume: float = 0.18, ruta: str = _RUTA):
        self.volume = max(0.0, min(1.0, float(volume)))
        self._bed = b""      # PCM lineal 16-bit a 8 kHz
        self._pos = 0
        self.activo = False
        if self.volume <= 0:
            return
        try:
            with open(ruta, "rb") as f:
                pcm24 = f.read()
            # 24 kHz -> 8 kHz (ratecv maneja el filtrado; mono, 2 bytes/muestra)
            pcm8, _ = audioop.ratecv(pcm24, 2, 1, 24000, 8000, None)
            self._bed = pcm8
            self.activo = len(pcm8) > 0
        except Exception as exc:
            logger.warning("[ambiente] no pude cargar el lecho: %s", exc)
            self.activo = False

    def mezclar(self, mulaw: bytes) -> bytes:
        """Devuelve la trama con el ambiente debajo. Si algo falla, la original."""
        if not self.activo or not mulaw:
            return mulaw
        try:
            voz = audioop.ulaw2lin(mulaw, 2)          # mulaw -> PCM16
            n = len(voz)
            # El lecho es un loop: se recorre circular
            if self._pos + n > len(self._bed):
                cacho = self._bed[self._pos:] + self._bed[:(self._pos + n) % len(self._bed)]
                self._pos = (self._pos + n) % len(self._bed)
            else:
                cacho = self._bed[self._pos:self._pos + n]
                self._pos += n
            if len(cacho) != n:
                return mulaw
            cacho = audioop.mul(cacho, 2, self.volume)
            return audioop.lin2ulaw(audioop.add(voz, cacho, 2), 2)
        except Exception:
            return mulaw


def crear(tenant_config: dict):
    """Devuelve un AmbienteMulaw listo, o None si el tenant lo tiene apagado."""
    cobr = tenant_config.get("cobranza") or {}
    hab = cobr.get("office_ambience_enabled",
                   tenant_config.get("office_ambience_enabled", True))
    if not bool(hab):
        return None
    vol = cobr.get("office_ambience_volume",
                   tenant_config.get("office_ambience_volume", 0.18))
    amb = AmbienteMulaw(volume=float(vol or 0.18))
    return amb if amb.activo else None
