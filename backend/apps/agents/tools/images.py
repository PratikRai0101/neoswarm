"""Approval-gated image generation tool."""

from __future__ import annotations

import json

from backend.apps.agents.tools.base import BaseTool, ToolContext
from backend.apps.images.images import image_service
from backend.apps.images.models import ImageGenerateRequest
from backend.apps.settings.settings import load_settings
from backend.apps.settings.models import AppSettings


class GenerateImageTool(BaseTool):
    name = "GenerateImage"
    description = (
        "Generate an image from a prompt using the configured OpenAI image provider "
        "and save it to the local Artifact workspace."
    )

    def __init__(self, settings: AppSettings | None = None):
        self._settings = settings

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Detailed image description."},
                "model": {
                    "type": "string",
                    "enum": ["gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"],
                    "default": "gpt-image-1.5",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1536x1024", "1024x1536", "auto"],
                    "default": "1024x1024",
                },
                "quality": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "auto"],
                    "default": "medium",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["png", "jpeg", "webp"],
                    "default": "png",
                },
                "background": {
                    "type": "string",
                    "enum": ["transparent", "opaque", "auto"],
                    "default": "auto",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        try:
            request = ImageGenerateRequest(**input_data)
            result = await image_service.generate(
                request, self._settings or load_settings()
            )
        except (OSError, ValueError) as exc:
            return [{"type": "text", "text": f"Error generating image: {exc}"}]

        artifact = result.artifact
        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "artifact": {
                            "id": artifact.id,
                            "name": artifact.name,
                            "filename": artifact.filename,
                            "media_type": artifact.media_type,
                            "size_bytes": artifact.size_bytes,
                        },
                        "revised_prompt": result.revised_prompt,
                    }
                ),
            }
        ]
