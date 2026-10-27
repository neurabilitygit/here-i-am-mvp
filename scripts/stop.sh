#!/bin/bash
set -euo pipefail

NATIVE_PROFILE="${HERE_I_AM_DEPLOYMENT_PROFILE:-/Users/ericbass/Library/Application Support/Here-I-Am/native-production/production.json}"
if [[ -f "$NATIVE_PROFILE" && "${HERE_I_AM_LEGACY_DOCKER:-false}" != true ]]; then
  NATIVE_PYTHON="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["backend_python"])' "$NATIVE_PROFILE")"
  NATIVE_SOURCE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_root"])' "$NATIVE_PROFILE")"
  exec "$NATIVE_PYTHON" "$NATIVE_SOURCE/scripts/native_deployment.py" stop --profile "$NATIVE_PROFILE"
fi

DATA_DIR="${HERE_I_AM_DATA_DIR:-/Volumes/Personal/here-i-am}"
BUILD_DIR="${HERE_I_AM_BUILD_DIR:-/tmp/here-i-am-mvp-build}"
RUN_DIR="$DATA_DIR/run"

if [[ -d "$BUILD_DIR" ]]; then (cd "$BUILD_DIR" && docker compose down); else docker rm -f here-i-am-app >/dev/null 2>&1 || true; fi
for service in voice ollama-control ollama; do
  pid_file="$RUN_DIR/$service.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(tr -cd '0-9' <"$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
      expected=''
      case "$service" in
        voice) expected='mlx_voice_bridge' ;;
        ollama-control) expected='ollama_control_bridge' ;;
        ollama) expected='ollama serve' ;;
      esac
      if [[ "$command" == *"$expected"* ]]; then
        kill "$pid" 2>/dev/null || true
      else
        echo "Refusing to stop PID $pid for $service because its process identity does not match." >&2
      fi
    fi
    rm -f "$pid_file"
  fi
done
echo 'Here I Am, its local voice, and launcher-owned Ollama services are stopped.'
