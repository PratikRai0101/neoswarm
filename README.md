<p align="center">
  <img src="assets/icon.png" alt="NeoSwarm Logo" width="128" height="128"/>
</p>

<h1 align="center">NeoSwarm</h1>

<p align="center">
  <strong>A cross-platform, locally-running AI agent orchestrator</strong>
  <br>
  A fork of OpenSwarm with the Team Lead (Orchestrator) Agent that manages a swarm of worker agents in parallel.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/platforms-Linux%20%7C%20Windows%20%7C%20macOS-green.svg" alt="Platforms"></a>
  <a href="https://github.com/pratikrai0101/neoswarm/stargazers"><img src="https://img.shields.io/github/stars/pratikrai0101/neoswarm?style=social" alt="GitHub Stars"></a>
  <a href="https://github.com/pratikrai0101/neoswarm/pulls"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

## What is NeoSwarm?

NeoSwarm is a **locally-running AI agent orchestrator** with a Team Lead (Orchestrator) Agent that manages a swarm of worker agents in parallel. It runs 100% on your machine — no cloud relay, no telemetry.

Built for **Linux first**, then Windows, then macOS. Available as a **Tauri GUI**, an **OpenCode-style TUI**, and a **Codex-style CLI**.

## Why NeoSwarm?

- **Orchestrator Agent**: Your AI project manager — give it a mission, it figures out who does what
- **100% Local**: No data leaves your machine unless you configure cloud providers
- **Offline-capable**: Run entirely with local Ollama models
- **Three Interfaces**: GUI, TUI, and CLI — your choice at runtime
- **Native AgentLoop**: Replaces proprietary SDK with pure Python
- **Cross-platform**: Linux first, then Windows, then macOS

## Key Features

- **Team Lead / Orchestrator Agent** — Decompose complex goals into tasks, spawn workers, monitor progress, synthesize results
- **Parallel agents, one screen** — Launch as many agents as you need
- **Human-in-the-Loop Approvals** — Every tool-use request surfaces in one place
- **Git Worktree Isolation** — Each agent works in its own branch
- **Offline operation** — Run entirely with Ollama (local models)

## Quick Start

### 1. Backend (FastAPI)

```bash
cd neoswarm
source backend/.venv/bin/activate
PYTHONPATH=. python -m uvicorn backend.main:app --port 8324
```

Then open:
- **API**: http://localhost:8324
- **Health**: http://localhost:8324/api/health/check
- **API Docs**: http://localhost:8324/docs

### 2. CLI

```bash
cd neoswarm/cli
pip install -e .

# Commands
neoswarm models      # Show available models
neoswarm status      # Show session status
neoswarm sessions    # List all sessions
```

### 3. Native App (Tauri)

```bash
# Run the pre-built binary
./src-tauri/target/debug/neoswarm

# Or build release
cargo tauri build
```

### 4. Run Script

```bash
bash run.sh
```

## Architecture

```
┌─────────────────────────────────────┐
│       USER INTERFACES               │
│  Tauri GUI  │  TUI  │  CLI          │
└──────┬──────────────────┬───────────┘
       │     REST+WebSocket
       ▼
┌──────────────────────────────┐
│    NEOSWARM CORE             │
│    FastAPI :8324             │
│  ┌──────────────────────┐    │
│  │  Orchestrator Agent  │    │
│  │  Agent Manager       │    │
│  │  Provider Registry   │    │
│  └──────────────────────┘    │
└──────────────────────────────┘
       │
   Ollama (local) / Cloud APIs
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop Shell | Tauri v2 (Rust) |
| GUI Frontend | React 18 + TypeScript + Redux + Material UI |
| Backend | FastAPI + Python 3.11+ |
| Agent Loop | Native Python AgentLoop |
| Local Models | Ollama |

## License

MIT License — see [LICENSE](LICENSE) for details.

## Credits

**NeoSwarm is built upon [OpenSwarm](https://github.com/openswarm-ai/openswarm) by [Haik Decie](https://github.com/haikdecie).**

OpenSwarm was created by Haik Decie and licensed under the MIT License. NeoSwarm is a fork that extends the original with:

- Linux-first support (replacing Electron with Tauri)
- Native AgentLoop (replacing claude-agent-sdk)
- Ollama local model support
- Team Lead / Orchestrator Agent

Original OpenSwarm repository: https://github.com/openswarm-ai/openswarm

---

*NeoSwarm: Your local AI agent swarm, your way.*
