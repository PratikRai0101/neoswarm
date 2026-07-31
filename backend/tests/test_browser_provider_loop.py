"""Browser-agent coverage across the provider adapter seam."""

from unittest.mock import AsyncMock

import pytest

import backend.apps.agents.browser_agent as browser_agent
from backend.apps.agents.agent_manager import agent_manager
from backend.apps.agents.providers.base import (
    ContentBlock,
    ModelResponse,
    ProviderMessage,
    ToolCall,
    ToolSchema,
)
import backend.apps.agents.providers.registry as provider_registry


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.responses = [
            ModelResponse(
                content=[
                    ContentBlock(
                        type="tool_use",
                        tool_call=ToolCall(
                            id="browser-call-1",
                            name="BrowserGetText",
                            input={},
                        ),
                    )
                ],
                stop_reason="tool_use",
                usage={"input_tokens": 5, "output_tokens": 2},
            ),
            ModelResponse(
                content=[ContentBlock(type="text", text="Browser task complete.")],
                stop_reason="end_turn",
                usage={"input_tokens": 8, "output_tokens": 3},
            ),
        ]

    async def create_message(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)

    def format_user_message(self, content):
        return ProviderMessage(role="user", content=content)

    def format_assistant_message(self, response):
        return ProviderMessage(role="assistant", content={"provider": "assistant"})

    def format_tool_result(self, tool_use_id, content):
        return {"provider_tool_result": tool_use_id, "content": content}


@pytest.mark.asyncio
async def test_browser_agent_uses_selected_provider_and_generic_tool_history(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(provider_registry, "create_provider", lambda *_: provider)
    monkeypatch.setattr(browser_agent, "load_builtin_permissions", lambda: {})
    execute = AsyncMock(return_value={"text": "Page contents"})
    monkeypatch.setattr(browser_agent, "execute_browser_tool", execute)

    result = await browser_agent.run_browser_agent(
        task="Inspect this page",
        browser_id="browser-test",
        model="llama3.3",
    )

    try:
        session = agent_manager.sessions[result["session_id"]]
        assert session.provider == "ollama"
        assert result["summary"] == "Browser task complete."
        assert session.tokens == {"input": 13, "output": 5}
        assert all(isinstance(tool, ToolSchema) for tool in provider.calls[0]["tools"])
        assert isinstance(provider.calls[0]["messages"][0], ProviderMessage)
        assert provider.calls[1]["messages"][-1].role == "tool_result"
        assert provider.calls[1]["messages"][-1].content[0]["provider_tool_result"] == "browser-call-1"
        execute.assert_any_await("BrowserGetText", {}, "browser-test", "")
    finally:
        agent_manager.sessions.pop(result["session_id"], None)
        browser_agent.clear_browser_history("browser-test")
