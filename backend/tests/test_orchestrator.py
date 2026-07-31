"""Behaviour tests for multi-agent mission orchestration."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.apps.agents.models import AgentSession, Message
from backend.apps.agents.orchestrator import Orchestrator, SubTask, TaskStatus


class FakeAgentManager:
    def __init__(self):
        self.tasks: dict[str, asyncio.Task] = {}
        self.sessions: dict[str, AgentSession] = {}
        self.active_workers = 0
        self.max_active_workers = 0

    async def launch_agent(self, config):
        session = AgentSession(
            name=config.name,
            model=config.model,
            provider=config.provider or "anthropic",
            mode=config.mode,
        )
        self.sessions[session.id] = session
        return session

    async def send_message(self, session_id, prompt):
        session = self.sessions[session_id]

        async def complete():
            self.active_workers += 1
            self.max_active_workers = max(self.max_active_workers, self.active_workers)
            await asyncio.sleep(0.01)
            self.active_workers -= 1
            session.messages.append(Message(role="assistant", content=f"Completed: {prompt}"))
            session.status = "completed"

        self.tasks[session_id] = asyncio.create_task(complete())

    async def stop_agent(self, session_id):
        task = self.tasks.get(session_id)
        if task and not task.done():
            task.cancel()


@pytest.mark.asyncio
async def test_parallel_mission_runs_workers_and_synthesizes_results(monkeypatch):
    manager = FakeAgentManager()
    coordinator = Orchestrator(manager)
    mission = await coordinator.create_session(
        "Build and verify a feature", num_workers=2, execution_mode="parallel"
    )
    subtasks = [
        SubTask(id="one", description="Implement the feature"),
        SubTask(id="two", description="Verify the feature"),
    ]
    monkeypatch.setattr(coordinator, "decompose_mission", AsyncMock(return_value=subtasks))

    summary = await coordinator.run_mission(mission.id)

    assert mission.status == "completed"
    assert all(task.status == TaskStatus.COMPLETED for task in mission.decomposed_tasks)
    assert manager.max_active_workers == 2
    assert "✓ Implement the feature" in summary
    assert "✓ Verify the feature" in summary


@pytest.mark.asyncio
async def test_sequential_mission_uses_one_worker_at_a_time(monkeypatch):
    manager = FakeAgentManager()
    coordinator = Orchestrator(manager)
    mission = await coordinator.create_session(
        "Build and verify a feature", num_workers=2, execution_mode="sequential"
    )
    monkeypatch.setattr(
        coordinator,
        "decompose_mission",
        AsyncMock(
            return_value=[
                SubTask(id="one", description="Implement"),
                SubTask(id="two", description="Verify"),
            ]
        ),
    )

    await coordinator.run_mission(mission.id)

    assert mission.status == "completed"
    assert manager.max_active_workers == 1


@pytest.mark.asyncio
async def test_mission_creation_validates_input():
    coordinator = Orchestrator(FakeAgentManager())

    with pytest.raises(ValueError, match="mission is required"):
        await coordinator.create_session("  ")
    with pytest.raises(ValueError, match="execution_mode"):
        await coordinator.create_session("Build", execution_mode="invalid")


@pytest.mark.asyncio
async def test_missions_persist_and_interrupted_work_is_reconciled(tmp_path):
    storage = tmp_path / "missions"
    first = Orchestrator(FakeAgentManager(), storage_dir=str(storage))
    completed = await first.create_session("Completed mission", num_workers=1)
    completed.status = "completed"
    completed.completed_at = completed.created_at
    first._persist(completed)

    interrupted = await first.create_session("Interrupted mission", num_workers=1)
    interrupted.status = "running"
    interrupted.decomposed_tasks = [
        SubTask(id="running-task", description="Still running", status=TaskStatus.RUNNING)
    ]
    first._persist(interrupted)

    restored = Orchestrator(FakeAgentManager(), storage_dir=str(storage))

    assert restored.get_session(completed.id).status == "completed"
    restored_interrupted = restored.get_session(interrupted.id)
    assert restored_interrupted.status == "failed"
    assert restored_interrupted.decomposed_tasks[0].status == TaskStatus.FAILED
    assert "Backend stopped" in restored_interrupted.error

    restored.delete(completed.id)
    assert restored.get_session(completed.id) is None
    assert not (storage / f"{completed.id}.json").exists()


@pytest.mark.asyncio
async def test_mission_routes_create_start_and_report_a_mission(monkeypatch):
    import backend.apps.agents.agents as agents_api

    coordinator = Orchestrator(FakeAgentManager())
    monkeypatch.setattr(agents_api, "orchestrator", coordinator)
    monkeypatch.setattr(
        coordinator,
        "decompose_mission",
        AsyncMock(return_value=[SubTask(id="one", description="Implement")]),
    )

    created = await agents_api.create_mission(
        {"mission": "Implement a feature", "workers": 1, "execution_mode": "parallel"}
    )
    mission_id = created["mission"]["id"]
    started = await agents_api.start_mission(mission_id)
    worker_task = coordinator._execution_tasks[mission_id]
    await worker_task
    reported = await agents_api.get_mission(mission_id)

    assert started["mission"]["id"] == mission_id
    assert reported["mission"]["status"] == "completed"
    assert reported["mission"]["tasks"][0]["status"] == "completed"
