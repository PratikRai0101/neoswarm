from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


ImageModel = Literal["gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"]
ImageSize = Literal["1024x1024", "1536x1024", "1024x1536", "auto"]
ImageQuality = Literal["low", "medium", "high", "auto"]
ImageFormat = Literal["png", "jpeg", "webp"]
ImageBackground = Literal["transparent", "opaque", "auto"]


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32000)
    model: ImageModel = "gpt-image-1.5"
    size: ImageSize = "1024x1024"
    quality: ImageQuality = "medium"
    output_format: ImageFormat = "png"
    background: ImageBackground = "auto"

    @model_validator(mode="after")
    def validate_background_format(self) -> "ImageGenerateRequest":
        if self.background == "transparent" and self.output_format not in {"png", "webp"}:
            raise ValueError("Transparent backgrounds require PNG or WEBP output")
        if self.model == "gpt-image-2" and self.background == "transparent":
            raise ValueError("GPT Image 2 does not support transparent backgrounds")
        return self
