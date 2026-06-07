#!/bin/sh
echo "[startup] WORKDIR=$(pwd)"
echo "[startup] Python=$(python --version 2>&1)"
echo "[startup] arq=$(which arq 2>&1)"
echo "[startup] worker.py=$(test -f worker.py && echo FOUND || echo MISSING)"
echo "[startup] sys.path check:"
python -c "import sys; print(sys.path)"

echo "[startup] Starting ARQ worker (arq worker.WorkerSettings)..."
arq worker.WorkerSettings &
WORKER_PID=$!
echo "[startup] Worker PID=$WORKER_PID"

sleep 3
if kill -0 $WORKER_PID 2>/dev/null; then
  echo "[startup] Worker running OK"
else
  echo "[startup] ERROR: Worker exited — attempting import test:"
  python -c "from worker import WorkerSettings; print('import OK')" 2>&1
fi

echo "[startup] Starting uvicorn on port ${PORT}..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
