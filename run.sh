#!/usr/bin/env bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🐝 Starting NeoSwarm..."

cd "$PROJECT_ROOT"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 not found"
    exit 1
fi

# Check for Node.js
if ! command -v node &> /dev/null; then
    echo "Error: Node.js not found"
    exit 1
fi

# Start backend
echo "Starting FastAPI backend on :8324..."
cd "$PROJECT_ROOT/backend"
python3 -m uvicorn main:app --host 127.0.0.1 --port 8324 &
BACKEND_PID=$!

cd "$PROJECT_ROOT"

# Wait for backend
echo "Waiting for backend..."
for i in {1..30}; do
    if curl -s http://localhost:8324/health &> /dev/null 2>&1; then
        echo "Backend ready!"
        break
    fi
    sleep 1
done

# Start frontend dev server
echo "Starting React frontend on :3000..."
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "🐝 NeoSwarm running!"
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8324"
echo ""
echo "Press Ctrl+C to stop"

# Wait for either to exit
wait $BACKEND_PID $FRONTEND_PID