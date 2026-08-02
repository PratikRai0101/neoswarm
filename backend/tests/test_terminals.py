"""Terminal session lifecycle and streaming behavior."""

from fastapi.testclient import TestClient

import backend.apps.terminals.terminals as terminals_api
from backend.main import app


def test_terminal_can_start_stream_input_resize_interrupt_and_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(terminals_api, "TERMINALS_DIR", str(tmp_path / "terminals"))

    with TestClient(app) as client:
        created_response = client.post(
            "/api/terminals/create",
            json={"cwd": str(tmp_path), "shell": "/bin/sh", "title": "Test shell"},
        )
        assert created_response.status_code == 201
        created = created_response.json()
        terminal_id = created["id"]
        assert created["cwd"] == str(tmp_path)
        assert created["title"] == "Test shell"
        assert created["status"] == "running"

        listed = client.get("/api/terminals/list")
        assert listed.status_code == 200
        assert listed.json()["terminals"][0]["id"] == terminal_id

        with client.websocket_connect(f"/ws/terminals/{terminal_id}") as websocket:
            initial = websocket.receive_json()
            assert initial["event"] == "terminal:state"
            assert initial["data"]["id"] == terminal_id

            websocket.send_json({"type": "input", "data": "printf 'neoswarm-terminal-test\\n'\n"})
            output = ""
            for _ in range(12):
                message = websocket.receive_json()
                if message["event"] == "terminal:output":
                    output += message["data"]
                    if "neoswarm-terminal-test" in output:
                        break
            assert "neoswarm-terminal-test" in output

            resized = client.post(
                f"/api/terminals/{terminal_id}/resize",
                json={"cols": 120, "rows": 40},
            )
            assert resized.status_code == 200
            assert resized.json()["ok"] is True

            interrupted = client.post(f"/api/terminals/{terminal_id}/interrupt")
            assert interrupted.status_code == 200
            assert interrupted.json()["ok"] is True

        stopped = client.delete(f"/api/terminals/{terminal_id}")
        assert stopped.status_code == 200
        assert stopped.json()["ok"] is True


def test_terminal_rejects_missing_working_directory(tmp_path):
    with TestClient(app) as client:
        response = client.post(
            "/api/terminals/create",
            json={"cwd": str(tmp_path / "does-not-exist")},
        )
    assert response.status_code == 400
    assert "working directory" in response.json()["detail"].lower()
