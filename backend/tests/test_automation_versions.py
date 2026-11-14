from app.extensions import db
from app.models import AutomationRule, AutomationRuleVersion, InboxMessage, MessageTemplate, Task
from helpers.automations import contact_for
from helpers.growth import rule

BODY = {
    'name': 'Boas-vindas',
    'task_title': 'Ligar',
    'event': 'contact.created',
    'active': False,
    'actions': [{'kind': 'create_task', 'title': 'Ligar'}],
}


def versions(client, headers, rule_id):
    response = client.get(f'/api/v1/automations/{rule_id}/versions', headers=headers)
    assert response.status_code == 200, response.json
    return response.json['items']


def test_each_saved_change_is_a_version_and_restore_records_a_new_one(env):
    client, d = env
    headers = d['headers']()
    created = client.post('/api/v1/automations', headers=headers, json=BODY).json
    rule_id = created['id']
    assert (
        client.patch(f'/api/v1/automations/{rule_id}', headers=headers, json={'name': 'Primeiro contato'}).status_code
        == 200
    )
    # Pausing or resuming is not a configuration change.
    assert client.patch(f'/api/v1/automations/{rule_id}', headers=headers, json={'active': True}).status_code == 200
    items = versions(client, headers, rule_id)
    assert [item['number'] for item in items] == [2, 1]
    assert items[0]['changes'] == ['nome'] and items[0]['current'] and items[0]['author_name'] == 'Owner'
    assert items[1]['note'] == 'Criada' and not items[1]['current']

    restored = client.post(f'/api/v1/automations/{rule_id}/versions/1/restore', headers=headers)
    assert restored.status_code == 200, restored.json
    assert restored.json['name'] == 'Boas-vindas' and restored.json['active'] is True
    items = versions(client, headers, rule_id)
    assert items[0]['number'] == 3 and items[0]['note'] == 'Restaurada da versão 1' and items[0]['current']
    assert client.post(f'/api/v1/automations/{rule_id}/versions/3/restore', headers=headers).status_code == 409
    assert client.post(f'/api/v1/automations/{rule_id}/versions/9/restore', headers=headers).status_code == 404


def test_versions_are_admin_only_and_scoped_to_the_account(env):
    client, d = env
    rule_id = client.post('/api/v1/automations', headers=d['headers'](), json=BODY).json['id']
    assert client.get(f'/api/v1/automations/{rule_id}/versions', headers=d['headers'](d['member'])).status_code == 403
    outsider = d['headers'](d['outsider'])
    assert client.get(f'/api/v1/automations/{rule_id}/versions', headers=outsider).status_code == 404
    assert client.post(f'/api/v1/automations/{rule_id}/versions/1/restore', headers=outsider).status_code == 404


def test_rule_saved_before_history_keeps_its_configuration_as_version_one(env):
    client, d = env
    headers = d['headers']()
    legacy = rule(d, event='contact.created')
    assert (
        client.patch(f'/api/v1/automations/{legacy.id}', headers=headers, json={'task_title': 'Novo'}).status_code
        == 200
    )
    items = versions(client, headers, legacy.id)
    assert [item['number'] for item in items] == [2, 1]
    assert items[1]['snapshot']['task_title'] == 'Retornar ao lead' and items[1]['author_id'] is None
    assert items[0]['changes'] == ['título da tarefa']
    # Deleting a rule that never ran also deletes its history.
    assert client.delete(f'/api/v1/automations/{legacy.id}', headers=headers).status_code == 204
    assert AutomationRuleVersion.query.count() == 0 and db.session.get(AutomationRule, legacy.id) is None


def test_preview_explains_each_check_and_marks_messages_without_sending(env):
    client, d = env
    headers = d['headers']()
    template = MessageTemplate(workspace_id=d['ws'].id, name='Oi', channel='email', subject='Oi', content='Oi')
    db.session.add(template)
    db.session.commit()
    contact = contact_for(d, tags=['vip'], source='Site', email='lead@example.com')
    deal = client.post(
        '/api/v1/opportunities',
        headers=headers,
        json={'title': 'Negócio', 'stage_id': d['stage'].id, 'contact_id': contact.id, 'amount': '1500'},
    ).json
    body = {
        **BODY,
        'source': 'site',
        'conditions': {'mode': 'all', 'items': [{'field': 'tag', 'operator': 'equals', 'value': 'VIP'}]},
        'actions': [
            {'kind': 'send_message', 'template_id': template.id, 'delay_minutes': 10},
            {
                'kind': 'create_task',
                'title': 'Proposta grande',
                'conditions': {'mode': 'all', 'items': [{'field': 'deal.amount', 'operator': 'gte', 'value': '5000'}]},
            },
        ],
    }
    response = client.post(
        '/api/v1/automations/preview', headers=headers, json={'rule': body, 'opportunity_id': deal['id']}
    )
    assert response.status_code == 200, response.json
    result = response.json
    assert result['eligible']
    assert [gate['label'] for gate in result['gates']] == [
        'Contato ativo',
        'Origem é site',
        'Condições do gatilho (todas)',
    ]
    assert result['gates'][2]['checks'][0] == {
        'field': 'tag',
        'operator': 'equals',
        'value': 'VIP',
        'actual': ['vip'],
        'passed': True,
    }
    message, task = result['steps']
    assert message['sends_message'] and message['delay_minutes'] == 10
    assert task['outcome'] == 'Condição não atendida' and not task['sends_message']
    assert task['checks'][0]['actual'] == '1500.00' and not task['checks'][0]['passed']
    assert InboxMessage.query.count() == 0 and Task.query.count() == 0

    body['required_tag'] = 'cliente'
    blocked = client.post(
        '/api/v1/automations/preview', headers=headers, json={'rule': body, 'opportunity_id': deal['id']}
    ).json
    assert not blocked['eligible'] and blocked['steps'] == []
    assert [gate for gate in blocked['gates'] if not gate['passed']][0]['label'] == 'Tem a tag cliente'
