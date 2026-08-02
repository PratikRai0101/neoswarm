"""Contract tests for the native scheduling tools."""

from types import SimpleNamespace

import pytest

from backend.apps.agents.tools.base import ToolContext
from backend.apps.agents.tools.registry import get_tool


@pytest.mark.asyncio
async def test_cron_create_uses_the_scheduler_module(monkeypatch):
    import backend.apps.scheduler.schedules as schedules_api

    created = SimpleNamespace(
        id="schedule-1",
        name="Nightly",
        status="scheduled",
        next_run_at=None,
    )

    class FakeScheduler:
        async def create(self, request):
            assert request.name == "Nightly"
            assert request.interval_seconds == 60
            return created

    monkeypatch.setattr(schedules_api, "scheduler", FakeScheduler())
    result = await get_tool("CronCreate").execute(
        {
            "name": "Nightly",
            "prompt": "Run checks",
            "interval_seconds": 60,
        },
        ToolContext(cwd="/tmp", session_id="session-1"),
    )

    assert "schedule-1" in result[0]["text"]


def test_scheduling_tools_are_registered_with_real_schemas():
    assert get_tool("CronCreate").to_tool_schema().input_schema["required"] == [
        "name",
        "prompt",
    ]
    assert get_tool("CronList") is not None
    assert get_tool("CronDelete") is not None
