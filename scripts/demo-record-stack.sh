#!/usr/bin/env bash
# Bring up the full stack with the demo recorder armed, for the Task 3 golden run.
#
# Replaces the plan's "docker compose up -d redis" — this machine has neither
# Docker nor Homebrew, so Redis is built from source into /tmp on first run.
#
#   ./scripts/demo-record-stack.sh energy-price-cap
#
# Then drive the browser at http://localhost:3000 through steps 1-5 without
# refreshing. Ctrl-C here when the report has rendered; the recorder flushes
# the tape to frontend/public/demo/<scenario>/tape.json.
set -euo pipefail

SCENARIO="${1:-energy-price-cap}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REDIS_SRC=/tmp/redis-7.2.5
REDIS_VER=7.2.5
TAPE_PATH="$REPO_ROOT/frontend/public/demo/$SCENARIO/tape.json"

cd "$REPO_ROOT"

if [ ! -f .env ]; then
  echo "ERROR: no .env. Run: cp .env.demo-record.example .env && \$EDITOR .env" >&2
  exit 1
fi

# Fail fast on the five secrets rather than 20 minutes into a paid run.
missing=()
for k in SECRET_KEY SUPABASE_SERVICE_KEY SUPABASE_JWT_SECRET LLM_API_KEY TAVILY_API_KEY ZEP_API_KEY; do
  v=$(grep -m1 "^${k}=" .env 2>/dev/null | cut -d= -f2- || true)
  [ -z "$v" ] && missing+=("$k")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: these are empty in .env: ${missing[*]}" >&2
  exit 1
fi

# --- Redis -----------------------------------------------------------------
if [ ! -x "$REDIS_SRC/src/redis-server" ]; then
  echo ">> building redis $REDIS_VER from source (one time, ~2 min)"
  curl -sSL -o /tmp/redis.tar.gz "https://download.redis.io/releases/redis-$REDIS_VER.tar.gz"
  tar xzf /tmp/redis.tar.gz -C /tmp
  make -C "$REDIS_SRC" -j8 MALLOC=libc redis-server >/tmp/redis-build.log 2>&1
fi

if ! nc -z localhost 6379 2>/dev/null; then
  echo ">> starting redis on 6379"
  mkdir -p /tmp/glas-redis
  "$REDIS_SRC/src/redis-server" --port 6379 --daemonize yes \
    --dir /tmp/glas-redis --save '' --appendonly no
  sleep 1
fi
nc -z localhost 6379 || { echo "ERROR: redis failed to start" >&2; exit 1; }
echo ">> redis up"

mkdir -p "$(dirname "$TAPE_PATH")"

PIDS=()
cleanup() {
  echo ""
  echo ">> stopping workers/backend (redis left running)"
  for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
  if [ -f "$TAPE_PATH" ]; then
    echo ">> tape written: $TAPE_PATH"
    ls -lh "$TAPE_PATH"
  else
    echo ">> WARNING: no tape at $TAPE_PATH — did the run reach the backend?"
  fi
}
trap cleanup EXIT INT TERM

# --- Celery workers --------------------------------------------------------
cd "$REPO_ROOT/backend"
CELERY=".venv/bin/celery"
echo ">> starting celery workers (default, research, simulation, beat-less)"
for q in celery research simulation; do
  $CELERY -A app.celery_app.celery_app worker -Q "$q" -n "${q}@%h" \
    --concurrency=2 --loglevel=INFO >"/tmp/glas-worker-$q.log" 2>&1 &
  PIDS+=($!)
done

# --- Backend with the recorder armed --------------------------------------
echo ">> starting backend with DEMO_RECORD=1 scenario=$SCENARIO"
DEMO_RECORD=1 \
DEMO_SCENARIO="$SCENARIO" \
DEMO_TAPE_PATH="$TAPE_PATH" \
  .venv/bin/python run.py >/tmp/glas-backend.log 2>&1 &
PIDS+=($!)

sleep 3
echo ""
echo "=============================================================="
echo " Backend  : http://localhost:5001   (log: /tmp/glas-backend.log)"
echo " Workers  : /tmp/glas-worker-{celery,research,simulation}.log"
echo " Tape     : $TAPE_PATH"
echo ""
echo " Now start the frontend in another shell, WITHOUT demo mode:"
echo "   cd frontend && npm run dev"
echo ""
echo " Then run the scenario at http://localhost:3000 through steps 1-5."
echo " Do not refresh. Ctrl-C here once the report has rendered."
echo "=============================================================="
wait
