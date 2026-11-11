"""Validation of automation rule definitions."""

from ..common import APIError, get, user_ref
from ..models import MessageTemplate, PipelineStage
from ..schemas.growth import ActionSchema

MAX_STEPS = 30  # Across every path of the flow.
MAX_DEPTH = 5  # Branches inside branches.


def validate_rule(data, current=None):
    user_ref(data.get('assignee_id'))
    event = data.get('event', current.event if current else None)
    actions = data.get('actions', current.actions if current else [])
    if event == 'opportunity.stage_idle' and (not actions or not actions[0].get('stage_days')):
        raise APIError('Informe quantos dias o negócio deve permanecer na etapa.', 422)
    stop_on_reply = data.get('stop_on_reply', current.stop_on_reply if current else False)
    if stop_on_reply and has_reply_wait(actions):
        raise APIError('Desative a interrupção ao responder para usar a espera com dois caminhos.', 422)
    if 'actions' in data:
        data['actions'] = validate_steps(data['actions'], [0], 0, event)
    elif 'event' in data and current:
        validate_steps(current.actions or [], [0], 0, event)


def has_reply_wait(steps):
    return any(
        step.get('wait_reply_minutes') or has_reply_wait(step.get('yes', [])) or has_reply_wait(step.get('no', []))
        for step in steps
    )


def validate_steps(steps, counter, depth, event):
    loaded = []
    for index, action in enumerate(steps):
        action = ActionSchema().load(action)
        counter[0] += 1
        if counter[0] > MAX_STEPS:
            raise APIError(f'Uma automação aceita até {MAX_STEPS} passos somando todos os caminhos.', 422)
        if 'stage_days' in action and (depth or index or event != 'opportunity.stage_idle'):
            raise APIError('Configure o prazo de permanência no gatilho de negócio parado.', 422)
        if 'booking_before_minutes' in action and (
            depth or index or event not in ('booking.created', 'booking.rescheduled')
        ):
            raise APIError('Configure a antecedência no gatilho de agendamento.', 422)
        if action.get('wait_reply_minutes') and action['kind'] != 'branch':
            raise APIError('A espera por resposta precisa de dois caminhos.', 422)
        if action.get('assign_deal_owner') and action['kind'] not in ('create_task', 'follow_up'):
            raise APIError('Atribua ao dono do negócio em uma tarefa ou retorno.', 422)
        if action['kind'] == 'branch':
            validate_branch(action, index, len(steps), counter, depth, event)
        else:
            action.pop('yes', None)
            action.pop('no', None)
            validate_action(action, event)
        loaded.append(action)
    return loaded


def validate_branch(action, index, total, counter, depth, event):
    if index != total - 1:
        raise APIError(
            'A ramificação precisa ser o último passo do caminho; os passos seguintes ficam dentro dela.', 422
        )
    if depth >= MAX_DEPTH:
        raise APIError(f'Use no máximo {MAX_DEPTH} ramificações uma dentro da outra.', 422)
    if action.get('wait_reply_minutes') and not action.get('reply_channel'):
        raise APIError('Escolha o canal em que a resposta deve chegar.', 422)
    if not action.get('wait_reply_minutes') and not (action.get('conditions') or {}).get('items'):
        raise APIError('Defina ao menos uma condição para a ramificação.', 422)
    action['yes'] = validate_steps(action.get('yes', []), counter, depth + 1, event)
    action['no'] = validate_steps(action.get('no', []), counter, depth + 1, event)


INSTAGRAM_DMS = ('private_reply', 'instagram_message')


def validate_action(action, event):
    if action['kind'] not in INSTAGRAM_DMS:
        action.pop('buttons', None)
        action.pop('quick_replies', None)
    else:
        if action.get('buttons') and len(action.get('content') or '') > 640:
            raise APIError('Com botões, o Instagram aceita até 640 caracteres de texto.', 422)
        replies = action.get('quick_replies') or []
        if len(set(replies)) != len(replies):
            raise APIError('As respostas rápidas precisam ser diferentes entre si.', 422)
    if action['kind'] == 'send_message':
        if not action.get('template_id'):
            raise APIError('Selecione um modelo para enviar a mensagem.', 422)
        action['template_id'] = str(action['template_id'])
        get(MessageTemplate, action['template_id'])
    elif action['kind'] in ('reply_comment', *INSTAGRAM_DMS):
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
    elif action['kind'] == 'atlas_assign':
        if event not in ('message.received', 'form.submitted', 'opportunity.stage_changed'):
            raise APIError(
                'Selecione mensagem recebida, formulário recebido ou mudança de etapa para acionar o Atlas.', 422
            )
        if event == 'message.received':
            action.pop('atlas_channel', None)
        elif not action.get('atlas_channel') or not (action.get('content') or '').strip():
            raise APIError('Escolha o canal e informe o objetivo do Atlas.', 422)
    elif not action.get('title'):
        raise APIError('Informe o título da tarefa ou retorno.', 422)
