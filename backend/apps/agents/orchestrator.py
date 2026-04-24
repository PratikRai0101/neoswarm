"""Orchestrator Agent - The Team Lead that decomposes goals into tasks.

The Orchestrator Agent is the "Team Lead" that:
1. Takes a mission from the user
2. Decomposes it into subtasks
3. Spawns worker agents in parallel
4. Monitors progress
5. Synthesizes results

This is the core of NeoSwarm's multi-agent system.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
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
    """A single task in the decomposed goal."""

    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_worker_id: str | None = None
    result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Worker:
    """A worker agent that executes tasks."""

    id: str
    name: str
    status: WorkerStatus = WorkerStatus.IDLE
    current_task_id: str | None = None
    session_id: str | None = None
    model: str = "sonnet"


@dataclass
class OrchestratorSession:
    """Session for an Orchestrator Agent managing multiple workers."""

    id: str
    mission: str
    decomposed_tasks: list[SubTask] = field(default_factory=list)
    workers: list[Worker] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    final_result: str | None = None


class Orchestrator:
    """Orchestrator Agent - decomposes goals and manages workers."""

    def __init__(self, agent_manager):
        self.agent_manager = agent_manager
        self.sessions: dict[str, OrchestratorSession] = {}

    async def create_session(
        self,
        mission: str,
        num_workers: int = 3,
        model: str = "sonnet",
    ) -> OrchestratorSession:
        """Create a new Orchestrator session with workers."""
        session_id = uuid4().hex
        session = OrchestratorSession(
            id=session_id,
            mission=mission,
            workers=[
                Worker(
                    id=uuid4().hex,
                    name=f"Worker-{i + 1}",
                    model=model,
                )
                for i in range(num_workers)
            ],
        )
        self.sessions[session_id] = session
        logger.info(
            f"Created Orchestrator session {session_id} with {num_workers} workers"
        )
        return session

    async def decompose_mission(self, session: OrchestratorSession) -> list[SubTask]:
        """Decompose the mission into subtasks using the LLM.

        This prompts the model to break down the mission into atomic tasks.
        """
        from backend.apps.settings.settings import load_settings

        settings = load_settings()
        if not settings.anthropic_api_key and not getattr(
            settings, "google_api_key", None
        ):
            return self._simple_decompose(session.mission)

        prompt = f"""You are a Team Lead. Break down this mission into 3-5 atomic subtasks:

Mission: {session.mission}

Return a JSON array of task descriptions. Each should be independent and executable."""

        try:
            from backend.apps.agents.providers.registry import create_provider

            provider = create_provider("Anthropic", settings)

            from backend.apps.agents.providers.base import ProviderMessage, ToolSchema

            messages = [ProviderMessage(role="user", content=prompt)]

            response = await provider.create_message(
                model=session.workers[0].model,
                system="You are a task decomposition expert. Return only valid JSON.",
                messages=messages,
                tools=[],
                max_tokens=4096,
            )

            import json

            text = response.content[0].text if response.content else ""
            task_list = json.loads(text)

            tasks = []
            for i, desc in enumerate(task_list):
                tasks.append(
                    SubTask(
                        id=uuid4().hex,
                        description=desc
                        if isinstance(desc, str)
                        else desc.get("task", ""),
                    )
                )

            return tasks
        except Exception as e:
            logger.warning(f"LLM decomposition failed: {e}, using simple fallback")
            return self._simple_decompose(session.mission)

    def _simple_decompose(self, mission: str) -> list[SubTask]:
        """Simple keyword-based decomposition fallback."""
        keywords = ["and", "then", "also", "plus", "with", ","]
        parts = [mission]
        for kw in keywords:
            new_parts = []
            for part in parts:
                new_parts.extend(part.split(f" {kw} "))
            parts = new_parts

        tasks = []
        for i, desc in enumerate([p.strip() for p in parts if p.strip()]):
            tasks.append(SubTask(id=uuid4().hex, description=desc))

        if len(tasks) < 3:
            tasks = [
                SubTask(id=uuid4().hex, description=f"Task {i + 1}")
                for i in range(min(3, len(tasks) or 1))
            ]

        return tasks[:5]

    async def run_mission(
        self,
        session_id: str,
        ws_manager,
    ) -> str:
        """Execute the mission by spawning workers and monitoring progress."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        logger.info(f"Starting mission: {session.mission}")

        await ws_manager.send_to_session(
            session_id,
            "orchestrator:status",
            {
                "session_id": session_id,
                "status": "decomposing",
            },
        )

        session.decomposed_tasks = await self.decompose_mission(session)
        logger.info(f"Decomposed into {len(session.decomposed_tasks)} tasks")

        await ws_manager.send_to_session(
            session_id,
            "orchestrator:tasks",
            {
                "session_id": session_id,
                "tasks": [
                    {"id": t.id, "description": t.status.value}
                    for t in session.decomposed_tasks
                ],
            },
        )

        session.status = "running"
        return session.mission

    async def assign_task_to_worker(
        self,
        session_id: str,
        worker_id: str,
        task_id: str,
    ) -> None:
        """Assign a pending task to an idle worker."""
        session = self.sessions.get(session_id)
        if not session:
            return

        worker = next((w for w in session.workers if w.id == worker_id), None)
        task = next((t for t in session.decomposed_tasks if t.id == task_id), None)

        if not worker or not task:
            return

        worker.status = WorkerStatus.BUSY
        worker.current_task_id = task_id
        task.status = TaskStatus.RUNNING
        task.assigned_worker_id = worker_id
        task.started_at = datetime.now()

        logger.info(f"Assigned task {task_id} to worker {worker_id}")

    async def complete_task(
        self,
        session_id: str,
        worker_id: str,
        result: Any,
    ) -> None:
        """Mark a worker's task as completed."""
        session = self.sessions.get(session_id)
        if not session:
            return

        worker = next((w for w in session.workers if w.id == worker_id), None)
        if not worker or not worker.current_task_id:
            return

        task = next(
            (t for t in session.decomposed_tasks if t.id == worker.current_task_id),
            None,
        )
        if task:
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now()

        worker.status = WorkerStatus.IDLE
        worker.current_task_id = None

        logger.info(f"Worker {worker_id} completed task {task.id if task else '?'}")

    async def synthesize_results(
        self,
        session_id: str,
    ) -> str:
        """Synthesize into a final result when all tasks complete."""
        session = self.sessions.get(session_id)
        if not session:
            return ""

        completed = [
            t for t in session.decomposed_tasks if t.status == TaskStatus.COMPLETED
        ]

        if len(completed) == len(session.decomposed_tasks):
            session.status = "completed"
            session.completed_at = datetime.now()

            results_text = "\n\n".join(
                [f"Task: {t.description}\nResult: {t.result}" for t in completed]
            )

            session.final_result = f"""Mission completed by {len(completed)} workers:

{results_text}

---"""
            logger.info(f"Orchestrator session {session_id} completed")

        return session.final_result or "In progress..."


orchestrator = Orchestrator(None)


async def create_orchestrator_session(
    mission: str,
    num_workers: int = 3,
    model: str = "sonnet",
) -> OrchestratorSession:
    """Create a new Orchestrator session."""
    global orchestrator
    return await orchestrator.create_session(mission, num_workers, model)
