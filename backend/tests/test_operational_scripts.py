"""Exercise operational guards and release failure handling without touching actual services."""

import importlib.util
import json
import plistlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_dev_refuses_production_database_and_ports(tmp_path, monkeypatch):
    dev = module('dev')
    monkeypatch.setattr(dev, 'ROOT', tmp_path)
    for values in (
        {'DEV_DATABASE_URL': 'postgresql:///antarescrm'},
        {'API_PORT': '5002'},
        {'WEB_PORT': '3002'},
        {'DEV_DATABASE_URL': 'postgresql://production/antares_test_dev'},
    ):
        with pytest.raises(ValueError):
            dev.environment(values)
    env, api, web = dev.environment(
        {'DATABASE_URL': 'postgresql:///antarescrm', 'EVOLUTION_API_KEY': 'production-secret'}
    )
    assert (api, web) == (5003, 3003) and env['DATABASE_URL'].endswith('/antares_test_dev')
    assert 'EVOLUTION_API_KEY' not in env and 'NEXT_DIST_DIR' not in env
    assert env['ANTARES_ENV_FILE'].endswith('.env.development')


def definition(name):
    return {
        'Label': f'com.antarescrm.{name}',
        'WorkingDirectory': f'/old/{name}',
        'ProgramArguments': [f'/old/{name}/runtime', 'start'],
        'EnvironmentVariables': {'POLICY': 'preserved'},
    }


def test_release_keeps_persistent_data_and_dispatch_policy():
    deploy = module('deploy')
    old = definition('backend')
    old['EnvironmentVariables']['PROJECT_FILES_DIR'] = '/private/files'
    new = deploy.remap_definition(old, Path('/releases/v2'), Path('/persistent'))
    assert new['ProgramArguments'][0] == '/releases/v2/backend/runtime'
    assert new['EnvironmentVariables']['PROJECT_FILES_DIR'] == '/private/files'
    assert new['EnvironmentVariables']['POLICY'] == 'preserved'
    assert old['WorkingDirectory'] == '/old/backend'


def test_release_replaces_next_runtime_and_keeps_frontend_bind_settings():
    deploy = module('deploy')
    old = definition('frontend')
    old['ProgramArguments'] = [
        '/usr/local/bin/node',
        '/old/frontend/node_modules/next/dist/bin/next',
        'start',
        '--hostname',
        '127.0.0.1',
        '--port',
        '3002',
    ]
    old['EnvironmentVariables']['NEXT_DIST_DIR'] = '.next-public'
    new = deploy.remap_definition(old, Path('/releases/v2'), Path('/persistent'))
    assert new['ProgramArguments'] == ['/usr/local/bin/node', '/releases/v2/frontend/scripts/start.mjs']
    assert new['EnvironmentVariables']['PORT'] == '3002'
    assert new['EnvironmentVariables']['HOST'] == '127.0.0.1'
    assert 'NEXT_DIST_DIR' not in new['EnvironmentVariables']
    assert old['EnvironmentVariables']['NEXT_DIST_DIR'] == '.next-public'


@pytest.mark.parametrize('schema_change', [False, True])
def test_failed_activation_never_restores_database(tmp_path, monkeypatch, schema_change):
    deploy = module('deploy')
    release = tmp_path / 'release'
    release.mkdir()
    agents = tmp_path / 'agents'
    agents.mkdir()
    definitions = {name: definition(name) for name in ('frontend', 'backend', 'worker')}
    for name, value in definitions.items():
        (agents / f'com.antarescrm.{name}.plist').write_bytes(plistlib.dumps(value))
    planned = {key: deploy.remap_definition(value, release, tmp_path) for key, value in definitions.items()}
    (release / 'release.json').write_text(json.dumps({'services': planned}))
    monkeypatch.setattr(deploy, 'revision', lambda *args: 'before')
    calls = []

    def run(args, **kwargs):
        args = [str(arg) for arg in args]
        calls.append(args)
        if 'upgrade' in args:
            raise RuntimeError('migration failure')
        return SimpleNamespace(stdout='after' if schema_change else 'before')

    monkeypatch.setattr(deploy, 'run', run)
    monkeypatch.setattr(deploy.subprocess, 'run', Mock())
    with pytest.raises(RuntimeError, match='migration failure'):
        deploy.activate(release, agents, 'http://fixture')
    assert not any('pg_restore' in ' '.join(call) for call in calls)
    resumed = [call for call in calls if 'bootstrap' in call]
    assert bool(resumed) is not schema_change
    assert plistlib.loads((agents / 'com.antarescrm.backend.plist').read_bytes()) == definitions['backend']


