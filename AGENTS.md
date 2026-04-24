# AGENTS.md — NeoSwarm Development Context

> Quick reference for developers working on NeoSwarm. Updated as we build.

## Current Phase

**Phase 1: Fork + Rebrand + Linux Foundation** — IN PROGRESS

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

- [ ] Backend requires `PYTHONPATH=.` when running
- [ ] 9Router code removed but more cleanup needed in settings/credentials.py
- [ ] Needs Tauri build configuration

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Python 3.14 |
| Frontend | React 18 + TypeScript |
| Desktop | Tauri v2 |
| Local Models | Ollama |

## Dependencies

```bash
# Install backend deps
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install debugger (for debug.py)
cd ../debugger
pip install -e .
```

## Commands

```bash
# Test backend
curl http://localhost:8324/api/health/check

# View debug logs (noisy)
# Uses debugger package - see debugger/ package
```

## Notes

- Backend imports use `backend.` prefix (e.g., `from backend.config.Apps import MainApp`)
- Run from project root with `PYTHONPATH=.`
- Health check is at `/api/health/check` not `/health`

---

*Last updated: 2026-04-24*