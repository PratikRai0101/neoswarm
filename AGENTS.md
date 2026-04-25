# AGENTS.md — NeoSwarm Development Context

> Quick reference for developers working on NeoSwarm. Updated as we build.

---

## Vision: "Codex for Everything" — NeoSwarm

NeoSwarm aims to be a powerful local-first AI agent orchestrator similar to OpenAI's Codex app, with multi-agent coordination, computer use, and extensible tools.

---

## Build Structure

```
┌─────────────────────────────────────────────────────┐
│                 NeoSwarm Backend                    │
│         (Auth, Providers, Agents, API)              │
├─────────────────────────────────────────────────────┤
│                        │                            │
│           ┌───────────┴───────────┐                 │
│           ▼                       ▼                 │
│    ┌──────────────┐      ┌──────────────┐           │
│    │   TUI App    │      │  Native App  │           │
│    │  (Textual)   │      │   (Tauri)    │           │
│    │              │      │              │           │
│    │ OpenCode     │      │ Codex-style  │           │
│    │  style TUI   │      │  Everything  │           │
│    └──────────────┘      └──────────────┘           │
└─────────────────────────────────────────────────────┘
```

---

## Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Fork + Rebrand | ✅ Complete | Forked from OpenSwarm, Tauri instead of Electron |
| Phase 2: Native Agent System | ✅ Complete | Ollama support, native AgentLoop |
| Phase 3: Orchestrator Agent | ✅ Complete | Multi-agent coordination |
| Phase 4: CLI + TUI | ✅ Complete | Basic CLI and TUI |
| Phase 5: Packaging | ✅ Complete | Tauri app with custom icon |
| Phase 6: Codex-style Features | ✅ Complete | Auth System |
| Phase 7: Enhanced TUI | ✅ Complete | TUI (OpenCode-style) |
| Phase 8: Native App Enhancements | 🔄 In Progress | Native App (Codex-style) |

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

### Orchestrator Modes
The orchestrator supports **both sequential and parallel** execution modes:
- **Sequential**: Workers complete tasks one by one (better for dependent tasks)
- **Parallel**: Workers run simultaneously (better for independent tasks)
- **User Choice**: Users can select mode when launching a mission

### Computer Use
NeoSwarm supports two levels of computer automation:
- **Browser Automation** ✅ (Current): Controls web browsers for web automation, testing, scraping
- **Native App Control** 🔄 (Future): Controls native applications (Linux first, then macOS)

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

## Complete Feature Roadmap

### STEP 1: Authentication System (Backend Core) 🔧

| Feature | OpenCode-style | Description |
|---------|----------------|--------------|
| `neoswarm auth login` | ✅ | Interactive provider setup |
| `neoswarm auth logout` | ✅ | Remove credentials |
| `neoswarm auth status` | ✅ | Show connected providers |
| Auth storage | ✅ | `~/.neoswarm/auth.json` |
| API key input | ✅ | Manual key entry |
| OAuth (future) | 🔄 | Browser-based auth |
| Env var priority | ✅ | ENV > auth.json > settings |

**Files:** `backend/apps/settings/`, `cli/main.py`

### STEP 2a: OpenCode-style TUI App 💻

| Feature | OpenCode | Description |
|---------|----------|--------------|
| Chat interface | ✅ | Message input + history |
| Model switching | ✅ | Switch mid-chat (`/model`) |
| Provider status | ✅ | Show connected providers |
| Session management | ✅ | Create/switch sessions |
| Tools panel | ✅ | List MCP tools |
| Keyboard shortcuts | ✅ | ^n, ^s, ^r bindings |
| Command palette | ✅ | Quick actions |
| Streaming responses | ✅ | Real-time output |

**Files:** `cli/tui.py`

### STEP 2b: Codex-style Native App 🖥️

