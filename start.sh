#!/usr/bin/env bash
# Start both servers for local development.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Starting Pulse API on :8000"
cd "$ROOT/backend"
export PULSE_SECRET_KEY="${PULSE_SECRET_KEY:-dev-only-insecure-key}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./pulse.db}"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

echo "==> Starting Next.js dev server on :3000"
cd "$ROOT/frontend"
npm run dev &
NEXT_PID=$!

echo ""
echo "  Pulse    http://localhost:3000"
echo "  API docs http://localhost:8000/api/docs"
echo ""
echo "  Press Ctrl-C to stop both servers."
trap 'kill $API_PID $NEXT_PID 2>/dev/null; exit 0' INT TERM
wait
