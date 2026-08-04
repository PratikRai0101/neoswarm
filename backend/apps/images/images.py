from __future__ import annotations

import base64
import binascii
import mimetypes
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import HTTPException
from openai import AsyncOpenAI

from backend.apps.artifacts.artifacts import publish_bytes
from backend.apps.artifacts.models import Artifact
from backend.apps.images.models import ImageGenerateRequest
from backend.apps.settings.models import AppSettings
from backend.apps.settings.settings import load_settings
from backend.config.Apps import SubApp


class GeneratedImageResponse:
    def __init__(self, artifact: Artifact, revised_prompt: str | None = None):
        self.artifact = artifact
        self.revised_prompt = revised_prompt

    def model_dump(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.model_dump(),
            "revised_prompt": self.revised_prompt,
        }


class ImageGenerationService:
    async def generate(
        self,
        request: ImageGenerateRequest,
        settings: AppSettings,
    ) -> GeneratedImageResponse:
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key not configured. Set it in Settings.")

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        try:
            try:
                response = await client.images.generate(
                    model=request.model,
                    prompt=request.prompt,
                    size=request.size,
                    quality=request.quality,
                    output_format=request.output_format,
                    background=request.background,
                )
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"Image provider request failed: {exc}") from exc
            if not response.data:
                raise ValueError("Image provider returned no image")
            image = response.data[0]
            image_bytes = await self._image_bytes(image)
        finally:
            await client.close()

        extension = request.output_format
        media_type = mimetypes.types_map.get(f".{extension}", f"image/{extension}")
        artifact = publish_bytes(
            image_bytes,
            name=f"generated-image.{extension}",
            media_type=media_type,
            description=f"Generated image: {request.prompt[:500]}",
        )
        return GeneratedImageResponse(
            artifact=artifact,
            revised_prompt=getattr(image, "revised_prompt", None),
        )

    @staticmethod
    async def _image_bytes(image: Any) -> bytes:
        encoded = getattr(image, "b64_json", None)
        if encoded:
            try:
                return base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Image provider returned invalid base64 data") from exc

        url = getattr(image, "url", None)
        if not url:
            raise ValueError("Image provider returned neither image data nor a URL")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content


image_service = ImageGenerationService()


@asynccontextmanager
async def images_lifespan():
    yield


images = SubApp("images", images_lifespan)


def _error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@images.router.post("/generate")
async def generate_image(body: ImageGenerateRequest):
    try:
        result = await image_service.generate(body, load_settings())
        return result.model_dump()
    except (OSError, ValueError, httpx.HTTPError) as exc:
        raise _error(ValueError(str(exc))) from exc
