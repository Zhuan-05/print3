#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
mode=${1:-start}
case "$mode" in start|install|reconfigure|build|test) ;; *) echo 'ERROR: Unknown deployment mode.'; exit 1 ;; esac
if [[ $(uname -s) != Linux ]]; then
  echo 'ERROR: Use Ubuntu/Debian Linux or Windows WSL2.'
  exit 1
fi
if uname -r | grep -Eqi 'microsoft' && ! uname -r | grep -Eqi 'microsoft.*WSL2|microsoft-standard'; then
  echo 'ERROR: WSL2 required. Convert with: wsl --set-version Ubuntu-24.04 2'
  exit 1
fi
# Build only needs Python standard library; it never installs or configures services.
if [[ $mode == build ]]; then
  exec python3 scripts/build_release.py
fi
if ! command -v cloudflared >/dev/null || ! command -v flock >/dev/null || ! python3 -c 'import venv,ensurepip; import sys; sys.exit(sys.version_info < (3,11))' 2>/dev/null; then
  bash scripts/install_dependencies.sh
fi
project_id=$(printf '%s' "$PWD" | sha256sum | cut -c1-16)
runtime="$HOME/.local/share/print3d-launcher/$project_id"
mkdir -p "$runtime"
chmod 700 "$runtime"
exec 9>"$runtime/launcher.lock"
flock -n 9 || { echo 'ERROR: Another launcher for this project is running. Close it first.'; exit 1; }
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
case "$mode" in
  install)
    echo 'Installation ready. Run npm start to configure and start Print3D.'
    exit 0
    ;;
  test)
    "$runtime/venv/bin/python" -m pip install --disable-pip-version-check -r requirements-test.txt >"$runtime/install.log" 2>&1 || {
      echo 'ERROR: Test dependency installation failed. Check internet access.'; exit 1;
    }
    exec "$runtime/venv/bin/python" -B -m pytest -q -p no:cacheprovider
    ;;
  reconfigure)
    exec "$runtime/venv/bin/python" -u auto_setup.py --reconfigure
    ;;
esac
"$runtime/venv/bin/python" -u auto_setup.py
exec "$runtime/venv/bin/python" -u scripts/run_local.py "$runtime"
