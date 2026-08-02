"""Durable, local-first scheduling for agent prompts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from backend.apps.agents.models import AgentConfig
from backend.apps.scheduler.models import ScheduleCreate, ScheduleUpdate, ScheduledTask

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now().astimezone()


class ScheduleStore:
    """Small JSON-file repository for user-owned schedules."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory).expanduser().resolve()
        self.tasks: dict[str, ScheduledTask] = {}
        self.load()

    def load(self) -> None:
        self.tasks = {}
        if not self.directory.exists():
            return
        for path in self.directory.glob("*.json"):
            try:
                task = ScheduledTask.model_validate_json(path.read_text())
            except Exception as exc:
                logger.warning("Skipping invalid schedule %s: %s", path, exc)
                continue
            if task.status == "running":
                task.status = "scheduled" if task.enabled else "disabled"
                task.last_error = "Backend restarted before this schedule completed"
                task.updated_at = _now()
            self.tasks[task.id] = task
        for task in self.tasks.values():
            self.save(task)

    def save(self, task: ScheduledTask) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{task.id}.json"
        descriptor, temporary = tempfile.mkstemp(
            prefix=f"{task.id}-", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(task.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def delete(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)
        (self.directory / f"{task_id}.json").unlink(missing_ok=True)


class Scheduler:
    """Schedule prompts and launch them through the existing AgentManager seam."""

    def __init__(
        self,
        storage_dir: str | os.PathLike[str],
        agent_manager=None,
        clock: Callable[[], datetime] = _now,
        tick_seconds: float = 1.0,
    ):
        self.store = ScheduleStore(storage_dir)
        self.agent_manager = agent_manager
        self.clock = clock
        self.tick_seconds = tick_seconds
        self._loop_task: asyncio.Task | None = None
        self._run_tasks: set[asyncio.Task] = set()

    @property
    def tasks(self) -> dict[str, ScheduledTask]:
        return self.store.tasks

    async def start(self) -> None:
        if self._loop_task and not self._loop_task.done():
            return
        self._loop_task = asyncio.create_task(self._run_loop(), name="neoswarm-scheduler")

    async def stop(self) -> None:
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None
        for task in list(self._run_tasks):
            task.cancel()
        if self._run_tasks:
            await asyncio.gather(*self._run_tasks, return_exceptions=True)
        for task in self.tasks.values():
            self.store.save(task)

    def list(self) -> list[ScheduledTask]:
        return sorted(self.tasks.values(), key=lambda task: task.created_at, reverse=True)

    def get(self, task_id: str) -> ScheduledTask | None:
        return self.tasks.get(task_id)

    async def create(self, request: ScheduleCreate) -> ScheduledTask:
        task = ScheduledTask.from_create(request)
        self.tasks[task.id] = task
        self.store.save(task)
        return task

    async def update(self, task_id: str, patch: ScheduleUpdate) -> ScheduledTask:
        task = self._require(task_id)
        values = task.model_dump()
        updates = patch.model_dump(exclude_unset=True)
        values.update(updates)
        # A timing field omitted from a patch keeps the existing schedule. When
        # changing kinds, supply a valid timing field before Pydantic validates
        # the resulting schedule (the old kind's timing field may be null).
        resulting_kind = updates.get("kind", task.kind)
        if resulting_kind == "interval" and "interval_seconds" not in updates:
            values["interval_seconds"] = task.interval_seconds or 10
        if resulting_kind == "once" and "run_at" not in updates:
            values["run_at"] = task.run_at or self.clock()
        updated = ScheduledTask.model_validate(values)
        if updated.kind == "interval":
            updated.run_at = None
            if updated.next_run_at is None or "kind" in updates or "interval_seconds" in updates:
                updated.next_run_at = self.clock() + timedelta(
                    seconds=updated.interval_seconds or 10
                )
        else:
            updated.interval_seconds = None
            if "kind" in updates or "run_at" in updates:
                updated.next_run_at = updated.run_at
        updated.updated_at = self.clock()
        if not updated.enabled:
            updated.status = "disabled"
        elif updated.status == "disabled":
            updated.status = "scheduled"
        self.tasks[task_id] = updated
        self.store.save(updated)
        return updated

    async def delete(self, task_id: str) -> None:
        task = self._require(task_id)
        if task.status == "running":
            raise ValueError("Running schedules must be disabled before deletion")
        self.store.delete(task_id)

    async def run_now(self, task_id: str) -> ScheduledTask:
        task = self._require(task_id)
        if task.status == "running":
            return task
        await self._dispatch(task, force=True)
        return task

    async def _run_loop(self) -> None:
        while True:
            now = self.clock()
            for task in list(self.tasks.values()):
                if not task.enabled or task.status == "running":
                    continue
                if task.next_run_at and task.next_run_at <= now:
                    run_task = asyncio.create_task(self._dispatch(task), name=f"neoswarm-schedule-{task.id}")
                    self._run_tasks.add(run_task)
                    run_task.add_done_callback(self._run_tasks.discard)
            await asyncio.sleep(self.tick_seconds)

    async def _dispatch(self, task: ScheduledTask, force: bool = False) -> None:
        if not force and (not task.enabled or task.status == "running"):
            return
        if not self.agent_manager:
            task.status = "failed"
            task.last_error = "Scheduler has no AgentManager"
            task.updated_at = self.clock()
            self.store.save(task)
            return

        now = self.clock()
        task.status = "running"
        task.last_run_at = now
        task.last_error = None
        if task.kind == "once":
            task.enabled = False
            task.next_run_at = None
        else:
            task.next_run_at = now + timedelta(
                seconds=task.interval_seconds or 10
            )
        task.updated_at = now
        self.store.save(task)

        try:
            session = await self.agent_manager.launch_agent(
                AgentConfig(
                    name=f"Schedule: {task.name}",
                    model=task.model,
                    provider=task.provider,
                    mode="agent",
                    target_directory=task.target_directory,
                )
            )
            task.last_session_id = session.id
            self.store.save(task)
            await self.agent_manager.send_message(
                session.id,
                task.prompt,
                model=task.model,
                provider=task.provider,
            )
            worker = self.agent_manager.tasks.get(session.id)
            if worker:
                waiter = asyncio.create_task(
                    self._finish(task.id, session.id, worker),
                    name=f"neoswarm-schedule-wait-{task.id}",
                )
                self._run_tasks.add(waiter)
                waiter.add_done_callback(self._run_tasks.discard)
            else:
                await self._finish_without_wait(task.id, session.id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Scheduled task %s failed to launch", task.id)
            task.status = "failed"
            task.last_error = str(exc)
            task.updated_at = self.clock()
            self.store.save(task)

    async def _finish(self, task_id: str, session_id: str, worker: asyncio.Task) -> None:
        try:
            await worker
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Scheduled session %s failed: %s", session_id, exc)
        await self._finish_without_wait(task_id, session_id)

    async def _finish_without_wait(self, task_id: str, session_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        session = self.agent_manager.get_session(session_id) if self.agent_manager else None
        failed = session is not None and session.status == "error"
        if failed:
            task.status = "failed"
        elif task.kind == "once":
            task.status = "completed"
        elif task.enabled:
            task.status = "scheduled"
        else:
            task.status = "disabled"
        if failed and not task.last_error:
            task.last_error = "Scheduled agent session failed"
        task.updated_at = self.clock()
        self.store.save(task)

    def _require(self, task_id: str) -> ScheduledTask:
        task = self.get(task_id)
        if not task:
            raise KeyError(task_id)
        return task


def schedule_to_dict(task: ScheduledTask) -> dict[str, Any]:
    return task.model_dump(mode="json")
