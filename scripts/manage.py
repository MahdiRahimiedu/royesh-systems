"""Laptop launcher: python scripts/manage.py setup|start|check. No Docker required."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'
SERVICES = {'personnel': (8001, 3001), 'inventory': (8002, 3002), 'commerce': (8003, 3003)}


def environment():
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    config = ROOT / '.env'
    if config.exists():
        for line in config.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def run(command, cwd=ROOT):
    subprocess.run([str(x) for x in command], cwd=cwd, env=environment(), check=True)


def setup():
    if not PYTHON.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    requirements = ROOT / ('requirements.lock.txt' if (ROOT / 'requirements.lock.txt').exists() else 'requirements.txt')
    run([PYTHON, '-m', 'pip', 'install', '-r', requirements])
    run([NPM, 'ci'], ROOT / 'frontend')
    run([NPM, 'run', 'build'], ROOT / 'frontend')
    print('Setup complete. Run start.cmd or python scripts/manage.py start', flush=True)


def health(url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(.5)
    raise RuntimeError(f'Could not start {url}; inspect .runtime logs')


def start(only=None):
    if not PYTHON.exists() or not (ROOT / 'frontend/.next/BUILD_ID').exists():
        raise RuntimeError('Run setup.cmd first. A production frontend build and Python environment are required.')
    env = environment()
    selected = {only: SERVICES[only]} if only else SERVICES
    processes, logs = [], []
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    stop_request = runtime / 'stop.request'
    stop_request.unlink(missing_ok=True)
    try:
        for service, (api_port, web_port) in selected.items():
            for label, args, cwd in [
                ('api', [str(PYTHON), '-m', 'uvicorn', f'services.{service}.app:app', '--host', env.get('API_HOST', '127.0.0.1'), '--port', str(api_port)], ROOT),
                ('web', [NPM, 'run', f'start:{service}'], ROOT / 'frontend'),
            ]:
                log = open(runtime / f'{service}-{label}.log', 'w', encoding='utf-8')
                logs.append(log)
                processes.append(subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        for service, (api_port, web_port) in selected.items():
            health(f'http://127.0.0.1:{api_port}/health')
            health(f'http://127.0.0.1:{web_port}')
            print(f'{service}: http://localhost:{web_port} | API docs: http://localhost:{api_port}/docs', flush=True)
        print('Ready. Keep this window open. Press Ctrl+C to stop all applications.', flush=True)
        while True:
            time.sleep(1)
            if stop_request.exists():
                print('Stop requested. Closing applications...', flush=True)
                break
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f'Application process stopped ({process.returncode}); inspect .runtime logs.')
    except KeyboardInterrupt:
        print('Stopping applications...', flush=True)
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.terminate()
        for log in logs:
            log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['setup', 'start', 'stop', 'check'])
    parser.add_argument('--service', choices=list(SERVICES))
    args = parser.parse_args()
    if args.command == 'setup':
        setup()
    elif args.command == 'start':
        start(args.service)
    elif args.command == 'stop':
        runtime = ROOT / '.runtime'
        runtime.mkdir(exist_ok=True)
        (runtime / 'stop.request').write_text('stop', encoding='utf-8')
        print('Stop requested for applications started by this launcher.')
    else:
        run([PYTHON, '-m', 'pytest', '-q'])
        run([NPM, 'test'], ROOT / 'frontend')
        run([NPM, 'run', 'typecheck'], ROOT / 'frontend')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
