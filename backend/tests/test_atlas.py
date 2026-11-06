import pytest
from app.common import APIError
from app.extensions import db
from app.models import AtlasJob, InboxThread
from app.services import atlas, whatsapp
from app.services.instagram import client as instagram_client
from helpers.instagram import configure_instagram, event, receive
from helpers.whatsapp import arrange, raw


def test_whatsapp_opening_and_live_reply_use_existing_delivery(env, monkeypatch):
    _, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)
    account = atlas.operator(data['ws'].id, data['owner'].id)
    target_id = atlas.enroll(account, 'whatsapp', conversation.id, 'Apresentar a oficina.', True)

    opening = atlas.claim(account.workspace_id)
    assert opening['acao'] == 'iniciar conversa'
    assert 'Apresente-se brevemente uma única vez' in opening['instructions']
    assert atlas.claim(account.workspace_id) is None
    assert atlas.finish(account.workspace_id, opening['id'], 'Olá, sou Atlas.') == 'sent'
    with pytest.raises(APIError):
        atlas.finish(account.workspace_id, opening['id'], 'Olá, sou Atlas.')

    whatsapp.ingest(connection, raw('imported'), historical=True)
    whatsapp.ingest(connection, raw('inbound'))
    whatsapp.ingest(connection, raw('inbound'))
    db.session.commit()
    assert AtlasJob.query.count() == 2
    reply = atlas.claim(account.workspace_id)
    assert reply['acao'] == 'responder à conversa'
    assert 'sem repetir apresentação' in reply['instructions']
    assert reply['mensagem_recebida']
    gateway.send_text.side_effect = APIError('Tempo de espera excedido.', 502)
    assert atlas.finish(account.workspace_id, reply['id'], 'Como posso ajudar?') == 'unknown'
    assert atlas.claim(account.workspace_id) is None
    assert gateway.send_text.call_count == 2

    whatsapp.ingest(connection, raw('after'))
    db.session.commit()
    pending = atlas.claim(account.workspace_id)
    assert 'sem repetir apresentação' in pending['instructions']
    atlas.pause(account, target_id)
    with pytest.raises(APIError):
        atlas.finish(account.workspace_id, pending['id'], 'Não deve sair.')
    assert gateway.send_text.call_count == 2


def test_instagram_live_reply_is_scoped_and_sent_once(env, monkeypatch):
    client, data = env
    configure_instagram(client, data)
    assert receive(client, event()).status_code == 200
    thread = InboxThread.query.one()
    account = atlas.operator(data['ws'].id, data['owner'].id)
    atlas.enroll(account, 'instagram', thread.id, 'Apresentar a oficina.', False)
    assert atlas.claim(account.workspace_id) is None
    with pytest.raises(APIError):
        atlas.operator(data['ws'].id, data['outsider'].id)

    for _ in range(2):
        assert receive(client, event('new-message')).status_code == 200
    assert AtlasJob.query.count() == 1
    assert atlas.claim(data['other'].id) is None
    payload = atlas.claim(account.workspace_id)
    assert 'Apresente-se brevemente uma única vez' in payload['instructions']
    calls = []

    def send(path, token, method, **kwargs):
        assert path == '1234/messages' and method == 'POST'
        calls.append(kwargs['json'])
        return {'message_id': 'atlas-ig'}

    monkeypatch.setattr(instagram_client, 'graph', send)
    assert atlas.finish(account.workspace_id, payload['id'], 'Quer saber mais?') == 'sent'
    assert calls == [{'recipient': {'id': '5678'}, 'message': {'text': 'Quer saber mais?'}}]
    assert atlas.claim(account.workspace_id) is None
    assert receive(client, event('another-message')).status_code == 200
    continuation = atlas.claim(account.workspace_id)
    assert 'sem repetir apresentação' in continuation['instructions']


