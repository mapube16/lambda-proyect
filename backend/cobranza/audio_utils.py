import audioop
import io
import wave
from typing import Tuple


def parse_sample_rate_from_content_type(content_type: str | None) -> int | None:
    """Parse sample rate from values like 'audio/l16;rate=24000'."""
    if not content_type:
        return None

    parts = [p.strip() for p in content_type.split(";")]
    for part in parts[1:]:
        if part.startswith("rate="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return None
    return None


def pcm16_mono_resample(pcm16_mono: bytes, in_rate: int, out_rate: int) -> bytes:
    """Resample raw 16-bit mono PCM using stdlib audioop."""
    if in_rate == out_rate:
        return pcm16_mono

    converted, _state = audioop.ratecv(
        pcm16_mono,
        2,  # width bytes (16-bit)
        1,  # mono
        in_rate,
        out_rate,
        None,
    )
    return converted


def pcm16_to_mulaw(pcm16_mono: bytes) -> bytes:
    """Convert 16-bit mono PCM to 8-bit μ-law (PCMU)."""
    return audioop.lin2ulaw(pcm16_mono, 2)


def wav_bytes_from_pcm16(pcm16_mono: bytes, sample_rate: int) -> bytes:
    """Wrap raw 16-bit mono PCM into a RIFF/WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_mono)
    return buf.getvalue()


def pcm16_from_wav_bytes(wav_bytes: bytes) -> Tuple[bytes, int]:
    """Extract raw 16-bit mono PCM + sample rate from a WAV file."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        if channels != 1:
            raise ValueError(f"Expected mono WAV, got {channels} channels")
        if sampwidth != 2:
            raise ValueError(f"Expected 16-bit WAV, got sampwidth={sampwidth}")
        frames = wf.readframes(wf.getnframes())
    return frames, framerate
