#!/bin/bash
set -u

check() {
  local label="$1" url="$2"
  if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then printf '%-24s ready\n' "$label"; else printf '%-24s unavailable\n' "$label"; fi
}

check 'Application' http://127.0.0.1:8787/api/health
check 'Application readiness' http://127.0.0.1:8787/api/ready
check 'Local voice' http://127.0.0.1:8779/health
check 'Ollama control' http://127.0.0.1:8778/ollama/status
check 'Ollama' http://127.0.0.1:11434/api/tags
