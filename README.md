<p align="center">
  <img src="src-tauri/icons/icon.png" alt="NeoSwarm Logo" width="128" height="128"/>
</p>

<h1 align="center">NeoSwarm</h1>

<p align="center">
  <strong>A local-first AI-agent workspace with GUI, TUI, and multi-agent missions</strong>
</p>

## What it is

NeoSwarm is a FastAPI agent backend with a React/Tauri desktop workspace and a
Textual terminal UI. It can run with local Ollama models or direct Anthropic,
OpenAI, and Google Gemini API keys. Agents keep session data locally and can use built-in tools or
configured MCP tools.

> **Privacy:** model requests go to whichever provider you configure. Anonymous
> product analytics are off by default and require explicit opt-in in Settings;
> prompts, responses, profile details, file contents, and error messages are not
> included. API keys remain local, are stored in the platform keychain when
> available (with an owner-only file fallback), and are redacted from settings
> responses.

## Implemented capabilities

- Streaming single-agent sessions with tool approvals, branches, and persistence
- Anthropic, Ollama, direct OpenAI, and Google Gemini provider paths
- React dashboard: chats, skills, modes, tools, outputs, browser cards, settings
- Textual TUI: session rail, streaming transcript, activity panel, model picker,
  approval commands, and reconnecting WebSocket transport
- Multi-agent mission workspace and API with sequential or parallel workers
- Optional per-worker git worktree isolation with dirty-worktree protection
- Tauri desktop shell with native browser child webviews, updater support, and a
  self-contained PyInstaller backend executable; current release targets are
  **macOS DMG packages for Intel and Apple Silicon**
- Local memory workspace, durable automations, Git workspace/API with explicit
  commit, remote push, and GitHub PR controls, an approval-gated Artifact
  workspace, multi-tab local terminal sessions, saved SSH workspaces, and
  OpenAI image generation with local Artifact publishing and streaming PTY output
- Optional approval-gated native desktop control (mouse, keyboard, scrolling,
  and screenshots) via the host computer adapter

## Quick start

```bash
# 1. Backend runtime (Python 3.11+)
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

# 2. Web workspace
(cd frontend && npm install)

# 3. Start backend + web UI
./run.sh
```

Open the web UI at http://localhost:3000. The backend health check is
http://127.0.0.1:8324/api/health/check and interactive OpenAPI docs are at
http://127.0.0.1:8324/docs.

### TUI

With the backend running:

```bash
backend/.venv/bin/python -m cli.tui
```

The terminal UI uses `^N` for a new chat, `^P`/`^M` for the command center,
`^S` to toggle sessions, `^A` to toggle activity, and `/approve` or `/deny` for
a waiting tool approval.

### Tauri development

Complete the backend/frontend setup above, then run:

```bash
cd frontend
npm exec tauri -- dev --config ../src-tauri/tauri.conf.json
```

Release bundles currently target macOS. The build installs the pinned build
requirements, creates a self-contained backend executable, builds the frontend,
and bundles both into a DMG app package:

```bash
npm --prefix frontend exec -- tauri build --config src-tauri/tauri.conf.json
```

Tagging a commit with `v*` starts the macOS release workflow for Intel and Apple
Silicon. Configure the `TAURI_SIGNING_PRIVATE_KEY` and optional password
repository secrets first; Apple signing/notarization secrets are required for
trusted distribution.

The resulting desktop installation does not require the user to install Python
or backend packages.

## Multi-agent missions

Use **Missions** in the desktop/web sidebar to launch and monitor work, or use
the endpoints below. Worker sessions reuse the same provider and model selection
as regular agents and can optionally run in isolated git worktrees.

```bash
curl -X POST http://127.0.0.1:8324/api/agents/missions \
  -H 'content-type: application/json' \
  -d '{"mission":"Implement and verify a small feature","workers":2,"execution_mode":"parallel","model":"llama3.3","provider":"ollama"}'

curl -X POST http://127.0.0.1:8324/api/agents/missions/<mission-id>/start
curl http://127.0.0.1:8324/api/agents/missions/<mission-id>
```

## Architecture

```text
React web workspace / Textual TUI / Tauri desktop
                    │ REST + WebSocket
                    ▼
              FastAPI backend
         sessions · providers · tools · missions
                    │
        Ollama / configured cloud-model providers / MCP tools
```

Persistent data defaults to `backend/data/` in development. Set
`NEOSWARM_DATA_DIR` to place it elsewhere. Packaged desktop builds use the
platform application-data directory.

## Development checks

```bash
# Backend and TUI tests
PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests cli/tests -q

# Web type-check and production build
(cd frontend && npm run typecheck && npm run build)

# Tauri type/build check
cargo check --manifest-path src-tauri/Cargo.toml --locked
```

## License

MIT License — see [LICENSE](LICENSE). NeoSwarm is based on the MIT-licensed
[OpenSwarm](https://github.com/openswarm-ai/openswarm) project.
