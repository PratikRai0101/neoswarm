"""Output auto-run preserves model provider identity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.apps.outputs.models import AutoRunAgentRequest, AutoRunRequest
import backend.apps.outputs.outputs as outputs_api


@pytest.mark.asyncio
async def test_direct_auto_run_forwards_provider_to_auxiliary_generation(monkeypatch):
    import backend.apps.agents.auxiliary as auxiliary

    generate = AsyncMock(return_value='{"topic": "local models"}')
    monkeypatch.setattr(auxiliary, "generate_auxiliary_text", generate)

    result = await outputs_api.auto_run_output(
        AutoRunRequest(
            prompt="Generate a topic",
            input_schema={
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
            model="qwen-local:latest",
            provider="ollama",
        )
    )

    assert result["input_data"] == {"topic": "local models"}
    assert generate.await_args.kwargs["model"] == "qwen-local:latest"
    assert generate.await_args.kwargs["provider"] == "ollama"


@pytest.mark.asyncio
async def test_agent_auto_run_launches_with_selected_provider(monkeypatch):
    import backend.apps.agents.agent_manager as manager_module

    launch = AsyncMock(return_value=SimpleNamespace(id="auto-run-session"))
    send = AsyncMock()
    monkeypatch.setattr(manager_module.agent_manager, "launch_agent", launch)
    monkeypatch.setattr(manager_module.agent_manager, "send_message", send)
    monkeypatch.setattr(
        outputs_api,
        "_load",
        lambda _output_id: SimpleNamespace(
            name="Research View",
            input_schema={"type": "object", "properties": {}},
        ),
    )

    result = await outputs_api.auto_run_agent(
        AutoRunAgentRequest(
            prompt="Collect the data",
            output_id="output-1",
            model="vendor/agent-model",
            provider="openrouter",
        )
    )

    config = launch.await_args.args[0]
    assert config.model == "vendor/agent-model"
    assert config.provider == "openrouter"
    send.assert_awaited_once()
    assert result == {"session_id": "auto-run-session"}
