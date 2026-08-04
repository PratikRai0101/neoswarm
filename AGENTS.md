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
| Phase 1: Fork + Rebrand | ✅ Complete | NeoSwarm branding, icon, and Tauri v2 desktop shell |
| Phase 2: Native Agent System | ✅ Complete | Provider-agnostic streaming AgentLoop, tools, approvals, and persistence |
| Phase 3: Orchestrator Agent | ✅ Complete | Durable mission API/UI with parallel or sequential workers |
| Phase 4: CLI + TUI | ✅ Complete | Streaming Textual TUI and legacy Click commands are covered by the CLI test suite |
| Phase 5: Packaging | 🟡 Pipeline complete | Bundled PyInstaller backend and macOS DMG targets are configured for Intel and Apple Silicon; release artifacts still need target verification |
| Phase 6: Provider Auth | 🟡 API-key auth complete | Secure settings/keychain storage is complete; direct model-provider OAuth is not implemented |
| Phase 7: Enhanced TUI | ✅ Complete | Session rail, streaming transcript, command center, approvals, and reconnecting transport |
| Phase 8: Native App Runtime | 🔄 In Progress | Tauri bridge, browser cards, MCP execution, memory, automations, and release hardening |

### Current implementation gaps (2026-08-02)

- Tauri updater metadata and update-install flow are covered by frontend lifecycle tests; live signed-update validation on a clean Mac remains.
- Tauri browser cards now use native child webviews for their visual surface, but browser command/control parity and lifecycle behavior need target-platform testing.
- Release artifacts are configured for macOS DMG builds on Intel and Apple Silicon, but signed/notarized packaging and updater smoke tests remain.
- Optional approval-gated native desktop control is implemented through the host computer adapter; macOS Accessibility and Screen Recording permissions still need host testing.
- Browser control parity, release hardening, and direct model-provider OAuth remain; local Git/PR workflows, artifact viewing, multi-tab terminals, saved SSH workspaces, and OpenAI image generation are implemented.

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
# macOS DMG output
open src-tauri/target/release/bundle/dmg/NeoSwarm_*.dmg

