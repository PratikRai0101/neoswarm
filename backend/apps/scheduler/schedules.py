"""REST interface for scheduled agent prompts."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import HTTPException

from backend.config.Apps import SubApp
from backend.config.paths import SCHEDULES_DIR
from backend.apps.agents.agent_manager import agent_manager
from backend.apps.scheduler.models import ScheduleCreate, ScheduleUpdate
from backend.apps.scheduler.scheduler import Scheduler, schedule_to_dict


scheduler = Scheduler(SCHEDULES_DIR, agent_manager=agent_manager)


@asynccontextmanager
async def schedules_lifespan():
    await scheduler.start()
    yield
    await scheduler.stop()


schedules = SubApp("schedules", schedules_lifespan)


def _get_or_404(schedule_id: str):
    task = scheduler.get(schedule_id)
    if not task:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return task


@schedules.router.get("")
async def list_schedules():
    return {"schedules": [schedule_to_dict(task) for task in scheduler.list()]}


@schedules.router.get("/{schedule_id}")
async def get_schedule(schedule_id: str):
    return {"schedule": schedule_to_dict(_get_or_404(schedule_id))}


@schedules.router.post("")
async def create_schedule(body: ScheduleCreate):
    try:
        task = await scheduler.create(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"schedule": schedule_to_dict(task)}


@schedules.router.patch("/{schedule_id}")
async def update_schedule(schedule_id: str, body: ScheduleUpdate):
    _get_or_404(schedule_id)
    try:
        task = await scheduler.update(schedule_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"schedule": schedule_to_dict(task)}


@schedules.router.post("/{schedule_id}/run")
async def run_schedule(schedule_id: str):
    try:
        task = await scheduler.run_now(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    return {"schedule": schedule_to_dict(task)}


@schedules.router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    try:
        await scheduler.delete(schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Schedule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True}
