#!/bin/bash
set -euo pipefail

DATA_DIR="${HERE_I_AM_DATA_DIR:-/Volumes/Personal/here-i-am}"
BUILD_DIR="${HERE_I_AM_BUILD_DIR:-/tmp/here-i-am-mvp-build}"
RUN_DIR="$DATA_DIR/run"

if [[ -d "$BUILD_DIR" ]]; then (cd "$BUILD_DIR" && docker compose down); else docker rm -f here-i-am-app >/dev/null 2>&1 || true; fi
for service in voice ollama-control ollama; do
  pid_file="$RUN_DIR/$service.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(tr -cd '0-9' <"$pid_file")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
    rm -f "$pid_file"
  fi
done
echo 'Here I Am, its local voice, and launcher-owned Ollama services are stopped.'
