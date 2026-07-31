# Getting started with NeoSwarm

## Prerequisites

- Python **3.11+**
- Node.js **18+** and npm
- Rust/Cargo only when using the Tauri desktop shell
- [Ollama](https://ollama.com/) only when using local models

## Install

Run these commands from the repository root:

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

The backend venv includes the Textual TUI runtime as well as FastAPI.

## Run the web workspace

```bash
./run.sh
```

This starts FastAPI at `http://127.0.0.1:8324` and Webpack at
`http://localhost:3000`.

Run only the backend when needed:

```bash
./run-backend.sh
```

Both scripts resolve paths relative to themselves. Set `NEOSWARM_PYTHON` to use
a non-default Python interpreter and `NEOSWARM_PORT` to select another port.

## Run the TUI

Start the backend first, then in another terminal:

```bash
backend/.venv/bin/python -m cli.tui
```

The TUI uses the same `NEOSWARM_URL` setting as other local clients; it defaults
to `http://localhost:8324`.

## Configure a model

Use the Settings screen to enter an Anthropic or OpenAI key, or run Ollama:

```bash
ollama serve
ollama pull llama3.3
```

Model selection persists the corresponding provider with each new session. API
keys are stored in local settings and are never returned by the settings API.

## Run a mission

NeoSwarm can coordinate worker sessions through the API:

```bash
curl -X POST http://127.0.0.1:8324/api/agents/missions \
  -H 'content-type: application/json' \
  -d '{"mission":"Analyze, implement, and verify a feature","workers":3,"execution_mode":"parallel","model":"llama3.3","provider":"ollama"}'

# Copy the returned mission id.
curl -X POST http://127.0.0.1:8324/api/agents/missions/<mission-id>/start
curl http://127.0.0.1:8324/api/agents/missions/<mission-id>
```

Use `execution_mode: "sequential"` when tasks must run in order.

## Optional Tauri desktop shell

```bash
cd src-tauri
cargo tauri dev
```

The current release bundle targets Linux AppImage and deb packages.

## Verification

```bash
PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests cli/tests -q
(cd frontend && npm run build)
cargo check --manifest-path src-tauri/Cargo.toml
```

## Troubleshooting

- **Backend import failure:** start it through `./run-backend.sh`, not from the
  `backend/` directory with `main:app`.
- **No local models:** ensure `ollama serve` is running on port 11434 and pull a
  model before selecting it.
- **TUI cannot connect:** confirm `/api/health/check` responds on the configured
  backend URL.
- **Browser or OAuth tools fail:** configure their provider credentials in the
  Tools screen; model credentials and tool OAuth are separate.
