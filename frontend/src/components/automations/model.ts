import type { Conditions } from '@/components/automations/conditions-editor';
import { emptyConditions } from '@/components/automations/conditions-editor';

export const EVENTS: Record<string, { label: string; hint: string }> = {
  'contact.created': { label: 'Contato criado', hint: 'Um novo contato entra na conta.' },
  'form.submitted': { label: 'Formulário recebido', hint: 'Alguém preenche um formulário público.' },
  'message.received': { label: 'Mensagem recebida', hint: 'O contato responde por qualquer canal.' },
  'booking.created': { label: 'Agendamento recebido', hint: 'Um horário é reservado na agenda pública.' },
  'booking.rescheduled': { label: 'Agendamento reagendado', hint: 'O horário de uma reserva muda.' },
  'task.completed': { label: 'Tarefa concluída', hint: 'Uma tarefa vinculada a um contato ou negócio é concluída pela primeira vez.' },
  'opportunity.stage_idle': { label: 'Negócio parado na etapa', hint: 'Um negócio permanece aberto na mesma etapa pelo prazo definido. Use uma condição para selecionar a etapa.' },
  'booking.cancelled': { label: 'Agendamento cancelado', hint: 'Uma reserva é cancelada.' },
  'instagram.comment': { label: 'Comentário no Instagram', hint: 'Alguém comenta em uma publicação da conta conectada. Respostas a comentários e comentários da própria conta são ignorados.' },
  'opportunity.created': { label: 'Negócio criado', hint: 'Um negócio é aberto no funil.' },
  'opportunity.stage_changed': { label: 'Etapa do negócio alterada', hint: 'Um negócio muda de etapa.' },
  'opportunity.won': { label: 'Negócio ganho', hint: 'Uma venda é fechada.' },
  'atlas.handoff': { label: 'Atlas encaminhou para a equipe', hint: 'Quando o Atlas repassar uma conversa, a ação Criar tarefa inclui o resumo e usa o responsável da conversa se nenhum for escolhido.' },
  'opportunity.lost': { label: 'Negócio perdido', hint: 'Um negócio é encerrado como perdido.' },
};

export const ACTIONS: Record<string, string> = {
  create_task: 'Criar tarefa',
  send_message: 'Enviar mensagem',
  follow_up: 'Agendar retorno',
  add_tag: 'Adicionar tag ao contato',
  move_stage: 'Mover negócio de etapa',
  reply_comment: 'Responder o comentário (Instagram)',
  private_reply: 'Enviar DM ao autor do comentário',
  instagram_message: 'Enviar direct no Instagram',
  atlas_assign: 'Atribuir conversa ao Atlas',
};

export const ATLAS_EVENTS = ['message.received', 'form.submitted', 'opportunity.stage_changed'];
/** Instagram direct messages can carry link buttons and quick replies. */
export const INSTAGRAM_DMS = ['private_reply', 'instagram_message'];
export const MAX_BUTTONS = 3;
export const MAX_QUICK_REPLIES = 13;
export type LinkButton = { title: string; url: string };

export type Step = {
  conditions?: Conditions;
  wait_reply_minutes?: number;
  reply_channel?: string;
  stage_days?: number;
  booking_before_minutes?: number;
  assign_deal_owner?: boolean;
  kind: string;
  title?: string;
  template_id?: string;
  tag?: string;
  content?: string;
  atlas_channel?: string;
  stage_id?: string;
  delay_minutes: number;
  due_days: number;
  /** Only on `kind: 'branch'`: the steps for when its conditions match, and for when they don't. */
  yes?: Step[];
  no?: Step[];
  /** How far the user dragged the card from its automatic place on the canvas. */
  offset?: { x: number; y: number };
  buttons?: LinkButton[];
  quick_replies?: string[];
};

export const newStep = (kind = 'create_task'): Step => ({ kind, title: '', delay_minutes: 0, due_days: 0 });
export const newBranch = (yes: Step[] = []): Step => ({ kind: 'branch', conditions: emptyConditions(), delay_minutes: 0, due_days: 0, yes, no: [] });

/** Limits the API enforces: 10 steps per path, 30 across the whole flow, branches 5 levels deep. */
export const MAX_PATH_STEPS = 10;
export const MAX_STEPS = 30;
export const MAX_DEPTH = 5;
export const BRANCH_LABEL = 'Ramificação (Se / Senão)';

/**
 * Where a step lives in the flow tree: indexes into each list, with the side taken at every branch.
 * `[2]` is the third top-level step; `[2, 'yes', 0]` is the first step of its "Sim" path.
 */
export type StepPath = (number | 'yes' | 'no')[];
export const pathKey = (path: StepPath) => path.join('.');

export function listAt(steps: Step[], listPath: StepPath): Step[] {
  let list = steps;
  for (let k = 0; k < listPath.length; k += 2) list = list[listPath[k] as number]?.[listPath[k + 1] as 'yes' | 'no'] || [];
  return list;
}

