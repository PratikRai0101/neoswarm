<p align="center">
  <img src="src-tauri/icons/icon.png" alt="NeoSwarm Logo" width="128" height="128"/>
</p>

<h1 align="center">NeoSwarm</h1>

<p align="center">
  <strong>A local-first AI-agent workspace with GUI, TUI, and multi-agent missions</strong>
</p>

## What it is

NeoSwarm is a FastAPI agent backend with a React/Tauri desktop workspace and a
Textual terminal UI. It can run with local Ollama models or direct Anthropic and
OpenAI API keys. Agents keep session data locally and can use built-in tools or
configured MCP tools.

> **Privacy:** model requests go to whichever provider you configure. Product
> analytics are enabled by default but can be disabled in Settings; disabling
> them prevents PostHog event capture. API keys remain local and are redacted
> from settings responses.

## Implemented capabilities

- Streaming single-agent sessions with tool approvals, branches, and persistence
- Anthropic, Ollama, and direct OpenAI provider paths
- React dashboard: chats, skills, modes, tools, outputs, browser cards, settings
- Textual TUI: session rail, streaming transcript, activity panel, model picker,
  approval commands, and reconnecting WebSocket transport
- Multi-agent mission API with sequential or parallel worker scheduling:
  `POST /api/agents/missions`
- Tauri desktop shell, currently bundled for **Linux AppImage and deb**

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

Install the Tauri v2 CLI, complete the backend/frontend setup above, then run:

```bash
cd src-tauri
cargo tauri dev
```

Release bundles currently target Linux:

```bash
cd src-tauri
cargo tauri build
```

## Multi-agent missions

Create a mission, start it, and poll its status. Worker sessions reuse the same
provider and model selection as regular agents.

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

# Web production build
(cd frontend && npm run build)

# Tauri type/build check
cargo check --manifest-path src-tauri/Cargo.toml
```

## License

MIT License — see [LICENSE](LICENSE). NeoSwarm is based on the MIT-licensed
[OpenSwarm](https://github.com/openswarm-ai/openswarm) project.
