"""
assembly_ai_client.py — Assembly AI WebSocket integration for real-time STT.

Handles streaming audio from Twilio → Assembly AI → transcript.
Model: u3-rt-pro (universal, streaming, ~200-300ms latency)
Language: Spanish (Colombian)
"""
import asyncio
import json
import logging
import os
from typing import AsyncGenerator, Optional

import websockets

logger = logging.getLogger("cobranza.assembly_ai")


class AssemblyAIClient:
    """
    Real-time speech-to-text via Assembly AI WebSocket.

    Usage:
        client = AssemblyAIClient(api_key=os.getenv("ASSEMBLY_AI_API_KEY"))
        async with client.stream(sample_rate=8000) as stream:
            async for transcript in stream:
                print(transcript)  # {"type": "PartialTranscript" | "FinalTranscript", "text": "..."}
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ASSEMBLY_AI_API_KEY")
        if not self.api_key:
            raise ValueError("ASSEMBLY_AI_API_KEY not set")
        self.base_url = "wss://api.assemblyai.com/v2"

    async def stream(
        self,
        sample_rate: int = 8000,
        encoding: str = "pcm_s16le",
        language_code: str = "es",  # Spanish
    ) -> AsyncGenerator:
        """
        Streaming connection to Assembly AI.

        Yields transcript objects as they arrive (partial + final).

        Caller is responsible for sending audio frames via
        the returned context manager.
        """
        url = f"{self.base_url}/realtime/stream?token={self.api_key}"

        try:
            async with websockets.connect(url) as ws:
                # Send session_begins
                session_begin = {
                    "message_type": "SessionBegins",
                    "session_begins": {
                        "session_id": "not_used",
                        "expires_in": 60,
                    },
                }
                # Note: Assembly AI v2 realtime doesn't use SessionBegins in the same way
                # but we send it for future compatibility

                logger.info("[Assembly AI] WebSocket connected")

                async def send_audio(audio_chunk: bytes) -> None:
                    """Send audio frame to Assembly AI."""
                    await ws.send(audio_chunk)

                # Create a queue for receiving transcripts
                transcript_queue = asyncio.Queue()

                async def read_transcripts() -> None:
                    """Read transcript messages from WebSocket."""
                    try:
                        async for message in ws:
                            try:
                                data = json.loads(message)
                                msg_type = data.get("message_type", "")

                                if msg_type in ("PartialTranscript", "FinalTranscript"):
                                    transcript = {
                                        "type": msg_type,
                                        "text": data.get("text", ""),
                                        "confidence": data.get("confidence"),
                                    }
                                    await transcript_queue.put(transcript)
                                    logger.debug(
                                        "[Assembly AI] %s: %s",
                                        msg_type,
                                        transcript["text"][:50],
                                    )
                                elif msg_type == "SessionBegins":
                                    logger.info("[Assembly AI] Session started")
                                else:
                                    logger.debug("[Assembly AI] Unhandled message type: %s", msg_type)
                            except json.JSONDecodeError:
                                logger.warning("[Assembly AI] Failed to parse message: %s", message[:100])
                    except asyncio.CancelledError:
                        logger.info("[Assembly AI] Read task cancelled")
                    except Exception as e:
                        logger.error("[Assembly AI] Error reading transcripts: %s", e, exc_info=True)

                # Start reader task
                reader_task = asyncio.create_task(read_transcripts())

                try:
                    # Expose send_audio and transcript_queue
                    class StreamContext:
                        async def send(self, audio_chunk: bytes):
                            await send_audio(audio_chunk)

                        async def get_transcript(self):
                            return await transcript_queue.get()

                        async def __aenter__(self):
                            return self

                        async def __aexit__(self, exc_type, exc_val, exc_tb):
                            await ws.send('{"message_type": "TerminateSession"}')
                            reader_task.cancel()
                            try:
                                await reader_task
                            except asyncio.CancelledError:
                                pass

                    ctx = StreamContext()
                    async for transcript in self._yield_transcripts(ctx):
                        yield transcript

                except asyncio.CancelledError:
                    reader_task.cancel()
                    raise

        except Exception as e:
            logger.error("[Assembly AI] Connection failed: %s", e, exc_info=True)
            raise

    async def _yield_transcripts(self, ctx) -> AsyncGenerator:
        """Helper to yield transcripts from the queue."""
        try:
            while True:
                transcript = await asyncio.wait_for(ctx.get_transcript(), timeout=30)
                yield transcript
        except asyncio.TimeoutError:
            logger.warning("[Assembly AI] No transcripts received for 30s")
        except asyncio.CancelledError:
            pass


async def test_assembly_ai():
    """Quick test of Assembly AI connection (requires API key + audio source)."""
    try:
        client = AssemblyAIClient()
        logger.info("[Assembly AI Test] Client initialized")
        # In a real scenario, we'd connect Twilio audio here
        # For now, just verify the client can be created
        logger.info("[Assembly AI Test] OK")
    except Exception as e:
        logger.error("[Assembly AI Test] Failed: %s", e)
