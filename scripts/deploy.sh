#!/bin/bash
set -euo pipefail

SRC="/Volumes/Personal/here-i-am-mvp"
BUILD="/tmp/here-i-am-mvp-build"

echo "==> Moving to repo"
cd "$SRC"

echo "==> Git status"
git status --short || true

if [ -n "$(git status --porcelain)" ]; then
  echo "==> Uncommitted changes detected"
  read -r -p "Enter commit message (or leave blank to skip commit): " COMMIT_MSG

  if [ -n "${COMMIT_MSG}" ]; then
    echo "==> Staging changes"
    git add .

    echo "==> Committing"
    git commit -m "$COMMIT_MSG"

    echo "==> Pushing to GitHub"
    git push || echo "Git push failed. Continuing with local deploy."
  else
    echo "==> Skipping git commit and push"
  fi
else
  echo "==> Working tree clean"
  echo "==> Attempting git push"
  git push || echo "Git push failed or nothing to push. Continuing with local deploy."
fi

echo "==> Preparing clean build folder"
rm -rf "$BUILD"
mkdir -p "$BUILD"

echo "==> Syncing repo to build folder"
rsync -av --delete \
  --exclude '._*' \
  --exclude '.DS_Store' \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$SRC"/ "$BUILD"/

echo "==> Clearing macOS extended attributes"
xattr -rc "$BUILD" || true

echo "==> Rebuilding and restarting Docker app"
cd "$BUILD"
docker compose down
docker compose up --build
