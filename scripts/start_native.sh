#!/bin/bash
set -euo pipefail
PROFILE="${HERE_I_AM_DEPLOYMENT_PROFILE:-/Users/ericbass/Library/Application Support/Here-I-Am/native-production/production.json}"
[[ -f "$PROFILE" ]] || { echo 'Native deployment is not configured.' >&2; exit 1; }
PYTHON="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["backend_python"])' "$PROFILE")"
SOURCE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_root"])' "$PROFILE")"
KIND="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["kind"])' "$PROFILE")"
[[ "$KIND" == production ]] || { echo 'The normal launcher requires a production profile.' >&2; exit 1; }
"$PYTHON" "$SOURCE/scripts/native_deployment.py" check --profile "$PROFILE"
if [[ "${HERE_I_AM_ENABLE_TAILSCALE:-true}" == true ]]; then
  TAILSCALE_DNS_NAME="$("$SOURCE/scripts/start_tailscale.sh")"
  export TAILSCALE_DNS_NAME
fi
"$PYTHON" "$SOURCE/scripts/native_deployment.py" start --profile "$PROFILE"
ready=false
for _ in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:8787/api/ready >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]] || { echo 'Native application is not ready. Inspect its private service logs.' >&2; exit 1; }
URL=http://127.0.0.1:8787
if [[ "${HERE_I_AM_ENABLE_TAILSCALE:-true}" == true ]]; then
  "$SOURCE/scripts/enable_tailscale.sh"
  URL="https://$TAILSCALE_DNS_NAME"
fi
if [[ "${HERE_I_AM_OPEN_BROWSER:-true}" == true ]]; then open -a Safari "$URL"; fi
echo "Here I Am is ready at $URL (native Mac application; Docker not required)."
