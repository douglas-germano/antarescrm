#!/usr/bin/env python3
"""Prepare immutable local releases; activate only during a controlled maintenance window."""

import argparse
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ('frontend', 'backend', 'worker', 'backup')
IGNORED = {
    '.git',
    '.venv',
    'node_modules',
    '__pycache__',
    '.local-services',
    '.review',
    '.playwright-cli',
    '.pytest_cache',
    '.ruff_cache',
    '.coverage',
    'output',
}


def ignored(directory, names):
    return [
        name for name in names if name in IGNORED or name.startswith(('.next', '.env')) or name.endswith('.tsbuildinfo')
    ]


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def backup_environment(env):
    paths = []
    for name in ('pg_dump', 'pg_restore'):
        binary = shutil.which(name, path=env.get('PATH')) or shutil.which(name)
        if not binary:
            raise RuntimeError(f'Configure {name} antes de ativar a release.')
        paths.append(str(Path(binary).parent))
    return {**env, 'PATH': os.pathsep.join(dict.fromkeys(paths + env.get('PATH', os.defpath).split(os.pathsep)))}


def remap_definition(definition, release, persistent_root):
    """Keep ports, dispatch policy and secrets; change only code/runtime locations."""
    result = dict(definition)
    old_root = str(Path(definition['WorkingDirectory']).parent)
    result['WorkingDirectory'] = definition['WorkingDirectory'].replace(old_root, str(release), 1)
    result['ProgramArguments'] = [
        arg.replace(old_root + '/', str(release) + '/') for arg in definition['ProgramArguments']
    ]
    env = {**definition.get('EnvironmentVariables', {}), 'APP_ENV': 'production'}
    # Default uploaded files must survive release changes (the app's old default lives under backend/).
    configured = dotenv_values(persistent_root / 'backend/.env')
    env.setdefault(
        'PROJECT_FILES_DIR',
        configured.get('PROJECT_FILES_DIR') or str(persistent_root / 'backend/.local-services/project-files'),
    )
    if Path(env['PROJECT_FILES_DIR']).is_absolute() is False:
        env['PROJECT_FILES_DIR'] = str(Path(definition['WorkingDirectory']) / env['PROJECT_FILES_DIR'])
    env['ANTARES_ENV_FILE'] = str(persistent_root / 'backend/.env')
    if result['Label'] == 'com.antarescrm.frontend':
        env['NEXT_DIST_DIR'] = '.next-public'
    result['EnvironmentVariables'] = env
    return result


def load_definitions(agents):
    result = {}
    for service in SERVICES:
        path = agents / f'com.antarescrm.{service}.plist'
        if path.exists():
            result[service] = plistlib.loads(path.read_bytes())
    if not {'frontend', 'backend'} <= result.keys():
        raise RuntimeError('Os LaunchAgents de frontend e backend precisam existir.')
    return result


def prepare(source, releases, agents, persistent_root):
    if shutil.disk_usage(releases).free < 1536 * 1024**2:
        raise RuntimeError('Libere pelo menos 1,5 GiB para preparar dependências e build sem afetar a versão ativa.')
    definitions = load_definitions(agents)
    release = releases / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3))
    release.mkdir(parents=True, mode=0o700)
    shutil.copytree(source, release, ignore=ignored, dirs_exist_ok=True)
    for filename in ('.env.local', '.env.production', '.env.production.local'):
        original = persistent_root / 'frontend' / filename
        if original.exists():
            (release / 'frontend' / filename).symlink_to(original)
    definitions = {key: remap_definition(value, release, persistent_root) for key, value in definitions.items()}
    python = Path(sys.executable)
    run([python, '-m', 'venv', release / 'backend/.venv'])
    python = release / 'backend/.venv/bin/python'
    run([python, '-m', 'pip', 'install', '-r', release / 'backend/requirements.txt'])
    env = {
        **os.environ,
        **definitions['frontend'].get('EnvironmentVariables', {}),
        'NEXT_DIST_DIR': '.next-public',
        'NEXT_BUILD_CPUS': '2',
    }
    env.setdefault('NODE_OPTIONS', '--max-old-space-size=1024')
    # The service uses NODE_ENV=production; TypeScript is still required to build and load next.config.ts.
    run(['npm', 'ci', '--include=dev'], cwd=release / 'frontend', env=env)
    run(['npm', 'run', 'build'], cwd=release / 'frontend', env=env)
    # Verify factory/configuration using the same environment as the future backend.
    run(
        [python, '-c', 'from app import create_app; create_app()'],
        cwd=release / 'backend',
        env={**os.environ, **definitions['backend']['EnvironmentVariables']},
    )
    plan = release / 'release.json'
    plan.write_text(json.dumps({'services': definitions}, indent=2))
    plan.chmod(0o600)
    print(f'Release preparada: {release}\nAtivar: scripts/deploy-prod.sh activate {release}')
    return release


