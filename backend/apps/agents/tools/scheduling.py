"""Native scheduling tools exposed to the AgentLoop."""

from __future__ import annotations

import json

from backend.apps.agents.tools.base import BaseTool, ToolContext


def _text(value: str) -> list[dict]:
    return [{"type": "text", "text": value}]


class CronCreateTool(BaseTool):
    name = "CronCreate"
    description = (
        "Create a durable scheduled agent run. Use kind=interval with an interval_seconds "
        "value, or kind=once with an ISO-8601 run_at timestamp."
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable schedule name."},
                "prompt": {"type": "string", "description": "Prompt to send to the agent when triggered."},
                "kind": {"type": "string", "enum": ["interval", "once"], "default": "interval"},
                "interval_seconds": {
                    "type": "integer",
                    "minimum": 10,
                    "description": "Interval between runs in seconds (minimum 10).",
                },
                "run_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO-8601 timestamp for a one-time run.",
                },
                "model": {"type": "string", "description": "Model to use for the scheduled agent."},
                "provider": {"type": "string", "description": "Optional provider override."},
                "target_directory": {"type": "string", "description": "Optional working directory."},
            },
            "required": ["name", "prompt"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        from backend.apps.scheduler.models import ScheduleCreate
        from backend.apps.scheduler.schedules import scheduler

        try:
            task = await scheduler.create(ScheduleCreate(**input_data))
        except Exception as exc:
            return _text(f"Unable to create schedule: {exc}")
        return _text(
            json.dumps(
                {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                }
            )
        )


class CronListTool(BaseTool):
    name = "CronList"
    description = "List all scheduled agent runs and their current status."

    def get_schema(self) -> dict:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        from backend.apps.scheduler.scheduler import schedule_to_dict
        from backend.apps.scheduler.schedules import scheduler

        return _text(json.dumps([schedule_to_dict(task) for task in scheduler.list()]))


class CronDeleteTool(BaseTool):
    name = "CronDelete"
    description = "Delete a scheduled agent run by its schedule ID."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"schedule_id": {"type": "string", "description": "Schedule ID."}},
            "required": ["schedule_id"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        from backend.apps.scheduler.schedules import scheduler

        try:
            await scheduler.delete(input_data["schedule_id"])
        except Exception as exc:
            return _text(f"Unable to delete schedule: {exc}")
        return _text(f"Deleted schedule {input_data['schedule_id']}.")
