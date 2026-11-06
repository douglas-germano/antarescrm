from datetime import timedelta
from uuid import uuid4

from app.extensions import db
from app.models import AtlasJob, AtlasTarget, Contact, InboxThread, Opportunity, Task, WhatsAppConversation, now
from app.services import atlas, atlas_oauth, automations, whatsapp
from helpers.instagram import configure_instagram, event, receive
from helpers.whatsapp import arrange, raw


def rule(client, data, event_name, **action):
    result = client.post(
        '/api/v1/automations',
        headers=data['headers'](),
        json={
            'name': event_name,
            'task_title': 'Atender o contato',
            'event': event_name,
            'active': True,
            'actions': [action],
        },
    )
    assert result.status_code == 201, result.json
    return result.json


def connected(monkeypatch):
    monkeypatch.setattr(atlas_oauth, 'status', lambda _: {'connected': True})


def test_atlas_assigns_exact_whatsapp_conversation_and_handoff_creates_task(env, monkeypatch):
    client, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)
    connected(monkeypatch)
    rule(client, data, 'message.received', kind='atlas_assign')
    rule(client, data, 'atlas.handoff', kind='create_task', title='Continuar atendimento')
    conversation.assigned_to_id = data['member'].id
    db.session.add(
        WhatsAppConversation(
            workspace_id=data['ws'].id,
            phone='5566999991234',
            contact_id=conversation.contact_id,
        )
    )
    whatsapp.ingest(connection, raw('first'))
    db.session.commit()
    assert automations.process()[0]['status'] == 'completed'
    assert AtlasTarget.query.one().conversation_id == conversation.id

    whatsapp.ingest(connection, raw('second'))
    db.session.commit()
    assert automations.process()[0]['detail'] == 'O Atlas já recebeu este evento.'
    assert AtlasJob.query.count() == 2
    monkeypatch.setattr(atlas, 'now', lambda: now() + timedelta(seconds=6))
    payload = atlas.claim(data['ws'].id, group=True)
    assert payload['novas_mensagens'] == ['Olá', 'Olá']
    assert atlas.finish(data['ws'].id, payload['id'], '', decision={'handoff': 'Quer um orçamento.'}) == 'handoff'
    assert automations.process()[0]['status'] == 'completed'
    task = Task.query.one()
    assert task.description == 'Quer um orçamento.'
    assert task.assignee_id == data['member'].id
    assert task.contact_id == conversation.contact_id
    whatsapp.ingest(connection, raw('after-handoff'))
    db.session.commit()
    assert 'encaminhada para a equipe' in automations.process()[0]['detail']
    assert atlas.claim(data['ws'].id) is None
    gateway.send_text.assert_not_called()


def test_atlas_assigns_instagram_without_an_existing_target(env, monkeypatch):
    client, data = env
    connected(monkeypatch)
    configure_instagram(client, data)
    rule(client, data, 'message.received', kind='atlas_assign', content='Esclarecer dúvidas.')
    assert receive(client, event()).status_code == 200
    assert automations.process()[0]['status'] == 'completed'
    assert AtlasTarget.query.one().conversation_id == InboxThread.query.one().id
    assert atlas.claim(data['ws'].id)['objetivo'] == 'Esclarecer dúvidas.'


def test_form_answers_reach_atlas_only_with_a_recent_conversation(env, monkeypatch):
    client, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)
    connected(monkeypatch)
    form = data['form']
    form.fields = [{'key': 'vehicle', 'type': 'text', 'label': 'Veículo', 'required': True}]
    contact = db.session.get(Contact, conversation.contact_id)
    contact.email = 'cliente@example.com'
    db.session.commit()
    rule(
        client,
        data,
        'form.submitted',
        kind='atlas_assign',
        atlas_channel='whatsapp',
        content='Perguntar sobre o veículo.',
    )
    route = f'/api/v1/public/forms/{form.id}/submit'
    body = {'name': 'Cliente', 'email': contact.email, 'consent': True, 'answers': {'vehicle': 'HB20'}}
    assert client.post(route, json={**body, 'submission_key': str(uuid4())}).status_code == 200
    assert '24 horas' in automations.process()[0]['detail']
    assert AtlasTarget.query.count() == 0

    whatsapp.ingest(connection, raw('recent'))
    db.session.commit()
    assert client.post(route, json={**body, 'submission_key': str(uuid4())}).status_code == 200
    assert automations.process()[0]['status'] == 'completed'
    payload = atlas.claim(data['ws'].id)
    assert payload['acao'] == 'iniciar conversa'
    assert payload['dados_do_evento']['respostas'] == [{'campo': 'Veículo', 'resposta': 'HB20'}]
    assert atlas.finish(data['ws'].id, payload['id'], 'Olá! Vamos falar sobre o HB20?') == 'sent'
    gateway.send_text.assert_called_once()


def test_stage_follow_up_uses_stage_and_rechecks_before_delivery(env, monkeypatch):
    client, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)
    connected(monkeypatch)
    rule(
        client,
        data,
        'opportunity.stage_changed',
        kind='atlas_assign',
        atlas_channel='whatsapp',
        content='Revisar proposta.',
    )
    opportunity = Opportunity(
        workspace_id=data['ws'].id,
        contact_id=conversation.contact_id,
        stage_id=data['stage'].id,
        title='Proposta da oficina',
    )
    db.session.add(opportunity)
    whatsapp.ingest(connection, raw('recent', timestamp=int((now() - timedelta(hours=1)).timestamp())))
    db.session.commit()
    from app.models import PipelineStage

    stage = PipelineStage(workspace_id=data['ws'].id, name='Proposta enviada', position=1)
    db.session.add(stage)
    db.session.commit()
    route = f'/api/v1/opportunities/{opportunity.id}'
    assert client.patch(route, json={'stage_id': stage.id}, headers=data['headers']()).status_code == 200
    assert automations.process()[0]['status'] == 'completed'
    payload = atlas.claim(data['ws'].id)
    assert payload['dados_do_evento'] == {'negocio': 'Proposta da oficina', 'etapa': 'Proposta enviada'}
    assert client.patch(route, json={'stage_id': data['stage'].id}, headers=data['headers']()).status_code == 200
    assert atlas.finish(data['ws'].id, payload['id'], 'Podemos avançar com a proposta?') == 'blocked'
    gateway.send_text.assert_not_called()
