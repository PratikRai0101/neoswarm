"""Source/frozen process command contracts for the desktop backend."""

import io
import json
import sys

import pytest

from backend.apps.outputs.executor import execute_backend_code
from backend.config import runtime
from backend.standalone import _run_internal


def test_internal_server_command_switches_for_frozen_runtime(monkeypatch):
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "executable", "/bundle/neoswarm-backend")

    command, args = runtime.internal_server_command("browser-agent-mcp")

    assert command == "/bundle/neoswarm-backend"
    assert args == ["--internal", "browser-agent-mcp"]


def test_bundled_python_exec_mode_captures_stdout_and_result(monkeypatch):
    payload = {
        "code": "print('working')\nresult = {'answer': input_data['value'] * 2}",
        "input_data": {"value": 21},
    }
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", output)

    _run_internal("python-exec")

    assert json.loads(output.getvalue()) == {
        "__stdout__": "working\n",
        "__result__": {"answer": 42},
    }


@pytest.mark.asyncio
async def test_development_output_execution_still_uses_python_child():
    executed = await execute_backend_code(
        "print('hello')\nresult = {'name': input_data['name']}",
        {"name": "NeoSwarm"},
    )

    assert executed.stdout == "hello\n"
    assert executed.result == {"name": "NeoSwarm"}
