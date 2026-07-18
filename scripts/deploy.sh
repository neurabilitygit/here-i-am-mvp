#!/bin/bash
set -euo pipefail

ROOT="${HERE_I_AM_SOURCE_DIR:-/Volumes/Personal/here-i-am-mvp}"
cd "$ROOT"
[[ -z "$(git status --porcelain)" ]] || { echo 'Deployment refused: commit or intentionally discard working changes first.' >&2; exit 1; }
git fetch --prune origin
git status -sb
tmpdir="$(mktemp -d /tmp/here-i-am-release.XXXXXX)"
trap 'rm -rf "$tmpdir"' EXIT
rsync -a --exclude='.git' --exclude='._*' --exclude='.DS_Store' --exclude='__pycache__' ./ "$tmpdir/"
docker build --target test -t here-i-am-release-test "$tmpdir"
docker run --rm here-i-am-release-test
"$ROOT/scripts/start.sh"
