#!/usr/bin/env python3
"""Share a read-only Neo4j snapshot through an expiring, secret-path Quick Tunnel."""

import argparse
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from code_graph.graph import Client, fingerprint  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def snapshot(root, expires_at):
    client = Client('http://127.0.0.1:7475', Path.home() / '.config/antares-code-graph/auth')
    repo = str(root)
    metadata = client.query('MATCH (g:CodeGraph {repo: $repo}) RETURN properties(g) AS meta', repo=repo)
    if not metadata or metadata[0]['meta']['fingerprint'] != fingerprint(root):
        raise ValueError('Run python3 scripts/code-graph.py sync before sharing.')
    nodes = client.query(
        'MATCH (n:CodeEntity {repo: $repo}) RETURN n{.id,.name,.kind,.path,.line,.test,.description} AS node ORDER BY n.id',
        repo=repo,
    )
    edges = client.query(
        'MATCH (a:CodeEntity {repo: $repo})-[r]->(b:CodeEntity {repo: $repo}) RETURN {source:a.id,target:b.id,kind:type(r),path:r.path,line:r.line,origin:r.origin} AS edge',
        repo=repo,
    )
    return dict(
        meta=metadata[0]['meta'],
        nodes=[r['node'] for r in nodes],
        edges=[r['edge'] for r in edges],
        expires_at=expires_at,
    )


def handler_for(content, secret_path, nonce, deadline):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not secrets.compare_digest(self.path, secret_path):
                self.send_error(404)
                return
            if time.monotonic() >= deadline:
                self.send_error(410, 'Temporary access expired')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header(
                'Content-Security-Policy',
                f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass  # Do not record the secret path in access logs.

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=float, default=8)
    parser.add_argument('--port', type=int, default=7476)
    parser.add_argument('--state', type=Path, default=ROOT / '.local-services/code-graph-share.json')
    args = parser.parse_args()
    if not 0 < args.hours <= 24:
        parser.error('--hours must be greater than zero and at most 24')
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=args.hours)).isoformat()
    data = json.dumps(snapshot(ROOT, expires_at), ensure_ascii=False).replace('<', r'\u003c')
    nonce, secret_path = secrets.token_urlsafe(24), '/view/' + secrets.token_urlsafe(32)
    template = (ROOT / 'scripts/code_graph/preview.html').read_text()
    content = template.replace('__GRAPH_DATA__', data).replace('__NONCE__', nonce).encode()
    deadline = time.monotonic() + args.hours * 3600
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(content, secret_path, nonce, deadline))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.state.with_suffix('.log')
    fd = os.open(log_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as log:
        tunnel = subprocess.Popen(
            [
                'cloudflared',
                'tunnel',
                '--no-autoupdate',
                '--protocol',
                'http2',
                '--edge-ip-version',
                '4',
                '--url',
                f'http://127.0.0.1:{args.port}',
            ],
            stdout=log,
            stderr=log,
        )

    def stop(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        started = time.monotonic()
        while time.monotonic() - started < 45:
            if tunnel.poll() is not None:
                raise ValueError('Quick Tunnel exited. Check its private log.')
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', log_path.read_text())
            if match:
                state = dict(
                    url=match.group() + secret_path,
                    expires_at=expires_at,
                    pid=os.getpid(),
                    tunnel_pid=tunnel.pid,
                    port=args.port,
                )
                fd = os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump(state, stream, indent=2)
                print(json.dumps(state), flush=True)
                break
            time.sleep(0.25)
        else:
            raise ValueError('Quick Tunnel did not supply a URL within 45 seconds.')
        while time.monotonic() < deadline and tunnel.poll() is None:
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        tunnel.terminate()
        try:
            tunnel.wait(timeout=10)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f'Graph sharing: {exc}', file=sys.stderr)
        sys.exit(1)
