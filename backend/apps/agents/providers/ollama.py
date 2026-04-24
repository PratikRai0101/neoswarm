"""Ollama provider for fully local model inference.

Uses the Ollama REST API (http://localhost:11434) to run models locally
without any external API calls.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from backend.apps.agents.providers.base import (
    BaseProvider,
    ContentBlock,
    ModelResponse,
    ProviderMessage,
    StreamEvent,
    ToolCall,
    ToolSchema,
)

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaProvider(BaseProvider):
    """Provider adapter for local Ollama models."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        timeout: float = 120.0,
    ):
        import httpx

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self.client.aclose()

    async def _post(self, path: str, data: dict) -> dict:
        import httpx

        resp = await self.client.post(f"{self.base_url}{path}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def list_models(self) -> list[dict]:
        try:
            data = await self._post("/api/tags", {})
            return data.get("models", [])
        except Exception:
            return []

    def get_model_id(self, short_name: str) -> str:
        return short_name

    def _format_tools(self, tools: list[ToolSchema]) -> list[dict]:
        """Convert tools to Ollama format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    def _format_message(self, msg: ProviderMessage) -> dict:
        """Convert ProviderMessage to Ollama format."""
        content = msg.content
        if isinstance(content, str):
            return {"role": msg.role, "content": content}
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            return {"role": msg.role, "content": "\n".join(text_parts)}
        return {"role": msg.role, "content": str(content)}

    async def stream_message(
        self,
        model: str,
        system: str | None,
        messages: list[ProviderMessage],
        tools: list[ToolSchema],
        max_tokens: int = 8192,
    ) -> AsyncIterator[StreamEvent]:
        import httpx

        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        for msg in messages:
            ollama_messages.append(self._format_message(msg))

        payload: dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = self._format_tools(tools)

        try:
            async with self.client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload, timeout=None
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    msg = data.get("message", {})
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])

                    if content:
                        yield StreamEvent(
                            type="content_block_start",
                            index=0,
                            block_type="text",
                        )
                        yield StreamEvent(
                            type="content_block_delta",
                            index=0,
                            delta_type="text_delta",
                            text=content,
                        )

                    for tc in tool_calls:
                        yield StreamEvent(
                            type="content_block_start",
                            index=0,
                            block_type="tool_use",
                        )
                        yield StreamEvent(
                            type="content_block_delta",
                            index=0,
                            delta_type="input_json_delta",
                            text=json.dumps(tc),
                            tool_name=tc.get("function", {}).get("name", ""),
                            tool_id=tc.get("id", ""),
                        )

                    if data.get("done"):
                        yield StreamEvent(type="message_stop")
        except httpx.HTTPError as e:
            logger.error(f"Ollama streaming error: {e}")
            raise

    async def create_message(
        self,
        model: str,
        system: str | None,
        messages: list[ProviderMessage],
        tools: list[ToolSchema],
        max_tokens: int = 8192,
    ) -> ModelResponse:
        ollama_messages = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        for msg in messages:
            ollama_messages.append(self._format_message(msg))

        payload: dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = self._format_tools(tools)

        data = await self._post("/api/chat", payload)
        msg = data.get("message", {})
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls", [])

        blocks: list[ContentBlock] = []
        if content:
            blocks.append(ContentBlock(type="text", text=content))
        for tc in tool_calls:
            blocks.append(
                ContentBlock(
                    type="tool_use",
                    tool_call=ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("function", {}).get("name", ""),
                        input=tc.get("function", {}).get("arguments", {}),
                    ),
                )
            )

        return ModelResponse(
            content=blocks,
            stop_reason=data.get("done_reason", "end_turn"),
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
        )