def revision(release, env):
    result = run(
        [
            release / 'backend/.venv/bin/python',
            '-c',
            'from app import create_app; from app.extensions import db; '
            'app=create_app(); ctx=app.app_context(); ctx.push(); '
            "print(','.join(sorted(db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalars())))",
        ],
        cwd=release / 'backend',
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def smoke(url):
    for path, expected in (('/login', 200), ('/api/backend/auth/me', 401)):
        try:
            request = Request(url.rstrip('/') + path, headers={'User-Agent': 'AntaresDeploy/1.0'})
            with urlopen(request, timeout=15) as response:
                status = response.status
        except HTTPError as error:
            status = error.code
        if status != expected:
            raise RuntimeError(f'Smoke test {path}: HTTP {status}; esperado {expected}.')


def activate(release, agents, smoke_url):
    release = release.resolve()
    planned = json.loads((release / 'release.json').read_text())['services']
    previous = load_definitions(agents)
    if set(previous) != set(planned):
        raise RuntimeError('Os serviços mudaram desde a preparação. Prepare uma nova release.')
    domain = f'gui/{os.getuid()}'
    env = {**os.environ, **planned['backend']['EnvironmentVariables']}
    # No production writes until the release and a real, readable backup are ready.
    run(
        [release / 'backend/.venv/bin/python', release / 'scripts/backup.py', '--verify'],
        cwd=release / 'backend',
        env=backup_environment(env),
    )
    before = revision(release, env)
    target = run(
        [
            release / 'backend/.venv/bin/python',
            '-c',
            "from alembic.script import ScriptDirectory; print(','.join(sorted(ScriptDirectory('migrations').get_heads())))",
        ],
        cwd=release / 'backend',
        capture_output=True,
        text=True,
    ).stdout.strip()
    schema_changes = before != target
    rollback_file = release / 'previous-services.plist'
    rollback_file.write_bytes(plistlib.dumps(previous))
    rollback_file.chmod(0o600)
    stopped, started = [], []
    migration_started = False
    try:
        # Removing LaunchAgents prevents KeepAlive from restarting writers during migration.
        for name in SERVICES:
            if name not in previous:
                continue
            path = agents / f'com.antarescrm.{name}.plist'
            run(['launchctl', 'bootout', domain, path])
            stopped.append(name)
        migration_started = True
        run(
            [release / 'backend/.venv/bin/python', '-m', 'flask', '--app', 'run', 'db', 'upgrade'],
            cwd=release / 'backend',
            env=env,
        )
        for name in ('backend', 'frontend'):
            path = agents / f'com.antarescrm.{name}.plist'
            path.write_bytes(plistlib.dumps(planned[name]))
            path.chmod(0o600)
            run(['launchctl', 'bootstrap', domain, path])
            started.append(name)
        for attempt in range(10):
            try:
                # Also test the database through the configured backend, not just the unauthenticated BFF.
                from urllib.parse import urlparse

                backend_url = planned['frontend']['EnvironmentVariables'].get(
                    'FLASK_API_URL', 'http://127.0.0.1:5002/api/v1'
                )
                if urlparse(backend_url).hostname not in ('localhost', '127.0.0.1'):
                    raise RuntimeError('O health check de deploy requer uma API local.')
                with urlopen(backend_url.rstrip('/') + '/health', timeout=10) as response:
                    if json.load(response).get('status') != 'ok':
                        raise RuntimeError('Backend sem saúde.')
                smoke(smoke_url)
                break
            except Exception:
                if attempt == 9:
                    raise
                time.sleep(2)
        # Workers resume only after application health has been verified.
        for name in ('worker', 'backup'):
            if name not in planned:
                continue
            path = agents / f'com.antarescrm.{name}.plist'
            path.write_bytes(plistlib.dumps(planned[name]))
            path.chmod(0o600)
            run(['launchctl', 'bootstrap', domain, path])
            started.append(name)
    except Exception:
        for name in reversed(started):
            subprocess.run(
                ['launchctl', 'bootout', domain, agents / f'com.antarescrm.{name}.plist'], capture_output=True
            )
        for name in stopped:
            path = agents / f'com.antarescrm.{name}.plist'
            path.write_bytes(plistlib.dumps(previous[name]))
            path.chmod(0o600)
        if schema_changes and migration_started:
            print(
                'Migração iniciada: serviços mantidos parados. Banco NÃO restaurado automaticamente. '
                f'Verifique a migração antes de retomar; configuração anterior em {rollback_file}.',
                file=sys.stderr,
            )
        else:
            for name in reversed(stopped):
                run(['launchctl', 'bootstrap', domain, agents / f'com.antarescrm.{name}.plist'])
            print('Código, dependências e build anteriores retomados. Banco preservado.', file=sys.stderr)
        raise
    print(f'Release ativada e validada: {release}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'activate'), nargs='?', default='prepare')
    parser.add_argument('release', type=Path, nargs='?')
    args = parser.parse_args()
    releases = Path(os.getenv('RELEASES_DIR', str(Path.home() / '.antarescrm-releases'))).resolve()
    releases.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = releases / '.deploy-lock'
    try:
        lock.mkdir()
    except FileExistsError:
        sys.exit('Outro deploy está em andamento. Verifique .deploy-lock antes de tentar novamente.')
    try:
        agents = Path.home() / 'Library/LaunchAgents'
        if args.action == 'prepare':
            prepare(
                Path(os.getenv('SOURCE_DIR', str(ROOT))).resolve(),
                releases,
                agents,
                Path(os.getenv('PROD_DIR', str(ROOT))).resolve(),
            )
        else:
            if not args.release or args.release.resolve().parent != releases:
                parser.error('Informe uma release preparada dentro de RELEASES_DIR.')
            activate(args.release, agents, os.getenv('SMOKE_URL', 'https://antares.douglasgermano.com'))
    finally:
        lock.rmdir()


if __name__ == '__main__':
    main()
