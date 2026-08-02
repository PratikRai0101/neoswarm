"""Cross-platform local desktop control behind a small testable seam."""

from __future__ import annotations

import io
from typing import Any, Protocol


class ComputerControlUnavailable(RuntimeError):
    """Raised when the host cannot provide desktop-control capabilities."""


class ComputerController(Protocol):
    def screenshot(self) -> bytes: ...

    def position(self) -> tuple[int, int]: ...

    def move(self, x: int, y: int, duration: float = 0) -> None: ...

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None: ...

    def type_text(self, text: str, interval: float = 0) -> None: ...

    def press(self, key: str) -> None: ...

    def hotkey(self, keys: list[str]) -> None: ...

    def scroll(self, amount: int) -> None: ...


class PyAutoGUIController:
    """Adapter around PyAutoGUI, imported only when the tool is actually used."""

    def __init__(self, module: Any):
        self._pyautogui = module
        # Keep the emergency-corner failsafe enabled. A user can move the mouse
        # to the top-left corner to interrupt a long-running action sequence.
        self._pyautogui.FAILSAFE = True
        self._pyautogui.PAUSE = 0.05

    def screenshot(self) -> bytes:
        image = self._pyautogui.screenshot()
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def position(self) -> tuple[int, int]:
        point = self._pyautogui.position()
        return int(point.x), int(point.y)

    def move(self, x: int, y: int, duration: float = 0) -> None:
        self._pyautogui.moveTo(x, y, duration=max(0, duration))

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        self._pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=0.1)

    def type_text(self, text: str, interval: float = 0) -> None:
        self._pyautogui.write(text, interval=max(0, interval))

    def press(self, key: str) -> None:
        self._pyautogui.press(key)

    def hotkey(self, keys: list[str]) -> None:
        self._pyautogui.hotkey(*keys)

    def scroll(self, amount: int) -> None:
        self._pyautogui.scroll(amount)


def create_controller() -> ComputerController:
    """Create the host controller or return an actionable setup error."""
    try:
        import pyautogui
    except ImportError as exc:
        raise ComputerControlUnavailable(
            "Native computer control requires the optional 'pyautogui' package."
        ) from exc
    except Exception as exc:
        raise ComputerControlUnavailable(
            f"Native computer control could not initialize: {exc}"
        ) from exc
    return PyAutoGUIController(pyautogui)
