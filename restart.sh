#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Killing existing processes ==="

# Kill processes on port 8000 (backend)
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null && echo "  Backend port 8000 freed" || echo "  Backend port 8000 already free"

# Kill processes on port 5173 (frontend)
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null && echo "  Frontend port 5173 freed" || echo "  Frontend port 5173 already free"

echo ""
echo "=== Starting backend (port 8000) ==="
cd "$PROJECT_DIR/backend"
source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

echo ""
echo "=== Starting frontend (port 5173) ==="
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"

echo ""
echo "=== Done ==="
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo ""
echo "Waiting for processes... (Ctrl+C to stop all)"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
