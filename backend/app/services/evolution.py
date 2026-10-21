"""Evolution API v2 adapter based on SDental EvolutionService (d06194f)."""

import requests
from flask import current_app

from ..common import APIError


class EvolutionService:
    def __init__(self, connection):
        self.connection = connection
        self.base = (current_app.config.get('EVOLUTION_API_URL') or '').rstrip('/')
        self.key = current_app.config.get('EVOLUTION_API_KEY')
        self.instance = connection.instance_name
        if not self.base or not self.key:
            raise APIError('Configure EVOLUTION_API_URL e EVOLUTION_API_KEY no servidor.', 503)

    def request(self, method, path, data=None, allow_404=False):
        try:
            response = requests.request(
                method,
                self.base + path,
                headers={'apikey': self.key, 'Content-Type': 'application/json'},
                json=data,
                timeout=(5, 25),
            )
            if allow_404 and response.status_code == 404:
                return {'state': 'not_found'}
            if response.status_code >= 400:
                raise APIError('A Evolution API não concluiu a operação. Confira a configuração e a conexão.', 502)
            return response.json() if response.content else {}
        except requests.Timeout:
            raise APIError(
                'A Evolution API demorou a responder. Confira o estado antes de repetir um envio.', 504
            ) from None
        except (requests.RequestException, ValueError):
            raise APIError('Não foi possível comunicar com a Evolution API.', 502) from None

    def create_instance(self):
        # Check before create; never reset/delete a previously paired instance.
        state = self.status()
        if state['state'] == 'not_found':
            self.request(
                'POST',
                '/instance/create',
                {'instanceName': self.instance, 'qrcode': True, 'integration': 'WHATSAPP-BAILEYS'},
            )
        return self.configure_webhook()

    def configure_webhook(self):
        base = (current_app.config.get('WHATSAPP_WEBHOOK_BASE_URL') or '').rstrip('/')
        if not base:
            raise APIError('Defina WHATSAPP_WEBHOOK_BASE_URL para a Evolution entregar as mensagens.', 503)
        self.request(
            'POST',
            '/webhook/set/' + self.instance,
            {
                'webhook': {
                    'enabled': True,
                    'url': base + '/api/v1/whatsapp/webhook',
                    'webhookByEvents': False,
                    'webhookBase64': False,
                    'headers': {'X-Webhook-Secret': self.connection.webhook_secret},
                    'events': ['MESSAGES_UPSERT', 'MESSAGES_UPDATE', 'CONNECTION_UPDATE'],
                }
            },
        )
        return {'webhook_configured': True}

    def status(self):
        data = self.request('GET', '/instance/connectionState/' + self.instance, allow_404=True)
        data = data.get('instance', data)
        state = data.get('state', 'unknown')
        owner = data.get('owner') or data.get('ownerJid') or ''
        return {'state': state, 'connected': state == 'open', 'phone_number': owner.split('@')[0].split(':')[0] or None}

    def qr(self):
        data = self.request('GET', '/instance/connect/' + self.instance)
        qr = data.get('base64') or (data.get('qrcode') or {}).get('base64')
        if not qr:
            return {
                'qrcode': None,
                'expires_in': 30,
                'message': 'Aguarde a geração do QR Code ou confira se o aparelho já está conectado.',
            }
        if not qr.startswith('data:image/png;base64,'):
            if qr.startswith('data:'):
                raise APIError('Formato de QR Code não suportado.', 502)
            qr = 'data:image/png;base64,' + qr
        return {'qrcode': qr, 'expires_in': 30}

    def disconnect(self):
        return self.request('DELETE', '/instance/logout/' + self.instance)

    def send_text(self, phone, content):
        return self.request(
            'POST',
            '/message/sendText/' + self.instance,
            {
                'number': phone,
                'text': content,
                'options': {'delay': 800, 'presence': 'composing', 'linkPreview': False},
            },
        )

    def send_media(self, phone, kind, encoded, mime, filename, caption=''):
        if kind == 'audio':
            return self.request(
                'POST', '/message/sendWhatsAppAudio/' + self.instance, {'number': phone, 'audio': encoded}
            )
        return self.request(
            'POST',
            '/message/sendMedia/' + self.instance,
            {
                'number': phone,
                'mediatype': kind,
                'mimetype': mime,
                'media': encoded,
                'fileName': filename,
                'caption': caption,
            },
        )

    def media(self, message):
        return self.request(
            'POST',
            '/chat/getBase64FromMediaMessage/' + self.instance,
            {
                'message': message.raw_message if message.raw_message else {'key': {'id': message.provider_id}},
                'convertToMp4': False,
            },
        )

    def history(self, phone):
        records, seen = [], set()
        for page in range(1, 6):
            body = self.request(
                'POST',
                '/chat/findMessages/' + self.instance,
                {'where': {'key': {'remoteJid': phone + '@s.whatsapp.net'}}, 'page': page, 'offset': 100, 'limit': 100},
            )
            chunk = body if isinstance(body, list) else body.get('records') or body.get('messages', [])
            if isinstance(chunk, dict):
                chunk = chunk.get('records', [])
            if not isinstance(chunk, list) or not chunk:
                break
            fresh = [r for r in chunk if isinstance(r, dict) and r.get('key', {}).get('id') not in seen]
            if not fresh:
                break
            for raw in fresh:
                seen.add(raw.get('key', {}).get('id'))
                records.append(raw)
            if len(chunk) < 100:
                break
        return records
