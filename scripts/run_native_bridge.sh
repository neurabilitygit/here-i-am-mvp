#!/bin/bash
set -euo pipefail

SOURCE_DIR="${HERE_I_AM_SOURCE_DIR:-/Volumes/Personal/here-i-am-mvp}"
SECRET_DIR="${HERE_I_AM_SECRET_DIR:-/Users/ericbass/Library/Application Support/Here-I-Am/secrets}"
VOICE_ENV="${HERE_I_AM_VOICE_ENV:-/Users/ericbass/Library/Application Support/Here-I-Am/voice-mlx-runtime}"
TOKEN_FILE="$SECRET_DIR/local_bridge_token"

[[ -s "$TOKEN_FILE" ]] || { echo "Missing protected local bridge token." >&2; exit 1; }
export LOCAL_BRIDGE_TOKEN
LOCAL_BRIDGE_TOKEN="$(tr -d '\r\n' <"$TOKEN_FILE")"
[[ -n "$LOCAL_BRIDGE_TOKEN" ]] || { echo "Protected local bridge token is empty." >&2; exit 1; }

case "${1:-}" in
  voice)
    exec "$SOURCE_DIR/scripts/start_voice.sh"
    ;;
  ollama-control)
    [[ -x "$VOICE_ENV/bin/uvicorn" ]] || { echo "Voice runtime is missing uvicorn." >&2; exit 1; }
    exec "$VOICE_ENV/bin/uvicorn" scripts.ollama_control_bridge:app \
      --app-dir "$SOURCE_DIR" --host 127.0.0.1 --port 8778
    ;;
  *)
    echo "Usage: $0 {voice|ollama-control}" >&2
    exit 2
    ;;
esac
