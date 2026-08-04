"""Image generation service and artifact publishing behavior."""

import base64
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.apps.artifacts.artifacts as artifacts_api
import backend.apps.images.images as images_api
from backend.apps.agents.tools.images import GenerateImageTool
from backend.apps.agents.tools.base import ToolContext
from backend.apps.images.models import ImageGenerateRequest
from backend.apps.settings.models import AppSettings
from backend.main import app


class FakeImagesClient:
    last_request: dict = {}

    def __init__(self, api_key: str):
        assert api_key == "test-key"
        self.images = self

    async def generate(self, **kwargs):
        type(self).last_request = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(b"fake-png-bytes").decode(),
                    revised_prompt="A revised prompt",
                )
            ]
        )

    async def close(self):
        return None


@pytest.fixture
def image_store(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    monkeypatch.setattr(artifacts_api, "ARTIFACTS_DIR", str(root))
    monkeypatch.setattr(images_api, "AsyncOpenAI", FakeImagesClient)
    return root


@pytest.mark.asyncio
async def test_image_generation_publishes_local_artifact(image_store):
    request = ImageGenerateRequest(
        prompt="A geometric blue fox logo",
        model="gpt-image-1.5",
        size="1536x1024",
        quality="high",
        output_format="png",
        background="transparent",
    )

    result = await images_api.image_service.generate(
        request, AppSettings(openai_api_key="test-key")
    )

    assert result.revised_prompt == "A revised prompt"
    assert result.artifact.media_type == "image/png"
    assert result.artifact.filename.endswith(".png")
    assert (image_store / f"{result.artifact.id}.png").read_bytes() == b"fake-png-bytes"
    assert FakeImagesClient.last_request == {
        "model": "gpt-image-1.5",
        "prompt": "A geometric blue fox logo",
        "size": "1536x1024",
        "quality": "high",
        "output_format": "png",
        "background": "transparent",
    }


def test_image_generation_http_endpoint_returns_artifact(image_store, monkeypatch):
    monkeypatch.setattr(images_api, "load_settings", lambda: AppSettings(openai_api_key="test-key"))

    with TestClient(app) as client:
        response = client.post(
            "/api/images/generate",
            json={"prompt": "A green paper airplane", "output_format": "webp"},
        )

    assert response.status_code == 200
    assert response.json()["artifact"]["media_type"] == "image/webp"


@pytest.mark.asyncio
async def test_generate_image_tool_uses_settings_and_returns_artifact(image_store):
    context = ToolContext(cwd=".", session_id="image-test")
    tool = GenerateImageTool(settings=AppSettings(openai_api_key="test-key"))

    result = await tool.execute({"prompt": "A tiny red kite"}, context)

    assert result[0]["type"] == "text"
    assert "artifact" in result[0]["text"]
