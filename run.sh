#!/usr/bin/env bash
#
# FreightIQ — start the dashboard and the API.
#
# Safe to run on a fresh clone. It installs what is missing, trains the
# forecasting models the first time, then runs both processes until you stop it
# with Ctrl-C.
#
#   ./run.sh                 set up if needed, then run both
#   ./run.sh --setup         install and train, then stop
#   ./run.sh --backend       API only
#   ./run.sh --frontend      dashboard only
#   ./run.sh --offline       block every outbound call, prove the offline path
#   ./run.sh --retrain       refit the models before starting
#   ./run.sh --test          run both test suites, then stop
#   ./run.sh --stop          kill anything left listening on the two ports
#
set -euo pipefail

# Job control, so each background process becomes its own process group leader.
# Without it, stopping the script leaves orphans: `npm exec vite` spawns node as
# a grandchild, and signalling the wrapper never reaches the server underneath.
# With it, `kill -- -$pid` takes down the whole group in one go.
set -m

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"
LOGS="$ROOT/.run-logs"

API_PORT="${FREIGHTIQ_API_PORT:-8000}"
WEB_PORT="${FREIGHTIQ_WEB_PORT:-5173}"

# Python 3.14 has no statsmodels or pandas wheels yet and will try to build them
# from source, which fails slowly and confusingly. Prefer a version that works.
PREFERRED_PYTHONS=(python3.12 python3.11 python3.13)

RUN_BACKEND=1
RUN_FRONTEND=1
SETUP_ONLY=0
RETRAIN=0
TEST_ONLY=0
STOP_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --setup)     SETUP_ONLY=1 ;;
    --backend)   RUN_FRONTEND=0 ;;
    --frontend)  RUN_BACKEND=0 ;;
    --offline)   export FREIGHTIQ_OFFLINE=1 ;;
    --retrain)   RETRAIN=1 ;;
    --test)      TEST_ONLY=1 ;;
    --stop)      STOP_ONLY=1 ;;
    # Print the header comment, stopping at the first line of code, so the
    # help text cannot drift out of step with edits above.
    -h|--help)   awk 'NR>2 && /^#/ {sub(/^# ?/, ""); print; next} NR>2 {exit}' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)           echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# ── Output ────────────────────────────────────────────────────────────────────

if [ -t 1 ]; then
  DIM=$'\033[2m'; BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; OFF=$'\033[0m'
else
  DIM=''; BOLD=''; RED=''; GREEN=''; OFF=''
fi

step() { printf "%s==>%s %s\n" "$BOLD" "$OFF" "$*"; }
info() { printf "    %s%s%s\n" "$DIM" "$*" "$OFF"; }
ok()   { printf "    %s%s%s\n" "$GREEN" "$*" "$OFF"; }
die()  { printf "%serror:%s %s\n" "$RED" "$OFF" "$*" >&2; exit 1; }

# ── Shut both processes down together ─────────────────────────────────────────

PIDS=()
cleanup() {
  trap - INT TERM EXIT
  if [ ${#PIDS[@]} -gt 0 ]; then
    printf "\n"; step "stopping"
    for pid in "${PIDS[@]}"; do
      # The process group first, then the leader as a fallback for any shell
      # that did not honour job control.
      kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    done
    # Give them a moment to close their ports, then insist.
    sleep 2
    for pid in "${PIDS[@]}"; do
      kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    done
  fi
}
trap cleanup INT TERM EXIT

# ── Ports ─────────────────────────────────────────────────────────────────────

listeners_on() { lsof -ti :"$1" -sTCP:LISTEN 2>/dev/null || true; }

free_port() {
  local port="$1" label="$2" pids
  pids="$(listeners_on "$port")"
  [ -z "$pids" ] && return 0

  info "port $port is in use by $label from an earlier run; stopping it"
  # shellcheck disable=SC2086
  kill -TERM $pids 2>/dev/null || true
  sleep 2
  pids="$(listeners_on "$port")"
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    kill -KILL $pids 2>/dev/null || true
    sleep 1
  fi
  [ -z "$(listeners_on "$port")" ] || die "could not free port $port"
}

if [ "$STOP_ONLY" = 1 ]; then
  step "stopping anything on :$API_PORT and :$WEB_PORT"
  free_port "$API_PORT" api
  free_port "$WEB_PORT" dashboard
  ok "ports clear"
  trap - INT TERM EXIT
  exit 0
fi

# ── Prerequisites ─────────────────────────────────────────────────────────────

find_python() {
  for candidate in "${PREFERRED_PYTHONS[@]}"; do
    command -v "$candidate" >/dev/null 2>&1 && { echo "$candidate"; return; }
  done
  # Fall back to python3 only if it is not the version known to break.
  if command -v python3 >/dev/null 2>&1; then
    local v; v="$(python3 -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    case "$v" in
      3.10|3.11|3.12|3.13) echo python3; return ;;
    esac
  fi
  echo ""
}

setup_backend() {
  step "backend"

  if [ ! -x "$PY" ]; then
    if command -v uv >/dev/null 2>&1; then
      info "creating .venv with uv (downloads CPython 3.12 if needed)"
      uv venv --python 3.12 "$VENV" >/dev/null
    else
      local base; base="$(find_python)"
      [ -n "$base" ] || die "no usable Python found. Install 3.11 or 3.12, or install uv.
    Python 3.14 is not usable here: statsmodels and pandas have no wheels for it
    and will try to build from source."
      info "creating .venv with $base"
      "$base" -m venv "$VENV"
    fi
  fi

  local version; version="$("$PY" --version 2>&1)"
  case "$version" in
    *3.14*|*3.15*) die "$VENV is on $version, which cannot install statsmodels.
    Remove it and re-run: rm -rf backend/.venv && ./run.sh" ;;
  esac
  ok "$version"

  if ! "$PY" -c "import fastapi, statsmodels" >/dev/null 2>&1; then
    info "installing requirements (this takes a minute the first time)"
    if command -v uv >/dev/null 2>&1; then
      uv pip install --quiet --python "$PY" -r "$BACKEND/requirements.txt"
    else
      "$PY" -m pip install --quiet --upgrade pip
      "$PY" -m pip install --quiet -r "$BACKEND/requirements.txt"
    fi
  fi
  ok "dependencies installed"

  # Models are rebuildable and git-ignored, so a fresh clone has none. Training
  # reads the committed snapshot and needs no network.
  if [ "$RETRAIN" = 1 ] || [ -z "$(ls "$BACKEND"/models/*.pkl 2>/dev/null)" ]; then
    info "training forecasting models (offline, from the committed snapshot)"
    ( cd "$BACKEND" && "$PY" train.py ) 2>&1 | grep -E "MAPE|converge|trained" | sed 's/^[0-9-]* [0-9:,]* [A-Z]* *[a-z.]*: /    /' || true
  fi
  ok "$(ls "$BACKEND"/models/*.pkl 2>/dev/null | wc -l | tr -d ' ') models ready"
}

