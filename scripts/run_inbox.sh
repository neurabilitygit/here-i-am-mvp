#!/bin/bash
set -euo pipefail

cd /Volumes/Personal/here-i-am-mvp
source venv/bin/activate
python scripts/inbox_listener.py
