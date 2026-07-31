"""End-to-end native provider loop regression tests."""

import pytest

from backend.apps.agents.agent_manager import AgentManager
from backend.apps.agents.models import AgentConfig
from backend.apps.agents.providers.base import (
    ContentBlock,
    ModelResponse,
    ProviderMessage,
    StreamEvent,
)


class StreamingFakeProvider:
    def __init__(self):
        self.tools = []
        self.closed = False

    def format_user_message(self, content):
        return ProviderMessage(role="user", content=content)

    def format_assistant_message(self, response: ModelResponse):
        text = "".join(block.text for block in response.content if block.type == "text")
        return ProviderMessage(role="assistant", content=text)

    def format_tool_result(self, tool_use_id, content):
        return {"role": "tool", "tool_call_id": tool_use_id, "content": str(content)}

    async def stream_message(self, *, tools, **_kwargs):
        self.tools = tools
        yield StreamEvent(type="content_block_start", index=0, block_type="text")
        yield StreamEvent(
            type="content_block_delta",
            index=0,
            delta_type="text_delta",
            text="Streaming works",
        )
        yield StreamEvent(type="content_block_stop", index=0)
        yield StreamEvent(
            type="usage", usage={"input_tokens": 12, "output_tokens": 3}
        )
        yield StreamEvent(type="message_stop")

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_native_loop_streams_persists_and_closes_provider(tmp_path, monkeypatch):
    import backend.apps.agents.providers.registry as registry

    provider = StreamingFakeProvider()
    monkeypatch.setattr(registry, "create_provider", lambda *_args, **_kwargs: provider)
    manager = AgentManager()
    session = await manager.launch_agent(
        AgentConfig(
            name="Provider loop",
            model="test-model",
            provider="test-provider",
            allowed_tools=["Read"],
            target_directory=str(tmp_path),
        )
    )

    await manager.send_message(session.id, "Run the end-to-end loop")
    await manager.tasks[session.id]

    assert session.status == "completed"
    assert [message.role for message in session.messages] == ["user", "assistant"]
    assert session.messages[-1].content == "Streaming works"
    assert session.tokens == {"input": 12, "output": 3}
    tool_schemas = {tool.name: tool for tool in provider.tools}
    assert "Read" in tool_schemas
    assert tool_schemas["Read"].input_schema["required"] == ["file_path"]
    assert all(tool.input_schema for tool in provider.tools)
    assert provider.closed is True
