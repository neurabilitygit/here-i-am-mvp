#!/bin/bash
set -euo pipefail

BUILD="/tmp/here-i-am-mvp-build"

if [ -d "$BUILD" ]; then
  echo "Stopping containers..."
  cd "$BUILD"
  docker compose down
else
  echo "Build folder not found. Nothing to stop in Docker build directory."
fi

echo "Containers stopped."
echo "If Ollama is running in a Terminal window, stop it there with Ctrl+C."
