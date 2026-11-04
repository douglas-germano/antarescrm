"""Code graph extraction, freshness and isolated optional Neo4j round trips."""

import importlib.util
import io
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('code_graph_impl', ROOT / 'scripts/code_graph/graph.py')
graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph)


def write(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)


@pytest.fixture()
def repository(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    write(tmp_path, '.gitignore', '.env\nnode_modules/\n')
    write(tmp_path, 'backend/app/services/core.py', 'def ingest():\n    return 1\n')
    write(tmp_path, 'backend/app/services/__init__.py', 'from .core import ingest as receive\n')
    write(
        tmp_path,
        'backend/app/routes/messages.py',
        "from ..services import receive as deliver\n@bp.post('/messages')\ndef create():\n    return deliver()\n",
    )
    write(
        tmp_path,
        'backend/tests/test_messages.py',
        'from app.services import receive\ndef test_receive():\n    assert receive() == 1\n',
    )
    write(tmp_path, '.env', 'SECRET=never-send-this\n')
    return tmp_path


def test_python_relative_alias_reexports_routes_and_test_dependencies(repository):
    data, digest = graph.build(repository)
    edges = list(data.edges.values())
    source = 'backend/app/routes/messages.py'
    target = 'backend/app/services/core.py'
    assert any(
        e['source'] == source + '::create'
        and e['target'] == target + '::ingest'
        and e['kind'] == 'CALLS'
        and e['line'] == 4
        for e in edges
    )
    assert any(
        e['source'] == 'backend/tests/test_messages.py' and e['target'] == target and e['kind'] == 'IMPORTS'
        for e in edges
    )
    assert 'endpoint:POST /api/v1/messages' in data.nodes
    assert data.nodes['backend/tests/test_messages.py']['test']
    assert '.env' not in data.nodes and 'never-send-this' not in json.dumps(list(data.nodes.values()))
    assert graph.fingerprint(repository) == digest
    write(repository, target, 'def ingest():\n    return 2\n')
    assert graph.fingerprint(repository) != digest


def test_shadowed_parameter_does_not_create_call_and_deleted_file_invalidates(repository):
    path = 'backend/app/services/consumer.py'
    write(repository, path, 'from .core import ingest\ndef run(ingest):\n    return ingest()\n')
    data, digest = graph.build(repository)
    assert not any(e['source'] == path + '::run' and e['kind'] == 'CALLS' for e in data.edges.values())
    (repository / path).unlink()
    assert graph.fingerprint(repository) != digest


def test_rules_require_unique_evidence_anchors(repository):
    rule = {
        'id': 'silent',
        'title': 'Silent import',
        'description': 'No dispatch',
        'applies_to': [{'path': 'backend/app/services/core.py', 'anchor': 'def ingest():'}],
        'tests': [{'path': 'backend/tests/test_messages.py', 'anchor': 'def test_receive():'}],
    }
    write(repository, graph.RULES, json.dumps([rule]))
    data, _ = graph.build(repository)
    assert any(
        e['source'] == 'rule:silent' and e['kind'] == 'VERIFIED_BY' and e['origin'] == 'curated' and e['line'] == 2
        for e in data.edges.values()
    )
    rule['applies_to'][0]['anchor'] = 'removed'
    write(repository, graph.RULES, json.dumps([rule]))
    with pytest.raises(ValueError, match='anchor must match exactly once'):
        graph.build(repository)


def test_frontend_alias_reexport_dynamic_import_css_and_endpoint_candidates(repository):
    write(
        repository,
        'frontend/tsconfig.json',
        json.dumps(
            {'compilerOptions': {'moduleResolution': 'bundler', 'module': 'esnext', 'paths': {'@/*': ['./src/*']}}}
        ),
    )
    write(repository, 'frontend/src/lib/api.ts', 'export function post(path: string) {}\n')
    write(repository, 'frontend/src/lib/reexport.ts', "export { post } from './api';\n")
    write(repository, 'frontend/src/screen.css', 'body {}\n')
    write(
        repository,
        'frontend/src/screen.tsx',
        "import {post as send} from '@/lib/api';\nimport './screen.css';\n"
        "export function Screen() { send('/messages'); return import('./lib/reexport'); }\n",
    )
    data, _ = graph.build(repository)
    edges = list(data.edges.values())
    assert any(e['target'] == 'frontend/src/lib/reexport.ts' and e['kind'] == 'IMPORTS' for e in edges)
    assert any(e['target'] == 'frontend/src/screen.css' for e in edges)
    assert any(
        e['source'] == 'frontend/src/screen.tsx'
        and e['target'] == 'backend/app/routes/messages.py'
        and e['origin'] == 'inferred'
        for e in edges
    )
    assert 'frontend/src/screen.tsx::Screen' in data.nodes
    write(repository, 'frontend/src/broken.ts', "import './does-not-exist';\n")
    with pytest.raises(ValueError, match='Unresolved local import'):
        graph.build(repository)


def test_neo4j_202_errors_are_not_reported_as_success(tmp_path, monkeypatch):
    auth = tmp_path / 'auth'
    auth.write_text('neo4j/test-password')
    client = graph.Client('http://127.0.0.1:7475', auth)
    monkeypatch.setattr(
        graph, 'urlopen', lambda *a, **kw: io.BytesIO(json.dumps({'errors': [{'message': 'query failed'}]}).encode())
    )
    with pytest.raises(ValueError, match='query failed'):
        client.query('RETURN 1')
    with pytest.raises(ValueError, match='local'):
        graph.Client('https://remote.example', auth)


@pytest.mark.skipif(os.getenv('CODE_GRAPH_INTEGRATION') != '1', reason='Dedicated local Neo4j opt-in')
def test_neo4j_atomic_refresh_deletions_and_reverse_impact(repository):
    client = graph.Client('http://127.0.0.1:7475', Path.home() / '.config/antares-code-graph/auth')
    repo = str(repository)
    try:
        extracted = graph.build(repository)
        first = graph.sync(client, repository, extracted)
        result = graph.impact(client, repository, ['backend/app/services/core.py'])
        assert any(d['path'] == 'backend/tests/test_messages.py' and d['candidate_test'] for d in result['dependents'])
        assert graph.search(client, repository, 'ingest')
        second = graph.sync(client, repository, extracted)
        assert first['nodes'] == second['nodes'] and first['edges'] == second['edges']
        # Force an error after deleting the snapshot inside the transaction.
        with pytest.raises(ValueError):
            client.query(
                'MATCH (n:CodeEntity {repo: $repo}) DETACH DELETE n WITH count(*) AS c RETURN 1 / toInteger($zero)',
                repo=repo,
                zero=0,
            )
        assert graph.search(client, repository, 'ingest')
        (repository / 'backend/tests/test_messages.py').unlink()
        graph.sync(client, repository, graph.build(repository))
        result = graph.impact(client, repository, ['backend/app/services/core.py'])
        assert not any(d['candidate_test'] for d in result['dependents'])
        assert graph.impact(client, repository, ['missing.py'])['unindexed'] == ['missing.py']
    finally:
        client.query('MATCH (n:CodeEntity {repo: $repo}) DETACH DELETE n', repo=repo)
        client.query('MATCH (g:CodeGraph {repo: $repo}) DELETE g', repo=repo)
