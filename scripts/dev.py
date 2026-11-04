#!/usr/bin/env python3
"""Run development in an isolated database, build directory and pair of ports."""

import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def environment(overrides=None):
    # Never import backend/.env or inherit production credentials/integration settings.
    inherited = os.environ if overrides is None else overrides
    allowed = ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'SHELL')
    env = {key: value for key, value in inherited.items() if key in allowed}
    config_file = ROOT / 'backend/.env.development'
    env.update({key: value for key, value in dotenv_values(config_file).items() if value is not None})
    for key in ('DEV_DATABASE_URL', 'API_PORT', 'WEB_PORT'):
        if key in inherited:
            env[key] = inherited[key]
    uri = env.pop('DEV_DATABASE_URL', 'postgresql+psycopg:///antares_test_dev')
    parsed = urlparse(uri)
    name = parsed.path.lstrip('/')
    if not parsed.scheme.startswith('postgresql') or not (name.startswith('antares_test_') or name.endswith('_dev')):
        raise ValueError('Desenvolvimento requer um banco PostgreSQL antares_test_* ou terminado em _dev.')
    if parsed.hostname not in (None, 'localhost', '127.0.0.1', '::1'):
        raise ValueError('O banco de desenvolvimento deve ser local.')
    api, web = int(env.pop('API_PORT', '5003')), int(env.pop('WEB_PORT', '3003'))
    if api == web or any(port in (3002, 5002) or not 1024 <= port <= 65535 for port in (api, web)):
        raise ValueError('Use portas distintas de desenvolvimento; 3002 e 5002 são reservadas à produção.')
    env.update(
        APP_ENV='development',
        DATABASE_URL=uri,
        ANTARES_ENV_FILE=str(config_file),
        SECRET_KEY=env.get('SECRET_KEY') or secrets.token_hex(32),
        JWT_SECRET_KEY=env.get('JWT_SECRET_KEY') or secrets.token_hex(32),
        FLASK_API_URL=f'http://127.0.0.1:{api}/api/v1',
        APP_URL=f'http://127.0.0.1:{web}',
        COOKIE_SECURE='false',
        PROJECT_FILES_DIR=str(ROOT / '.local-services/dev/project-files'),
        BACKUP_STATUS_PATH=str(ROOT / '.local-services/dev/backup-status.json'),
        ALLOWED_ORIGINS=f'http://localhost:{web},http://127.0.0.1:{web}',
    )
    return env, api, web


def main():
    env, api, web = environment()
    for port in (api, web):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))  # Refuse occupied ports before applying any migration.
    python = str(ROOT / 'backend/.venv/bin/python')
    subprocess.run([python, '-m', 'flask', '--app', 'run', 'db', 'upgrade'], cwd=ROOT / 'backend', env=env, check=True)
    commands = [
        (
            [python, '-m', 'flask', '--app', 'run', 'run', '--host', '127.0.0.1', '--port', str(api), '--debug'],
            ROOT / 'backend',
        ),
        (['npm', 'run', 'dev', '--', '--port', str(web)], ROOT / 'frontend'),
    ]
    children = []

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        for command, cwd in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True))
        print(f'Desenvolvimento: http://127.0.0.1:{web} (API {api}; Vite + TanStack Start)', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        return next((child.returncode for child in children if child.returncode), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        sys.exit(str(error))
