"""Contract tests for local Ollama model and tool-call translation."""

import json

import httpx
import pytest

from backend.apps.agents.providers.base import ProviderMessage, ToolSchema
from backend.apps.agents.providers.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_provider_executes_and_round_trips_tool_calls():
    requests: list[dict] = []
    responses = [
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "Read",
                            "arguments": {"file_path": "README.md"},
                        },
                    }
                ],
            },
            "prompt_eval_count": 12,
            "eval_count": 4,
            "done": True,
        },
        {
            "message": {"role": "assistant", "content": "README inspected."},
            "prompt_eval_count": 20,
            "eval_count": 5,
            "done": True,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    provider = OllamaProvider(transport=httpx.MockTransport(handler))
    tools = [
        ToolSchema(
            name="Read",
            description="Read a file",
            input_schema={
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
        )
    ]

    first = await provider.create_message(
        "qwen2.5", "You are an agent", [ProviderMessage("user", "Read it")], tools
    )
    assert first.stop_reason == "tool_use"
    assert first.content[0].tool_call.name == "Read"
    assert first.usage == {"input_tokens": 12, "output_tokens": 4}

    history = [
        ProviderMessage("user", "Read it"),
        provider.format_assistant_message(first),
        ProviderMessage(
            "tool_result",
            [provider.format_tool_result("call-1", [{"type": "text", "text": "contents"}])],
        ),
    ]
    second = await provider.create_message("qwen2.5", None, history, tools)

    assert second.content[0].text == "README inspected."
    assert requests[1]["messages"][1]["tool_calls"][0]["function"]["name"] == "Read"
    assert requests[1]["messages"][2]["role"] == "tool"
    await provider.close()


@pytest.mark.asyncio
async def test_ollama_stream_emits_balanced_blocks_and_normalized_usage():
    chunks = "\n".join(
        [
            json.dumps({"message": {"role": "assistant", "content": "Hel"}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": "lo"}, "done": False}),
            json.dumps(
                {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "prompt_eval_count": 7,
                    "eval_count": 2,
                }
            ),
        ]
    )
    provider = OllamaProvider(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text=chunks))
    )

    events = [
        event
        async for event in provider.stream_message(
            "qwen2.5", None, [ProviderMessage("user", "Hello")], []
        )
    ]

    assert [event.type for event in events] == [
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "usage",
        "message_stop",
    ]
    assert events[-2].usage == {"input_tokens": 7, "output_tokens": 2}
    await provider.close()
