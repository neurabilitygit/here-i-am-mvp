#!/bin/bash
set -euo pipefail

SRC="/Volumes/Personal/here-i-am-mvp"
BUILD="/tmp/here-i-am-mvp-build"

echo "Checking external drive paths..."
if [ ! -d "/Volumes/Personal/here-i-am" ]; then
  echo "Error: /Volumes/Personal/here-i-am not found."
  exit 1
fi

if [ ! -d "$SRC" ]; then
  echo "Error: $SRC not found."
  exit 1
fi

echo "Checking Ollama..."
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama is not reachable at http://localhost:11434"
  echo "Start it first with: ollama serve"
  exit 1
fi

echo "Preparing clean local build folder..."
rm -rf "$BUILD"
mkdir -p "$BUILD"

echo "Syncing project from Personal to local build folder..."
rsync -av --delete \
  --exclude '._*' \
  --exclude '.DS_Store' \
  --exclude '.git' \
  "$SRC"/ "$BUILD"/

echo "Clearing macOS attributes from local build folder..."
xattr -rc "$BUILD" || true

echo "Starting containers..."
cd "$BUILD"
docker compose up --build
