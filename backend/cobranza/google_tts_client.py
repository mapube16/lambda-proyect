"""
google_tts_client.py — Google Cloud Text-to-Speech integration.

Converts response text to natural Spanish audio.
Uses cloud_tts credentials (base64 encoded in .env).
"""
import base64
import json
import logging
import os
from io import BytesIO
from typing import Optional

logger = logging.getLogger("cobranza.google_tts")


async def text_to_speech(
    text: str,
    language_code: str = "es-CO",  # Colombian Spanish
    voice_name: str = "es-CO-Neural2-A",  # Natural voice
) -> Optional[bytes]:
    """
    Convert text to speech using Google Cloud TTS.

    Returns audio bytes (MP3 or WAV) or None on error.

    Requires GOOGLE_CLOUD_TTS_CREDENTIALS_JSON (base64 encoded) in .env
    """
    try:
        from google.cloud import texttospeech
        from google.oauth2 import service_account
    except ImportError:
        logger.error("[Google TTS] google-cloud-texttospeech not installed")
        return None

    # Load credentials
    creds_b64 = os.getenv("GOOGLE_CLOUD_TTS_CREDENTIALS_JSON")
    if not creds_b64:
        logger.error("[Google TTS] GOOGLE_CLOUD_TTS_CREDENTIALS_JSON not set")
        return None

    try:
        creds_json = base64.b64decode(creds_b64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
    except Exception as e:
        logger.error("[Google TTS] Failed to load credentials: %s", e)
        return None

    try:
        client = texttospeech.TextToSpeechClient(credentials=credentials)

        # Input text
        synthesis_input = texttospeech.SynthesisInput(text=text)

        # Voice config
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )

        # Audio config (MP3 format)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,  # Normal speed
            pitch=0.0,  # Normal pitch
        )

        # Synthesize
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        logger.info(
            "[Google TTS] Synthesized %d chars → %d bytes",
            len(text),
            len(response.audio_content),
        )
        return response.audio_content

    except Exception as e:
        logger.error("[Google TTS] Synthesis failed: %s", e, exc_info=True)
        return None


async def get_available_voices(language_code: str = "es-CO") -> list[dict]:
    """
    List available voices for Spanish (Colombian).

    Returns list of dicts: {"name": "es-CO-Neural2-A", "natural_sample_rate_hertz": 24000, ...}
    """
    try:
        from google.cloud import texttospeech
        from google.oauth2 import service_account
    except ImportError:
        logger.error("[Google TTS] google-cloud-texttospeech not installed")
        return []

    creds_b64 = os.getenv("GOOGLE_CLOUD_TTS_CREDENTIALS_JSON")
    if not creds_b64:
        logger.warning("[Google TTS] Credentials not set")
        return []

    try:
        creds_json = base64.b64decode(creds_b64).decode("utf-8")
        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        client = texttospeech.TextToSpeechClient(credentials=credentials)
        response = client.list_voices(language_code=language_code)

        voices = []
        for voice in response.voices:
            voices.append(
                {
                    "name": voice.name,
                    "ssml_gender": voice.ssml_gender.name,
                    "natural_sample_rate_hertz": voice.natural_sample_rate_hertz,
                }
            )
        logger.info("[Google TTS] Found %d voices for %s", len(voices), language_code)
        return voices
    except Exception as e:
        logger.error("[Google TTS] Failed to list voices: %s", e)
        return []
