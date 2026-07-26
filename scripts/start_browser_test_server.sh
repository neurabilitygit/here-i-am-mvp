#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${HERE_I_AM_BROWSER_TEST_DATA:-/tmp/here-i-am-browser-test-data}"
mkdir -p "$DATA_ROOT/library/sessions" "$DATA_ROOT/library/archive" "$DATA_ROOT/appdata"

export DATA_ROOT
export SESSIONS_DIR="$DATA_ROOT/library/sessions"
export ARCHIVE_DIR="$DATA_ROOT/library/archive"
export CHROMA_DIR="$DATA_ROOT/appdata/chroma"
export LOGS_DIR="$DATA_ROOT/appdata/logs"
export TMP_DIR="$DATA_ROOT/appdata/tmp"
export JOBS_DIR="$DATA_ROOT/appdata/jobs"
export LOCKS_DIR="$DATA_ROOT/appdata/locks"
export EXPORTS_DIR="$DATA_ROOT/appdata/exports"
export BACKUP_ROOT="$DATA_ROOT/appdata/backups"
export PREFERENCES_PATH="$DATA_ROOT/appdata/preferences.json"
export FIDELITY_PROFILE_PATH="$DATA_ROOT/appdata/speaker_fingerprint.json"
export FEEDBACK_PATH="$DATA_ROOT/appdata/answer_feedback.jsonl"
export GENERATION_AUDIT_PATH="$DATA_ROOT/appdata/generation_audit.jsonl"
export ACTIVITY_EVENT_PATH="$DATA_ROOT/appdata/logs/activity_events.jsonl"
export VOICE_DIR="$DATA_ROOT/appdata/voice"
export SPEAKERS_DIR="$DATA_ROOT/appdata/speakers"
export CORS_ORIGINS="http://127.0.0.1:8791"
export TRUSTED_HOSTS="127.0.0.1,localhost,testserver"
export PYTHONPATH="$ROOT/app"

if command -v uvicorn >/dev/null 2>&1; then
  exec uvicorn main:app --app-dir "$ROOT/app" --host 127.0.0.1 --port 8791 --no-access-log
fi

if docker image inspect here-i-am-patch-test >/dev/null 2>&1; then
  STALE_CONTAINERS="$(docker ps -q --filter label=com.hereiam.browser-test=true)"
  if [[ -n "$STALE_CONTAINERS" ]]; then
    docker stop $STALE_CONTAINERS >/dev/null
  fi
  CONTAINER_NAME="here-i-am-browser-test-$$"
  cleanup_browser_container() {
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
  }
  trap cleanup_browser_container EXIT INT TERM
  docker run --rm --name "$CONTAINER_NAME" --label com.hereiam.browser-test=true -p 127.0.0.1:8791:8000 \
    -v "$DATA_ROOT:/data" \
    -e DATA_ROOT=/data -e SESSIONS_DIR=/data/library/sessions -e ARCHIVE_DIR=/data/library/archive \
    -e CHROMA_DIR=/data/appdata/chroma -e LOGS_DIR=/data/appdata/logs -e TMP_DIR=/data/appdata/tmp \
    -e JOBS_DIR=/data/appdata/jobs -e LOCKS_DIR=/data/appdata/locks -e EXPORTS_DIR=/data/appdata/exports \
    -e BACKUP_ROOT=/data/appdata/backups -e PREFERENCES_PATH=/data/appdata/preferences.json \
    -e FIDELITY_PROFILE_PATH=/data/appdata/speaker_fingerprint.json -e FEEDBACK_PATH=/data/appdata/answer_feedback.jsonl \
    -e GENERATION_AUDIT_PATH=/data/appdata/generation_audit.jsonl -e ACTIVITY_EVENT_PATH=/data/appdata/logs/activity_events.jsonl \
    -e VOICE_DIR=/data/appdata/voice -e SPEAKERS_DIR=/data/appdata/speakers \
    -e CORS_ORIGINS=http://127.0.0.1:8791 -e TRUSTED_HOSTS=127.0.0.1,localhost,testserver \
    --entrypoint uvicorn here-i-am-patch-test main:app --app-dir /app --host 0.0.0.0 --port 8000 --no-access-log &
  wait $!
  exit $?
fi

echo 'uvicorn or the here-i-am-patch-test image is required for browser tests' >&2
exit 1
