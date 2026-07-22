#!/bin/bash
set -euo pipefail

ROOT="/Volumes/Personal/here-i-am-mvp"
export QWEN_TTS_CACHE_DIR="${QWEN_TTS_CACHE_DIR:-/Volumes/Personal/here-i-am/appdata/voice/cache}"
# Keep executable packages on the Mac's native filesystem. External ExFAT
# volumes can corrupt Python package metadata; recordings and derived voice
# references remain in the configured application data directory.
ENV_DIR="${HERE_I_AM_VOICE_ENV:-/Users/ericbass/Library/Application Support/Here-I-Am/voice-mlx-runtime}"
REQUIREMENTS="$ROOT/requirements-voice-mlx.txt"
REQUIREMENTS_HASH="$(shasum -a 256 "$REQUIREMENTS" | awk '{print $1}')"
STAMP_FILE="$ENV_DIR/.here-i-am-requirements-sha256"

if [[ ! -x "$ENV_DIR/bin/python" || ! -f "$STAMP_FILE" || "$(cat "$STAMP_FILE" 2>/dev/null || true)" != "$REQUIREMENTS_HASH" ]]; then
  PREVIOUS_ENV="$ENV_DIR.previous.$$"
  rm -rf "$PREVIOUS_ENV"
  if [[ -e "$ENV_DIR" ]]; then
    mv "$ENV_DIR" "$PREVIOUS_ENV"
  fi
  restore_previous_env() {
    local exit_code=$?
    trap - EXIT
    rm -rf "$ENV_DIR"
    if [[ -e "$PREVIOUS_ENV" ]]; then
      mv "$PREVIOUS_ENV" "$ENV_DIR"
    fi
    exit "$exit_code"
  }
  trap restore_previous_env EXIT
  # Virtual-environment launchers embed absolute interpreter paths, so the
  # environment must be created at its final location rather than moved there.
  python3.12 -m venv "$ENV_DIR"
  "$ENV_DIR/bin/pip" install -U pip
  "$ENV_DIR/bin/pip" install -r "$REQUIREMENTS"
  printf '%s\n' "$REQUIREMENTS_HASH" >"$STAMP_FILE"
  trap - EXIT
  rm -rf "$PREVIOUS_ENV"
fi

if curl -fsS --max-time 2 http://127.0.0.1:8779/health >/dev/null 2>&1; then
  echo "Here I Am voice bridge is already running on port 8779."
  exit 0
fi

if pgrep -f "uvicorn scripts.(qwen_voice_bridge|mlx_voice_bridge):app" >/dev/null 2>&1; then
  echo "A previous Here I Am voice worker is still shutting down; refusing to start a duplicate." >&2
  exit 1
fi

exec "$ENV_DIR/bin/uvicorn" scripts.mlx_voice_bridge:app \
  --app-dir "$ROOT" --host 127.0.0.1 --port 8779