def test_failed_release_health_restores_previous_code_and_dependencies(tmp_path, monkeypatch):
    import io
    from contextlib import contextmanager

    deploy = module('deploy')
    release = tmp_path / 'release'
    release.mkdir()
    agents = tmp_path / 'agents'
    agents.mkdir()
    previous = {name: definition(name) for name in ('frontend', 'backend', 'worker')}
    for name, value in previous.items():
        (agents / f'com.antarescrm.{name}.plist').write_bytes(plistlib.dumps(value))
    planned = {key: deploy.remap_definition(value, release, tmp_path) for key, value in previous.items()}
    (release / 'release.json').write_text(json.dumps({'services': planned}))
    calls = []
    monkeypatch.setattr(deploy, 'revision', lambda *args: 'same')
    monkeypatch.setattr(
        deploy, 'run', lambda args, **kwargs: calls.append([str(arg) for arg in args]) or SimpleNamespace(stdout='same')
    )
    monkeypatch.setattr(deploy.subprocess, 'run', Mock())
    monkeypatch.setattr(deploy.time, 'sleep', lambda *args: None)

    @contextmanager
    def health(*args, **kwargs):
        yield io.StringIO('{"status":"ok"}')

    monkeypatch.setattr(deploy, 'urlopen', health)
    monkeypatch.setattr(deploy, 'smoke', Mock(side_effect=RuntimeError('health failed')))
    with pytest.raises(RuntimeError, match='health failed'):
        deploy.activate(release, agents, 'http://fixture')
    for name, value in previous.items():
        assert plistlib.loads((agents / f'com.antarescrm.{name}.plist').read_bytes()) == value
    bootstraps = [call for call in calls if 'bootstrap' in call]
    # Only frontend/backend of the new release were started; worker starts only during rollback.
    assert len(bootstraps) == 5
    assert not any('pg_restore' in ' '.join(call) for call in calls)


def test_prepare_installs_build_dependencies_under_production_node_env(tmp_path, monkeypatch):
    deploy = module('deploy')
    source = tmp_path / 'source'
    (source / 'frontend').mkdir(parents=True)
    (source / 'backend').mkdir()
    releases = tmp_path / 'releases'
    releases.mkdir()
    definitions = {key: definition(key) for key in ('frontend', 'backend')}
    definitions['frontend']['EnvironmentVariables']['NODE_ENV'] = 'production'
    monkeypatch.setattr(deploy, 'load_definitions', lambda *args: definitions)
    monkeypatch.setattr(deploy.shutil, 'disk_usage', lambda *args: SimpleNamespace(free=4 * 1024**3))
    calls = []
    monkeypatch.setattr(deploy, 'run', lambda args, **kwargs: calls.append(([str(arg) for arg in args], kwargs)))
    release = deploy.prepare(source, releases, tmp_path / 'agents', source)
    npm_ci = next((args, options) for args, options in calls if args[:2] == ['npm', 'ci'])
    assert '--include=dev' in npm_ci[0] and npm_ci[1]['env']['NODE_ENV'] == 'production'
    assert (release / 'release.json').exists()
    assert not any('launchctl' in args for args, _ in calls)


def test_activation_backup_finds_postgres_outside_launchagent_path(monkeypatch):
    deploy = module('deploy')

    def which(name, path=None):
        return None if path == '/usr/bin' else f'/postgres/bin/{name}'

    monkeypatch.setattr(deploy.shutil, 'which', which)
    env = deploy.backup_environment({'PATH': '/usr/bin', 'APP_ENV': 'production'})
    assert env['PATH'] == '/postgres/bin' + deploy.os.pathsep + '/usr/bin'
    assert env['APP_ENV'] == 'production'


def test_public_smoke_identifies_deploy_monitor(monkeypatch):
    from contextlib import contextmanager

    deploy = module('deploy')
    calls = []

    @contextmanager
    def response(request, timeout):
        calls.append(request)
        yield SimpleNamespace(status=401 if request.full_url.endswith('/auth/me') else 200)

    monkeypatch.setattr(deploy, 'urlopen', response)
    deploy.smoke('https://crm.example.test')
    assert len(calls) == 2
    assert all(request.get_header('User-agent') == 'AntaresDeploy/1.0' for request in calls)
