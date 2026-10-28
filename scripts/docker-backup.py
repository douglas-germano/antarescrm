#!/usr/bin/env python3
"""Back up the installed Docker stack and verify a restore in a disposable database."""

import json
import os
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    os.umask(0o077)
    runtime = Path(os.environ.get('ANTARES_RUNTIME_DIR', str(Path.home() / '.config/antares-docker')))
    os.environ.setdefault('DOCKER_CONTEXT', 'colima')
    compose = [
        'docker',
        'compose',
        '--env-file',
        str(runtime / '.env'),
        '-f',
        str(runtime / 'compose.yaml'),
        '--profile',
        'live',
    ]

    def run(args, **kwargs):
        return subprocess.run(compose + args, check=True, **kwargs)

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = runtime / 'backups' / ('antares-' + stamp + '-' + secrets.token_hex(3))
    destination.mkdir(parents=True, mode=0o700)
    active = run(['ps', '--status', 'running', '--services'], capture_output=True, text=True).stdout.splitlines()
    writers = [name for name in ('worker', 'frontend', 'backend') if name in active]
    try:
        if writers:
            run(['stop', *writers], stdout=subprocess.DEVNULL)
        with (destination / 'database.dump').open('wb') as stream:
            run(
                [
                    'exec',
                    '-T',
                    'postgres',
                    'pg_dump',
                    '-U',
                    'antares',
                    '-d',
                    'antarescrm',
                    '-Fc',
                    '--no-owner',
                    '--no-acl',
                ],
                stdout=stream,
            )
        with (destination / 'project-files.tar.gz').open('wb') as stream:
            run(
                [
                    'run',
                    '--rm',
                    '-T',
                    '--no-deps',
                    '--entrypoint',
                    'tar',
                    'backend',
                    'czf',
                    '-',
                    '-C',
                    '/data/project-files',
                    '.',
                ],
                stdout=stream,
            )
        for name in (
            '.env',
            'backend.env',
            'frontend.env',
            'compose.yaml',
            'tunnel.yml',
            'tunnel.json',
            'migration.json',
            'antares-docker.sh',
            'docker-backup.py',
        ):
            path = runtime / name
            if path.exists():
                shutil.copyfile(path, destination / name)
    finally:
        if writers:
            run(['start', *reversed(writers)], stdout=subprocess.DEVNULL)

    name = 'antares_restore_test_' + secrets.token_hex(6)
    run(['exec', '-T', 'postgres', 'createdb', '-U', 'antares', name], stdout=subprocess.DEVNULL)
    try:
        with (destination / 'database.dump').open('rb') as stream:
            run(
                [
                    'exec',
                    '-T',
                    'postgres',
                    'pg_restore',
                    '--exit-on-error',
                    '--no-owner',
                    '--no-acl',
                    '-U',
                    'antares',
                    '-d',
                    name,
                ],
                stdin=stream,
                stdout=subprocess.DEVNULL,
            )
        query = "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
        count = run(
            ['exec', '-T', 'postgres', 'psql', '-U', 'antares', '-d', name, '-Atc', query],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if int(count) < 1:
            raise RuntimeError('Restored database contains no tables.')
    finally:
        run(['exec', '-T', 'postgres', 'dropdb', '-U', 'antares', name], stdout=subprocess.DEVNULL)
    record = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'path': str(destination / 'database.dump'),
        'bytes': (destination / 'database.dump').stat().st_size,
        'restore_verified': True,
        'project_files_archive': str(destination / 'project-files.tar.gz'),
    }
    temporary = runtime / 'status' / 'latest.json.tmp'
    temporary.write_text(json.dumps(record, ensure_ascii=False) + '\n')
    temporary.chmod(0o644)  # Only metadata is mounted read-only into the app; archives stay private.
    temporary.replace(runtime / 'status' / 'latest.json')
    (destination / 'backup.json').write_text(json.dumps(record, ensure_ascii=False) + '\n')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
