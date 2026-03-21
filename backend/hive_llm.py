"""
hive_llm.py — OpenRouter LLMProvider for aden-hive/hive GraphExecutor.

Implements framework.llm.provider.LLMProvider using the openai SDK
pointed at OpenRouter, so we don't need litellm (which has a version
conflict with openai 1.12 installed on this machine).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from framework.llm.provider import LLMProvider, LLMResponse, Tool
from framework.llm.stream_events import (
    FinishEvent,
    StreamErrorEvent,
    StreamEvent,
    TextDeltaEvent,
    TextEndEvent,
    ToolCallEvent,
)

logger = logging.getLogger(__name__)


def _tool_to_openai(tool: Tool) -> dict:
    """Convert Hive Tool → OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters or {"type": "object", "properties": {}},
        },
    }


def _build_messages(messages: list[dict], system: str) -> list[dict]:
    """Prepend system message if provided."""
    result = []
    if system:
        result.append({"role": "system", "content": system})
    result.extend(messages)
    return result


class OpenRouterProvider(LLMProvider):
    """
    LLM provider that hits OpenRouter (openai-compatible endpoint)
    using the openai SDK directly.

    No litellm dependency — works with openai 1.x.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o-mini",
        base_url: str = "https://openrouter.ai/api/v1",
        max_output_tokens: int = 4096,
    ):
        from openai import AsyncOpenAI
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    # ── sync complete() — required by base class ────────────────────────────

    def complete(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[Tool] | None = None,
        max_tokens: int = 1024,
        response_format: dict | None = None,
        json_mode: bool = False,
        max_retries: int | None = None,
    ) -> LLMResponse:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.acomplete(messages, system, tools, max_tokens,
                               response_format, json_mode, max_retries)
            )
        finally:
            loop.close()

    # ── async complete() ────────────────────────────────────────────────────

    async def acomplete(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[Tool] | None = None,
        max_tokens: int = 1024,
        response_format: dict | None = None,
        json_mode: bool = False,
        max_retries: int | None = None,
    ) -> LLMResponse:
        oai_messages = _build_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = [_tool_to_openai(t) for t in tools]
        if json_mode or (response_format and response_format.get("type") == "json_object"):
            kwargs["response_format"] = {"type": "json_object"}

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        content = choice.message.content or ""
        return LLMResponse(
            content=content,
            model=resp.model,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
            stop_reason=choice.finish_reason or "",
        )

    # ── async stream() — yields StreamEvents ───────────────────────────────

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[Tool] | None = None,
        max_tokens: int = 2000,
    ) -> AsyncIterator[StreamEvent]:
        oai_messages = _build_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": oai_messages,
            "max_tokens": min(max_tokens, self._max_output_tokens),
            "stream": True,
        }
        if tools:
            kwargs["tools"] = [_tool_to_openai(t) for t in tools]

        # Accumulate tool call deltas keyed by index
        tc_accum: dict[int, dict] = {}  # idx → {id, name, arguments_str}
        text_snapshot = ""
        input_tokens = 0
        output_tokens = 0
        stop_reason = ""
        model_name = self._model

        try:
            async with await self._client.chat.completions.create(**kwargs) as stream:
                async for chunk in stream:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta
                    finish = chunk.choices[0].finish_reason
                    if chunk.model:
                        model_name = chunk.model

                    # Text delta
                    if delta.content:
                        text_snapshot += delta.content
                        yield TextDeltaEvent(
                            content=delta.content, snapshot=text_snapshot
                        )

                    # Tool call deltas
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tc_accum:
                                tc_accum[idx] = {
                                    "id": tc_delta.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc_delta.id:
                                tc_accum[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tc_accum[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tc_accum[idx]["arguments"] += tc_delta.function.arguments

                    if finish:
                        stop_reason = finish

            # Yield accumulated tool calls
            for tc in tc_accum.values():
                try:
                    tool_input = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse tool call args for %s: %r",
                        tc["name"], tc["arguments"]
                    )
                    tool_input = {}
                yield ToolCallEvent(
                    tool_use_id=tc["id"],
                    tool_name=tc["name"],
                    tool_input=tool_input,
                )

        except Exception as exc:
            logger.error("OpenRouter stream error: %s", exc)
            yield StreamErrorEvent(error=str(exc), recoverable=False)
            return

        if text_snapshot:
            yield TextEndEvent(full_text=text_snapshot)

        yield FinishEvent(
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model_name,
        )
