#!/usr/bin/env bash
# Start everything this project needs: virtualenv, Ollama, models, Streamlit.
# Safe to run twice: it detects what is already running and only starts what is missing.
#
#   ./start.sh              start and open the app
#   ./start.sh --demo       use the separate demo archive (demo.db), never memory.db
#   ./start.sh --no-browser do not open a browser tab
#   ./start.sh --status     show what is running, change nothing

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

if [ -t 1 ]; then
  B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else
  B=''; G=''; Y=''; R=''; N=''
fi

step() { printf '\n%s==>%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '  %sok%s  %s\n' "$G" "$N" "$*"; }
warn() { printf '  %swarn%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '\n%sError:%s %s\n\n' "$R" "$N" "$*" >&2; exit 1; }

OPEN_BROWSER=1
ACTION=start
DEMO=0
for arg in "$@"; do
  case "$arg" in
    --demo)       DEMO=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --status)     ACTION=status ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) die "Unknown option: $arg (try --help)" ;;
  esac
done

# --- configuration: shell environment wins, then .env, then defaults -------------
env_get() {
  [ -f "$ROOT/.env" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ROOT/.env" | tail -n 1 \
    | sed 's/[[:space:]]*$//'
}

BASE_URL="${OLLAMA_BASE_URL:-$(env_get OLLAMA_BASE_URL)}"
BASE_URL="${BASE_URL:-http://127.0.0.1:11434}"
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-$(env_get OLLAMA_CHAT_MODEL)}"
CHAT_MODEL="${CHAT_MODEL:-qwen3.5:9b}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-$(env_get OLLAMA_EMBED_MODEL)}"
EMBED_MODEL="${EMBED_MODEL:-embeddinggemma}"
PORT="${STREAMLIT_PORT:-$(env_get STREAMLIT_PORT)}"
PORT="${PORT:-8501}"
APP_URL="http://localhost:$PORT"
HEALTH_URL="http://127.0.0.1:$PORT/_stcore/health"

# Which archive the app opens. --demo always uses the committed demo.db, so nothing done on
# stage can touch memory.db.
if [ "$DEMO" = 1 ]; then
  DB_PATH="$ROOT/demo.db"
  MODE_FLAG=" --demo"
else
  DB_PATH="${DATABASE_PATH:-$(env_get DATABASE_PATH)}"
  DB_PATH="${DB_PATH:-./memory.db}"
  case "$DB_PATH" in
    /*) ;;
    *)  DB_PATH="$ROOT/${DB_PATH#./}" ;;
  esac
  MODE_FLAG=""
fi

http_ok() { curl -fsS -m 3 -o /dev/null "$1" >/dev/null 2>&1; }

wait_http() {  # url seconds
  local url=$1 secs=$2 i
  for ((i = 0; i < secs; i++)); do
    http_ok "$url" && return 0
    sleep 1
  done
  return 1
}

pid_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

streamlit_running() {
  pid_alive "$RUN_DIR/streamlit.pid" && http_ok "$HEALTH_URL"
}

ollama_running() { http_ok "$BASE_URL/api/tags"; }

model_present() {  # name
  local want=$1 names
  names="$(ollama list 2>/dev/null | awk 'NR > 1 {print $1}')" || return 1
  printf '%s\n' "$names" | grep -qxF "$want" && return 0
  case "$want" in
    *:*) return 1 ;;
    *)   printf '%s\n' "$names" | grep -qxF "$want:latest" ;;
  esac
}

if [ "$ACTION" = status ]; then
  step "Status"
  recorded_db="$(cat "$RUN_DIR/database" 2>/dev/null || true)"
  if [ -n "$recorded_db" ]; then
    case "$recorded_db" in
      */demo.db) ok "Database: $recorded_db (demo)" ;;
      *)         ok "Database: $recorded_db" ;;
    esac
  else
    ok "Database on next start: $DB_PATH"
  fi
  if ollama_running; then ok "Ollama is running at $BASE_URL"
  else warn "Ollama is not running at $BASE_URL"; fi
  if streamlit_running; then ok "App is running at $APP_URL"
  else warn "App is not running"; fi
  exit 0
fi

printf '%sEpisodic Memory Agent%s\n' "$B" "$N"
printf '  project: %s\n' "$ROOT"
printf '  models:  %s + %s\n' "$CHAT_MODEL" "$EMBED_MODEL"
if [ "$DEMO" = 1 ]; then
  printf '  database: %s %s(demo - memory.db is never opened)%s\n' "$DB_PATH" "$Y" "$N"
else
  printf '  database: %s\n' "$DB_PATH"
fi

# --- 1. Python environment ------------------------------------------------------
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  step "Creating the Python virtual environment"
  command -v python3 >/dev/null || die "python3 is not installed. Install Python 3.10+ first."
  python3 -m venv "$ROOT/.venv" || die "Could not create .venv"
  ok "Created .venv"
fi

if ! "$ROOT/.venv/bin/python" -c 'import streamlit, ollama, pydantic, numpy, dotenv' >/dev/null 2>&1; then
  step "Installing Python dependencies (one-time, needs internet)"
  "$ROOT/.venv/bin/python" -m pip install -q --upgrade pip || true
  "$ROOT/.venv/bin/python" -m pip install -q -r "$ROOT/requirements.txt" \
    || die "pip install failed. Check your internet connection and retry."
  ok "Dependencies installed"
