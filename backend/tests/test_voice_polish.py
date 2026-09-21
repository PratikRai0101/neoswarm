"""Phase E (upstream port): voice dictation polish."""

import pytest

from backend.apps.voice.voice import PolishRequest, polish


@pytest.mark.asyncio
async def test_polish_empty_returns_unpolished():
    result = await polish(PolishRequest(text="   "))
    assert result == {"text": "", "polished": False}


@pytest.mark.asyncio
async def test_polish_failure_returns_raw_text(monkeypatch):
    import backend.apps.agents.auxiliary as auxiliary

    async def _boom(*args, **kwargs):
        raise RuntimeError("no aux lane")

    monkeypatch.setattr(auxiliary, "generate_auxiliary_text", _boom)
    result = await polish(PolishRequest(text="um hello world"))
    assert result == {"text": "um hello world", "polished": False}


@pytest.mark.asyncio
async def test_polish_success_cleans_text(monkeypatch):
    import backend.apps.agents.auxiliary as auxiliary

    async def _clean(prompt, **kwargs):
        assert "um hello" in prompt
        return "Hello."

    monkeypatch.setattr(auxiliary, "generate_auxiliary_text", _clean)
    result = await polish(PolishRequest(text="um hello"))
    assert result == {"text": "Hello.", "polished": True}


@pytest.mark.asyncio
async def test_polish_empty_model_output_falls_back_to_raw(monkeypatch):
    import backend.apps.agents.auxiliary as auxiliary

    async def _empty(*args, **kwargs):
        return "  "

    monkeypatch.setattr(auxiliary, "generate_auxiliary_text", _empty)
    result = await polish(PolishRequest(text="hello there"))
    assert result == {"text": "hello there", "polished": False}
