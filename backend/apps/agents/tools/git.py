"""Native tools for inspecting and explicitly committing local Git work."""

from __future__ import annotations

import json

from backend.apps.agents.tools.base import BaseTool, ToolContext
from backend.apps.git.git import GitService
from backend.apps.git.models import GitCommitRequest


def _text(value: str) -> list[dict]:
    return [{"type": "text", "text": value}]


_service = GitService()


class GitStatusTool(BaseTool):
    name = "GitStatus"
    description = "Inspect the current branch and working tree status for a local repository."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Repository path; defaults to the agent working directory."}},
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        try:
            status = await _service.status(input_data.get("path") or context.cwd)
            return _text(json.dumps(status.model_dump(mode="json")))
        except Exception as exc:
            return _text(f"Unable to inspect Git status: {exc}")


class GitDiffTool(BaseTool):
    name = "GitDiff"
    description = "Read the current Git diff, optionally for staged changes."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repository path; defaults to the agent working directory."},
                "staged": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        try:
            diff = await _service.diff(input_data.get("path") or context.cwd, bool(input_data.get("staged", False)))
            return _text(diff.diff or "Working tree has no matching diff.")
        except Exception as exc:
            return _text(f"Unable to read Git diff: {exc}")


class GitCommitTool(BaseTool):
    name = "GitCommit"
    description = "Create a Git commit when the user explicitly asks for a commit. Never commit unrelated changes."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repository path; defaults to the agent working directory."},
                "message": {"type": "string", "description": "Commit message."},
                "stage_all": {"type": "boolean", "default": False, "description": "Stage all changes before committing; use only when explicitly requested."},
            },
            "required": ["message"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        try:
            request = GitCommitRequest(
                path=input_data.get("path") or context.cwd,
                message=input_data["message"],
                stage_all=bool(input_data.get("stage_all", False)),
            )
            commit = await _service.commit(request)
            return _text(json.dumps(commit.model_dump(mode="json")))
        except Exception as exc:
            return _text(f"Unable to create Git commit: {exc}")
