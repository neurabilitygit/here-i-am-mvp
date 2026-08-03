#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRET_DIR="${HERE_I_AM_SECRET_DIR:-/Users/ericbass/Library/Application Support/Here-I-Am/secrets}"
LOCAL_APP_URL="http://127.0.0.1:8787"

command -v tailscale >/dev/null 2>&1 || {
  echo 'tailscale CLI not found. Install Tailscale first: https://tailscale.com/download' >&2
  exit 1
}

[[ -s "$SECRET_DIR/auth_passphrase_hash" ]] || {
  echo "No login passphrase is configured. Run './scripts/set_passphrase.py' before exposing Here I Am over Tailscale." >&2
  exit 1
}

curl -fsS --max-time 2 "$LOCAL_APP_URL/api/health" >/dev/null 2>&1 || {
  echo "Here I Am is not reachable at $LOCAL_APP_URL. Run './scripts/start.sh' first." >&2
  exit 1
}

DNS_NAME="${TAILSCALE_DNS_NAME:-}"
if [[ -z "$DNS_NAME" ]]; then
  DNS_NAME="$("$SCRIPT_DIR/start_tailscale.sh")"
fi
[[ -n "$DNS_NAME" ]] || {
  echo 'Could not determine this device'"'"'s tailnet hostname.' >&2
  exit 1
}

echo "Configuring tailscale serve to forward https://$DNS_NAME -> $LOCAL_APP_URL"
tailscale serve --bg "$LOCAL_APP_URL"

if ! curl -fsS --max-time 5 "https://$DNS_NAME/api/health" >/dev/null 2>&1; then
  echo "Warning: https://$DNS_NAME/api/health did not respond yet." >&2
  echo 'HTTPS certificates may need to be enabled for this tailnet in the admin console:' >&2
  echo '  https://login.tailscale.com/admin/dns' >&2
fi

cat <<EOF

Here I Am is reachable from devices signed into your tailnet at:
  https://$DNS_NAME

Open that URL on your iPhone while Tailscale is connected, then log in with
the Here I Am passphrase. Docker remains bound to this Mac's loopback address.
EOF
