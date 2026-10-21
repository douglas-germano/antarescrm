import os
from datetime import timedelta, datetime, timezone
from decimal import Decimal
import click
from flask import g
from werkzeug.security import generate_password_hash
from .extensions import db
from .models import Workspace, User, Company, Contact, PipelineStage, Opportunity, Activity, Task
from .common import add, today
from .routes.auth import DEFAULT_STAGES


def register_commands(app):
    @app.cli.command('run-worker')
    @click.option('--once', is_flag=True, help='Execute one pass and exit.')
    @click.option('--interval', default=10, type=click.IntRange(1, 300))
    @click.option('--dispatch/--no-dispatch', default=False, help='Habilite envios somente após configurar e validar os canais.')
    def run_worker(once, interval, dispatch):
        import time
        from .services.automations import process
        from .services.communications import dispatch as dispatch_messages
        from .models import WorkerHeartbeat, now
        while True:
            failed = False
            try:
                actions, messages = process(limit=50), (dispatch_messages(limit=20) if dispatch else [])
                if actions or messages or once:
                    click.echo(f'{len(actions)} etapa(s), {len(messages)} mensagem(ns).')
            except Exception:
                db.session.rollback()
                app.logger.error('Falha no processamento da fila; confira configuração e banco.')
                failed = True
            finally:
                try:
                    heartbeat = WorkerHeartbeat.query.filter_by(name='default').first()
                    if not heartbeat:
                        heartbeat = WorkerHeartbeat(name='default'); db.session.add(heartbeat)
                    heartbeat.last_seen_at, heartbeat.error, heartbeat.dispatch_enabled = now(), failed, dispatch
                    if not failed: heartbeat.last_success_at = now()
                    db.session.commit()
                finally: db.session.remove()
            if once:
                if failed: raise click.ClickException('Falha no processamento.')
                return
            time.sleep(interval)

    @app.cli.command('process-automations')
    @click.option('--limit', default=50, type=click.IntRange(1, 100))
    def process_automations(limit):
        from .services.automations import process
        click.echo(f'{len(process(limit=limit))} etapa(s) processada(s).')

    @app.cli.command('process-outbox')
    @click.option('--limit', default=20, type=click.IntRange(1, 100))
    def process_outbox(limit):
        from .services.communications import dispatch
        click.echo(f'{len(dispatch(limit=limit))} mensagem(ns) processada(s).')

    @app.cli.command('instagram-refresh-names')
    def instagram_refresh_names():
        """Fills in names for Instagram contacts still using the placeholder name."""
        from .models import Contact, InstagramConnection
        from .services.instagram import apply_profile, fetch_profile
        updated = 0
        for connection in InstagramConnection.query.filter_by(active=True).all():
            for contact in Contact.query.filter_by(workspace_id=connection.workspace_id, archived=False).all():
                scoped = (contact.custom_fields or {}).get('instagram_scoped_id')
                if scoped and contact.name == 'Instagram ' + scoped:
                    before = contact.name
                    apply_profile(contact, scoped, fetch_profile(connection, scoped))
                    updated += contact.name != before
        db.session.commit()
        click.echo(f'{updated} contato(s) atualizado(s).')

    @app.cli.command('instagram-import')
    @click.option('--workspace-id', required=True)
    def instagram_import(workspace_id):
        """Bind the private .env token explicitly to one account; never expose it in output."""
        from .services.instagram import connect, configured
        from .common import APIError
        workspace = db.session.get(Workspace, workspace_id)
        token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
        if not workspace or not workspace.active or not token or not configured():
            raise click.ClickException('Conta ou configuração do Instagram indisponível.')
        try:
            row = connect(workspace.id, token)
            db.session.commit()
            click.echo(f'Instagram @{row.username} vinculado à conta {workspace.name}.')
        except APIError as error:
            db.session.rollback()
            raise click.ClickException(error.message)

    @app.cli.command('seed-demo')
    def seed_demo():
        """Create an isolated demonstration workspace; never overwrite existing data."""
        if Workspace.query.filter_by(slug='demo').first():
            click.echo('O workspace demo já existe; nenhum dado foi alterado.')
            return
        password = os.getenv('DEMO_PASSWORD') or click.prompt('Senha do proprietário (mínimo 10 caracteres)', hide_input=True, confirmation_prompt=True)
        if len(password) < 10 or len(password) > 128:
            raise click.ClickException('A senha deve ter entre 10 e 128 caracteres.')
        workspace = Workspace(name='Antares CRM — demonstração', slug='demo')
        db.session.add(workspace)
        db.session.flush()
        owner = User(workspace_id=workspace.id, name='Proprietário', email='admin@antarescrm.local', role='owner', title='Proprietário', password_hash=generate_password_hash(password))
        db.session.add(owner)
        db.session.flush()
        g.user, g.workspace_id = owner, workspace.id
        stages = [add(PipelineStage, {'name': name, 'position': i}) for i, name in enumerate(DEFAULT_STAGES)]
        company = add(Company, {'name': 'Empresa Exemplo Ltda', 'industry': 'Serviços', 'phone': '5511999990000'})
        contact = add(Contact, {'name': 'Contato Exemplo', 'phone': '5511999990001', 'company_id': company.id, 'owner_id': owner.id, 'source': 'Indicação', 'position': 'Diretor'})
        deal = add(Opportunity, {'contact_id': contact.id, 'company_id': company.id, 'stage_id': stages[3].id, 'title': 'Proposta anual', 'amount': Decimal('18000.00'), 'owner_id': owner.id})
        add(Activity, {'title': 'Ligar para apresentar a proposta', 'kind': 'call', 'contact_id': contact.id, 'opportunity_id': deal.id, 'owner_id': owner.id, 'scheduled_at': datetime.now(timezone.utc) + timedelta(days=1)})
        add(Task, {'title': 'Enviar proposta revisada', 'contact_id': contact.id, 'opportunity_id': deal.id, 'assignee_id': owner.id, 'due_date': today() + timedelta(days=2), 'priority': 'high'})
        db.session.commit()
        click.echo('Demonstração criada. Workspace: demo | E-mail: admin@antarescrm.local')