# Or standalone binary
./src-tauri/target/release/neoswarm
```

Native desktop control on macOS requires granting NeoSwarm **Accessibility** and
**Screen Recording** permissions in System Settings when prompted.

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
NeoSwarm has browser and optional native desktop computer-use paths:
- **Browser Automation** ✅: Browser-agent loops, MCP routing, Tauri native child webviews, and Tauri command routing are implemented; cross-platform command/lifecycle testing remains.
- **Native App Control** 🟡: Approval-gated PyAutoGUI adapter supports screenshots, mouse, keyboard, and scrolling; host permissions, packaging, and target testing remain.

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
| `neoswarm auth status` | 🟡 | Works through the backend, but the legacy CLI needs cleanup |
| Auth storage | ✅ | `settings.json` plus OS keychain, with owner-only file fallback |
| API key input | ✅ | Settings UI and CLI support direct provider keys |
| OAuth (future) | 🟡 | Tool OAuth and Copilot device flow exist; direct model-provider OAuth remains future work |
| Env var priority | ✅ | ENV > keychain/settings > defaults |

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
| Computer Use | ✅ macOS app control | 🟡 Approval-gated optional mouse/keyboard/screenshot adapter; host permissions and target testing remain | High |
| In-app Browser | ✅ Local servers + web | 🟡 Basic iframe fallback; native Tauri webview/control remains | High |
| Image Generation | ✅ gpt-image-1.5 | ✅ OpenAI image generation with local Artifact publishing and approval-gated agent access | Low |
| Memory | ✅ Persistent | ✅ Local memory store, relevance context, tools, API, and Memory workspace | Medium |
| 90+ Plugins | ✅ MCP servers | ✅ Registry/configuration, discovery, schemas, permissions, and native runtime execution | High |
| Multi-agent | ✅ Parallel | ✅ Mission workspace with sequential/parallel workers; in-chat delegation follows MCP work | Done |
| Automations | ✅ Scheduled tasks | ✅ Durable interval/one-time schedules, agent tools, REST API, and Automations workspace | Low |
| Git Integration | ✅ PR review, commits | ✅ Git workspace/API with explicit commits, remote pushes, and authenticated GitHub PR creation through `gh` | Medium |
| Artifact Viewer | ✅ PDF, spreadsheets | ✅ Approval-gated publishing plus local previews/downloads for PDF, images, CSV, JSON, Markdown, and text | Low |
| Terminal | ✅ Multiple tabs | ✅ Local PTY tabs with streaming input/output, resize, interrupt, restart, and session metadata | Low |
| SSH | ✅ Remote devboxes | ✅ Saved local profiles and remote PTY tabs through the system SSH client/agent | Low |

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
| Command palette | `^p` | Quick actions (/new, /model, /clear, etc.) |

### Native App Features (Codex-style)

| Feature | Status | Description |
|---------|--------|-------------|
| Multi-agent | ✅ | Mission orchestrator coordinates workers; in-chat delegation is being wired through MCP |
| Browser Agent | ✅ | Browser-agent loop, MCP execution, browser cards, and Tauri child-webview rendering |
| MCP Tools | ✅ | Registry, discovery, schemas, permissions, and native call routing |
| Sessions | ✅ | Chat session persistence and searchable history |
| Model Switching | ✅ | Per-session switching with provider-aware fork handling |
| Auth System | ✅ | API-key settings, keychain storage, redaction, and CLI/UI flows |
| In-app Browser | 🟡 | Native Tauri child-webview rendering exists; command/control parity and packaging tests remain |
| Artifacts | ✅ | Approval-gated local publishing, secure workspace serving, previews, downloads, and default-app opening |
| Terminal | ✅ | Local interactive shell tabs with streaming output, resize handling, interrupt, and persisted working directories |
| SSH | ✅ | Saved non-secret connection profiles opening remote shells in Terminal tabs |
| Memory | ✅ | User-controlled local memories with search, editing, deletion, tools, and prompt context |
| Scheduled Tasks | ✅ | Durable interval/one-time automation with manual run controls |
| Git Tools | ✅ | Git workspace plus native status, diff, explicit commits, remote pushes, and GitHub PR creation from the UI |
| Image Gen | ✅ | OpenAI image generation workspace and approval-gated GenerateImage tool |

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
- [x] Model picker modal (^m or /model)
- [x] Command palette (^p) - /new, /model, /clear, /refresh, /sidebar, /help
- [x] Session management (create, switch, delete)
- [x] Tool output display
- [x] Keyboard shortcuts (like OpenCode)
- [x] Dynamic Ollama model fetching (from /api/tags)
- [x] GitHub Copilot OAuth Device Flow
- [x] Provider/model header display

### Phase 9: Native App Enhancements (High Priority)
- [x] Full message history
- [x] Tool output panel
- [x] Settings panel
- [x] In-app browser visual surface through Tauri child webviews
- [~] Browser command/control parity and cross-platform lifecycle testing
- [~] Tauri frontend bridge: backend sidecar and browser bridge exist; updater and native capture remain
- [x] MCP runtime: connect configured servers and execute their tools from the native loop
- [x] Persistent memory workspace and relevant prompt context
- [x] Durable automations workspace and scheduler lifecycle

### Phase 10: Advanced Features (Low Priority)
- [x] Memory system beyond session persistence
- [x] Scheduled/automated tasks
- [x] MCP runtime execution for configured integrations
- [x] Image generation workspace and approval-gated `GenerateImage` tool with local Artifact publishing
- [~] Native macOS application control: approval-gated PyAutoGUI adapter exists; DMG packaging and host-permission testing remain
- [x] Dedicated Git/PR workflow: explicit remote pushes and GitHub pull-request creation through authenticated `gh`
- [x] Artifact viewer/publishing workspace for PDF, images, CSV, JSON, Markdown, and text files
- [x] Multi-tab terminal with local PTY sessions, streaming I/O, resize, interrupt, restart, and persisted tab metadata
- [x] SSH workspaces with saved profiles and remote PTY terminal tabs
- [ ] Tauri updater and release-install smoke tests

### Phase 11: Standalone Binary (High Priority)
- [x] Fix backend not spawning for standalone binary (use bundled executable or venv Python)
- [x] Comprehensive backend search (resource dir, next to binary, CWD, dev path)
- [x] Tauri v2 shell scope configuration
- [~] Build and smoke-test Intel and Apple Silicon macOS release artifacts

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
| **Artifacts** | `backend/apps/artifacts/`, `backend/apps/agents/tools/artifacts.py`, `frontend/src/app/pages/Artifacts/` |
| **Terminal** | `backend/apps/terminals/`, `frontend/src/app/pages/Terminals/`, `frontend/src/shared/state/terminalsSlice.ts` |
| **Hosted Git/PR** | `backend/apps/git/`, `frontend/src/app/pages/Git/`, `frontend/src/shared/state/gitSlice.ts` |
| **SSH** | `backend/apps/ssh/`, `frontend/src/app/pages/SSH/`, `frontend/src/shared/state/sshSlice.ts` |
| **Images** | `backend/apps/images/`, `backend/apps/agents/tools/images.py`, `frontend/src/app/pages/Images/` |

---

## Comparison: NeoSwarm vs OpenAI Codex

| Feature | Codex | NeoSwarm |
|---------|-------|----------|
| Computer Use | ✅ macOS app control | 🟡 Browser automation plus optional approval-gated native desktop adapter |
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
- Default model: `sonnet` (Anthropic Sonnet 4.6); Ollama is the keyless local option and is selected when an Ollama model is chosen
- Provider credentials: environment variables take precedence, then the platform keychain/settings store
- Native AgentLoop built-ins: filesystem, shell, question, web, memory, scheduling, and Git tools; configured MCP/browser delegation runs through `MCPClientManager`
- Persistent memory lives under the configured data root in `memory/`; schedules live under `schedules/`
- Native desktop control is optional (`backend/requirements-computer.txt`) and defaults to approval-required policy
- Validation: `PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests cli/tests -q` (currently 136 tests pass)

---

*Last updated: 2026-08-02*
*Building toward "Codex for Everything" - local-first AI agent orchestrator*