/** Returns a new tree with the list at `listPath` replaced by `edit(list)`. */
export function editList(steps: Step[], listPath: StepPath, edit: (list: Step[]) => Step[]): Step[] {
  if (!listPath.length) return edit(steps);
  const [index, side, ...rest] = listPath as [number, 'yes' | 'no', ...StepPath];
  return steps.map((step, i) => (i === index ? { ...step, [side]: editList(step[side] || [], rest, edit) } : step));
}

export const stepAt = (steps: Step[], path: StepPath) => listAt(steps, path.slice(0, -1))[path[path.length - 1] as number];

export const countSteps = (steps: Step[]): number =>
  steps.reduce((total, step) => total + 1 + countSteps(step.yes || []) + countSteps(step.no || []), 0);

/** The first step that cannot be saved yet, depth first, so the editor can open it. */
export function firstProblem(steps: Step[], event?: string, listPath: StepPath = []): { path: StepPath; problem: string } | null {
  for (let i = 0; i < steps.length; i += 1) {
    const problem = stepProblem(steps[i], event);
    if (problem) return { path: [...listPath, i], problem };
    for (const side of ['yes', 'no'] as const) {
      const nested = firstProblem(steps[i][side] || [], event, [...listPath, i, side]);
      if (nested) return nested;
    }
  }
  return null;
}

export const DELAY_UNITS = [
  { value: 1, label: 'minutos' },
  { value: 60, label: 'horas' },
  { value: 1440, label: 'dias' },
];

/** Splits minutes into the largest unit that divides evenly, for the editor's number + unit inputs. */
export function splitDelay(minutes: number) {
  if (minutes > 0 && minutes % 1440 === 0) return { amount: minutes / 1440, unit: 1440 };
  if (minutes > 0 && minutes % 60 === 0) return { amount: minutes / 60, unit: 60 };
  return { amount: minutes, unit: 1 };
}

export function formatDelay(minutes: number) {
  const { amount, unit } = splitDelay(minutes);
  if (unit === 1440) return `${amount} ${amount === 1 ? 'dia' : 'dias'}`;
  if (unit === 60) return `${amount} h`;
  return `${amount} min`;
}

/** The legacy single-task rules have no `actions`; show them as one step. */
export function stepsOf(rule: Record<string, any>): Step[] {
  return rule.actions?.length ? rule.actions : [{ kind: 'create_task', title: rule.task_title, delay_minutes: 0, due_days: rule.due_days || 0 }];
}

export function describeStep(step: Step, lookups: { template: (id?: string) => string | undefined; stage: (id?: string) => string | undefined }) {
  switch (step.kind) {
    case 'branch': {
      if (step.wait_reply_minutes) return `Aguardar resposta por até ${formatDelay(step.wait_reply_minutes)}`;
      const count = step.conditions?.items?.length || 0;
      return `Se ${count === 1 ? 'a condição for atendida' : `${step.conditions?.mode === 'any' ? 'alguma das' : 'as'} ${count} condições forem atendidas`}, segue pelo Sim; senão, pelo Não.`;
    }
    case 'send_message': return `Enviar mensagem · ${lookups.template(step.template_id) || 'modelo indisponível'}`;
    case 'reply_comment': return `Responder o comentário: ${step.content || ''}`;
    case 'private_reply': return `Enviar DM ao autor: ${step.content || ''}`;
    case 'instagram_message': return `Enviar direct: ${step.content || ''}`;
    case 'atlas_assign': return step.content ? `Atlas · ${step.content}` : 'Atribuir conversa ao Atlas';
    case 'add_tag': return `Adicionar a tag “${step.tag || ''}”`;
    case 'move_stage': return `Mover o negócio para ${lookups.stage(step.stage_id) || 'etapa indisponível'}`;
    case 'follow_up': return `Agendar retorno${step.title ? ': ' + step.title : ''}${step.due_days ? ` (em ${step.due_days} d)` : ''}`;
    default: return `Criar tarefa${step.title ? ': ' + step.title : ''}${step.due_days ? ` (prazo ${step.due_days} d)` : ''}`;
  }
}

export const RUN_STATUS: Record<string, { label: string; badge: string }> = {
  queued: { label: 'Agendada', badge: 'doing' },
  pending: { label: 'Pendente', badge: 'doing' },
  completed: { label: 'Concluída', badge: 'completed' },
  failed: { label: 'Falhou', badge: 'lost' },
  skipped: { label: 'Ignorada', badge: 'skipped' },
  cancelled: { label: 'Cancelada', badge: 'skipped' },
};

