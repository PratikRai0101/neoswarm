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

### TUI (Terminal UI)
```bash
source backend/.venv/bin/activate
python -m cli.tui
```

### CLI
```bash
cd cli
pip install -e .
neoswarm --help
neoswarm models
neoswarm status
```

### Native App
```bash
# AppImage (recommended)
./src-tauri/target/release/bundle/appimage/NeoSwarm.AppDir/AppRun

# Or standalone binary
./src-tauri/target/release/neoswarm
```

### Health Check
```bash
curl http://localhost:8324/api/health/check
```

## Architecture Notes

### Provider Model
The system uses a pluggable provider adapter pattern:
- **Ollama** (default, fully local) — no API key needed
- **Anthropic** — requires ANTHROPIC_API_KEY
- **OpenAI** — requires OPENAI_API_KEY
- **Google/Gemini** — requires GOOGLE_API_KEY
- **OpenRouter** — requires OPENROUTER_API_KEY

### Agent Loop
The native `AgentLoop` (`backend/apps/agents/agent_loop.py`) replaces `claude_agent_sdk`.
It handles streaming, tool use, and HITL approvals in a provider-agnostic way.

### Environment Variables
Key env vars (formerly OPENSWARM_*):
- `NEOSWARM_PORT` — backend port (default: 8324)
- `NEOSWARM_PACKAGED` — set to "1" when running as Tauri app
- `NEOSWARM_ELECTRON_PATH` — path to electron (legacy, unused)

### Cache Directory
User data: `~/.neoswarm/` (formerly `~/.openswarm/`)
Packaged data: `~/.local/share/NeoSwarm/data/` (Linux), `~/Library/Application Support/NeoSwarm/data/` (macOS)

## Notes

- Backend imports use `backend.` prefix (e.g., `from backend.config.Apps import MainApp`)
- Run from project root with `PYTHONPATH=.`
- Health check is at `/api/health/check` not `/health`
- MCP server names: `neoswarm-browser-agent`, `neoswarm-invoke-agent`

---

## Roadmap

### In Progress
- [ ] Auth system (OpenCode-style: `neoswarm auth login`)
- [ ] Provider configuration (Anthropic, OpenAI, Ollama, Google)
- [ ] Model switching mid-conversation
- [ ] Enhanced TUI with full chat functionality

### TODO
- [ ] Fix standalone binary backend spawn
- [ ] Build release AppImage with working bundler

---

*Last updated: 2026-04-25*
*All 6 phases complete — moving to auth system and TUI enhancements*