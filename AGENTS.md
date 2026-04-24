# AGENTS.md — NeoSwarm Development Context

> Quick reference for developers working on NeoSwarm. Updated as we build.

## All Phases Complete! ✅

### Phase 1: Fork + Rebrand + Linux Foundation — ✅ COMPLETE
- Copied from OpenSwarm
- Removed Electron (replaced by Tauri)
- Created README, LICENSE, NOTICE

### Phase 2: Native Agent System — ✅ COMPLETE
- Added OllamaProvider for fully local model inference
- Added Ollama models to registry (llama3.3, qwen2.5, mistral, codellama, deepseek-coder)
- Swapped import priority: native AgentLoop first, mock fallback
- Removed 9Router from credentials, registry, analytics
- Backend runs without any cloud dependencies

### Phase 3: Orchestrator Agent — ✅ COMPLETE
- Created OrchestratorAgent class in orchestrator.py
- Added SubTask and Worker dataclasses
- Added task decomposition (LLM + fallback)
- Added worker spawning and progress tracking
- Added result synthesis

### Phase 4: CLI + TUI — ✅ COMPLETE
- Added CLI with Click (chat, launch, status, models, sessions)
- Added TUI with Textual (rich terminal UI)
- Created setup.py entry point

### Phase 5: Packaging — ✅ COMPLETE
- Built Tauri v2 native app (debug binary: 224MB)
- Added icons for Linux/Windows/macOS
- Native desktop shell replaces Electron

## Running the App

### Backend
```bash
cd /home/raijinnn0101/Development/NeoSwarm
source backend/.venv/bin/activate
PYTHONPATH=. python -m uvicorn backend.main:app --host 127.0.0.1 --port 8324
```

### CLI
```bash
cd cli
python main.py --help
python main.py models
python main.py status
```

### Native App
```bash
./src-tauri/target/debug/neoswarm
```

### Health Check
```bash
curl http://localhost:8324/api/health/check
```

## Notes

- Backend imports use `backend.` prefix (e.g., `from backend.config.Apps import MainApp`)
- Run from project root with `PYTHONPATH=.`
- Health check is at `/api/health/check` not `/health`

---

*Last updated: 2026-04-24*
*All 5 phases complete - app is ready!*