else
  ok "Python environment ready"
fi

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  ok "Created .env from .env.example"
fi

# --- 2. Ollama server -----------------------------------------------------------
command -v ollama >/dev/null || die "Ollama is not installed.
  macOS: brew install ollama   (or download the app from https://ollama.com)
  Linux: https://ollama.com/download"

OLLAMA_STARTED_BY_US=0
if ollama_running; then
  ok "Ollama already running at $BASE_URL"
else
  step "Starting Ollama"
  nohup ollama serve >"$LOG_DIR/ollama.log" 2>&1 &
  echo $! >"$RUN_DIR/ollama.pid"
  OLLAMA_STARTED_BY_US=1

  if ! wait_http "$BASE_URL/api/tags" 30; then
    # On macOS the desktop app may be able to recover a server the CLI could not bind.
    if [ -d "/Applications/Ollama.app" ]; then
      warn "CLI server did not come up; trying the Ollama app"
      open -a Ollama >/dev/null 2>&1 || true
      wait_http "$BASE_URL/api/tags" 20 \
        || die "Ollama did not start. See $LOG_DIR/ollama.log"
    else
      die "Ollama did not start. See $LOG_DIR/ollama.log"
    fi
  fi
  ok "Ollama started (pid $(cat "$RUN_DIR/ollama.pid"))"
fi
echo "$OLLAMA_STARTED_BY_US" >"$RUN_DIR/ollama_started_by_us"
echo "$BASE_URL" >"$RUN_DIR/base_url"

# --- 3. Models ------------------------------------------------------------------
missing=0
for model in "$CHAT_MODEL" "$EMBED_MODEL"; do
  if model_present "$model"; then
    ok "Model present: $model"
  else
    missing=1
    warn "Model missing: $model"
  fi
done

if [ "$missing" = 1 ]; then
  printf '  pull a missing model with:  ollama pull <name>\n'
  if [ -t 0 ]; then
    printf '  Download the missing model(s) now? This can take a while. [y/N] '
    read -r reply
    case "$reply" in
      [yY]*)
        for model in "$CHAT_MODEL" "$EMBED_MODEL"; do
          model_present "$model" && continue
          step "Pulling $model"
          ollama pull "$model" || die "Could not pull $model"
        done ;;
      *) die "Cannot continue without the models." ;;
    esac
  else
    die "Missing models. Run: ollama pull $CHAT_MODEL  and  ollama pull $EMBED_MODEL"
  fi
fi

# --- 4. Demo archive ------------------------------------------------------------
if [ "$DEMO" = 1 ]; then
  if [ -f "$DB_PATH" ]; then
    ok "Demo archive present: $(basename "$DB_PATH")"
  else
    step "Building the demo archive (one-time, about two minutes)"
    "$ROOT/.venv/bin/python" "$ROOT/scripts/build_demo_db.py" --db "$DB_PATH" \
      || die "Could not build the demo archive. See the output above."
    ok "Demo archive built"
  fi
fi

# --- 5. Streamlit ---------------------------------------------------------------
if streamlit_running; then
  recorded_db="$(cat "$RUN_DIR/database" 2>/dev/null || true)"
  if [ -n "$recorded_db" ] && [ "$recorded_db" != "$DB_PATH" ]; then
    die "The app is already running against a different database:
  running:   $recorded_db
  requested: $DB_PATH
  Run ./stop.sh first, then ./start.sh$MODE_FLAG."
  fi
  ok "App already running at $APP_URL"
else
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    die "Port $PORT is already used by another program.
  Stop it, or choose another port:  STREAMLIT_PORT=8502 ./start.sh$MODE_FLAG"
  fi

  step "Starting Streamlit"
  DATABASE_PATH="$DB_PATH" nohup "$ROOT/.venv/bin/python" -m streamlit run "$ROOT/app.py" \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false \
    >"$LOG_DIR/streamlit.log" 2>&1 &
  echo $! >"$RUN_DIR/streamlit.pid"
  echo "$PORT" >"$RUN_DIR/port"

  if ! wait_http "$HEALTH_URL" 60; then
    printf '\n--- last lines of %s ---\n' "$LOG_DIR/streamlit.log" >&2
    tail -n 20 "$LOG_DIR/streamlit.log" >&2 || true
    die "Streamlit did not become ready."
  fi
  ok "App started (pid $(cat "$RUN_DIR/streamlit.pid"))"
fi
echo "$PORT" >"$RUN_DIR/port"
echo "$DB_PATH" >"$RUN_DIR/database"

# --- 6. Open the browser --------------------------------------------------------
if [ "$OPEN_BROWSER" = 1 ]; then
  if command -v open >/dev/null 2>&1; then
    open "$APP_URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$APP_URL" >/dev/null 2>&1 || true
  fi
fi

printf '\n%s%sReady.%s\n' "$G" "$B" "$N"
printf '  App:      %s\n' "$APP_URL"
printf '  Database: %s\n' "$DB_PATH"
if [ "$DEMO" = 1 ]; then
  printf '  %sDemo mode: memory.db is never opened.%s\n' "$Y" "$N"
fi
printf '  Ollama:   %s\n' "$BASE_URL"
printf '  Logs:     %s/{streamlit,ollama}.log\n' "$LOG_DIR"
printf '  Stop:     ./stop.sh\n'
printf '\nThe first reply after a restart is slower: Ollama has to load the 9B model into memory.\n'
