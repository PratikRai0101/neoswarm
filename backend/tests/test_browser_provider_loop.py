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


# ---------------------------------------------------------------------------
# Dead-card and stagnation guards (ported from upstream browser_loop).
# These are pure helpers, so they are unit-tested directly rather than through
# a full agent run.
# ---------------------------------------------------------------------------


def test_card_is_unavailable_detects_gone_and_wedged_cards():
    assert browser_agent.card_is_unavailable(
        {"error": "Browser card 'c1' not found or not an Electron webview"}
    )
    assert browser_agent.card_is_unavailable({"error": "no dashboard is connected"})
    assert browser_agent.card_is_unavailable({"error": "command timed out"})
    assert browser_agent.card_is_unavailable(
        {"error": "Browser webview 'card-1' was not found"}
    )
    # A normal error is not a dead card.
    assert not browser_agent.card_is_unavailable({"error": "selector not found"})
    assert not browser_agent.card_is_unavailable({"text": "ok"})


def test_is_unproductive_ignores_progress_and_neutral_tools():
    # An error with no URL change is unproductive.
    assert browser_agent.is_unproductive("BrowserClick", {"error": "nope"}, "u1", "t")
    # A URL change is progress even when the text looks like a failure.
    assert not browser_agent.is_unproductive(
        "BrowserClick", {"url": "u2", "text": "failed"}, "u1", "t"
    )
    # Read-only tools never count toward stagnation.
    assert not browser_agent.is_unproductive("BrowserGetText", {"error": "x"}, "u1", "t")
    # A changed observation is progress.
    assert not browser_agent.is_unproductive(
        "BrowserClick", {"text": "new state"}, "u1", "old state"
    )


def test_advance_stagnation_escalates_then_resets():
    streak = 0
    prev_url, prev_text = "u1", ""
    nudges = 0
    # Three unproductive actions in a row should escalate at the threshold.
    for _ in range(browser_agent.STAGNATION_ESCALATION_AT):
        streak, prev_url, prev_text, nudge = browser_agent.advance_stagnation(
            streak, prev_url, prev_text, "BrowserClick", {"error": "nope"},
        )
        if nudge:
            nudges += 1
    assert streak == browser_agent.STAGNATION_ESCALATION_AT
    assert nudges == 1
    assert browser_agent.stagnation_exhausted(streak) is False

    # A productive action resets the streak and clears the nudge.
    streak, prev_url, prev_text, nudge = browser_agent.advance_stagnation(
        streak, prev_url, prev_text, "BrowserNavigate", {"url": "u2", "text": "ok"},
    )
    assert streak == 0
    assert nudge is None


def test_advance_stagnation_passes_through_neutral_tools():
    streak, prev_url, prev_text, nudge = browser_agent.advance_stagnation(
        2, "u1", "t", "BrowserScreenshot", {"error": "x"},
    )
    assert (streak, prev_url, prev_text, nudge) == (2, "u1", "t", None)


def test_completion_is_honest_flags_only_unambiguous_ghosts():
    honest, _ = browser_agent.completion_is_honest(
        [{"tool": "BrowserNavigate", "ok": True, "result_summary": "navigated"}]
    )
    assert honest

    # A read-only task is honest when a read returned content.
    honest, _ = browser_agent.completion_is_honest(
        [{"tool": "BrowserGetText", "ok": True, "result_summary": "some content"}]
    )
    assert honest

    honest, reason = browser_agent.completion_is_honest([])
    assert not honest and "single action" in reason

    honest, reason = browser_agent.completion_is_honest(
        [{"tool": "BrowserClick", "ok": False, "result_summary": "err"}]
    )
    assert not honest and "state-changing action failed" in reason

    honest, reason = browser_agent.completion_is_honest(
        [{"tool": "BrowserScreenshot", "ok": False, "result_summary": ""}]
    )
    assert not honest and "only looked around" in reason

    # A partial failure that still landed a real action stays honest.
    honest, _ = browser_agent.completion_is_honest([
        {"tool": "BrowserClick", "ok": False, "result_summary": "err"},
        {"tool": "BrowserNavigate", "ok": True, "result_summary": "navigated"},
    ])
    assert honest
