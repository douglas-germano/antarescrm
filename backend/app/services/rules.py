"""Validation of automation rule definitions."""

from ..common import APIError, get, user_ref
from ..models import MessageTemplate, PipelineStage
from ..schemas.growth import ActionSchema

MAX_STEPS = 30  # Across every path of the flow.
MAX_DEPTH = 5  # Branches inside branches.


def validate_rule(data):
    user_ref(data.get('assignee_id'))
    if 'actions' in data:
        counter = [0]
        data['actions'] = validate_steps(data['actions'], counter, 0)


def validate_steps(steps, counter, depth):
    loaded = []
    for index, action in enumerate(steps):
        action = ActionSchema().load(action)
        counter[0] += 1
        if counter[0] > MAX_STEPS:
            raise APIError(f'Uma automação aceita até {MAX_STEPS} passos somando todos os caminhos.', 422)
        if action['kind'] == 'branch':
            validate_branch(action, index, len(steps), counter, depth)
        else:
            action.pop('yes', None)
            action.pop('no', None)
            validate_action(action)
        loaded.append(action)
    return loaded


def validate_branch(action, index, total, counter, depth):
    if index != total - 1:
        raise APIError(
            'A ramificação precisa ser o último passo do caminho; os passos seguintes ficam dentro dela.', 422
        )
    if depth >= MAX_DEPTH:
        raise APIError(f'Use no máximo {MAX_DEPTH} ramificações uma dentro da outra.', 422)
    if not (action.get('conditions') or {}).get('items'):
        raise APIError('Defina ao menos uma condição para a ramificação.', 422)
    action['yes'] = validate_steps(action.get('yes', []), counter, depth + 1)
    action['no'] = validate_steps(action.get('no', []), counter, depth + 1)


def validate_action(action):
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
