"""OfficeAmbienceMixer — lecho de ruido de oficina bajo la voz de ARIA.

Igual que SoundfileMixer de Pipecat pero sin la dependencia de sistema
`soundfile`/`libsndfile`: carga un PCM CRUDO mono int16 (generado por
scripts/gen_office_ambience.py al mismo sample rate del output, 24kHz) y lo
mezcla en loop. El transporte lo llama continuamente (with_mixer en
base_output), asi que el ambiente suena tambien en los silencios de ARIA.
"""
import numpy as np

from pipecat.audio.mixers.base_audio_mixer import BaseAudioMixer
from pipecat.frames.frames import (
    MixerControlFrame,
    MixerEnableFrame,
    MixerUpdateSettingsFrame,
)


class OfficeAmbienceMixer(BaseAudioMixer):
    def __init__(self, pcm_path: str, *, volume: float = 0.15, expected_sample_rate: int = 24000):
        self._pcm_path = pcm_path
        self._volume = float(volume)
        self._expected_sr = expected_sample_rate
        self._bed: np.ndarray = np.zeros(0, dtype=np.int16)
        self._pos = 0
        self._mixing = True

    async def start(self, sample_rate: int):
        # El bed se genera al sample rate del output; si no coincide, se
        # deshabilita (mejor sin ambiente que con ambiente a velocidad/tono
        # equivocado). No resampleamos aqui — mantener el mixer barato.
        try:
            bed = np.fromfile(self._pcm_path, dtype="<i2")
        except Exception:
            bed = np.zeros(0, dtype=np.int16)
        if sample_rate != self._expected_sr or bed.size == 0:
            self._mixing = False
            self._bed = np.zeros(0, dtype=np.int16)
        else:
            self._bed = bed

    async def stop(self):
        pass

    async def process_frame(self, frame: MixerControlFrame):
        if isinstance(frame, MixerEnableFrame):
            self._mixing = frame.enable
        elif isinstance(frame, MixerUpdateSettingsFrame):
            vol = frame.settings.get("volume")
            if vol is not None:
                self._volume = float(vol)

    async def mix(self, audio: bytes) -> bytes:
        if not self._mixing or self._bed.size == 0 or self._volume <= 0:
            return audio
        voice = np.frombuffer(audio, dtype=np.int16)
        chunk = len(voice)
        if chunk == 0:
            return audio
        # Toma chunk del bed en loop (envuelve al final).
        end = self._pos + chunk
        if end <= self._bed.size:
            bed_chunk = self._bed[self._pos:end]
            self._pos = end % self._bed.size
        else:
            first = self._bed[self._pos:]
            rest = self._bed[: chunk - first.size]
            bed_chunk = np.concatenate((first, rest))
            self._pos = chunk - first.size
        mixed = np.clip(
            voice.astype(np.int32) + (bed_chunk.astype(np.float32) * self._volume).astype(np.int32),
            -32768, 32767,
        ).astype(np.int16)
        return mixed.tobytes()
