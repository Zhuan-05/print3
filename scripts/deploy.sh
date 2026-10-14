#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
if ! uname -r | grep -Eqi 'microsoft.*WSL2|microsoft-standard'; then
  echo 'ERROR: Use WSL2 Ubuntu 24.04. See README.md.'
  exit 1
fi
if [[ $EUID -eq 0 ]]; then
  echo 'ERROR: Open Ubuntu first and create your normal Linux username/password.'
  exit 1
fi
if ! command -v cloudflared >/dev/null || ! python3 -c 'import venv,ensurepip; import sys; sys.exit(sys.version_info < (3,11))' 2>/dev/null; then
  bash scripts/install_wsl_dependencies.sh
fi
project_id=$(printf '%s' "$PWD" | sha256sum | cut -c1-16)
runtime="$HOME/.local/share/print3d-launcher/$project_id"
mkdir -p "$runtime"
chmod 700 "$runtime"
exec 9>"$runtime/launcher.lock"
flock -n 9 || { echo 'ERROR: Another launcher/ID tool for this project is running. Close it first.'; exit 1; }
if [[ ! -x "$runtime/venv/bin/python" ]]; then
  python3 -m venv "$runtime/venv"
fi
requirements_hash=$(sha256sum requirements.txt | cut -d ' ' -f1)
if [[ ! -f "$runtime/requirements.sha256" ]] || [[ $(cat "$runtime/requirements.sha256") != "$requirements_hash" ]] || ! "$runtime/venv/bin/python" -m pip check >/dev/null 2>&1; then
  echo 'Installing Python dependencies...'
  if ! "$runtime/venv/bin/python" -m pip install --disable-pip-version-check -r requirements.txt >"$runtime/install.log" 2>&1; then
    echo 'ERROR: Dependency download failed. Check internet/proxy and retry.'
    exit 1
  fi
  printf '%s' "$requirements_hash" >"$runtime/requirements.sha256"
fi
if [[ ${1:-} == reconfigure ]]; then
  "$runtime/venv/bin/python" -u auto_setup.py --reconfigure
else
  "$runtime/venv/bin/python" -u auto_setup.py
fi
exec "$runtime/venv/bin/python" -u scripts/run_local.py "$runtime"