export const RECIPES = [
  { name: 'Boas-vindas a novos contatos', event: 'contact.created', steps: [{ kind: 'create_task', title: 'Entrar em contato com o novo lead', delay_minutes: 0, due_days: 0 }] },
  { name: 'Retorno após negócio criado', event: 'opportunity.created', steps: [{ kind: 'follow_up', title: 'Retornar sobre a proposta', delay_minutes: 2880, due_days: 0 }] },
  { name: 'Marcar clientes que compraram', event: 'opportunity.won', steps: [{ kind: 'add_tag', tag: 'cliente', delay_minutes: 0, due_days: 0 }] },
  { name: 'Responder comentários com a palavra “quero”', event: 'instagram.comment', conditions: { mode: 'all', items: [{ field: 'comment.text', operator: 'contains', value: 'quero' }] }, steps: [
    { kind: 'reply_comment', content: 'Oi, {{name}}! Te enviei os detalhes no direct.', delay_minutes: 0, due_days: 0 },
    { kind: 'private_reply', content: 'Olá! Obrigado pelo interesse. Como posso te ajudar?', delay_minutes: 0, due_days: 0 }] },
] as { name: string; event: string; steps: Step[]; conditions?: Conditions }[];

/** Fields each action needs before the rule can be saved; returns the first problem or null. */
export function stepProblem(step: Step, event?: string): string | null {
  if (step.kind === 'branch' && step.wait_reply_minutes && !step.reply_channel) return 'Escolha o canal da resposta.';
  if (step.kind === 'branch' && !step.wait_reply_minutes && !step.conditions?.items?.length) return 'Defina a condição que divide os caminhos.';
  if (step.kind === 'send_message' && !step.template_id) return 'Escolha o modelo de mensagem.';
  if ((step.kind === 'reply_comment' || INSTAGRAM_DMS.includes(step.kind)) && !step.content?.trim()) return 'Escreva o texto da mensagem.';
  if (INSTAGRAM_DMS.includes(step.kind)) {
    if (step.buttons?.some((b) => !b.title.trim() || !/^https:\/\/\S+\.\S+/.test(b.url.trim()))) return 'Cada botão precisa de um nome e de um link começando com https://.';
    if (step.buttons?.length && (step.content || '').length > 640) return 'Com botões, o texto pode ter até 640 caracteres.';
    const replies = (step.quick_replies || []).map((q) => q.trim());
    if (replies.some((q) => !q)) return 'Preencha ou remova as respostas rápidas vazias.';
    if (new Set(replies).size !== replies.length) return 'As respostas rápidas precisam ser diferentes.';
  }
  if (step.kind === 'atlas_assign' && event) {
    if (!ATLAS_EVENTS.includes(event)) return 'Selecione mensagem recebida, formulário recebido ou mudança de etapa para acionar o Atlas.';
    if (event !== 'message.received' && (!step.atlas_channel || !step.content?.trim())) return 'Escolha o canal e informe o objetivo do Atlas.';
  }
  if (step.kind === 'add_tag' && !step.tag?.trim()) return 'Informe a tag.';
  if (step.kind === 'move_stage' && !step.stage_id) return 'Escolha a etapa de destino.';
  if ((step.kind === 'create_task' || step.kind === 'follow_up') && !step.title?.trim()) return 'Informe o título.';
  return null;
}

const offsetOf = (step: Step) =>
  step.offset && (step.offset.x || step.offset.y) ? { offset: { x: Math.round(step.offset.x), y: Math.round(step.offset.y) } } : {};

/** The API payload for one step: only the fields its action uses. */
export function stepPayload(step: Step): Record<string, unknown> {
  if (step.kind === 'branch') {
    return { kind: 'branch', ...(step.wait_reply_minutes ? { wait_reply_minutes: step.wait_reply_minutes, reply_channel: step.reply_channel } : {}), conditions: step.conditions || emptyConditions(), delay_minutes: step.delay_minutes, due_days: 0,
      yes: (step.yes || []).map(stepPayload), no: (step.no || []).map(stepPayload), ...offsetOf(step) };
  }
  return {
    ...offsetOf(step),
    conditions: step.conditions || emptyConditions(), kind: step.kind, delay_minutes: step.delay_minutes, due_days: step.due_days,
    ...(step.kind === 'send_message' ? { template_id: step.template_id }
      : INSTAGRAM_DMS.includes(step.kind) ? {
        content: step.content,
        ...(step.buttons?.length ? { buttons: step.buttons.map((b) => ({ title: b.title.trim(), url: b.url.trim() })) } : {}),
        ...(step.quick_replies?.length ? { quick_replies: step.quick_replies.map((q) => q.trim()) } : {}),
      }
      : step.kind === 'atlas_assign' ? { content: step.content, atlas_channel: step.atlas_channel || undefined }
      : step.kind === 'reply_comment' ? { content: step.content }
      : step.kind === 'add_tag' ? { tag: step.tag }
      : step.kind === 'move_stage' ? { stage_id: step.stage_id }
      : { title: step.title, ...(step.assign_deal_owner ? { assign_deal_owner: true } : {}) }),
  };
}
