"""Host SDK for vibe-coded apps (ported from upstream `apps_sdk`).

Lets output views call back to the host: LLM text, MCP tools through a
per-app grant gate, and agent spawning. Identity is server-derived (minted
token or serve-path Referer) — a self-reported output id is never trusted.
"""

from backend.apps.applications.apps import apps
from backend.apps.applications import grants, identity

__all__ = ["apps", "grants", "identity"]
