#!/usr/bin/env python3
"""Local Neo4j code graph. Run --help; no application imports or provider calls."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from code_graph.graph import Client, build, fingerprint, impact, search, sync  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
AUTH = Path.home() / '.config/antares-code-graph/auth'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--auth-file', type=Path, default=AUTH)
    parser.add_argument('--url', default='http://127.0.0.1:7475')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='Create private credentials and start the dedicated Docker service')
    commands.add_parser('sync', help='Parse the current checkout and atomically replace its graph')
    commands.add_parser('status', help='Check graph counts and checkout freshness')
    find = commands.add_parser('search', help='Find files, symbols, endpoints and rules')
    find.add_argument('text')
    change = commands.add_parser('impact', help='Reverse dependencies, candidate tests and business rules')
    change.add_argument('path', nargs='?', help='Repository-relative file path')
    change.add_argument('--changed', action='store_true', help='Use tracked and untracked Git changes')
    change.add_argument('--depth', type=int, choices=range(1, 7), default=3)
    change.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == 'init':
        args.auth_file.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation never rotates credentials for an existing persistent database.
        try:
            fd = os.open(args.auth_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as stream:
                stream.write('neo4j/' + secrets.token_urlsafe(32) + '\n')
        env = {**os.environ, 'CODE_GRAPH_AUTH_FILE': str(args.auth_file.resolve())}
        subprocess.run(
            ['docker', 'compose', '-f', str(ROOT / 'infra/code-graph/compose.yaml'), 'up', '-d', '--wait'],
            env=env,
            check=True,
        )
        print(json.dumps({'browser': args.url + '/browser/', 'credentials_file': str(args.auth_file)}))
        return
    client = Client(args.url, args.auth_file)
    if args.command == 'sync':
        result = sync(client, root, build(root))
    else:
        status = client.query('MATCH (g:CodeGraph {repo: $repo}) RETURN properties(g) AS graph', repo=str(root))
        if not status:
            raise ValueError('Graph missing. Run python3 scripts/code-graph.py sync first.')
        fresh = status[0]['graph']['fingerprint'] == fingerprint(root)
        if args.command == 'status':
            result = {**status[0]['graph'], 'fresh': fresh}
        else:
            if not fresh:
                raise ValueError('Checkout changed. Run python3 scripts/code-graph.py sync before querying.')
            if args.command == 'search':
                result = search(client, root, args.text)
            else:
                paths = [args.path] if args.path else []
                if args.changed:
                    for command in (
                        ['git', 'diff', '--name-only', '-z', 'HEAD'],
                        ['git', 'ls-files', '--others', '--exclude-standard', '-z'],
                    ):
                        paths.extend(subprocess.check_output(command, cwd=root).decode().strip('\0').split('\0'))
                paths = sorted({p for p in paths if p})
                if not paths or args.limit < 1:
                    raise ValueError('Supply a file or --changed, and a positive --limit.')
                result = impact(client, root, paths, args.depth, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Code graph: {exc}', file=sys.stderr)
        sys.exit(1)
