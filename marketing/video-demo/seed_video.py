"""Dados fictícios extras para gravar o vídeo de demonstração (workspace demo).

Uso (a partir de backend/), apenas em banco antares_test_*:
  DATABASE_URL=postgresql+psycopg:///antares_test_video APP_ENV=development ANTARES_ENV_FILE=/dev/null \
  SECRET_KEY=x JWT_SECRET_KEY=y .venv/bin/python ../marketing/video-demo/seed_video.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

assert 'antares_test_' in os.environ.get('DATABASE_URL', ''), 'Use somente um banco antares_test_*'
sys.path.insert(0, os.getcwd())

from flask import g  # noqa: E402

from app import create_app  # noqa: E402
from app.common import add, today  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (Activity, Company, Contact, InboxMessage, InboxThread, Opportunity, PipelineStage, Task,  # noqa: E402
                        User, WhatsAppConversation, WhatsAppMessage, Workspace)

app = create_app()
with app.app_context(), app.test_request_context():
    ws = Workspace.query.filter_by(slug='demo').one()
    owner = User.query.filter_by(workspace_id=ws.id, role='owner').one()
    owner.name = 'Douglas'
    g.user, g.workspace_id = owner, ws.id
    if Contact.query.filter_by(workspace_id=ws.id, name='Maria Souza').first():
        sys.exit('Dados do vídeo já existem.')
    stages = PipelineStage.query.filter_by(workspace_id=ws.id).order_by(PipelineStage.position).all()
    now = datetime.now(timezone.utc)

    people = [
        ('Maria Souza', 'Studio Bella Estética', '5511987650001', 'Instagram', 0, 'Pacote de 10 sessões', 2400, -2),
        ('João Lima', 'Lima Arquitetura', '5511987650002', 'Indicação', 3, 'Projeto de interiores', 18500, -1),
        ('Clínica Bem Estar', 'Clínica Bem Estar', '5511987650003', 'Site', 2, 'Plano anual de atendimento', 4800, 5),
        ('Rafael Costa', 'Costa Engenharia', '5511987650004', 'WhatsApp', 1, 'Consultoria mensal', 3200, 7),
        ('Ana Ribeiro', 'Doce Ana Confeitaria', '5511987650005', 'Instagram', 4, 'Encomenda corporativa', 6900, 3),
        ('Pedro Alves', 'Alves Imóveis', '5511987650006', 'Formulário', 1, 'Gestão de anúncios', 2900, 10),
        ('Juliana Martins', 'JM Odontologia', '5511987650007', 'Google', 3, 'Implantação do sistema', 9600, 4),
        ('Carlos Nogueira', 'Nogueira Pet', '5511987650008', 'WhatsApp', 0, 'Banho e tosa — plano', 1500, 12),
    ]
    contacts = {}
    for name, comp, phone, source, st, title, amount, close in people:
        c = add(Company, {'name': comp, 'phone': phone, 'industry': 'Serviços'}) if comp != name else None
        ct = add(Contact, {'name': name, 'phone': phone, 'source': source, 'owner_id': owner.id,
                           'company_id': c.id if c else None, 'email': name.split()[0].lower() + '@exemplo.com.br'})
        op = add(Opportunity, {'contact_id': ct.id, 'company_id': c.id if c else None, 'stage_id': stages[st].id,
                               'title': title, 'amount': Decimal(amount), 'owner_id': owner.id,
                               'expected_close_date': today() + timedelta(days=close)})
        contacts[name] = (ct, op)

    # Pendências que aparecem na fila de acompanhamento
    ct, op = contacts['João Lima']
    add(Activity, {'title': 'Retornar sobre o orçamento', 'kind': 'call', 'contact_id': ct.id, 'opportunity_id': op.id,
                   'owner_id': owner.id, 'scheduled_at': now - timedelta(hours=20)})
    ct, op = contacts['Juliana Martins']
    add(Task, {'title': 'Enviar contrato revisado', 'contact_id': ct.id, 'opportunity_id': op.id, 'assignee_id': owner.id,
               'due_date': today() - timedelta(days=1), 'priority': 'high'})
    ct, op = contacts['Ana Ribeiro']
    add(Task, {'title': 'Confirmar data da entrega', 'contact_id': ct.id, 'opportunity_id': op.id, 'assignee_id': owner.id,
               'due_date': today(), 'priority': 'medium'})
    ct, op = contacts['Rafael Costa']
    add(Activity, {'title': 'Reunião de diagnóstico', 'kind': 'meeting', 'contact_id': ct.id, 'opportunity_id': op.id,
                   'owner_id': owner.id, 'scheduled_at': now + timedelta(days=1, hours=2)})

    # Conversas de WhatsApp aguardando resposta
    chats = [
        ('Maria Souza', [('in', 'Oi! Vi o anúncio no Instagram 😊', 130), ('in', 'Quanto custa o pacote de 10 sessões?', 128)], 2),
        ('Carlos Nogueira', [('in', 'Bom dia, vocês atendem sábado?', 55)], 1),
        ('Pedro Alves', [('out', 'Oi Pedro, segue a proposta 👍', 300), ('in', 'Recebi, vou ver com meu sócio e te falo', 240)], 0),
        ('Ana Ribeiro', [('in', 'Consegue entregar 200 unidades até sexta?', 18)], 1),
    ]
    for name, msgs, unread in chats:
        ct, _ = contacts[name]
        conv = add(WhatsAppConversation, {'contact_id': ct.id, 'phone': ct.phone, 'contact_name': name, 'assigned_to_id': owner.id,
                                          'unread_count': unread, 'last_message_at': now - timedelta(minutes=msgs[-1][2]),
                                          'last_message_preview': msgs[-1][1]})
        for k, (d, text, ago) in enumerate(msgs):
            add(WhatsAppMessage, {'conversation_id': conv.id, 'direction': d,
                                  'content': text, 'status': 'received' if d == 'in' else 'sent',
                                  'occurred_at': now - timedelta(minutes=ago), 'provider_id': f'video-{name}-{k}',
                                  'sent_by_id': owner.id if d == 'out' else None})

    # E-mail na caixa de entrada unificada
    ct, _ = contacts['Clínica Bem Estar']
    th = add(InboxThread, {'channel': 'email', 'address': ct.email, 'contact_id': ct.id, 'subject': 'Dúvida sobre o plano anual'})
    add(InboxMessage, {'thread_id': th.id, 'direction': 'in', 'content': 'Olá, o plano anual inclui suporte aos sábados?',
                       'subject': 'Dúvida sobre o plano anual', 'status': 'received', 'idempotency_key': 'video-email-1',
                       'scheduled_at': now - timedelta(minutes=95)})
    db.session.commit()
    print('Dados do vídeo criados:', len(people), 'contatos,', len(chats), 'conversas.')
