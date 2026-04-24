# AGENTS.md — NeoSwarm Development Context

> Quick reference for developers working on NeoSwarm. Updated as we build.

---

## Vision: "Codex for Everything" — NeoSwarm

NeoSwarm aims to be a powerful local-first AI agent orchestrator similar to OpenAI's Codex app, with multi-agent coordination, computer use, and extensible tools.

---

## Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Fork + Rebrand | ✅ Complete | Forked from OpenSwarm, Tauri instead of Electron |
| Phase 2: Native Agent System | ✅ Complete | Ollama support, native AgentLoop |
| Phase 3: Orchestrator Agent | ✅ Complete | Multi-agent coordination |
| Phase 4: CLI + TUI | ✅ Complete | Basic CLI and TUI |
| Phase 5: Packaging | ✅ Complete | Tauri app with new icon |
| Phase 6: Codex-style Features | 🔄 In Progress | Auth, TUI, memory, automation |

---

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

---

## Architecture

### Stack
| Layer | Technology |
|-------|------------|
| Desktop Shell | Tauri (Rust) |
| UI (Native) | React/TypeScript |
| UI (TUI) | Textual (Python) |
| Backend | FastAPI + Uvicorn |
| Agents | Orchestrator + Worker agents |
| Tools | MCP + Bash + Browser |
| Models | Ollama + Anthropic + OpenAI + Google |

### Provider Model
The system uses a pluggable provider adapter pattern:
- **Ollama** (default, fully local) — no API key needed, runs on localhost:11434
- **Anthropic** — requires ANTHROPIC_API_KEY
- **OpenAI** — requires OPENAI_API_KEY
- **Google/Gemini** — requires GOOGLE_API_KEY
- **OpenRouter** — requires OPENROUTER_API_KEY

### Agent Loop
The native `AgentLoop` (`backend/apps/agents/agent_loop.py`) handles streaming, tool use, and HITL approvals in a provider-agnostic way.

### Environment Variables
- `NEOSWARM_PORT` — backend port (default: 8324)
- `NEOSWARM_PACKAGED` — set to "1" when running as Tauri app
- `ANTHROPIC_API_KEY` — Anthropic API key
- `OPENAI_API_KEY` — OpenAI API key
- `GOOGLE_API_KEY` — Google API key

### Cache / Data Directory
- User data: `~/.neoswarm/`
- Packaged data: `~/.local/share/NeoSwarm/data/`

---

## Features (Codex-style)

### Implemented ✅
| Feature | Description |
|--------|-------------|
| Multi-agent | Orchestrator coordinates multiple workers |
| Browser Agent | Computer use via browser automation |
| MCP Tools | 9+ built-in tools (Read, Write, Edit, Glob, Grep, etc.) |
| Local Models | Ollama support (fully offline) |
| Sessions | Chat session persistence |
| Tauri App | Native desktop app with new icon |

### To Build 🔄
| Feature | Priority | Description |
|---------|-----------|-------------|
| Auth System | High | Interactive provider setup (like OpenCode's `/connect`) |
| Model Switching | High | Change model mid-conversation |
| Enhanced Chat UI | High | Full message history, tool output display |
| Memory System | Medium | Persistent context across sessions |
| In-app Browser | Medium | Tauri webview integration |
| Scheduled Tasks | Medium | Automation with scheduling |
| 90+ Tools | Low | More MCP integrations |

---

## Roadmap

### Phase 7: Auth System (High Priority)
- [ ] `neoswarm auth login` command - Interactive provider setup
- [ ] `auth.json` storage at `~/.neoswarm/auth.json`
- [ ] Provider status in TUI
- [ ] Environment variable integration

### Phase 8: Enhanced TUI (High Priority)
- [ ] Chat panel with message history
- [ ] Model picker (switch mid-conversation)
- [ ] Session management (create, switch, delete)
- [ ] Tool output display
- [ ] Keyboard shortcuts (like OpenCode)

### Phase 9: Memory System (Medium Priority)
- [ ] Session context persistence
- [ ] User preferences storage
- [ ] Context carryover between sessions

### Phase 10: Advanced Features (Low Priority)
- [ ] In-app browser (Tauri webview)
- [ ] Scheduled/automated tasks
- [ ] More MCP server integrations
- [ ] Image generation tool

---

## CLI Commands Reference

```bash
# Chat with specific model
neoswarm chat --model sonnet

# Launch orchestrator mission
neoswarm launch "build a web scraper" --workers 3

# List available models
neoswarm models

# List sessions
neoswarm sessions

# Check backend status
neoswarm status

# Start backend server
neoswarm server
```

---

## Notes

- Backend imports use `backend.` prefix (e.g., `from backend.config.Apps import MainApp`)
- Run from project root with `PYTHONPATH=.`
- Health check is at `/api/health/check` not `/health`
- MCP server names: `neoswarm-browser-agent`, `neoswarm-invoke-agent`
- Default model: `sonnet` (Anthropic Sonnet 4.6)
- Default provider: Ollama (local, no API key needed)

---

## Comparison: NeoSwarm vs OpenAI Codex

| Feature | Codex | NeoSwarm |
|---------|-------|----------|
| Computer Use | ✅ macOS app control | ✅ Browser automation |
| Local Models | ❌ Cloud only | ✅ Ollama (fully local) |
| Multi-agent | ✅ Parallel agents | ✅ Orchestrator |
| Open Source | ❌ Proprietary | ✅ MIT License |
| Self-hosted | ❌ Requires OpenAI | ✅ Runs locally |

---

*Last updated: 2026-04-25*
*Building toward "Codex for Everything" - local-first AI agent orchestrator*