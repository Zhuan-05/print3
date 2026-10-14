#!/usr/bin/env bash
set -euo pipefail
umask 077
if ! command -v apt-get >/dev/null; then
  echo 'ERROR: This installer requires Ubuntu/Debian Linux or WSL2.'
  exit 1
fi
privilege=()
if [[ $EUID -ne 0 ]]; then
  command -v sudo >/dev/null || { echo 'ERROR: sudo required to install system dependencies.'; exit 1; }
  sudo -v
  privilege=(sudo)
fi
"${privilege[@]}" apt-get update
"${privilege[@]}" apt-get install -y python3 python3-venv curl ca-certificates util-linux
if ! command -v cloudflared >/dev/null; then
  keyfile=$(mktemp)
  trap 'rm -f -- "$keyfile"' EXIT
  curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 \
    https://pkg.cloudflare.com/cloudflare-main.gpg --output "$keyfile"
  [[ -s "$keyfile" ]] || { echo 'ERROR: Empty Cloudflare signing key.'; exit 1; }
  "${privilege[@]}" install -d -m 0755 /usr/share/keyrings
  "${privilege[@]}" install -m 0644 "$keyfile" /usr/share/keyrings/cloudflare-main.gpg
  printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
    | "${privilege[@]}" tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  "${privilege[@]}" apt-get update
  "${privilege[@]}" apt-get install -y cloudflared
fi
cloudflared --version
python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' || {
  echo 'ERROR: Python 3.11+ required. Use Ubuntu-24.04.'
  exit 1
}
echo 'System dependencies ready.'
