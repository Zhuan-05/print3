#!/usr/bin/env bash
set -euo pipefail
umask 077
if ! uname -r | grep -Eqi 'microsoft.*WSL2|microsoft-standard'; then
  echo 'ERROR: WSL2 required. Check Windows: wsl --list --verbose'
  exit 1
fi
if ! command -v apt-get >/dev/null; then
  echo 'ERROR: This installer requires Ubuntu/Debian in WSL2.'
  exit 1
fi
if [[ $EUID -eq 0 ]]; then
  echo 'ERROR: Run as your normal Linux user, not root; sudo will request permission.'
  exit 1
fi
if ! command -v sudo >/dev/null; then
  echo 'ERROR: sudo is missing. Set up your Ubuntu user first.'
  exit 1
fi
sudo -v
sudo apt-get update
sudo apt-get install -y python3 python3-venv curl ca-certificates util-linux
if ! command -v cloudflared >/dev/null; then
  keyfile=$(mktemp)
  trap 'rm -f -- "$keyfile"' EXIT
  curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 \
    https://pkg.cloudflare.com/cloudflare-main.gpg --output "$keyfile"
  [[ -s "$keyfile" ]] || { echo 'ERROR: Empty Cloudflare signing key.'; exit 1; }
  sudo install -d -m 0755 /usr/share/keyrings
  sudo install -m 0644 "$keyfile" /usr/share/keyrings/cloudflare-main.gpg
  printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' \
    | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y cloudflared
fi
cloudflared --version
python3 -c 'import sys; sys.exit(sys.version_info < (3,11))' || {
  echo 'ERROR: Python 3.11+ required. Use Ubuntu-24.04.'
  exit 1
}
echo 'WSL dependencies ready. Starting Print3D next.'
