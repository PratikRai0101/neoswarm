"""Scheduling behavior at the scheduler's agent-manager seam."""

import asyncio
from types import SimpleNamespace

import pytest

from backend.apps.scheduler.models import ScheduleCreate, ScheduleUpdate
from backend.apps.scheduler.scheduler import Scheduler


class FakeAgentManager:
    def __init__(self):
        self.sessions = {}
        self.tasks = {}
        self.launches = []

    async def launch_agent(self, config):
        session = SimpleNamespace(id=f"session-{len(self.launches) + 1}", status="running")
        self.sessions[session.id] = session
        self.launches.append(config)
        return session

    async def send_message(self, session_id, prompt, **kwargs):
        self.sessions[session_id].prompt = prompt
        self.sessions[session_id].kwargs = kwargs

        async def complete():
            await asyncio.sleep(0)
            self.sessions[session_id].status = "completed"

        task = asyncio.create_task(complete())
        self.tasks[session_id] = task

    def get_session(self, session_id):
        return self.sessions.get(session_id)


@pytest.mark.asyncio
async def test_run_now_launches_an_agent_and_reschedules_interval(tmp_path):
    manager = FakeAgentManager()
    scheduler = Scheduler(tmp_path / "schedules", agent_manager=manager, tick_seconds=0.01)
    schedule = await scheduler.create(
        ScheduleCreate(
            name="Daily check",
            prompt="Check the project",
            interval_seconds=60,
            model="llama3.3",
            provider="ollama",
        )
    )

    running = await scheduler.run_now(schedule.id)
    assert running.status == "running"
    assert manager.launches[0].model == "llama3.3"
    assert manager.sessions["session-1"].prompt == "Check the project"

    await asyncio.sleep(0.02)
    assert scheduler.get(schedule.id).status == "scheduled"
    assert scheduler.get(schedule.id).next_run_at is not None


@pytest.mark.asyncio
async def test_update_can_change_schedule_kind_without_stale_timing_fields(tmp_path):
    scheduler = Scheduler(tmp_path / "schedules", agent_manager=FakeAgentManager())
    interval = await scheduler.create(
        ScheduleCreate(
            name="Interval",
            prompt="Run repeatedly",
            interval_seconds=60,
        )
    )

    once = await scheduler.update(
        interval.id,
        ScheduleUpdate(kind="once", run_at=scheduler.clock()),
    )
    assert once.kind == "once"
    assert once.interval_seconds is None
    assert once.run_at is not None

    interval_again = await scheduler.update(
        interval.id,
        ScheduleUpdate(kind="interval", interval_seconds=120),
    )
    assert interval_again.kind == "interval"
    assert interval_again.interval_seconds == 120
    assert interval_again.run_at is None


@pytest.mark.asyncio
async def test_one_time_schedule_disables_after_agent_finishes(tmp_path):
    manager = FakeAgentManager()
    scheduler = Scheduler(tmp_path / "schedules", agent_manager=manager)
    schedule = await scheduler.create(
        ScheduleCreate(
            name="One shot",
            prompt="Run once",
            kind="once",
            run_at=scheduler.clock(),
        )
    )

    await scheduler.run_now(schedule.id)
    await asyncio.sleep(0.02)

    completed = scheduler.get(schedule.id)
    assert completed.enabled is False
    assert completed.status == "completed"
    assert completed.next_run_at is None

    reloaded = Scheduler(tmp_path / "schedules", agent_manager=manager)
    assert reloaded.get(schedule.id).prompt == "Run once"
