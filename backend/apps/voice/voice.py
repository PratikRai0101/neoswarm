"""Dictation cleanup endpoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from pydantic import BaseModel

from backend.config.Apps import SubApp

logger = logging.getLogger(__name__)

POLISH_INPUT_CAP = 8_000

POLISH_SYSTEM = (
    "You clean up raw speech-to-text dictation. Return ONLY the cleaned text, nothing else. "
    "Fix punctuation, capitalization, and obvious homophone errors. Remove filler words (um, uh, "
    "like when used as filler, you know) and false starts. Apply spoken formatting commands: "
    "'new line'/'new paragraph' become real breaks, 'period'/'comma'/'question mark' become the "
    "mark when clearly dictated as punctuation. NEVER add content, never answer questions in the "
    "text, never translate, never wrap in quotes. Keep the speaker's words and tone; this is "
    "transcription cleanup, not rewriting."
)


@asynccontextmanager
async def voice_lifespan():
    yield


voice = SubApp("voice", voice_lifespan)


class PolishRequest(BaseModel):
    text: str
    # One-line hint about the dictation destination (e.g. a chat title), so names spell right.
    context: Optional[str] = None


class PolishResponse(BaseModel):
    text: str
    polished: bool


@voice.router.post("/polish")
async def polish(body: PolishRequest) -> dict:
    raw = (body.text or "").strip()
    if not raw:
        return PolishResponse(text="", polished=False).model_dump()
    if len(raw) > POLISH_INPUT_CAP:
        raw = raw[:POLISH_INPUT_CAP]

    from backend.apps.agents.auxiliary import generate_auxiliary_text

    prompt = raw
    if body.context:
        prompt = f"[Dictating into: {body.context}]\n{raw}"
    try:
        cleaned = await generate_auxiliary_text(
            prompt,
            system=POLISH_SYSTEM,
            max_tokens=min(2000, len(raw) + 500),
            preferred_tier="fast",
        )
    except Exception as exc:
        logger.warning("Dictation polish failed, returning raw text: %s", exc)
        return PolishResponse(text=raw, polished=False).model_dump()
    cleaned = (cleaned or "").strip().strip('"')
    if not cleaned:
        return PolishResponse(text=raw, polished=False).model_dump()
    return PolishResponse(text=cleaned, polished=True).model_dump()
