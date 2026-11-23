#!/usr/bin/env bash
# Stop what start.sh started and free memory.
#
#   ./stop.sh                stop the app, unload the models, quit Ollama
#   ./stop.sh --keep-ollama  leave the Ollama server running (models still unloaded)
#   ./stop.sh --clean        also delete logs and state in .run/
#
# Safe to run twice.

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"

if [ -t 1 ]; then
  B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
else
  B=''; G=''; Y=''; R=''; N=''
fi

step() { printf '\n%s==>%s %s\n' "$B" "$N" "$*"; }
ok()   { printf '  %sok%s  %s\n' "$G" "$N" "$*"; }
warn() { printf '  %swarn%s %s\n' "$Y" "$N" "$*"; }

env_get() {
  [ -f "$ROOT/.env" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ROOT/.env" | tail -n 1 \
    | sed 's/[[:space:]]*$//'
}

KEEP_OLLAMA=0
CLEAN=0
for arg in "$@"; do
  case "$arg" in
    --keep-ollama) KEEP_OLLAMA=1 ;;
    --clean)       CLEAN=1 ;;
    -h|--help)
      sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) printf 'Unknown option: %s (try --help)\n' "$arg" >&2; exit 2 ;;
  esac
done

BASE_URL="$(cat "$RUN_DIR/base_url" 2>/dev/null || true)"
BASE_URL="${BASE_URL:-${OLLAMA_BASE_URL:-$(env_get OLLAMA_BASE_URL)}}"
BASE_URL="${BASE_URL:-http://127.0.0.1:11434}"
CHAT_MODEL="${OLLAMA_CHAT_MODEL:-$(env_get OLLAMA_CHAT_MODEL)}"
CHAT_MODEL="${CHAT_MODEL:-qwen3.5:9b}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-$(env_get OLLAMA_EMBED_MODEL)}"
EMBED_MODEL="${EMBED_MODEL:-embeddinggemma}"
PORT="$(cat "$RUN_DIR/port" 2>/dev/null || true)"
PORT="${PORT:-${STREAMLIT_PORT:-$(env_get STREAMLIT_PORT)}}"
PORT="${PORT:-8501}"

stopped_any=0

pid_command() { ps -p "$1" -o command= 2>/dev/null || true; }

terminate() {  # pid label
  local pid=$1 label=$2 i
  if ! kill -0 "$pid" 2>/dev/null; then return 1; fi
  pkill -TERM -P "$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true
  for ((i = 0; i < 20; i++)); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -KILL -P "$pid" 2>/dev/null || true
    kill -KILL "$pid" 2>/dev/null || true
    warn "Force-killed $label (pid $pid)"
  else
    ok "Stopped $label (pid $pid)"
  fi
  stopped_any=1
  return 0
}

# --- Streamlit ------------------------------------------------------------------
step "Stopping the app"
app_pid=""
if [ -f "$RUN_DIR/streamlit.pid" ]; then
  candidate="$(cat "$RUN_DIR/streamlit.pid")"
  if kill -0 "$candidate" 2>/dev/null; then
    case "$(pid_command "$candidate")" in
      *streamlit*) app_pid="$candidate" ;;
      *) warn "PID $candidate is not Streamlit any more; ignoring the stale file" ;;
    esac
  fi
fi

if [ -z "$app_pid" ]; then
  # Fallback: find a Streamlit bound to our port and confirm it serves this project.
  port_pid="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true)"
  if [ -n "$port_pid" ]; then
    case "$(pid_command "$port_pid")" in
      *streamlit*) app_pid="$port_pid" ;;
      *) warn "Port $PORT is used by another program; leaving it alone." ;;
    esac
  fi
fi

if [ -n "$app_pid" ]; then
  terminate "$app_pid" "Streamlit"
else
  ok "App was not running"
fi
rm -f "$RUN_DIR/streamlit.pid"

# --- Models: unload from RAM/VRAM ----------------------------------------------
step "Unloading models"

loaded_has() {  # model name, matched against `ollama ps`
  local want=$1 name
  while read -r name; do
    case "$name" in
      "$want"|"$want":*) return 0 ;;
    esac
  done <<<"$(ollama ps 2>/dev/null | awk 'NR > 1 {print $1}')"
  return 1
}

if curl -fsS -m 2 -o /dev/null "$BASE_URL/api/tags" >/dev/null 2>&1; then
  for model in "$CHAT_MODEL" "$EMBED_MODEL"; do
    if loaded_has "$model"; then
      ollama stop "$model" >/dev/null 2>&1 || true
      ok "Unloaded $model"
    else
      ok "$model was not loaded"
    fi
  done
else
  ok "Ollama is not running, nothing to unload"
fi

# --- Ollama server --------------------------------------------------------------
step "Stopping Ollama"
started_by_us="$(cat "$RUN_DIR/ollama_started_by_us" 2>/dev/null || echo 0)"

stop_ollama() {
  # A running desktop app restarts its own server, so quit the app first.
  if [ -d "/Applications/Ollama.app" ]; then
    osascript -e 'tell application "Ollama" to quit' >/dev/null 2>&1 || true
    sleep 1
    # The app's AppleScript handler can cancel; a TERM to the app is reliable.
    pkill -TERM -f '/Applications/Ollama.app/Contents/MacOS/Ollama' 2>/dev/null || true
    sleep 2
    pkill -KILL -f '/Applications/Ollama.app/Contents/MacOS/Ollama' 2>/dev/null || true
  fi
  pkill -TERM -f 'ollama serve' 2>/dev/null || true
  sleep 1
  pkill -KILL -f 'ollama serve' 2>/dev/null || true
}

if [ "$KEEP_OLLAMA" = 1 ]; then
  if [ "$started_by_us" = 1 ] && [ -f "$RUN_DIR/ollama.pid" ] && kill -0 "$(cat "$RUN_DIR/ollama.pid")" 2>/dev/null; then
    terminate "$(cat "$RUN_DIR/ollama.pid")" "Ollama server"
  else
    ok "Leaving Ollama running (--keep-ollama); models were unloaded"
  fi
else
  ollama_was_up=0
  if curl -fsS -m 2 -o /dev/null "$BASE_URL/api/tags" >/dev/null 2>&1; then ollama_was_up=1; fi
  if pgrep -f 'ollama serve' >/dev/null 2>&1; then ollama_was_up=1; fi
  if [ "$ollama_was_up" = 1 ]; then
    stop_ollama
    ok "Ollama stopped"
    stopped_any=1
  else
    ok "Ollama was not running"
  fi
fi
rm -f "$RUN_DIR/ollama.pid" "$RUN_DIR/ollama_started_by_us"

# --- Verify ---------------------------------------------------------------------
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  warn "Port $PORT is still in use by another program."
else
  ok "Port $PORT is free"
fi
rm -f "$RUN_DIR/database" "$RUN_DIR/port"

# --- Optional cleanup -----------------------------------------------------------
if [ "$CLEAN" = 1 ]; then
  step "Cleaning logs and state"
  rm -rf "$LOG_DIR" "$RUN_DIR"/*.pid "$RUN_DIR"/*.txt 2>/dev/null || true
  ok "Removed .run/"
fi

printf '\n%sDone.%s\n' "$G$B" "$N"
