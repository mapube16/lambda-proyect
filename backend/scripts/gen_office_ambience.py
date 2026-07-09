"""Genera (UNA VEZ) un lecho de ruido de oficina sutil como PCM crudo mono 24kHz
(el audio_out_sample_rate del pipeline de voz). Se commitea como asset estatico
y lo reproduce OfficeAmbienceMixer por debajo de la voz de ARIA (call center feel).

Todo sintetico con numpy — sin descargar clips ni dependencias de sistema.
Receta: room tone (ruido browniano pasa-bajos = zumbido de HVAC/aire) + tecleo
ocasional + murmullo lejano muy tenue. RMS bajo a proposito; el volumen final
lo controla el mixer (~0.15), esto es solo la textura.

Salida: backend/static/voice/office_ambience.pcm  (int16 LE, mono, 24000 Hz)
"""
import os
import numpy as np

SR = 24000
DUR = 20.0  # segundos; loopea
OUT = os.path.join(os.path.dirname(__file__), "..", "static", "voice", "office_ambience.pcm")
rng = np.random.default_rng(7)
n = int(SR * DUR)


def _lowpass(x: np.ndarray, alpha: float) -> np.ndarray:
    """IIR de 1 polo (suave, barato). alpha bajo = mas grave."""
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += alpha * (x[i] - acc)
        y[i] = acc
    return y


# ── Room tone: ruido browniano (cumsum de blanco) pasa-bajos = zumbido de fondo
white = rng.standard_normal(n)
brown = np.cumsum(white)
brown -= np.linspace(brown[0], brown[-1], n)  # quita la deriva DC
room = _lowpass(brown, 0.0008)
room /= (np.max(np.abs(room)) + 1e-9)
room *= 0.35

# ── Aire/ambiente medio: blanco pasa-bajos suave, muy tenue
air = _lowpass(rng.standard_normal(n), 0.02)
air /= (np.max(np.abs(air)) + 1e-9)
air *= 0.06

# ── Tecleo ocasional: rafagas cortas de ruido pasa-altos con decaimiento rapido
keys = np.zeros(n)
t = 0
while t < n:
    t += int(rng.uniform(0.25, 1.6) * SR)  # cada 0.25-1.6s
    if t >= n:
        break
    for _ in range(int(rng.integers(1, 4))):  # pequenas rafagas de teclas
        pos = t + int(rng.uniform(0, 0.15) * SR)
        if pos >= n:
            break
        length = int(rng.uniform(0.004, 0.012) * SR)
        env = np.exp(-np.linspace(0, 6, length))
        click = rng.standard_normal(length) * env
        keys[pos:pos + len(click)] += click[: n - pos] * rng.uniform(0.15, 0.4)

# ── Murmullo lejano: ruido banda-media modulado en amplitud (voces indistintas)
murmur = _lowpass(rng.standard_normal(n), 0.05)
mod = 0.5 + 0.5 * np.sin(2 * np.pi * 0.15 * np.arange(n) / SR + rng.uniform(0, 6))
murmur = murmur * mod
murmur /= (np.max(np.abs(murmur)) + 1e-9)
murmur *= 0.05

mix = room + air + keys + murmur

# Crossfade de 0.4s entre el final y el inicio para un loop sin costura
xf = int(0.4 * SR)
head = mix[:xf].copy()
tail = mix[-xf:].copy()
ramp = np.linspace(0, 1, xf)
mix[:xf] = tail * (1 - ramp) + head * ramp
mix = mix[:-xf]

# Normaliza a un pico moderado y convierte a int16
mix /= (np.max(np.abs(mix)) + 1e-9)
mix *= 0.6
pcm = np.clip(mix * 32767, -32768, 32767).astype("<i2")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
pcm.tofile(OUT)
print(f"guardado: {OUT} ({os.path.getsize(OUT)} bytes, {len(pcm)/SR:.1f}s @ {SR}Hz mono)")
