"""Phase A (upstream port): resilience behaviors.

Covers the shutdown fuse, scheduler concurrency cap + missed-fire notes,
damaged-file isolation for tools/dashboards/settings, and the web-search
tier breaker. All hermetic — no network.
"""

import asyncio
import json
from datetime import timedelta

import pytest

from backend.apps.scheduler.models import ScheduleCreate
from backend.apps.scheduler.scheduler import MAX_CONCURRENT_RUNS, Scheduler


def test_shutdown_fuse_is_noop_under_pytest():
    from backend.apps.service.shutdown_fuse import (
        arm_shutdown_fuse,
        disarm_shutdown_fuse,
        fuse_armed,
    )

    disarm_shutdown_fuse()
    arm_shutdown_fuse()  # PYTEST_CURRENT_TEST is set: must not arm
    assert not fuse_armed()
    disarm_shutdown_fuse()
    assert not fuse_armed()


def test_scheduler_concurrency_cap_queues_extra_fires(tmp_path):
    from backend.apps.scheduler.scheduler import Scheduler

    scheduler = Scheduler(tmp_path / "schedules", agent_manager=None)

    async def _never():
        await asyncio.Event().wait()

    loop = asyncio.new_event_loop()
    try:
        for _ in range(MAX_CONCURRENT_RUNS):
            task = loop.create_task(_never())
            scheduler._run_tasks.add(task)
        assert scheduler._active_runs() == MAX_CONCURRENT_RUNS

        async def _dispatch_due():
            from backend.apps.scheduler.models import ScheduledTask

            task = ScheduledTask.from_create(
                ScheduleCreate(name="Due", prompt="run me", interval_seconds=60)
            )
            scheduler.tasks[task.id] = task
            await scheduler._dispatch(task)  # not forced: must stay queued
            assert scheduler.get(task.id).status == "scheduled"

        loop.run_until_complete(_dispatch_due())
    finally:
        for task in list(scheduler._run_tasks):
            task.cancel()
        loop.run_until_complete(asyncio.gather(*scheduler._run_tasks, return_exceptions=True))
        loop.close()


def test_scheduler_load_notes_missed_fires(tmp_path):
    from backend.apps.scheduler.models import ScheduledTask

    directory = tmp_path / "schedules"
    directory.mkdir()
    past_task = ScheduledTask.from_create(
        ScheduleCreate(name="Missed", prompt="run me", interval_seconds=60)
    )
    past_task.next_run_at = past_task.next_run_at - timedelta(hours=2)
    (directory / f"{past_task.id}.json").write_text(
        past_task.model_dump_json(indent=2)
    )

    scheduler = Scheduler(directory, agent_manager=None)
    loaded = scheduler.get(past_task.id)
    assert loaded is not None
    # Still due immediately, with an honest note instead of silent skipping.
    assert loaded.next_run_at is not None
    assert loaded.last_error and "backend was stopped" in loaded.last_error


def test_tools_lib_isolates_damaged_connector(tmp_path, monkeypatch):
    import backend.apps.tools_lib.tools_lib as tools_lib

    monkeypatch.setattr(tools_lib, "DATA_DIR", str(tmp_path))
    (tmp_path / "good.json").write_text(
        json.dumps(
            {
                "id": "good",
                "name": "Good",
                "description": "ok",
                "command": "echo",
                "mcp_config": {"type": "stdio", "command": "echo"},
                "credentials": {},
                "auth_type": "none",
                "auth_status": "configured",
            }
        )
    )
    (tmp_path / "bad.json").write_text("{ not valid json")

    loaded = tools_lib._load_all()
    assert [t.id for t in loaded] == ["good"]
    # Damaged file is preserved on disk for repair, not deleted.
    assert (tmp_path / "bad.json").exists()

    with pytest.raises(Exception) as excinfo:
        tools_lib._load("bad")
    assert getattr(excinfo.value, "status_code", None) == 422


def test_dashboards_skip_damaged_file_without_wiping_board(tmp_path, monkeypatch):
    import backend.apps.dashboards.dashboards as dashboards

    monkeypatch.setattr(dashboards, "DATA_DIR", str(tmp_path))
    (tmp_path / "bad.json").write_text("{ not valid json")

    assert dashboards._load_all() == []
    assert (tmp_path / "bad.json").exists()

    with pytest.raises(Exception) as excinfo:
        dashboards._load("bad")
    assert getattr(excinfo.value, "status_code", None) == 422


def test_settings_corrupt_file_is_backed_up_not_lost(tmp_path, monkeypatch):
    import backend.apps.settings.settings as settings_mod
    from backend.apps.settings.models import AppSettings

    bad_file = tmp_path / "settings.json"
    bad_file.write_text("{ not valid json")
    monkeypatch.setattr(settings_mod, "SETTINGS_FILE", str(bad_file))
    monkeypatch.setattr(settings_mod, "DATA_DIR", str(tmp_path))

    loaded = settings_mod._load_settings_file()
    assert isinstance(loaded, AppSettings)
    backups = list(tmp_path.glob("settings.json.corrupt-*.bak"))
    assert len(backups) == 1
    assert "not valid json" in backups[0].read_text()


def test_search_tier_breaker_benches_dead_engine():
    from backend.apps.agents.tools import web as web_tools

    web_tools.reset_search_tier_health()
    assert web_tools._tier_cooldown_left("ddg") == 0.0
    web_tools._record_tier_failure("ddg")
    web_tools._record_tier_failure("ddg")
    assert web_tools._tier_cooldown_left("ddg") == 0.0  # two strikes: still live
    web_tools._record_tier_failure("ddg")
    assert web_tools._tier_cooldown_left("ddg") > 0.0  # third strike: benched
    web_tools._record_tier_success("ddg")
    assert web_tools._tier_cooldown_left("ddg") == 0.0
