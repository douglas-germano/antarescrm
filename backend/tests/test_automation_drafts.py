from app.extensions import db
from app.models import AutomationRule
from test_automation_versions import BODY, versions


def active_rule(client, headers):
    created = client.post('/api/v1/automations', headers=headers, json={**BODY, 'active': True})
    assert created.status_code == 201, created.json
    return created.json['id']


def test_draft_does_not_change_the_running_rule_until_published(env):
    client, d = env
    headers = d['headers']()
    rule_id = active_rule(client, headers)
    saved = client.put(
        f'/api/v1/automations/{rule_id}/draft',
        headers=headers,
        json={**BODY, 'name': 'Boas-vindas v2', 'active': False},
    )
    assert saved.status_code == 200, saved.json
    assert saved.json['name'] == 'Boas-vindas' and saved.json['active'] is True
    assert saved.json['draft']['name'] == 'Boas-vindas v2' and 'active' not in saved.json['draft']
    assert saved.json['draft_author_id'] and saved.json['draft_saved_at']
    assert db.session.get(AutomationRule, rule_id).name == 'Boas-vindas'
    assert [item['number'] for item in versions(client, headers, rule_id)] == [1]

    published = client.post(f'/api/v1/automations/{rule_id}/draft/publish', headers=headers)
    assert published.status_code == 200, published.json
    assert published.json['name'] == 'Boas-vindas v2' and published.json['active'] is True
    assert published.json['draft'] is None and published.json['draft_author_id'] is None
    items = versions(client, headers, rule_id)
    assert items[0]['number'] == 2 and items[0]['note'] == 'Rascunho publicado' and items[0]['changes'] == ['nome']
    assert client.post(f'/api/v1/automations/{rule_id}/draft/publish', headers=headers).status_code == 409


def test_discarding_or_saving_the_same_configuration_leaves_no_draft(env):
    client, d = env
    headers = d['headers']()
    rule_id = active_rule(client, headers)
    same = client.put(f'/api/v1/automations/{rule_id}/draft', headers=headers, json=BODY)
    assert same.status_code == 200 and same.json['draft'] is None
    client.put(f'/api/v1/automations/{rule_id}/draft', headers=headers, json={**BODY, 'task_title': 'Mandar e-mail'})
    discarded = client.delete(f'/api/v1/automations/{rule_id}/draft', headers=headers)
    assert discarded.status_code == 200 and discarded.json['draft'] is None
    assert discarded.json['task_title'] == 'Ligar'
    assert client.delete(f'/api/v1/automations/{rule_id}/draft', headers=headers).status_code == 409
    assert [item['number'] for item in versions(client, headers, rule_id)] == [1]


def test_direct_save_replaces_a_pending_draft(env):
    client, d = env
    headers = d['headers']()
    rule_id = active_rule(client, headers)
    client.put(f'/api/v1/automations/{rule_id}/draft', headers=headers, json={**BODY, 'name': 'Rascunho'})
    paused = client.patch(f'/api/v1/automations/{rule_id}', headers=headers, json={'active': False})
    assert paused.json['draft']['name'] == 'Rascunho'
    saved = client.patch(f'/api/v1/automations/{rule_id}', headers=headers, json={'name': 'Direto'})
    assert saved.json['name'] == 'Direto' and saved.json['draft'] is None


def test_invalid_draft_is_refused_and_drafts_are_scoped(env):
    client, d = env
    headers = d['headers']()
    rule_id = active_rule(client, headers)
    invalid = client.put(
        f'/api/v1/automations/{rule_id}/draft',
        headers=headers,
        json={**BODY, 'event': 'opportunity.stage_idle'},
    )
    assert invalid.status_code == 422
    member = d['headers'](d['member'])
    outsider = d['headers'](d['outsider'])
    assert client.put(f'/api/v1/automations/{rule_id}/draft', headers=member, json=BODY).status_code == 403
    assert client.put(f'/api/v1/automations/{rule_id}/draft', headers=outsider, json=BODY).status_code == 404
    assert client.post(f'/api/v1/automations/{rule_id}/draft/publish', headers=outsider).status_code == 404
    assert client.delete(f'/api/v1/automations/{rule_id}/draft', headers=outsider).status_code == 404


def test_restoring_a_version_drops_the_pending_draft(env):
    client, d = env
    headers = d['headers']()
    rule_id = active_rule(client, headers)
    client.patch(f'/api/v1/automations/{rule_id}', headers=headers, json={'name': 'Segunda'})
    client.put(f'/api/v1/automations/{rule_id}/draft', headers=headers, json={**BODY, 'name': 'Rascunho'})
    restored = client.post(f'/api/v1/automations/{rule_id}/versions/1/restore', headers=headers)
    assert restored.status_code == 200, restored.json
    assert restored.json['name'] == 'Boas-vindas' and restored.json['draft'] is None
