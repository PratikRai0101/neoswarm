"""Mission orchestration for NeoSwarm worker agents.

The :class:`Orchestrator` is the single module that owns a mission's lifecycle:
create it, decompose it, schedule workers, collect their results, synthesize a
summary, and cancel it.  REST and UI callers use its small mission interface;
they do not coordinate individual worker sessions themselves.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class SubTask:
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_worker_id: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Worker:
    id: str
    name: str
    status: WorkerStatus = WorkerStatus.IDLE
    current_task_id: str | None = None
    session_id: str | None = None
    model: str = "sonnet"


@dataclass
class OrchestratorSession:
    id: str
    mission: str
    model: str = "sonnet"
    provider: str | None = None
    execution_mode: Literal["parallel", "sequential"] = "parallel"
    target_directory: str | None = None
    isolate_workers: bool = False
    decomposed_tasks: list[SubTask] = field(default_factory=list)
    workers: list[Worker] = field(default_factory=list)
    status: str = "pending"  # pending, decomposing, running, completed, failed, cancelled
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    final_result: str | None = None
    error: str | None = None


def mission_to_dict(session: OrchestratorSession) -> dict[str, Any]:
    """Return the REST-safe representation of a mission and its workers."""
    return {
        "id": session.id,
        "mission": session.mission,
        "model": session.model,
        "provider": session.provider,
        "execution_mode": session.execution_mode,
        "target_directory": session.target_directory,
        "isolate_workers": session.isolate_workers,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "completed_at": session.completed_at.isoformat()
        if session.completed_at
        else None,
        "final_result": session.final_result,
        "error": session.error,
        "tasks": [
            {
                **asdict(task),
                "status": task.status.value,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat()
                if task.completed_at
                else None,
            }
            for task in session.decomposed_tasks
        ],
        "workers": [
            {**asdict(worker), "status": worker.status.value}
            for worker in session.workers
        ],
    }


class Orchestrator:
    """Run durable-in-memory missions over the existing AgentManager seam."""

    def __init__(self, agent_manager=None):
        self.agent_manager = agent_manager
        self.sessions: dict[str, OrchestratorSession] = {}
        self._execution_tasks: dict[str, asyncio.Task] = {}

    async def create_session(
        self,
        mission: str,
        num_workers: int = 3,
        model: str = "sonnet",
        provider: str | None = None,
        execution_mode: Literal["parallel", "sequential"] = "parallel",
        target_directory: str | None = None,
        isolate_workers: bool = False,
    ) -> OrchestratorSession:
        mission = mission.strip()
        if not mission:
            raise ValueError("mission is required")
        if execution_mode not in {"parallel", "sequential"}:
            raise ValueError("execution_mode must be 'parallel' or 'sequential'")

        worker_count = max(1, min(int(num_workers), 8))
        session = OrchestratorSession(
            id=uuid4().hex,
            mission=mission,
            model=model,
            provider=provider,
            execution_mode=execution_mode,
            target_directory=target_directory,
            isolate_workers=isolate_workers,
            workers=[
                Worker(id=uuid4().hex, name=f"Worker-{index + 1}", model=model)
                for index in range(worker_count)
            ],
        )
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> OrchestratorSession | None:
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[OrchestratorSession]:
        return sorted(self.sessions.values(), key=lambda item: item.created_at, reverse=True)

    async def start(self, session_id: str) -> OrchestratorSession:
        session = self._require_session(session_id)
        running = self._execution_tasks.get(session_id)
        if running and not running.done():
            return session
        if session.status in {"completed", "failed", "cancelled"}:
            raise ValueError(f"Mission is already {session.status}")

        task = asyncio.create_task(
            self.run_mission(session_id), name=f"neoswarm-mission-{session_id}"
        )
        self._execution_tasks[session_id] = task
        task.add_done_callback(lambda _: self._execution_tasks.pop(session_id, None))
        return session

    async def cancel(self, session_id: str) -> OrchestratorSession:
        session = self._require_session(session_id)
        task = self._execution_tasks.get(session_id)
        if task and not task.done():
            task.cancel()

        for worker in session.workers:
            if worker.session_id and self.agent_manager:
                await self.agent_manager.stop_agent(worker.session_id)
            if worker.status == WorkerStatus.BUSY:
                worker.status = WorkerStatus.IDLE
                worker.current_task_id = None
        for subtask in session.decomposed_tasks:
            if subtask.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
                subtask.status = TaskStatus.CANCELLED
                subtask.completed_at = datetime.now()
        session.status = "cancelled"
        session.completed_at = datetime.now()
        session.final_result = "Mission cancelled by the user."
        return session

    async def decompose_mission(self, session: OrchestratorSession) -> list[SubTask]:
        """Ask the selected provider for independent work, with a safe fallback."""
        try:
            from backend.apps.agents.providers.base import ProviderMessage
            from backend.apps.agents.providers.registry import create_provider
            from backend.apps.settings.settings import load_settings

            provider_name = session.provider or "anthropic"
            provider = create_provider(provider_name, load_settings())
            response = await provider.create_message(
                model=session.model,
                system=(
                    "Decompose missions into 2–5 independent implementation tasks. "
                    "Return only a JSON array of concise strings."
                ),
                messages=[
                    ProviderMessage(
                        role="user",
                        content=(
                            f"Mission: {session.mission}\n"
                            "Each task must be executable by one worker and avoid overlap."
                        ),
                    )
                ],
                tools=[],
                max_tokens=1024,
            )
            text = response.content[0].text if response.content else ""
            descriptions = json.loads(text)
            if not isinstance(descriptions, list):
                raise ValueError("model did not return an array")
            cleaned = [
                item.strip() for item in descriptions if isinstance(item, str) and item.strip()
            ][:5]
            if cleaned:
                return [SubTask(id=uuid4().hex, description=item) for item in cleaned]
        except Exception as exc:
            logger.info("Mission decomposition using a model was unavailable: %s", exc)
        return self._simple_decompose(session.mission)

    async def run_mission(self, session_id: str) -> str:
        """Execute a mission once; callers should use :meth:`start` for background work."""
        session = self._require_session(session_id)
        if not self.agent_manager:
            raise RuntimeError("Orchestrator has no AgentManager")

        try:
            session.status = "decomposing"
            session.decomposed_tasks = await self.decompose_mission(session)
            if not session.decomposed_tasks:
                raise RuntimeError("Mission produced no executable tasks")

            session.status = "running"
            if session.execution_mode == "sequential":
                for index, subtask in enumerate(session.decomposed_tasks):
                    await self._execute_task(session, session.workers[index % len(session.workers)], subtask)
            else:
                queue: asyncio.Queue[SubTask] = asyncio.Queue()
                for subtask in session.decomposed_tasks:
                    queue.put_nowait(subtask)

                async def run_worker(worker: Worker) -> None:
                    while not queue.empty():
                        try:
                            subtask = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                        try:
                            await self._execute_task(session, worker, subtask)
                        finally:
                            queue.task_done()

                await asyncio.gather(*(run_worker(worker) for worker in session.workers))

            return await self.synthesize_results(session_id)
        except asyncio.CancelledError:
            if session.status != "cancelled":
                await self.cancel(session_id)
            raise
        except Exception as exc:
            logger.exception("Mission %s failed", session_id)
            session.status = "failed"
            session.error = str(exc)
            session.completed_at = datetime.now()
            session.final_result = f"Mission failed: {exc}"
            return session.final_result
    async def _execute_task(
        self, session: OrchestratorSession, worker: Worker, subtask: SubTask
    ) -> None:
        from backend.apps.agents.models import AgentConfig

        worker.status = WorkerStatus.BUSY
        worker.current_task_id = subtask.id
        subtask.status = TaskStatus.RUNNING
        subtask.assigned_worker_id = worker.id
        subtask.started_at = datetime.now()

        try:
            worker_session = await self.agent_manager.launch_agent(
                AgentConfig(
                    name=f"{worker.name}: {subtask.description[:48]}",
                    model=worker.model,
                    provider=session.provider,
                    mode="agent",
                    target_directory=session.target_directory,
                    use_worktree=session.isolate_workers,
                )
            )
            worker.session_id = worker_session.id
            await self.agent_manager.send_message(
                worker_session.id,
                (
                    f"You are {worker.name} in a coordinated mission.\n"
                    f"Mission: {session.mission}\n\n"
                    f"Your assigned task: {subtask.description}\n\n"
                    "Work only on this task. Report concrete changes, evidence, and blockers."
                ),
            )
            worker_task = self.agent_manager.tasks.get(worker_session.id)
            if worker_task:
                await worker_task

            if worker_session.status == "error":
                raise RuntimeError(self._worker_error(worker_session))
            subtask.result = self._worker_result(worker_session)
            subtask.status = TaskStatus.COMPLETED
            worker.status = WorkerStatus.COMPLETED
        except asyncio.CancelledError:
            subtask.status = TaskStatus.CANCELLED
            raise
        except Exception as exc:
            logger.warning("Worker %s failed task %s: %s", worker.id, subtask.id, exc)
            subtask.status = TaskStatus.FAILED
            subtask.error = str(exc)
            worker.status = WorkerStatus.ERROR
        finally:
            subtask.completed_at = datetime.now()
            worker.current_task_id = None

    async def synthesize_results(self, session_id: str) -> str:
        session = self._require_session(session_id)
        completed = [task for task in session.decomposed_tasks if task.status == TaskStatus.COMPLETED]
        failed = [task for task in session.decomposed_tasks if task.status == TaskStatus.FAILED]
        cancelled = [task for task in session.decomposed_tasks if task.status == TaskStatus.CANCELLED]

        sections = [f"Mission: {session.mission}", ""]
        for task in completed:
            sections.append(f"✓ {task.description}\n{task.result or 'Completed.'}")
        for task in failed:
            sections.append(f"✗ {task.description}\nBlocked: {task.error or 'Unknown error'}")
        for task in cancelled:
            sections.append(f"— {task.description}\nCancelled.")

        if failed:
            session.status = "failed"
        elif cancelled:
            session.status = "cancelled"
        else:
            session.status = "completed"
        session.completed_at = datetime.now()
        session.final_result = "\n\n".join(sections)
        return session.final_result

    @staticmethod
    def _simple_decompose(mission: str) -> list[SubTask]:
        parts = [mission]
        for separator in (" and ", " then ", " also ", " plus ", ","):
            parts = [piece for part in parts for piece in part.split(separator)]
        descriptions = [part.strip() for part in parts if part.strip()]
        if len(descriptions) < 2:
            descriptions = [
                f"Analyze requirements and risks for: {mission}",
                f"Implement the requested work for: {mission}",
                f"Review and verify the result for: {mission}",
            ]
        return [SubTask(id=uuid4().hex, description=item) for item in descriptions[:5]]

    @staticmethod
    def _worker_result(worker_session) -> str:
        for message in reversed(worker_session.messages):
            if message.role == "assistant" and isinstance(message.content, str):
                return message.content
        return "Worker completed without a text summary."

    @staticmethod
    def _worker_error(worker_session) -> str:
        for message in reversed(worker_session.messages):
            if message.role == "system" and isinstance(message.content, str):
                return message.content
        return "Worker agent returned an error."

    def _require_session(self, session_id: str) -> OrchestratorSession:
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Mission {session_id} not found")
        return session


orchestrator = Orchestrator()


async def create_orchestrator_session(
    mission: str,
    num_workers: int = 3,
    model: str = "sonnet",
    provider: str | None = None,
    execution_mode: Literal["parallel", "sequential"] = "parallel",
) -> OrchestratorSession:
    """Backward-compatible mission creation helper."""
    return await orchestrator.create_session(
        mission,
        num_workers,
        model,
        provider,
        execution_mode,
    )