def test_portable_oauth_callback_saves_encrypted_session_and_rejects_replay(env, monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    from app.models import AtlasCredential
    from app.services import atlas_oauth

    client, data = env
    client.application.config['ATLAS_ENCRYPTION_KEY'] = None
    path = '/api/v1/atlas/connection'
    headers = data['headers']()
    outsider_headers = data['headers'](data['outsider'])
    assert client.post(path, headers=data['headers'](data['member'])).status_code == 403
    started = client.post(path, headers=headers)
    assert started.status_code == 200, started.json
    authorization = started.json['authorization_url']
    params = parse_qs(urlsplit(authorization).query)
    assert params['client_id'] == ['dynamic_agent_client']
    assert params['redirect_uri'] == ['http://127.0.0.1:5002/auth/callback']
    assert params['code_challenge_method'] == ['S256']
    calls = []

    def exchange(**fields):
        calls.append(fields)
        return {
            'access_token': 'fake-access',
            'refresh_token': 'fake-refresh',
            'expires_in': 3600,
            'scope': atlas_oauth.SCOPES,
            'id_token': 'fake-identity',
        }

    def identity(token, client_id, nonce):
        assert (token, client_id, nonce) == ('fake-identity', 'oaiapp_test', params['nonce'][0])
        return 'subject'

    monkeypatch.setattr(atlas_oauth, 'exchange', exchange)
    monkeypatch.setattr(atlas_oauth, 'identity', identity)
    args = {'state': params['state'][0], 'code': 'code', 'client_id': 'oaiapp_test'}
    failed = client.get('/auth/callback', query_string=args, base_url='https://example.com')
    assert 'chatgpt=failed' in failed.location and not calls
    response = client.get('/auth/callback', query_string=args, base_url='http://127.0.0.1:5002')
    assert response.status_code == 303 and response.location.endswith('?tab=conexoes')
    assert len(calls) == 1
    assert 'fake-access' not in AtlasCredential.query.one().ciphertext
    db.session.remove()
    assert client.get(path, headers=headers).json['connected']
    assert not client.get(path, headers=outsider_headers).json['connected']
    replay = client.get('/auth/callback', query_string=args, base_url='http://127.0.0.1:5002')
    assert 'chatgpt=failed' in replay.location and len(calls) == 1


def test_rotated_oauth_credentials_survive_temporary_identity_failure(env, monkeypatch):
    from app.services import atlas_oauth
    from cryptography.fernet import Fernet

    client, data = env
    client.application.config['ATLAS_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    workspace = data['ws'].id
    atlas_oauth.save(
        workspace,
        {
            'client_id': 'oaiapp_test',
            'subject': 'subject',
            'expires_at': 0,
            'access_token': 'expired',
            'refresh_token': 'old',
            'scope': atlas_oauth.SCOPES,
        },
    )
    db.session.commit()
    calls = []

    def exchange(**fields):
        calls.append(fields)
        return {'access_token': 'next', 'refresh_token': 'rotated', 'id_token': 'new-id', 'expires_in': 3600}

    def unavailable(*args, **kwargs):
        raise APIError('Identidade temporariamente indisponível.', 502)

    monkeypatch.setattr(atlas_oauth, 'exchange', exchange)
    monkeypatch.setattr(atlas_oauth, 'identity', unavailable)
    with pytest.raises(APIError):
        atlas_oauth.access_token(workspace)
    db.session.remove()
    monkeypatch.setattr(atlas_oauth, 'identity', lambda *args, **kwargs: 'subject')
    assert atlas_oauth.access_token(workspace) == 'next'
    assert len(calls) == 1 and atlas_oauth.session(workspace)['refresh_token'] == 'rotated'


def test_inbox_atlas_assignment_requires_admin_and_only_handles_new_messages(env, monkeypatch):
    from app.services import atlas_oauth

    client, data = env
    connection, conversation, _ = arrange(data, monkeypatch)
    path = f'/api/v1/atlas/conversations/whatsapp/{conversation.id}'
    owner = data['headers']()
    member = data['headers'](data['member'])
    assert client.get(path, headers=member).json == {'active': False}
    assert client.post(path, headers=member).status_code == 403
    assert client.post(path, headers=owner).status_code == 409
    assert client.get(path, headers=data['headers'](data['outsider'])).status_code == 404

    monkeypatch.setattr(atlas_oauth, 'status', lambda _: {'connected': True})
    whatsapp.ingest(connection, raw('before-atlas'))
    db.session.commit()
    assert client.post(path, headers=owner).json == {'active': True}
    assert client.get(path, headers=member).json == {'active': True}
    assert AtlasJob.query.count() == 0

    whatsapp.ingest(connection, raw('after-atlas'))
    db.session.commit()
    assert AtlasJob.query.one().status == 'queued'
    assert client.delete(path, headers=owner).json == {'active': False}
    assert AtlasJob.query.one().status == 'cancelled'
    assert client.post(path, headers=owner).json == {'active': True}
    assert AtlasJob.query.count() == 1


def test_atlas_groups_replies_remembers_context_and_hands_off(env, monkeypatch):
    from datetime import timedelta

    from app.models import now
    from app.services.atlas_runner import parse_decision

    client, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)
    account = atlas.operator(data['ws'].id, data['owner'].id)
    atlas.enroll(account, 'whatsapp', conversation.id, 'Atendimento inicial.', False)
    playbook = {
        'offer': 'Oficina',
        'questions': 'Qual é o veículo?',
        'rules': 'Não informar preços',
        'handoff': 'Orçamento',
    }
    response = client.patch('/api/v1/atlas/playbook', json=playbook, headers=data['headers']())
    assert response.status_code == 200 and response.json == playbook
    assert atlas.playbook(data['other'].id) == {}
    whatsapp.ingest(connection, raw('one'))
    whatsapp.ingest(connection, raw('two'))
    db.session.commit()
    assert atlas.claim(account.workspace_id, group=True) is None
    monkeypatch.setattr(atlas, 'now', lambda: now() + timedelta(seconds=6))
    job = atlas.claim(account.workspace_id, group=True)
    assert job['roteiro'] == playbook
    assert len(job['novas_mensagens']) == 2
    assert AtlasJob.query.filter_by(status='grouped').count() == 1
    decision = parse_decision(
        '{"reply":"Qual é o veículo?", "memory":"O contato quer atendimento.", "handoff":null, "suggestion":null}'
    )
    assert atlas.finish(account.workspace_id, job['id'], decision['reply'], decision=decision) == 'sent'

    whatsapp.ingest(connection, raw('three'))
    db.session.commit()
    job = atlas.claim(account.workspace_id, group=True)
    assert job['contexto_guardado'] == 'O contato quer atendimento.'
    decision = parse_decision(
        '{"reply":"","memory":"O contato quer orçamento.", "handoff":"Solicitou orçamento.", '
        '"suggestion":{"kind":"task","title":"Enviar orçamento","reason":"Pedido do contato."}}'
    )
    assert atlas.finish(account.workspace_id, job['id'], '', decision=decision) == 'handoff'
    state = atlas.conversation_state(account, 'whatsapp', conversation.id)
    assert state['active'] is False and state['memory'] == 'O contato quer orçamento.'
    assert state['insight']['suggestion']['kind'] == 'task'
    assert conversation.assigned_to_id == account.user_id
    assert gateway.send_text.call_count == 1


def test_atlas_transcribes_whatsapp_voice_in_group_before_sending_context(env, monkeypatch):
    from datetime import timedelta

    from app.models import now
    from app.services import atlas_audio

    _, data = env
    connection, conversation, gateway = arrange(data, monkeypatch)
    account = atlas.operator(data['ws'].id, data['owner'].id)
    atlas.enroll(account, 'whatsapp', conversation.id, 'Teste de áudio.', False)
    voice = raw('voice')
    voice['message'] = {'audioMessage': {'mimetype': 'audio/ogg; codecs=opus', 'ptt': True}}
    message, _ = whatsapp.ingest(connection, voice)
    db.session.commit()
    assert message.kind == 'audio' and AtlasJob.query.count() == 1
    monkeypatch.setattr(atlas, 'now', lambda: now() + timedelta(seconds=6))
    job = atlas.claim(account.workspace_id, group=True)

    def transcript(content):
        assert content == b'private-pdf'
        return 'Quero um orçamento.'

    monkeypatch.setattr(atlas_audio, 'transcribe', transcript)
    atlas_audio.apply(account.workspace_id, job)
    assert '_audio' not in job
    assert job['novas_mensagens'] == ['Quero um orçamento.']
    assert job['mensagem_recebida'] == 'Quero um orçamento.'
    gateway.media.assert_called_once()
    gateway.send_text.assert_not_called()


def test_atlas_uses_audio_attachment_from_signed_instagram_event(env, monkeypatch):
    from contextlib import nullcontext
    from datetime import timedelta
    from types import SimpleNamespace

    from app.models import now
    from app.services import atlas_audio

    client, data = env
    configure_instagram(client, data)
    assert receive(client, event()).status_code == 200
    thread = InboxThread.query.one()
    account = atlas.operator(data['ws'].id, data['owner'].id)
    atlas.enroll(account, 'instagram', thread.id, 'Teste de áudio.', False)
    voice = event('voice')
    voice['entry'][0]['messaging'][0]['message'] = {
        'mid': 'voice',
        'attachments': [{'type': 'audio', 'payload': {'url': 'https://scontent.cdninstagram.com/audio'}}],
    }
    assert receive(client, voice).status_code == 200
    monkeypatch.setattr(atlas, 'now', lambda: now() + timedelta(seconds=6))
    job = atlas.claim(account.workspace_id, group=True)

    def download(url, **options):
        assert url == 'https://scontent.cdninstagram.com/audio'
        assert options['allow_redirects'] is False
        return nullcontext(SimpleNamespace(status_code=200, iter_content=lambda _: [b'audio']))

    monkeypatch.setattr(atlas_audio.requests, 'get', download)
    monkeypatch.setattr(atlas_audio, 'transcribe', lambda _: 'Tenho uma dúvida.')
    atlas_audio.apply(account.workspace_id, job)
    assert job['novas_mensagens'] == ['Tenho uma dúvida.']
