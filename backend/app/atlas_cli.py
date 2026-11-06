import json
import sys
from uuid import UUID

import click

from .common import APIError
from .models import AtlasJob, AtlasTarget
from .services import atlas


def register_atlas(app):
    @app.cli.group('atlas')
    def commands():
        """Operate the local Atlas pilot."""

    @commands.command('enroll')
    @click.argument('workspace_id', type=UUID)
    @click.argument('user_id', type=UUID)
    @click.argument('channel', type=click.Choice(['whatsapp', 'instagram']))
    @click.argument('conversation_id', type=UUID)
    @click.option('--brief', required=True)
    @click.option('--opening', is_flag=True, help='Queue one first message.')
    def enroll(workspace_id, user_id, channel, conversation_id, brief, opening):
        if not 0 < len(brief.strip()) <= 2000:
            raise click.ClickException('Informe um objetivo de até 2.000 caracteres.')
        try:
            account = atlas.operator(str(workspace_id), str(user_id))
            click.echo(atlas.enroll(account, channel, str(conversation_id), brief.strip(), opening))
        except APIError as error:
            raise click.ClickException(error.message) from None

    @commands.command('pause')
    @click.argument('workspace_id', type=UUID)
    @click.argument('user_id', type=UUID)
    @click.argument('target_id', type=UUID)
    def pause(workspace_id, user_id, target_id):
        try:
            atlas.pause(atlas.operator(str(workspace_id), str(user_id)), str(target_id))
        except APIError as error:
            raise click.ClickException(error.message) from None

    @commands.command('status')
    @click.argument('workspace_id', type=UUID)
    @click.argument('user_id', type=UUID)
    def status(workspace_id, user_id):
        try:
            account = atlas.operator(str(workspace_id), str(user_id))
        except APIError as error:
            raise click.ClickException(error.message) from None
        for row in account.query(AtlasTarget).all():
            jobs = account.query(AtlasJob).filter_by(target_id=row.id)
            click.echo(
                json.dumps(
                    {
                        'id': row.id,
                        'channel': row.channel,
                        'conversation_id': row.conversation_id,
                        'active': row.active,
                        'jobs': {
                            state: jobs.filter_by(status=state).count()
                            for state in (
                                'queued',
                                'claimed',
                                'sending',
                                'sent',
                                'unknown',
                                'blocked',
                                'failed',
                                'expired',
                                'cancelled',
                            )
                        },
                    }
                )
            )

    @commands.command('claim')
    @click.argument('workspace_id', type=UUID)
    def claim(workspace_id):
        click.echo(json.dumps(atlas.claim(str(workspace_id)), ensure_ascii=False))

    @commands.command('finish')
    @click.argument('workspace_id', type=UUID)
    @click.argument('job_id', type=UUID)
    def finish(workspace_id, job_id):
        content = sys.stdin.read(901).strip()
        try:
            click.echo(atlas.finish(str(workspace_id), str(job_id), content))
        except APIError as error:
            raise click.ClickException(error.message) from None
