from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import signal
import shutil
import struct
import termios
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pty
from fastapi import HTTPException, WebSocket

from backend.apps.terminals.models import Terminal, TerminalCreate, TerminalResize
from backend.config.Apps import SubApp
from backend.config.paths import TERMINALS_DIR

_MAX_SCROLLBACK_BYTES = 200 * 1024
_MAX_INPUT_BYTES = 64 * 1024
_TERMINAL_ID = re.compile(r"^[a-f0-9]{32}$")


@dataclass
class _Runtime:
    terminal: Terminal
    process: asyncio.subprocess.Process
    master_fd: int
    scrollback: str = ""
    connections: set[WebSocket] = field(default_factory=set)
    output_task: asyncio.Task | None = None
    stop_requested: bool = False


class TerminalManager:
    """Own interactive PTY sessions behind a small lifecycle interface."""

    def __init__(self) -> None:
        self._runtimes: dict[str, _Runtime] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _validate_id(terminal_id: str) -> None:
        if not _TERMINAL_ID.fullmatch(terminal_id):
            raise HTTPException(status_code=404, detail="Terminal not found")

    @classmethod
    def _metadata_path(cls, terminal_id: str) -> Path:
        cls._validate_id(terminal_id)
        return Path(TERMINALS_DIR) / f"{terminal_id}.json"

    @classmethod
    def _read_metadata(cls, terminal_id: str) -> Terminal:
        path = cls._metadata_path(terminal_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Terminal not found")
        try:
            return Terminal(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="Terminal metadata is invalid") from exc

    @staticmethod
    def _save_metadata(terminal: Terminal) -> None:
        root = Path(TERMINALS_DIR)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{terminal.id}.json").write_text(
            json.dumps(terminal.model_dump(), indent=2), encoding="utf-8"
        )

    @classmethod
    def _load_all_metadata(cls) -> list[Terminal]:
        root = Path(TERMINALS_DIR)
        if not root.is_dir():
            return []
        result: list[Terminal] = []
        for path in root.glob("*.json"):
            try:
                terminal = Terminal(**json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
            result.append(terminal)
        return result

    @staticmethod
    def resolve_cwd(raw_cwd: str | None) -> str:
        cwd = Path(raw_cwd or Path.home()).expanduser().resolve()
        if not cwd.is_dir():
            raise ValueError(f"Working directory does not exist: {cwd}")
        return str(cwd)

    @staticmethod
    def resolve_shell(raw_shell: str | None) -> str:
        requested = (raw_shell or os.environ.get("SHELL") or "/bin/sh").strip()
        shell = Path(requested).expanduser() if os.path.isabs(requested) else Path(shutil.which(requested) or "")
        if not shell.is_file() or not os.access(shell, os.X_OK):
            raise ValueError(f"Shell is not executable: {requested}")
        return str(shell.resolve())

    @staticmethod
    def _title(cwd: str, requested: str | None) -> str:
        title = (requested or "").strip()
        return title[:100] if title else (Path(cwd).name or cwd)[-100:]

    async def create(self, request: TerminalCreate) -> Terminal:
        cwd = self.resolve_cwd(request.cwd)
        shell = self.resolve_shell(request.shell)
        terminal = Terminal(
            title=self._title(cwd, request.title),
            cwd=cwd,
            shell=shell,
            status="stopped",
        )
        self._save_metadata(terminal)
        await self._start(terminal)
        return terminal

    async def start(self, terminal_id: str) -> Terminal:
        terminal = self._runtimes.get(terminal_id).terminal if terminal_id in self._runtimes else self._read_metadata(terminal_id)
        if terminal.status == "running" and terminal_id in self._runtimes:
            return terminal
        if not Path(terminal.cwd).is_dir():
            raise ValueError(f"Working directory does not exist: {terminal.cwd}")
        await self._start(terminal)
        return terminal

    async def _start(self, terminal: Terminal) -> None:
        existing = self._runtimes.get(terminal.id)
        if existing:
            await self._stop_runtime(existing)

        if not hasattr(pty, "openpty"):
            raise ValueError("Interactive terminals are not supported on this platform")

        master_fd, slave_fd = pty.openpty()
        self._set_size(master_fd, cols=120, rows=36)
        environment = os.environ.copy()
        environment.setdefault("TERM", "xterm-256color")
        try:
            process = await asyncio.create_subprocess_exec(
                terminal.shell,
                "-il",
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=terminal.cwd,
                env=environment,
                start_new_session=True,
            )
        except Exception:
            os.close(master_fd)
            os.close(slave_fd)
            raise
        finally:
            try:
                os.close(slave_fd)
            except OSError:
                pass

        os.set_blocking(master_fd, False)
        terminal.status = "running"
        terminal.pid = process.pid
        terminal.exit_code = None
        terminal.updated_at = self._now()
        runtime = _Runtime(terminal=terminal, process=process, master_fd=master_fd)
        self._runtimes[terminal.id] = runtime
        self._save_metadata(terminal)
        runtime.output_task = asyncio.create_task(self._pump_output(runtime))

    async def _pump_output(self, runtime: _Runtime) -> None:
        try:
            while True:
                try:
                    chunk = os.read(runtime.master_fd, 65536)
                except BlockingIOError:
                    if runtime.process.returncode is not None:
                        break
                    await asyncio.sleep(0.03)
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                runtime.scrollback = (runtime.scrollback + text)[-_MAX_SCROLLBACK_BYTES:]
                await self._broadcast(runtime, {"event": "terminal:output", "data": text})
        finally:
            try:
                return_code = await runtime.process.wait()
            except Exception:
                return_code = None
            if self._runtimes.get(runtime.terminal.id) is runtime:
                runtime.terminal.status = "stopped" if runtime.stop_requested else "exited"
                runtime.terminal.pid = None
                runtime.terminal.exit_code = return_code
                runtime.terminal.updated_at = self._now()
                self._save_metadata(runtime.terminal)
                await self._broadcast(
                    runtime,
                    {
                        "event": "terminal:exit",
                        "data": {
                            "status": runtime.terminal.status,
                            "exit_code": return_code,
                        },
                    },
                )
            try:
                os.close(runtime.master_fd)
            except OSError:
                pass

    @staticmethod
    def _set_size(master_fd: int, *, cols: int, rows: int) -> None:
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, size)

    async def _broadcast(self, runtime: _Runtime, message: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for websocket in list(runtime.connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            runtime.connections.discard(websocket)

    def get(self, terminal_id: str) -> Terminal:
        self._validate_id(terminal_id)
        runtime = self._runtimes.get(terminal_id)
        if runtime:
            return runtime.terminal
        terminal = self._read_metadata(terminal_id)
        if terminal.status == "running":
            terminal.status = "stopped"
            terminal.pid = None
        return terminal

    def list(self) -> list[Terminal]:
        terminals = {terminal.id: terminal for terminal in self._load_all_metadata()}
        for terminal_id, runtime in self._runtimes.items():
            terminals[terminal_id] = runtime.terminal
        return sorted(terminals.values(), key=lambda item: item.updated_at, reverse=True)

    async def write(self, terminal_id: str, data: str) -> None:
        if not isinstance(data, str) or len(data.encode("utf-8")) > _MAX_INPUT_BYTES:
            raise ValueError("Terminal input is too large")
        runtime = self._runtimes.get(terminal_id)
        if not runtime or runtime.terminal.status != "running":
            raise ValueError("Terminal is not running")
        try:
            os.write(runtime.master_fd, data.encode("utf-8"))
        except OSError as exc:
            raise ValueError(f"Could not write to terminal: {exc}") from exc

    async def resize(self, terminal_id: str, request: TerminalResize) -> None:
        runtime = self._runtimes.get(terminal_id)
        if not runtime or runtime.terminal.status != "running":
            raise ValueError("Terminal is not running")
        self._set_size(runtime.master_fd, cols=request.cols, rows=request.rows)
        if runtime.process.pid:
            try:
                os.killpg(runtime.process.pid, signal.SIGWINCH)
            except OSError:
                pass

    async def interrupt(self, terminal_id: str) -> None:
        runtime = self._runtimes.get(terminal_id)
        if not runtime or runtime.terminal.status != "running":
            raise ValueError("Terminal is not running")
        try:
            os.killpg(runtime.process.pid, signal.SIGINT)
        except OSError as exc:
            raise ValueError(f"Could not interrupt terminal: {exc}") from exc

    async def _stop_runtime(self, runtime: _Runtime) -> None:
        runtime.stop_requested = True
        if runtime.process.returncode is None:
            try:
                os.killpg(runtime.process.pid, signal.SIGTERM)
            except OSError:
                try:
                    runtime.process.terminate()
                except ProcessLookupError:
                    pass
            try:
                await asyncio.wait_for(runtime.process.wait(), timeout=3)
            except asyncio.TimeoutError:
                try:
                    os.killpg(runtime.process.pid, signal.SIGKILL)
                except OSError:
                    runtime.process.kill()
                await runtime.process.wait()
        try:
            os.close(runtime.master_fd)
        except OSError:
            pass
        if runtime.output_task and runtime.output_task is not asyncio.current_task():
            try:
                await asyncio.wait_for(runtime.output_task, timeout=1)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                runtime.output_task.cancel()
        self._runtimes.pop(runtime.terminal.id, None)

    async def stop(self, terminal_id: str, *, delete: bool = False) -> Terminal:
        terminal = self.get(terminal_id)
        runtime = self._runtimes.get(terminal_id)
        if runtime:
            await self._stop_runtime(runtime)
        terminal.status = "stopped"
        terminal.pid = None
        terminal.updated_at = self._now()
        self._save_metadata(terminal)
        if delete:
            self._metadata_path(terminal_id).unlink(missing_ok=True)
        return terminal

    async def connect(self, terminal_id: str, websocket: WebSocket) -> None:
        terminal = self.get(terminal_id)
        await websocket.accept()
        runtime = self._runtimes.get(terminal_id)
        if runtime:
            runtime.connections.add(websocket)
        await websocket.send_json({"event": "terminal:state", "data": terminal.model_dump()})
        if runtime and runtime.scrollback:
            await websocket.send_json({"event": "terminal:output", "data": runtime.scrollback})

    def disconnect(self, terminal_id: str, websocket: WebSocket) -> None:
        runtime = self._runtimes.get(terminal_id)
        if runtime:
            runtime.connections.discard(websocket)

    async def handle_message(self, terminal_id: str, message: dict[str, Any]) -> dict[str, Any] | None:
        message_type = message.get("type")
        if message_type == "input":
            await self.write(terminal_id, message.get("data", ""))
            return None
        if message_type == "resize":
            await self.resize(
                terminal_id,
                TerminalResize(cols=message.get("cols"), rows=message.get("rows")),
            )
            return {"event": "terminal:state", "data": self.get(terminal_id).model_dump()}
        if message_type == "interrupt":
            await self.interrupt(terminal_id)
            return None
        if message_type == "ping":
            return {"event": "terminal:pong", "data": {}}
        raise ValueError("Unsupported terminal message")

    async def shutdown_all(self) -> None:
        for terminal_id in list(self._runtimes):
            try:
                await self.stop(terminal_id)
            except (HTTPException, ValueError):
                pass


terminal_manager = TerminalManager()


@asynccontextmanager
async def terminals_lifespan():
    Path(TERMINALS_DIR).mkdir(parents=True, exist_ok=True)
    yield
    await terminal_manager.shutdown_all()


terminals = SubApp("terminals", terminals_lifespan)


def _http_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@terminals.router.get("/list")
async def list_terminals():
    return {"terminals": [terminal.model_dump() for terminal in terminal_manager.list()]}


@terminals.router.post("/create", status_code=201)
async def create_terminal(body: TerminalCreate):
    try:
        terminal = await terminal_manager.create(body)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return terminal.model_dump()


@terminals.router.post("/{terminal_id}/start")
async def start_terminal(terminal_id: str):
    try:
        terminal = await terminal_manager.start(terminal_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return terminal.model_dump()


@terminals.router.post("/{terminal_id}/resize")
async def resize_terminal(terminal_id: str, body: TerminalResize):
    try:
        await terminal_manager.resize(terminal_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return {"ok": True}


@terminals.router.post("/{terminal_id}/interrupt")
async def interrupt_terminal(terminal_id: str):
    try:
        await terminal_manager.interrupt(terminal_id)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return {"ok": True}


@terminals.router.get("/{terminal_id}")
async def get_terminal(terminal_id: str):
    return terminal_manager.get(terminal_id).model_dump()


@terminals.router.delete("/{terminal_id}")
async def delete_terminal(terminal_id: str):
    try:
        await terminal_manager.stop(terminal_id, delete=True)
    except ValueError as exc:
        raise _http_error(exc) from exc
    return {"ok": True}