| Feature | OpenAI Codex | NeoSwarm | Priority |
|---------|--------------|----------|----------|
| Computer Use | ✅ macOS app control | ✅ Browser automation + 🔄 Native App Control (Linux first, then macOS) | High |
| In-app Browser | ✅ Local servers + web | 🔄 Tauri webview | High |
| Image Generation | ✅ gpt-image-1.5 | 🔄 Future tool | Low |
| Memory | ✅ Persistent | 🔄 Session context | Medium |
| 90+ Plugins | ✅ MCP servers | ✅ Have 9+ tools | Done |
| Multi-agent | ✅ Parallel | ✅ Orchestrator (sequential or parallel - user choice) | Done |
| Automations | ✅ Scheduled tasks | 🔄 Future | Low |
| Git Integration | ✅ PR review, commits | 🔄 Bash tools | Medium |
| Artifact Viewer | ✅ PDF, spreadsheets | 🔄 Future | Low |
| Terminal | ✅ Multiple tabs | 🔄 Future | Low |
| SSH | ✅ Remote devboxes | 🔄 Future | Low |

**Files:** `src-tauri/`, `frontend/`

---

## Detailed Feature Comparison

### TUI Features (OpenCode-style)

| Feature | Command | Description |
|---------|----------|--------------|
| Chat | Default view | Send messages, see responses |
| New Chat | `^n` or `/new` | Start new session |
| Model Switch | `/model [name]` | Change active model |
| List Models | `/models` | Show available models |
| Auth | `/connect` | Connect provider |
| Settings | `/settings` | Configure app |
| Quit | `^q` | Exit TUI |

### Native App Features (Codex-style)

| Feature | Status | Description |
|---------|--------|-------------|
| Multi-agent | ✅ | Orchestrator coordinates workers |
| Browser Agent | ✅ | Computer use via browser |
| MCP Tools | ✅ | 9+ built-in tools |
| Sessions | ✅ | Chat session persistence |
| Model Switching | 🔄 | Change mid-conversation |
| Auth System | 🔄 | Interactive provider setup |
| In-app Browser | 🔄 | Tauri webview |
| Memory | 🔄 | Persistent context |
| Scheduled Tasks | 🔄 | Automation |
| Git Tools | 🔄 | Via Bash |
| Image Gen | 🔄 | Future |

---

## Implementation Priority

### Phase 7: Auth System (High Priority)
- [x] `neoswarm auth login` command - Interactive provider setup
- [x] Settings storage at `~/.neoswarm/settings.json` (via backend)
- [x] `neoswarm auth status` - Provider status
- [x] `neoswarm auth logout` - Remove credentials
- [x] Environment variable integration (ENV > settings.json > defaults)

### Phase 8: Enhanced TUI (High Priority)
- [x] Chat panel with message history
- [x] Model picker (switch mid-conversation)
- [x] Session management (create, switch, delete)
- [x] Tool output display
- [x] Keyboard shortcuts (like OpenCode)

### Phase 9: Native App Enhancements (Medium Priority)
- [ ] Full message history
- [ ] Tool output panel
- [ ] Settings panel
- [ ] In-app browser (Tauri webview)

### Phase 10: Advanced Features (Low Priority)
- [ ] Memory system
- [ ] Scheduled/automated tasks
- [ ] More MCP server integrations
- [ ] Image generation tool

---

## CLI Commands Reference

```bash
# Authentication
neoswarm auth login        # Interactive provider setup
neoswarm auth logout      # Remove credentials
neoswarm auth status      # Show connected providers

# Chat
neoswarm chat --model sonnet    # Chat with specific model
neoswarm chat --model haiku     # Chat with haiku

# Orchestrator
neoswarm launch "build a web scraper" --workers 3

# Info
neoswarm models           # List available models
neoswarm sessions         # List sessions
neoswarm status           # Check backend status
neoswarm server           # Start backend server
```

---

## Files to Modify

| Layer | Files |
|-------|-------|
| **Backend Auth** | `backend/apps/settings/`, `backend/apps/settings/models.py` |
| **CLI Commands** | `cli/main.py` |
| **TUI** | `cli/tui.py` |
| **Native App** | `src-tauri/`, `frontend/` (rebuild) |