setup_frontend() {
  step "frontend"
  command -v node >/dev/null 2>&1 || die "node is not installed"
  ok "node $(node --version)"
  if [ ! -d "$ROOT/node_modules" ]; then
    info "installing npm packages"
    ( cd "$ROOT" && npm install --silent )
  fi
  ok "packages installed"
}

# ── Waiting ───────────────────────────────────────────────────────────────────

wait_for() {
  local url="$1" name="$2" tries="${3:-60}"
  for _ in $(seq 1 "$tries"); do
    curl -fsS -m 2 -o /dev/null "$url" 2>/dev/null && return 0
    sleep 1
  done
  return 1
}

# ── Run ───────────────────────────────────────────────────────────────────────

[ "$RUN_BACKEND" = 1 ] && setup_backend
[ "$RUN_FRONTEND" = 1 ] && setup_frontend

if [ "$TEST_ONLY" = 1 ]; then
  step "tests"
  ( cd "$BACKEND" && "$PY" -m pytest tests -q )
  ( cd "$ROOT" && npx tsc -b && npm run lint && npm run build >/dev/null && echo "    frontend: typecheck, lint and build clean" )
  trap - INT TERM EXIT
  exit 0
fi

if [ "$SETUP_ONLY" = 1 ]; then
  step "setup complete"
  info "run ./run.sh to start"
  trap - INT TERM EXIT
  exit 0
fi

mkdir -p "$LOGS"

if [ "$RUN_BACKEND" = 1 ]; then
  step "starting API on :$API_PORT"
  free_port "$API_PORT" api
  ( cd "$BACKEND" && exec "$VENV/bin/uvicorn" app.main:app --port "$API_PORT" ) > "$LOGS/api.log" 2>&1 &
  PIDS+=($!)
  if wait_for "http://localhost:$API_PORT/api/health" api 90; then
    ok "http://localhost:$API_PORT/docs"
    sed -n 's/.*WARNING data.adapters: source \(.*\)/    source \1/p' "$LOGS/api.log" | head -6
  else
    printf "%s\n" "$(tail -20 "$LOGS/api.log")" >&2
    die "API did not come up. Full log: $LOGS/api.log"
  fi
fi

if [ "$RUN_FRONTEND" = 1 ]; then
  step "starting dashboard on :$WEB_PORT"
  free_port "$WEB_PORT" dashboard
  ( cd "$ROOT" && exec node_modules/.bin/vite --port "$WEB_PORT" ) > "$LOGS/web.log" 2>&1 &
  PIDS+=($!)
  if wait_for "http://localhost:$WEB_PORT/" web 60; then
    ok "http://localhost:$WEB_PORT"
  else
    printf "%s\n" "$(tail -20 "$LOGS/web.log")" >&2
    die "dashboard did not come up. Full log: $LOGS/web.log"
  fi
fi

printf "\n"
step "running"
info "logs in .run-logs/  ·  Ctrl-C to stop"
[ "$RUN_BACKEND" = 1 ] && [ "${FREIGHTIQ_OFFLINE:-0}" = 1 ] && \
  info "offline mode: every adapter is serving cached values"

wait
