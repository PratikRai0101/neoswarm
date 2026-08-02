"""Artifact publishing and preview API behavior."""

import json

import pytest
from fastapi.testclient import TestClient

import backend.apps.artifacts.artifacts as artifacts_api
from backend.apps.agents.tools.artifacts import PublishArtifactTool
from backend.apps.agents.tools.base import ToolContext
from backend.apps.artifacts.artifacts import publish_file
from backend.main import app


@pytest.fixture
def artifact_store(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    monkeypatch.setattr(artifacts_api, "ARTIFACTS_DIR", str(root))
    return root


def test_publish_list_preview_download_and_delete_artifact(artifact_store, tmp_path):
    source = tmp_path / "report.csv"
    source.write_text("name,total\nNeoSwarm,42\n", encoding="utf-8")

    artifact = publish_file(source, description="A test report")
    assert artifact.filename == "report.csv"
    assert artifact.media_type == "text/csv"
    assert artifact.size_bytes == source.stat().st_size

    with TestClient(app) as client:
        listed = client.get("/api/artifacts/list")
        assert listed.status_code == 200
        assert listed.json()["artifacts"][0]["id"] == artifact.id

        preview = client.get(f"/api/artifacts/{artifact.id}/content")
        assert preview.status_code == 200
        assert preview.text == "name,total\nNeoSwarm,42\n"
        assert preview.headers["content-type"].startswith("text/csv")
        assert "inline" in preview.headers["content-disposition"]

        download = client.get(f"/api/artifacts/{artifact.id}/download")
        assert download.status_code == 200
        assert "attachment" in download.headers["content-disposition"]
        assert download.content == source.read_bytes()

        deleted = client.delete(f"/api/artifacts/{artifact.id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/artifacts/{artifact.id}").status_code == 404


@pytest.mark.asyncio
async def test_publish_artifact_tool_uses_agent_working_directory(artifact_store, tmp_path):
    source = tmp_path / "summary.md"
    source.write_text("# Summary\n\nDone.\n", encoding="utf-8")
    context = ToolContext(cwd=str(tmp_path), session_id="artifact-test")

    result = await PublishArtifactTool().execute(
        {"path": "summary.md", "description": "Mission summary"}, context
    )

    payload = json.loads(result[0]["text"])
    assert payload["name"] == "summary.md"
    assert payload["description"] == "Mission summary"
    assert payload["media_type"] == "text/markdown"
    assert (artifact_store / f"{payload['id']}.md").read_bytes() == source.read_bytes()


def test_publish_artifact_rejects_files_above_limit(artifact_store, tmp_path, monkeypatch):
    source = tmp_path / "large.bin"
    source.write_bytes(b"0123456789")
    monkeypatch.setattr(artifacts_api, "MAX_ARTIFACT_BYTES", 4)

    with pytest.raises(ValueError, match="too large"):
        publish_file(source)
