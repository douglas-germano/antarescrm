"""Provider-independent regressions for ingestion, durable sends and private media."""

import io
from datetime import timedelta

import pytest
from app.common import APIError
from app.extensions import db
from app.models import CommunicationSuppression, Contact, WhatsAppMedia, WhatsAppMessage, now
from app.services import whatsapp as service
from helpers.whatsapp import arrange, raw
from werkzeug.datastructures import FileStorage


def test_contact_matching_is_account_scoped_and_accepts_mobile_variant(env):
    _, d = env
    existing = Contact(workspace_id=d['ws'].id, name='Existing', phone='(66) 99999-0000')
    outsider = Contact(workspace_id=d['other'].id, name='Outside', phone='5566999990000')
    db.session.add_all([existing, outsider])
    db.session.commit()
    connection = service.connection_for(d['ws'].id)
    conversation = service.conversation_for(connection, '556699990000')
    assert conversation.contact_id == existing.id
    assert service.connection_for(d['ws'].id).id == connection.id
    assert service.conversation_for(connection, '5566999990000').id == conversation.id
    with pytest.raises(APIError):
        service.normalize_phone('bad')


def test_ingestion_deduplicates_and_preserves_live_chronology(env, monkeypatch):
    _, d = env
    connection, conversation, _ = arrange(d, monkeypatch)
    message, created = service.ingest(connection, raw())
    db.session.commit()
    assert created and message.direction == 'in' and conversation.unread_count == 1
    duplicate, created = service.ingest(connection, raw())
    assert not created and duplicate.id == message.id
    service.ingest(
        connection, raw('historical', timestamp=int((now() - timedelta(days=10)).timestamp())), historical=True
    )
    assert conversation.unread_count == 1 and conversation.last_message_at == message.occurred_at
    assert service.ingest(connection, {}) == (None, False)


def test_outgoing_is_durable_idempotent_and_never_retries_ambiguous_send(env, monkeypatch):
    _, d = env
    connection, conversation, gateway = arrange(d, monkeypatch)
    gateway.send_text.side_effect = APIError('Provedor indisponível', 502)
    message, created = service.send_outgoing(connection, conversation, 'Olá', 'attempt', d['owner'].id)
    assert created and message.status == 'unknown' and gateway.send_text.call_count == 1
    repeated, created = service.send_outgoing(connection, conversation, 'Olá', 'attempt', d['owner'].id)
    assert not created and repeated.id == message.id and gateway.send_text.call_count == 1
    with pytest.raises(APIError):
        service.send_outgoing(connection, conversation, 'Outro texto', 'attempt')
    echoed, created = service.ingest(connection, raw('accepted-at-provider', outgoing=True))
    assert not created and echoed.id == message.id and echoed.status == 'sent'
    assert echoed.provider_id == 'accepted-at-provider'


def test_text_send_and_contact_suppression(env, monkeypatch):
    _, d = env
    connection, conversation, gateway = arrange(d, monkeypatch)
    message, created = service.send_outgoing(connection, conversation, 'Mensagem', 'success', d['owner'].id)
    assert created and message.status == 'sent' and message.provider_id == 'sent-text'
    assert conversation.assigned_to_id == d['owner'].id and gateway.send_text.call_count == 1
    db.session.add(
        CommunicationSuppression(workspace_id=d['ws'].id, contact_id=conversation.contact_id, channel='whatsapp')
    )
    db.session.commit()
    with pytest.raises(APIError, match='autoriza'):
        service.send_outgoing(connection, conversation, 'Blocked', 'blocked')
    assert gateway.send_text.call_count == 1


def file(content=b'file', filename='file.pdf', mime='application/pdf'):
    return FileStorage(stream=io.BytesIO(content), filename=filename, content_type=mime)


def test_media_send_caches_bytes_and_detects_conflicting_retries(env, monkeypatch):
    _, d = env
    connection, conversation, gateway = arrange(d, monkeypatch)
    message, created = service.send_outgoing(connection, conversation, '', 'media', file=file())
    assert created and message.kind == 'document' and message.status == 'sent'
    assert service.media_for(connection, message).content == b'file'
    assert not service.send_outgoing(connection, conversation, '', 'media', file=file())[1]
    with pytest.raises(APIError):
        service.send_outgoing(connection, conversation, '', 'media', file=file(b'changed'))
    with pytest.raises(APIError):
        service.send_outgoing(connection, conversation, '', 'media')
    assert gateway.send_media.call_count == 1
    with pytest.raises(APIError):
        service.send_outgoing(connection, conversation, 'caption', 'audio', file=file(mime='audio/ogg'))
    with pytest.raises(APIError):
        service.send_outgoing(connection, conversation, '', 'empty', file=file(b''))
    connection.state = 'disconnected'
    with pytest.raises(APIError):
        service.send_outgoing(connection, conversation, 'Test', 'offline')


def test_media_recovery_is_validated_and_cached(env, monkeypatch):
    _, d = env
    connection, conversation, gateway = arrange(d, monkeypatch)
    message = WhatsAppMessage(
        workspace_id=d['ws'].id, conversation_id=conversation.id, direction='in', kind='document', provider_id='pdf'
    )
    db.session.add(message)
    db.session.commit()
    cached = service.media_for(connection, message)
    assert cached.content == b'private-pdf' and '/' not in cached.filename
    assert service.media_for(connection, message).id == cached.id and gateway.media.call_count == 1
    db.session.delete(cached)
    db.session.commit()
    for invalid in ({}, {'base64': '%%%%'}, {'base64': ''}):
        gateway.media.return_value = invalid
        with pytest.raises(APIError):
            service.media_for(connection, message)
    assert WhatsAppMedia.query.count() == 0
