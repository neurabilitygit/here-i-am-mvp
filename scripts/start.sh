#!/bin/bash
set -euo pipefail

SOURCE_DIR="${HERE_I_AM_SOURCE_DIR:-/Volumes/Personal/here-i-am-mvp}"
DATA_DIR="${HERE_I_AM_DATA_DIR:-/Volumes/Personal/here-i-am}"
BUILD_DIR="${HERE_I_AM_BUILD_DIR:-/tmp/here-i-am-mvp-build}"
RUN_DIR="$DATA_DIR/run"
VOICE_ENV="${HERE_I_AM_VOICE_ENV:-/Users/ericbass/Library/Application Support/Here-I-Am/voice-mlx-runtime}"
SECRET_DIR="${HERE_I_AM_SECRET_DIR:-/Users/ericbass/Library/Application Support/Here-I-Am/secrets}"

wait_for_url() {
  local url="$1" timeout="$2" label="$3" elapsed=0
  printf 'Waiting for %s' "$label"
  until curl -fsS --max-time 3 "$url" >/dev/null 2>&1; do
    if (( elapsed >= timeout )); then printf '\n'; return 1; fi
    printf '.'; sleep 1; elapsed=$((elapsed + 1))
  done
  printf ' ready.\n'
}

[[ -d "$SOURCE_DIR" ]] || { echo "Missing source: $SOURCE_DIR" >&2; exit 1; }
[[ -d "$DATA_DIR" ]] || { echo "Missing data volume: $DATA_DIR" >&2; exit 1; }
for command in docker ollama rsync curl python3; do command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 1; }; done
mkdir -p "$RUN_DIR" "$SECRET_DIR"
umask 077
BRIDGE_TOKEN_FILE="$SECRET_DIR/local_bridge_token"
if [[ ! -s "$BRIDGE_TOKEN_FILE" ]]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(32))' >"$BRIDGE_TOKEN_FILE"
fi
LOCAL_BRIDGE_TOKEN="$(tr -d '\r\n' <"$BRIDGE_TOKEN_FILE")"
export LOCAL_BRIDGE_TOKEN

bridge_token_works() {
  local url="$1" status
  status="$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H "X-Here-I-Am-Local: $LOCAL_BRIDGE_TOKEN" "$url/auth/check" 2>/dev/null || true)"
  [[ "$status" == '200' ]]
}

restart_stale_bridge() {
  local service="$1" url="$2" health_url="$3" pid_file
  pid_file="$RUN_DIR/$service.pid"
  if curl -fsS --max-time 2 "$health_url" >/dev/null 2>&1 && ! bridge_token_works "$url"; then
    if [[ -s "$pid_file" ]]; then
      local pid
      pid="$(tr -cd '0-9' <"$pid_file")"
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do curl -fsS --max-time 1 "$health_url" >/dev/null 2>&1 || break; sleep 0.25; done
    else
      echo "$service is running with a different bridge token and was not started by this launcher." >&2
      exit 1
    fi
  fi
}

start_native_bridge() {
  local service="$1" log_file="$2"
  python3 "$SOURCE_DIR/scripts/daemonize.py" \
    --pid-file "$RUN_DIR/$service.pid" --log-file "$log_file" -- \
    "$SOURCE_DIR/scripts/run_native_bridge.sh" "$service"
}

if ! docker info >/dev/null 2>&1; then
  open -a Docker
  for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || { echo 'Docker Desktop did not become ready.' >&2; exit 1; }
fi

export OLLAMA_MODELS="$DATA_DIR/models/ollama"
mkdir -p "$OLLAMA_MODELS"
if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  nohup ollama serve >"$RUN_DIR/ollama.log" 2>&1 & echo $! >"$RUN_DIR/ollama.pid"
fi
wait_for_url http://127.0.0.1:11434/api/tags 120 Ollama
installed_models="$(ollama list | awk 'NR > 1 {print $1}')"
for model in gemma4:e4b embeddinggemma; do
  grep -Fxq "$model" <<<"$installed_models" || grep -Fxq "${model}:latest" <<<"$installed_models" || ollama pull "$model"
done

restart_stale_bridge voice http://127.0.0.1:8779 http://127.0.0.1:8779/health
if ! curl -fsS --max-time 2 http://127.0.0.1:8779/health >/dev/null 2>&1; then
  start_native_bridge voice "$RUN_DIR/voice.log"
fi
wait_for_url http://127.0.0.1:8779/health 600 'local voice'

restart_stale_bridge ollama-control http://127.0.0.1:8778 http://127.0.0.1:8778/ollama/status
if ! curl -fsS --max-time 2 http://127.0.0.1:8778/ollama/status >/dev/null 2>&1; then
  start_native_bridge ollama-control "$RUN_DIR/ollama-control.log"
fi
wait_for_url http://127.0.0.1:8778/ollama/status 60 'Ollama control service'

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
rsync -a --delete --exclude='.git' --exclude='._*' --exclude='.DS_Store' --exclude='venv' --exclude='__pycache__' "$SOURCE_DIR/" "$BUILD_DIR/"
xattr -rc "$BUILD_DIR" || true
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  umask 077
  mkdir -p "$SECRET_DIR"
  OPENAI_API_KEY_HOST_FILE="$SECRET_DIR/openai_api_key"
  printf '%s' "$OPENAI_API_KEY" >"$OPENAI_API_KEY_HOST_FILE"
  chmod 600 "$OPENAI_API_KEY_HOST_FILE"
  export OPENAI_API_KEY_HOST_FILE OPENAI_API_KEY_FILE=/run/secrets/openai_api_key
  unset OPENAI_API_KEY
fi
if [[ -s "$SECRET_DIR/openai_api_key" ]]; then
  OPENAI_API_KEY_HOST_FILE="$SECRET_DIR/openai_api_key"
  export OPENAI_API_KEY_HOST_FILE OPENAI_API_KEY_FILE=/run/secrets/openai_api_key
fi
(cd "$BUILD_DIR" && docker compose up -d --build --force-recreate)
wait_for_url http://127.0.0.1:8787/api/ready 240 'Here I Am'

if [[ "${HERE_I_AM_OPEN_BROWSER:-true}" == 'true' ]]; then open -a Safari http://127.0.0.1:8787; fi
echo 'Here I Am is ready at http://127.0.0.1:8787'
