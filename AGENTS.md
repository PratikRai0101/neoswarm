# AGENTS.md — NeoSwarm Development Context

> Quick reference for developers working on NeoSwarm. Updated as we build.

## Current Phase

**Phase 1: Fork + Rebrand + Linux Foundation** — ✅ COMPLETE

## Project Structure

```
NeoSwarm/
├── backend/           # FastAPI server (:8324)
│   ├── apps/         # API endpoints
│   │   ├── agents/   # Agent management
│   │   ├── health/   # Health checks
│   │   └── ...
│   ├── config/      # App config
│   ├── main.py      # Entry point
│   └── requirements.txt
├── frontend/         # React app (:3000)
├── src-tauri/        # Tauri v2 desktop shell
├── debugger/        # Debug tools
└── run.sh           # Starts backend + frontend
```

## Running the Project

```bash
# From project root
cd /home/raijinnn0101/Development/NeoSwarm

# Backend only (requires PYTHONPATH)
source backend/.venv/bin/activate
PYTHONPATH=. python -m uvicorn backend.main:app --host 127.0.0.1 --port 8324

# Or use run.sh
bash run.sh
```

## Key Endpoints

| Endpoint | Description |
|---------|------------|
| `/api/health/check` | Health check |
| `/api/agents/` | Agent CRUD |
| `/ws/agents/{session_id}` | WebSocket |

## Current Issues / Tech Debt

- [x] Backend requires `PYTHONPATH=.` when running - WORKS
- [x] Added debug.py stub - FIXED
- [ ] 9Router code remaining in agent_manager.py (not critical)
- [ ] Needs Tauri build configuration

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

**Phase 2: Native Agent System** — Coming next
- Replace `claude-agent-sdk` with native AgentLoop
- Add OllamaProvider
- Make agents truly run locally