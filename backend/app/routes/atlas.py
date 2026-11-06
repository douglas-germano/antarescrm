from flask import Blueprint, current_app, redirect, request
from marshmallow import fields, validate

from ..common import APIError, current_account, payload, require
from ..schemas.base import StrictSchema
from ..services import atlas, atlas_oauth

bp = Blueprint('atlas', __name__)


@bp.get('/atlas/connection')
@require('owner', 'admin')
def get_connection():
    return atlas_oauth.status(current_account().workspace_id)


@bp.post('/atlas/connection')
@require('owner', 'admin')
def connect():
    response = current_app.json.response({'authorization_url': atlas_oauth.start(current_account())})
    response.headers['Cache-Control'] = 'no-store'
    return response


def oauth_callback():
    try:
        success = atlas_oauth.callback(request.args, request.host)
    except APIError:
        success = False
    location = current_app.config['APP_URL'] + '/configuracoes?tab=conexoes'
    if not success:
        location += '&chatgpt=failed'
    response = redirect(location, 303)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@bp.route('/atlas/conversations/<channel>/<uuid:identifier>', methods=['GET', 'POST', 'DELETE'])
@require()
def conversation_assignment(channel, identifier):
    account = current_account()
    identifier = str(identifier)
    if request.method == 'GET':
        return atlas.conversation_state(account, channel, identifier)
    account = atlas.operator(account.workspace_id, account.user_id)
    if request.method == 'POST':
        atlas.assign(account, channel, identifier)
        return atlas.conversation_state(account, channel, identifier)
    atlas.unassign(account, channel, identifier)
    return atlas.conversation_state(account, channel, identifier)


class AtlasPlaybookSchema(StrictSchema):
    offer = fields.String(required=True, validate=validate.Length(max=3000))
    questions = fields.String(required=True, validate=validate.Length(max=2000))
    rules = fields.String(required=True, validate=validate.Length(max=2000))
    handoff = fields.String(required=True, validate=validate.Length(max=2000))


@bp.route('/atlas/playbook', methods=['GET', 'PATCH'])
@require('owner', 'admin')
def playbook():
    account = current_account()
    if request.method == 'PATCH':
        atlas.save_playbook(account.workspace_id, payload(AtlasPlaybookSchema))
    return atlas.playbook(account.workspace_id)
