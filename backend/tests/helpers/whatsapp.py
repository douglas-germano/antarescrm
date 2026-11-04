import base64
from types import SimpleNamespace
from unittest.mock import Mock

from app.extensions import db
from app.models import now
from app.services import whatsapp as service


def raw(identifier='inbound', outgoing=False, timestamp=None):
    return {
        'key': {'id': identifier, 'remoteJid': '5566999990000@s.whatsapp.net', 'fromMe': outgoing},
        'pushName': 'Cliente',
        'message': {'conversation': 'Olá'},
        'messageTimestamp': timestamp or int(now().timestamp()),
    }


def arrange(d, monkeypatch):
    connection = service.connection_for(d['ws'].id)
    connection.state = 'open'
    conversation = service.conversation_for(connection, '66999990000', 'Cliente')
    db.session.commit()
    gateway = SimpleNamespace(
        send_text=Mock(return_value={'key': {'id': 'sent-text'}}),
        send_media=Mock(return_value={'id': 'sent-file'}),
        media=Mock(
            return_value={
                'base64': base64.b64encode(b'private-pdf').decode(),
                'mimetype': 'application/pdf',
                'fileName': '../../private.pdf',
            }
        ),
    )
    monkeypatch.setattr(service, 'EvolutionService', lambda connection: gateway)
    return connection, conversation, gateway
