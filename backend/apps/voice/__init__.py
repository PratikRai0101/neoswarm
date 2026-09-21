"""Dictation cleanup service (ported from upstream `voice/polish`).

Raw speech-to-text becomes punctuated, filler-free prose via the cheap aux
tier. Every failure path returns the RAW text so dictation never breaks when
the aux lane is unreachable.
"""

from backend.apps.voice.voice import voice

__all__ = ["voice"]
