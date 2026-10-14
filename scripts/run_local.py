"""WSL-only foreground supervisor. Never print config values or raw service logs."""
import os
import json
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request


def export_google_settings(runtime, webhook, settings):
    """Private helper: paste into the existing form-bound Stage 1 Apps Script."""
    values = {"WEBHOOK_URL": webhook, "WEBHOOK_SECRET": settings.webhook_secret}
    script = ("// PRIVATE: contains your webhook secret. Do not share.\n"
              "// Paste into the EXISTING Stage 1 Apps Script; run configurePrint3D once.\n"
              "function configurePrint3D() {\n"
              "  PropertiesService.getScriptProperties().setProperties("
              + json.dumps(values, ensure_ascii=False) + ", false);\n"
              "  console.log('Print3D webhook properties saved.');\n}\n")
    target = runtime / 'ConfigurePrint3D.gs'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(script)
    return target


def main():
    runtime = Path(sys.argv[1])
    # Import the project's validated settings without displaying exception values.
    sys.path.insert(0, str(Path.cwd()))
    try:
        from app.config import Settings
        settings = Settings.load()
    except Exception:
        print('ERROR: Invalid or incomplete .env. Run deploy_print3d.bat reconfigure; no secrets were printed.')
        return 1
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 8000))
        except OSError:
            print('ERROR: Port 8000 is occupied. Stop the existing backend before retrying.')
            return 1
    children = []
    logs = []

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # Local health probes must bypass any outbound proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def healthy(url):
        try:
            with opener.open(url, timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def launch(command, name):
        log = open(runtime / name, 'w', encoding='utf-8')
        os.chmod(runtime / name, 0o600)
        logs.append(log)
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        children.append(child)
        return child

    try:
        backend = launch([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host',
                          '127.0.0.1', '--port', '8000', '--workers', '1',
                          '--no-access-log'], 'backend.log')
        print('Waiting for backend /healthz (up to 90 seconds)...', flush=True)
        deadline = time.monotonic() + 90
        while not healthy('http://127.0.0.1:8000/healthz'):
            if backend.poll() is not None or time.monotonic() > deadline:
                print('ERROR: Backend failed readiness. Check .env, Telegram access and duplicate bot processes.')
                return 1
            time.sleep(1)
        # An explicit empty config prevents an existing named tunnel config from interfering.
        config = runtime / 'quick-tunnel.yml'
        config.write_text('{}\n', encoding='utf-8')
        tunnel = launch(['cloudflared', 'tunnel', '--config', str(config),
                         '--no-autoupdate', '--url', 'http://127.0.0.1:8000'], 'tunnel.log')
        print('Waiting for Cloudflare Quick Tunnel (up to 90 seconds)...', flush=True)
        deadline = time.monotonic() + 90
        url = None
        while time.monotonic() < deadline:
            if backend.poll() is not None or tunnel.poll() is not None:
                break
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com\b',
                              (runtime / 'tunnel.log').read_text(errors='replace'))
            if match:
                url = match.group(0)
                break
            time.sleep(1)
        if not url:
            print('ERROR: Tunnel did not return a URL. Check WSL internet/firewall access.')
            return 1
        webhook = url + '/webhooks/google-form'
        (runtime / 'webhook-url.txt').write_text(webhook + '\n', encoding='utf-8')
        print('\nWEBHOOK_URL = ' + webhook)
        helper = export_google_settings(runtime, webhook, settings)
        print('Private Google configuration file: ' + str(helper))
        print('Paste this file into the EXISTING Stage 1 Apps Script and run configurePrint3D once.')
        print('This configures URL/Secret; the Stage 1 submit/retry triggers must already be installed.')
        try:
            subprocess.run(['clip.exe'], input=helper.read_bytes(), timeout=5,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print('Google configuration script copied to Windows clipboard. Paste into Apps Script.')
        except (OSError, subprocess.SubprocessError):
            print('Clipboard unavailable; open the private file above to copy its contents.')
        print('The generated file contains a secret; keep it private. A restart needs the new script applied again.')
        print('URL allocated; public reachability is not yet verified. Open ' + url + '/healthz')
        print('Keep this window open. Ctrl+C stops both processes. A restart changes the URL.', flush=True)
        while backend.poll() is None and tunnel.poll() is None:
            time.sleep(2)
        print('ERROR: A service exited. Both services will be stopped; restart after checking the cause.')
        return 1
    except KeyboardInterrupt:
        print('\nStopping backend and tunnel...')
        return 0
    except Exception as exc:
        print('ERROR: Launcher failed (' + type(exc).__name__ + '). No raw error values displayed.')
        return 1
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in reversed(children):
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for log in logs:
            log.close()


if __name__ == '__main__':
    sys.exit(main())
