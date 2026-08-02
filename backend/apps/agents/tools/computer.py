"""Native desktop computer-use tool with explicit permission gating."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Callable

from backend.apps.agents.tools.base import BaseTool, ToolContext
from backend.apps.computer.controller import ComputerController, create_controller


class ComputerUseTool(BaseTool):
    name = "ComputerUse"
    description = (
        "Control the local desktop with a screenshot, mouse, keyboard, or scroll action. "
        "Use only when the user explicitly asks for computer interaction; this tool is "
        "approval-gated by default."
    )

    def __init__(self, controller_factory: Callable[[], ComputerController] = create_controller):
        self._controller_factory = controller_factory

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["screenshot", "position", "move", "click", "type", "press", "hotkey", "scroll"],
                },
                "x": {"type": "integer", "description": "Absolute screen X coordinate."},
                "y": {"type": "integer", "description": "Absolute screen Y coordinate."},
                "button": {"type": "string", "enum": ["left", "middle", "right"], "default": "left"},
                "clicks": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
                "duration": {"type": "number", "minimum": 0, "maximum": 10, "default": 0},
                "text": {"type": "string", "description": "Text to type, limited to 10,000 characters."},
                "key": {"type": "string", "description": "Key name for a press action."},
                "keys": {"type": "array", "items": {"type": "string"}, "maxItems": 6, "description": "Keys for a hotkey combination."},
                "amount": {"type": "integer", "minimum": -10000, "maximum": 10000, "default": -5, "description": "Scroll amount; positive is up, negative is down."},
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        try:
            controller = self._controller_factory()
            action = input_data.get("action")
            if action == "screenshot":
                image = await asyncio.to_thread(controller.screenshot)
                encoded = base64.b64encode(image).decode("ascii")
                return [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encoded}},
                    {"type": "text", "text": "Desktop screenshot captured."},
                ]
            if action == "position":
                x, y = await asyncio.to_thread(controller.position)
                return [{"type": "text", "text": json.dumps({"x": x, "y": y})}]
            if action in {"move", "click"}:
                x, y = self._coordinates(input_data)
                if action == "move":
                    await asyncio.to_thread(controller.move, x, y, self._duration(input_data))
                    return [{"type": "text", "text": f"Moved pointer to ({x}, {y})."}]
                button = input_data.get("button", "left")
                clicks = int(input_data.get("clicks", 1))
                if button not in {"left", "middle", "right"} or not 1 <= clicks <= 3:
                    raise ValueError("button must be left, middle, or right and clicks must be 1-3")
                await asyncio.to_thread(controller.click, x, y, button, clicks)
                return [{"type": "text", "text": f"Clicked ({x}, {y}) with {button}."}]
            if action == "type":
                text = input_data.get("text")
                if not isinstance(text, str) or not text:
                    raise ValueError("text is required for type")
                if len(text) > 10_000:
                    raise ValueError("text must be 10,000 characters or fewer")
                await asyncio.to_thread(controller.type_text, text, self._duration(input_data))
                return [{"type": "text", "text": "Typed text into the focused application."}]
            if action == "press":
                key = input_data.get("key")
                if not isinstance(key, str) or not key:
                    raise ValueError("key is required for press")
                await asyncio.to_thread(controller.press, key)
                return [{"type": "text", "text": f"Pressed {key}."}]
            if action == "hotkey":
                keys = input_data.get("keys")
                if not isinstance(keys, list) or not 1 <= len(keys) <= 6 or not all(isinstance(key, str) and key for key in keys):
                    raise ValueError("keys must contain 1-6 non-empty key names")
                await asyncio.to_thread(controller.hotkey, keys)
                return [{"type": "text", "text": f"Pressed {'+'.join(keys)}."}]
            if action == "scroll":
                amount = int(input_data.get("amount", -5))
                if not -10_000 <= amount <= 10_000:
                    raise ValueError("amount must be between -10000 and 10000")
                await asyncio.to_thread(controller.scroll, amount)
                return [{"type": "text", "text": f"Scrolled by {amount}."}]
            raise ValueError(f"Unknown computer action: {action}")
        except Exception as exc:
            return [{"type": "text", "text": f"Computer control failed: {exc}"}]

    @staticmethod
    def _coordinates(input_data: dict) -> tuple[int, int]:
        try:
            x = int(input_data["x"])
            y = int(input_data["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("x and y coordinates are required") from exc
        if x < 0 or y < 0:
            raise ValueError("x and y coordinates must be non-negative")
        return x, y

    @staticmethod
    def _duration(input_data: dict) -> float:
        try:
            duration = float(input_data.get("duration", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("duration must be a number") from exc
        if not 0 <= duration <= 10:
            raise ValueError("duration must be between 0 and 10 seconds")
        return duration
