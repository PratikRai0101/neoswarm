"""SSH profile persistence and safe command construction."""

from fastapi.testclient import TestClient

import backend.apps.ssh.ssh as ssh_api
import backend.apps.terminals.terminals as terminals_api
from backend.apps.ssh.models import SSHProfile
from backend.apps.ssh.ssh import ssh_service
from backend.main import app


def test_ssh_profile_crud_does_not_store_private_key_material(tmp_path, monkeypatch):
    monkeypatch.setattr(ssh_api, "SSH_PROFILES_DIR", str(tmp_path / "ssh"))

    with TestClient(app) as client:
        created_response = client.post(
            "/api/ssh/profiles",
            json={
                "name": "Production",
                "host": "server.example.com",
                "user": "deploy",
                "port": 2222,
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()
        assert created["target"] == "deploy@server.example.com:2222"
        assert "private_key" not in created

        listed = client.get("/api/ssh/profiles")
        assert listed.status_code == 200
        assert listed.json()["profiles"][0]["id"] == created["id"]

        deleted = client.delete(f"/api/ssh/profiles/{created['id']}")
        assert deleted.status_code == 200
        assert client.get(f"/api/ssh/profiles/{created['id']}").status_code == 404


def test_ssh_command_uses_argument_list_and_identity_path(tmp_path):
    identity = tmp_path / "id_ed25519"
    identity.write_text("not a private key for this test")
    profile = SSHProfile(
        name="Staging",
        host="staging.example.com",
        user="ubuntu",
        port=2201,
        identity_file=str(identity),
    )

    assert ssh_service.command(profile) == [
        "ssh",
        "-tt",
        "-p",
        "2201",
        "-i",
        str(identity.resolve()),
        "ubuntu@staging.example.com",
    ]


def test_ssh_profile_rejects_option_injection():
    with TestClient(app) as client:
        response = client.post(
            "/api/ssh/profiles",
            json={"name": "Bad", "host": "--proxy-command=evil"},
        )
    assert response.status_code == 422


def test_ssh_profile_can_open_a_remote_terminal_tab(tmp_path, monkeypatch):
    monkeypatch.setattr(ssh_api, "SSH_PROFILES_DIR", str(tmp_path / "ssh"))
    monkeypatch.setattr(terminals_api, "TERMINALS_DIR", str(tmp_path / "terminals"))
    monkeypatch.setattr(ssh_service, "command", lambda _profile: ["/bin/sh", "-il"])

    with TestClient(app) as client:
        profile = client.post(
            "/api/ssh/profiles",
            json={"name": "Remote", "host": "server.example.com", "user": "dev"},
        ).json()
        terminal = client.post(
            "/api/terminals/create",
            json={"cwd": str(tmp_path), "ssh_profile_id": profile["id"]},
        )
        assert terminal.status_code == 201
        assert terminal.json()["connection"] == "ssh"
        assert terminal.json()["target"] == "dev@server.example.com:22"
        assert client.delete(f"/api/terminals/{terminal.json()['id']}").status_code == 200
