"""Ollama provider for fully local model inference.

Uses the Ollama REST API (http://localhost:11434) to run models locally
without any external API calls.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator
from uuid import uuid4

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
        transport=None,
    ):
        import httpx

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout, transport=transport)

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

    def format_tool_result(self, tool_use_id: str, content: list[dict]) -> dict:
        text = "\n".join(
            str(block.get("text", ""))
            if block.get("type") == "text"
            else json.dumps(block)
            for block in content
        )
        return {
            "role": "tool",
            "content": text or "Done.",
            "tool_call_id": tool_use_id,
        }

    def format_user_message(self, content: Any) -> ProviderMessage:
        return ProviderMessage(role="user", content=content)

    def format_assistant_message(self, response: ModelResponse) -> ProviderMessage:
        text = "\n".join(block.text for block in response.content if block.type == "text")
        tool_calls = []
        for block in response.content:
            if block.type == "tool_use" and block.tool_call:
                tool_calls.append(
                    {
                        "id": block.tool_call.id,
                        "type": "function",
                        "function": {
                            "name": block.tool_call.name,
                            "arguments": block.tool_call.input,
                        },
                    }
                )
        message: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return ProviderMessage(role="assistant", content=message)

    @staticmethod
    def _tool_arguments(value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

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

    def _build_messages(
        self, system: str | None, messages: list[ProviderMessage]
    ) -> list[dict]:
        result: list[dict] = []
        if system:
            result.append({"role": "system", "content": system})
        for message in messages:
            if message.role == "assistant" and isinstance(message.content, dict):
                result.append(message.content)
            elif message.role == "tool_result":
                values = message.content if isinstance(message.content, list) else [message.content]
                result.extend(value for value in values if isinstance(value, dict))
            else:
                result.append(self._format_message(message))
        return result

    async def stream_message(
        self,
        model: str,
        system: str | None,
        messages: list[ProviderMessage],
        tools: list[ToolSchema],
        max_tokens: int = 8192,
    ) -> AsyncIterator[StreamEvent]:
        import httpx

        payload: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(system, messages),
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = self._format_tools(tools)

        text_started = False
        text_index = 0
        next_index = 1
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
                    content = msg.get("content", "")
                    tool_calls = msg.get("tool_calls", [])

                    if content:
                        if not text_started:
                            text_started = True
                            yield StreamEvent(
                                type="content_block_start",
                                index=text_index,
                                block_type="text",
                            )
                        yield StreamEvent(
                            type="content_block_delta",
                            index=text_index,
                            delta_type="text_delta",
                            text=content,
                        )

                    if tool_calls and text_started:
                        yield StreamEvent(type="content_block_stop", index=text_index)
                        text_started = False
                    for tool_call in tool_calls:
                        function = tool_call.get("function", {})
                        block_index = next_index
                        next_index += 1
                        tool_id = tool_call.get("id") or uuid4().hex
                        arguments = self._tool_arguments(function.get("arguments", {}))
                        yield StreamEvent(
                            type="content_block_start",
                            index=block_index,
                            block_type="tool_use",
                            tool_name=function.get("name", ""),
                            tool_id=tool_id,
                        )
                        yield StreamEvent(
                            type="content_block_delta",
                            index=block_index,
                            delta_type="input_json_delta",
                            text=json.dumps(arguments),
                        )
                        yield StreamEvent(type="content_block_stop", index=block_index)

                    if data.get("done"):
                        if text_started:
                            yield StreamEvent(type="content_block_stop", index=text_index)
                            text_started = False
                        yield StreamEvent(
                            type="usage",
                            usage={
                                "input_tokens": data.get("prompt_eval_count", 0),
                                "output_tokens": data.get("eval_count", 0),
                            },
                        )
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
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(system, messages),
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
                        input=self._tool_arguments(
                            tc.get("function", {}).get("arguments", {})
                        ),
                    ),
                )
            )

        return ModelResponse(
            content=blocks,
            stop_reason="tool_use" if tool_calls else "end_turn",
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
        )
