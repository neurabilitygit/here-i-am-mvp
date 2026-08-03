#!/bin/bash
set -euo pipefail

TAILSCALE_APP="${HERE_I_AM_TAILSCALE_APP:-Tailscale}"

command -v tailscale >/dev/null 2>&1 || {
  echo 'Tailscale is required for iPhone access. Install it from https://tailscale.com/download' >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo 'python3 is required to inspect Tailscale status.' >&2
  exit 1
}

tailscale_state() {
  tailscale status --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("BackendState", ""))' 2>/dev/null \
    || true
}

if [[ "$(tailscale_state)" != 'Running' ]]; then
  echo 'Starting the private Tailscale connection for iPhone access…' >&2
  if [[ "$(uname -s)" == 'Darwin' ]]; then
    open -gj -a "$TAILSCALE_APP" >/dev/null 2>&1 || true
  fi

  # A flag passed to `tailscale up` makes the CLI require every existing
  # non-default preference. Run it with no flags so settings are preserved,
  # and implement the time limit outside the command.
  tailscale up >&2 &
  up_pid=$!
  connected=false
  for _ in $(seq 1 60); do
    if [[ "$(tailscale_state)" == 'Running' ]]; then
      connected=true
      break
    fi
    kill -0 "$up_pid" 2>/dev/null || break
    sleep 1
  done
  if [[ "$connected" != 'true' ]] && kill -0 "$up_pid" 2>/dev/null; then
    kill "$up_pid" 2>/dev/null || true
  fi
  wait "$up_pid" 2>/dev/null || true
  if [[ "$connected" != 'true' && "$(tailscale_state)" != 'Running' ]]; then
    echo 'Tailscale did not connect. Open the Tailscale menu-bar app, sign in if requested, then run this launcher again.' >&2
    exit 1
  fi
fi

DNS_NAME="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Self", {}).get("DNSName", "").rstrip("."))')"
[[ -n "$DNS_NAME" ]] || {
  echo 'Tailscale is connected, but this Mac has no MagicDNS hostname. Enable MagicDNS for the tailnet and try again.' >&2
  exit 1
}

echo "Tailscale is connected as $DNS_NAME" >&2
printf '%s\n' "$DNS_NAME"
