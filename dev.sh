#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# dev.sh — Start backend + frontend with full Hive LLM graph logs
# Run: bash dev.sh
# ──────────────────────────────────────────────────────────────────────────────

echo "▶ Starting Hive backend (port 8000)..."
cd backend

# Enable verbose logging so you can see the LLM graph interactions
PYTHONPATH="$(pwd):$(pwd)/../vendor/hive/core" \
PYTHONUNBUFFERED=1 \
python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level debug \
  --reload &

BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"
cd ..

sleep 2

echo ""
echo "▶ Starting frontend (port 5173)..."
cd frontend && npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Backend:   http://localhost:8000"
echo "  Frontend:  http://localhost:5173"
echo ""
echo "  LLM logs:  look for [HiveAdapter], [director], [OpenRouter]"
echo "  Tool logs: look for [discover_companies], [analyze_company]"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop all servers."
echo ""

trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
