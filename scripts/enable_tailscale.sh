#!/bin/bash
set -euo pipefail

SECRET_DIR="${HERE_I_AM_SECRET_DIR:-/Users/ericbass/Library/Application Support/Here-I-Am/secrets}"
LOCAL_APP_URL="http://127.0.0.1:8787"

command -v tailscale >/dev/null 2>&1 || {
  echo 'tailscale CLI not found. Install Tailscale first: https://tailscale.com/download' >&2
  exit 1
}

tailscale status >/dev/null 2>&1 || {
  echo 'Tailscale is not logged in. Run `tailscale up` first.' >&2
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

DNS_NAME="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
[[ -n "$DNS_NAME" ]] || {
  echo 'Could not determine this device'"'"'s tailnet hostname.' >&2
  exit 1
}

echo "Configuring tailscale serve to forward https://$DNS_NAME -> $LOCAL_APP_URL"
tailscale serve --bg https / "$LOCAL_APP_URL"

if ! curl -fsS --max-time 5 "https://$DNS_NAME/api/health" >/dev/null 2>&1; then
  echo "Warning: https://$DNS_NAME/api/health did not respond yet." >&2
  echo 'HTTPS certificates may need to be enabled for this tailnet in the admin console:' >&2
  echo '  https://login.tailscale.com/admin/dns' >&2
fi

cat <<EOF

Here I Am should now be reachable at:
  https://$DNS_NAME

Before it works from other devices, add this hostname to .env and restart:
  CORS_ORIGINS=http://localhost:8787,http://127.0.0.1:8787,https://$DNS_NAME
  TRUSTED_HOSTS=localhost,127.0.0.1,testserver,host.docker.internal,$DNS_NAME

Then run ./scripts/start.sh again to pick up the change, and open the URL
above on your phone. Log in with the passphrase set via set_passphrase.py.
EOF
