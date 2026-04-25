#!/bin/bash
cd /home/raijinnn0101/Development/NeoSwarm
export PYTHONPATH=.
exec /home/raijinnn0101/Development/NeoSwarm/backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8324 "$@"