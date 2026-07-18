#!/bin/bash
set -euo pipefail

ROOT="/Volumes/Personal/here-i-am-mvp"
export QWEN_TTS_CACHE_DIR="${QWEN_TTS_CACHE_DIR:-/Volumes/Personal/here-i-am/appdata/voice/cache}"
# Keep executable packages on the Mac's native filesystem. External ExFAT
# volumes can corrupt Python package metadata; recordings and derived voice
# references remain in the configured application data directory.
ENV_DIR="${HERE_I_AM_VOICE_ENV:-/Users/ericbass/Library/Application Support/Here-I-Am/voice-mlx-runtime}"

if [ ! -d "$ENV_DIR" ]; then
  python3.12 -m venv "$ENV_DIR"
  "$ENV_DIR/bin/pip" install -U pip
  "$ENV_DIR/bin/pip" install -r "$ROOT/requirements-voice-mlx.txt"
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