---

## Comparison: NeoSwarm vs OpenAI Codex

| Feature | Codex | NeoSwarm |
|---------|-------|----------|
| Computer Use | ✅ macOS app control | ✅ Browser automation + Native app control (Linux/macOS) |
| Local Models | ❌ Cloud only | ✅ Ollama (fully local) |
| Multi-agent | ✅ Parallel agents | ✅ Orchestrator |
| Open Source | ❌ Proprietary | ✅ MIT License |
| Self-hosted | ❌ Requires OpenAI | ✅ Runs locally |

---

## Swarm Architecture: Orchestrator vs Parallel Agents

### Option 1: Orchestrator (NeoSwarm's Approach) 🤖

```
         ┌─────────────┐
         │   Mission   │
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │ Manager/    │
         │ Orchestrator│
         └──────┬──────┘
                │
    ┌─────────┼─────────┐
    │         │         │
┌───▼───┐ ┌──▼───┐ ┌──▼───┐
│Worker1│ │Worker2│ │Worker3│
│  FE   │ │  BE   │ │ Tests│
└───┬───┘ └───┬───┘ └───┬───┘
    │         │         │
    └─────────┼─────────┘
              │
       ┌─────▼─────┐
       │  Manager   │
       │ Synthesizes│
       │   Result  │
       └───────────┘
```

**How it works:**
- 1 Manager receives the mission
- Manager breaks it into subtasks
- Manager assigns workers to each subtask
- Workers report back to manager
- Manager synthesizes final result

**Pros:**
- ✅ Organized, structured
- ✅ No duplicate work
- ✅ Manager handles coordination
- ✅ Better for complex missions

**Cons:**
- ❌ Single point of failure (manager)
- ❌ Requires good manager prompt

---

### Option 2: Parallel Agents (OpenAI Codex Approach) ⚡

```
┌─────────────┐
│   Mission   │
└──────┬──────┘
       │
┌──────┼──────┐
│      │      │
▼      ▼      ▼
┌──┐ ┌──┐ ┌──┐
│A1│ │A2│ │A3│
└──┘ └──┘ └──┘
```

**How it works:**
- Multiple independent agents run at the same time
- Each agent works on its own task
- User manages all threads manually
- No central coordinator

**Pros:**
- ✅ Fast (all start at once)
- ✅ No bottleneck
- ✅ Simple architecture

**Cons:**
- ❌ May do duplicate work
- ❌ User must coordinate
- ❌ Hard to synthesize results
- ❌ Can conflict with each other

---

### Which is Better?

| Factor | Orchestrator | Parallel |
|--------|-------------|----------|
| **Complex missions** | ✅ Better | ❌ Hard to coordinate |
| **Simple tasks** | ⚖️ Overhead | ✅ Fast |
| **Reliability** | ❌ Single point | ✅ Distributed |
| **Result quality** | ✅ Synthesized | ⚖️ May conflict |
| **Speed** | ⚖️ Sequential | ✅ Truly parallel |

**Verdict:** 
- **Orchestrator** is better for **complex, multi-step missions** (like "build a web app")
- **Parallel** is better for **simple, independent tasks** (like "answer these 3 questions")

**NeoSwarm uses Orchestrator** - it's more structured and produces better results for complex work.

---

## Notes

- Backend imports use `backend.` prefix (e.g., `from backend.config.Apps import MainApp`)
- Run from project root with `PYTHONPATH=.`
- Health check is at `/api/health/check` not `/health`
- MCP server names: `neoswarm-browser-agent`, `neoswarm-invoke-agent`
- Default model: `sonnet` (Anthropic Sonnet 4.6)
- Default provider: Ollama (local, no API key needed)

---

*Last updated: 2026-04-25*
*Building toward "Codex for Everything" - local-first AI agent orchestrator*
