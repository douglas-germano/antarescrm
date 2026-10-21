"""Validation of automation rule definitions."""

from ..common import APIError, get, user_ref
from ..models import MessageTemplate, PipelineStage
from ..schemas.growth import ActionSchema


def validate_rule(data):
    user_ref(data.get('assignee_id'))
    for index, action in enumerate(data.get('actions', [])):
        action = ActionSchema().load(action)
        data['actions'][index] = action
        if action['kind'] == 'send_message':
            if not action.get('template_id'):
                raise APIError('Selecione um modelo para enviar a mensagem.', 422)
            action['template_id'] = str(action['template_id'])
            get(MessageTemplate, action['template_id'])
        elif action['kind'] in ('reply_comment', 'private_reply'):
            if not (action.get('content') or '').strip():
                raise APIError('Escreva o texto da resposta.', 422)
            if len(action['content'].encode()) > 1000:
                raise APIError('A resposta aceita até 1.000 bytes.', 422)
        elif action['kind'] == 'add_tag':
            if not action.get('tag'):
                raise APIError('Informe a tag que será adicionada.', 422)
        elif action['kind'] == 'move_stage':
            if not action.get('stage_id'):
                raise APIError('Selecione a etapa de destino.', 422)
            action['stage_id'] = str(action['stage_id'])
            get(PipelineStage, action['stage_id'])
        elif not action.get('title'):
            raise APIError('Informe o título da tarefa ou retorno.', 422)
