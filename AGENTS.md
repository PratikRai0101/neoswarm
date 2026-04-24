# AGENTS.md — NeoSwarm Development Context

> Quick reference for developers working on NeoSwarm. Updated as we build.

## Current Phase

**Phase 1: Fork + Rebrand + Linux Foundation** — ✅ COMPLETE

## Phase 2: Native Agent System — ✅ COMPLETE

**What was done**:
- Added OllamaProvider for fully local model inference
- Added Ollama models to registry (llama3.3, qwen2.5, mistral, codellama, deepseek-coder)
- Swapped import priority: native AgentLoop first, mock fallback
- Removed 9Router from credentials, registry, analytics
- Backend runs without any cloud dependencies

## Phase 3: Orchestrator Agent — ✅ COMPLETE

**What was done**:
- Created OrchestratorAgent class in orchestrator.py
- Added SubTask and Worker dataclasses
- Added task decomposition (LLM + fallback)
- Added worker spawning and progress tracking
- Added result synthesis

## Running Backend

```bash
# Activate venv and run with PYTHONPATH
cd /home/raijinnn0101/Development/NeoSwarm
source backend/.venv/bin/activate
PYTHONPATH=. python -m uvicorn backend.main:app --host 127.0.0.1 --port 8324
```

## Testing

```bash
# Health check
curl http://localhost:8324/api/health/check

## Notes

- Backend imports use `backend.` prefix (e.g., `from backend.config.Apps import MainApp`)
- Run from project root with `PYTHONPATH=.`
- Health check is at `/api/health/check` not `/health`

---

*Last updated: 2026-04-24*

## Next Phase

**Phase 3: Orchestrator Agent** — Coming next
- Create OrchestratorAgent class
- Task decomposition and worker spawning
- Progress monitoring and result synthesis

## Phase 4: CLI + TUI (Future)
- Add OpenCode-style TUI
- Add Codex-style CLI

## Phase 5: Packaging (Future)
- Build AppImage for Linux
- Package for distribution