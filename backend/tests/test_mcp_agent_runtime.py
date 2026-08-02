"""Native agent-loop integration tests for MCP tool execution."""

import json
from unittest.mock import AsyncMock

import pytest

from backend.apps.agents.agent_manager import AgentManager
from backend.apps.agents.models import AgentConfig
from backend.apps.agents.providers.base import (
    ContentBlock,
    ModelResponse,
    ProviderMessage,
    StreamEvent,
    ToolCall,
    ToolSchema,
)


class McpStreamingFakeProvider:
    def __init__(self):
        self.tools: list[ToolSchema] = []
        self.closed = False

    def format_user_message(self, content):
        return ProviderMessage(role="user", content=content)

    def format_assistant_message(self, response: ModelResponse):
        return ProviderMessage(
            role="assistant",
            content=[
                {
                    "type": block.type,
                    "text": block.text,
                    "tool": block.tool_call.name if block.tool_call else None,
                }
                for block in response.content
            ],
        )

    def format_tool_result(self, tool_use_id, content):
        return {
            "role": "tool",
            "tool_call_id": tool_use_id,
            "content": content,
        }

    async def stream_message(self, *, messages, tools, **_kwargs):
        self.tools = tools
        has_tool_result = any(message.role == "tool_result" for message in messages)
        if not has_tool_result:
            yield StreamEvent(
                type="content_block_start",
                index=0,
                block_type="tool_use",
                tool_name="mcp__example__lookup",
                tool_id="call-1",
            )
            yield StreamEvent(
                type="content_block_delta",
                index=0,
                delta_type="input_json_delta",
                text=json.dumps({"value": "answer"}),
            )
            yield StreamEvent(type="content_block_stop", index=0)
        else:
            yield StreamEvent(type="content_block_start", index=0, block_type="text")
            yield StreamEvent(
                type="content_block_delta",
                index=0,
                delta_type="text_delta",
                text="MCP worked",
            )
            yield StreamEvent(type="content_block_stop", index=0)
        yield StreamEvent(type="message_stop")

    async def close(self):
        self.closed = True


class FakeMCPClientManager:
    instances: list["FakeMCPClientManager"] = []

    def __init__(self):
        self.servers = {}
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.closed = True

    async def connect_all(self, servers):
        self.servers = servers
        return [
            ToolSchema(
                name="mcp__example__lookup",
                description="Look up a value.",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            )
        ]

    @staticmethod
    def parse_mcp_tool_name(name):
        if name == "mcp__example__lookup":
            return "example", "lookup"
        return None

    async def call_tool(self, server_name, tool_name, arguments):
        self.calls.append((server_name, tool_name, arguments))
        return [{"type": "text", "text": f"lookup:{arguments['value']}"}]


@pytest.mark.asyncio
async def test_native_loop_connects_and_executes_mcp_tools(tmp_path, monkeypatch):
    import backend.apps.agents.mcp_client as mcp_client
    import backend.apps.agents.providers.registry as registry

    provider = McpStreamingFakeProvider()
    FakeMCPClientManager.instances.clear()
    monkeypatch.setattr(registry, "create_provider", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(mcp_client, "MCPClientManager", FakeMCPClientManager)

    manager = AgentManager()
    monkeypatch.setattr(
        manager,
        "_build_mcp_servers",
        AsyncMock(return_value={"example": {"type": "http", "url": "https://example.test/mcp"}}),
    )

    session = await manager.launch_agent(
        AgentConfig(
            name="MCP loop",
            model="test-model",
            provider="test-provider",
            mode="agent",
            allowed_tools=["Read"],
            target_directory=str(tmp_path),
        )
    )

    await manager.send_message(session.id, "Use the connected MCP tool")
    await manager.tasks[session.id]

    assert session.status == "completed"
    assert provider.closed is True
    assert len(FakeMCPClientManager.instances) == 1
    mcp = FakeMCPClientManager.instances[0]
    assert mcp.closed is True
    assert mcp.servers == {"example": {"type": "http", "url": "https://example.test/mcp"}}
    assert mcp.calls == [("example", "lookup", {"value": "answer"})]
    assert any(
        message.role == "tool_result"
        and message.content.get("text") == "lookup:answer"
        for message in session.messages
        if isinstance(message.content, dict)
    )
    assert session.messages[-1].content == "MCP worked"
    schemas = {tool.name: tool for tool in provider.tools}
    assert schemas["mcp__example__lookup"].input_schema["required"] == ["value"]
