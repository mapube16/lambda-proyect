"""
tts_adapter.py — Pluggable TTS providers.

Pattern: Define a TtsProvider interface, implement different backends,
let environment variable choose which one to use.

This makes it trivial to swap TTS providers without touching the orchestrator.
"""
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("cobranza.tts")


class TtsProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def synthesize(self, text: str, language_code: str = "es-CO") -> Optional[bytes]:
        """
        Convert text to audio.

        Args:
            text: Text to synthesize
            language_code: Language (e.g., "es-CO" for Colombian Spanish)

        Returns:
            Audio bytes (MP3, WAV, etc.) or None on error
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass


class GoogleCloudTts(TtsProvider):
    """Google Cloud Text-to-Speech provider."""

    async def synthesize(
        self, text: str, language_code: str = "es-CO"
    ) -> Optional[bytes]:
        from cobranza.google_tts_client import text_to_speech

        return await text_to_speech(text, language_code)

    def name(self) -> str:
        return "google-cloud"


class ElevenLabsTts(TtsProvider):
    """Elevenlabs TTS provider (premium, very natural voices)."""

    async def synthesize(
        self, text: str, language_code: str = "es-CO"
    ) -> Optional[bytes]:
        """
        Synthesize using Elevenlabs API.

        Requires ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID env vars.
        """
        import os

        api_key = os.getenv("ELEVENLABS_API_KEY")
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "default")

        if not api_key:
            logger.error("[ElevenLabs] ELEVENLABS_API_KEY not set")
            return None

        try:
            import httpx

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {"xi-api-key": api_key}
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                logger.debug("[ElevenLabs] Synthesized %d chars", len(text))
                return response.content

        except Exception as e:
            logger.error("[ElevenLabs] Synthesis failed: %s", e)
            return None

    def name(self) -> str:
        return "elevenlabs"


class AzureTts(TtsProvider):
    """Azure Speech Services TTS — Salome (es-CO), cached synthesizer."""

    _synth = None  # Reuse connection for speed

    async def synthesize(
        self, text: str, language_code: str = "es-CO"
    ) -> Optional[bytes]:
        """Returns WAV 8kHz 16-bit mono (no resampling needed for Twilio)."""
        api_key = os.getenv("AZURE_SPEECH_KEY")
        region = os.getenv("AZURE_SPEECH_REGION", "eastus")
        if not api_key:
            logger.error("[Azure TTS] AZURE_SPEECH_KEY not set")
            return None

        try:
            import azure.cognitiveservices.speech as speechsdk

            if AzureTts._synth is None:
                cfg = speechsdk.SpeechConfig(subscription=api_key, region=region)
                cfg.speech_synthesis_voice_name = "es-CO-SalomeNeural"
                cfg.set_speech_synthesis_output_format(
                    speechsdk.SpeechSynthesisOutputFormat.Riff8Khz16BitMonoPcm
                )
                AzureTts._synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)

            result = AzureTts._synth.speak_text_async(text).get()
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info("[Azure TTS] %d chars -> %d bytes (8kHz)", len(text), len(result.audio_data))
                return result.audio_data

            logger.error("[Azure TTS] Failed: %s", result.reason)
            AzureTts._synth = None
            return None

        except Exception as e:
            logger.error("[Azure TTS] Error: %s", e)
            AzureTts._synth = None
            return None

    def name(self) -> str:
        return "azure"


class DeepgramTts(TtsProvider):
    """Deepgram Speak TTS provider (Aura voices).

    Default model is configured via DEEPGRAM_TTS_MODEL (default: aura-2-celeste-es).
    Output is converted to 8kHz μ-law for Twilio Media Streams.
    """

    async def synthesize(
        self, text: str, language_code: str = "es-CO"
    ) -> Optional[bytes]:
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            logger.error("[Deepgram TTS] DEEPGRAM_API_KEY not set")
            return None

        try:
            from cobranza.deepgram_tts_client import speak_mulaw_8k

            audio = await speak_mulaw_8k(text, api_key=api_key)
            logger.info("[Deepgram TTS] %d chars -> %d bytes (mulaw 8k)", len(text), len(audio))
            return audio
        except Exception as e:
            logger.error("[Deepgram TTS] Synthesis failed: %s", e)
            return None

    def name(self) -> str:
        return "deepgram"


class TwilioTts(TtsProvider):
    """Twilio built-in TTS provider (basic but integrated)."""

    async def synthesize(
        self, text: str, language_code: str = "es-CO"
    ) -> Optional[bytes]:
        """
        Twilio TTS is synchronous via REST API.
        For now, return None (can be implemented via Twilio API if needed).
        """
        logger.warning("[Twilio TTS] Not yet implemented")
        return None

    def name(self) -> str:
        return "twilio"


class MockTts(TtsProvider):
    """Mock TTS for testing (returns silent audio)."""

    async def synthesize(
        self, text: str, language_code: str = "es-CO"
    ) -> Optional[bytes]:
        logger.debug("[Mock TTS] Would synthesize: %s", text[:50])
        return b"MOCK_AUDIO_FRAME"

    def name(self) -> str:
        return "mock"


def get_tts_provider() -> TtsProvider:
    """
    Factory function to get the configured TTS provider.

    Reads TTS_PROVIDER env var (default: "google-cloud").

    Options:
    - "google-cloud" → Google Cloud TTS
    - "elevenlabs" → Elevenlabs (premium, very natural)
    - "azure" → Azure Speech Services
    - "deepgram" → Deepgram Speak (Aura voices)
    - "twilio" → Twilio TTS
    - "mock" → Mock (for testing)
    """
    provider_name = os.getenv("TTS_PROVIDER", "google-cloud").lower()

    providers = {
        "google-cloud": GoogleCloudTts(),
        "elevenlabs": ElevenLabsTts(),
        "azure": AzureTts(),
        "deepgram": DeepgramTts(),
        "twilio": TwilioTts(),
        "mock": MockTts(),
    }

    if provider_name not in providers:
        logger.warning(
            "[TTS] Unknown provider '%s', defaulting to google-cloud", provider_name
        )
        provider_name = "google-cloud"

    provider = providers[provider_name]
    logger.info("[TTS] Using provider: %s", provider.name())
    return provider


# ── Usage in voice_orchestrator.py ───────────────────────────────────────────

"""
In voice_orchestrator.py, instead of:

    audio = await text_to_speech(response_text)

Use:

    from cobranza.tts_adapter import get_tts_provider
    tts = get_tts_provider()
    audio = await tts.synthesize(response_text)

Now you can swap providers by just changing TTS_PROVIDER=elevenlabs in .env!
"""
