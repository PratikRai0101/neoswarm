"""Safety and dispatch tests for the native computer-use tool."""

import base64

import pytest

from backend.apps.agents.tools.base import ToolContext
from backend.apps.agents.tools.computer import ComputerUseTool


class FakeComputer:
    def __init__(self):
        self.calls = []

    def screenshot(self):
        self.calls.append(("screenshot",))
        return b"png-bytes"

    def position(self):
        self.calls.append(("position",))
        return 10, 20

    def move(self, x, y, duration=0):
        self.calls.append(("move", x, y, duration))

    def click(self, x, y, button="left", clicks=1):
        self.calls.append(("click", x, y, button, clicks))

    def type_text(self, text, interval=0):
        self.calls.append(("type", text, interval))

    def press(self, key):
        self.calls.append(("press", key))

    def hotkey(self, keys):
        self.calls.append(("hotkey", keys))

    def scroll(self, amount):
        self.calls.append(("scroll", amount))


@pytest.fixture
def fake():
    return FakeComputer()


@pytest.fixture
def tool(fake):
    return ComputerUseTool(lambda: fake)


@pytest.fixture
def context(tmp_path):
    return ToolContext(cwd=str(tmp_path), session_id="computer-test")


@pytest.mark.asyncio
async def test_screenshot_returns_provider_compatible_image_block(tool, fake, context):
    result = await tool.execute({"action": "screenshot"}, context)

    assert result[0]["type"] == "image"
    assert base64.b64decode(result[0]["source"]["data"]) == b"png-bytes"
    assert fake.calls == [("screenshot",)]


@pytest.mark.asyncio
async def test_mouse_keyboard_and_scroll_actions_are_dispatched(tool, fake, context):
    await tool.execute({"action": "move", "x": 100, "y": 200, "duration": 0.2}, context)
    await tool.execute({"action": "click", "x": 100, "y": 200, "button": "right", "clicks": 2}, context)
    await tool.execute({"action": "type", "text": "hello"}, context)
    await tool.execute({"action": "press", "key": "enter"}, context)
    await tool.execute({"action": "hotkey", "keys": ["ctrl", "l"]}, context)
    await tool.execute({"action": "scroll", "amount": -4}, context)

    assert fake.calls == [
        ("move", 100, 200, 0.2),
        ("click", 100, 200, "right", 2),
        ("type", "hello", 0),
        ("press", "enter"),
        ("hotkey", ["ctrl", "l"]),
        ("scroll", -4),
    ]


@pytest.mark.asyncio
async def test_invalid_actions_are_rejected_without_controller_calls(tool, fake, context):
    missing_coordinates = await tool.execute({"action": "click", "x": 1}, context)
    oversized_text = await tool.execute({"action": "type", "text": "x" * 10_001}, context)
    invalid_hotkey = await tool.execute({"action": "hotkey", "keys": []}, context)

    assert "coordinates" in missing_coordinates[0]["text"]
    assert "10,000" in oversized_text[0]["text"]
    assert "1-6" in invalid_hotkey[0]["text"]
    assert fake.calls == []
