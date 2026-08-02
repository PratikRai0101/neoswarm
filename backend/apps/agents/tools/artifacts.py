"""Agent tool for publishing local files to the Artifact workspace."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.apps.agents.tools.base import BaseTool, ToolContext
from backend.apps.artifacts.artifacts import publish_file


class PublishArtifactTool(BaseTool):
    name = "PublishArtifact"
    description = (
        "Publish a local file to NeoSwarm's user-controlled Artifact workspace so it can "
        "be previewed or downloaded. Use only when the user asks to share or inspect a file."
    )

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path, relative to the agent working directory or absolute.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional display filename.",
                    "maxLength": 255,
                },
                "description": {
                    "type": "string",
                    "description": "Optional short description shown in the Artifact workspace.",
                    "maxLength": 1000,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        raw_path = input_data.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return [{"type": "text", "text": "Error: path is required."}]

        source = Path(raw_path).expanduser()
        if not source.is_absolute():
            source = Path(context.cwd) / source

        try:
            artifact = await asyncio.to_thread(
                publish_file,
                source,
                name=input_data.get("name"),
                description=input_data.get("description", ""),
            )
        except (OSError, ValueError) as exc:
            return [{"type": "text", "text": f"Error publishing artifact: {exc}"}]

        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "id": artifact.id,
                        "name": artifact.name,
                        "description": artifact.description,
                        "filename": artifact.filename,
                        "media_type": artifact.media_type,
                        "size_bytes": artifact.size_bytes,
                    }
                ),
            }
        ]
