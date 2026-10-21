import type { Conditions } from '@/components/automations/conditions-editor';

export const EVENTS: Record<string, { label: string; hint: string }> = {
  'contact.created': { label: 'Contato criado', hint: 'Um novo contato entra na conta.' },
  'form.submitted': { label: 'Formulário recebido', hint: 'Alguém preenche um formulário público.' },
  'message.received': { label: 'Mensagem recebida', hint: 'O contato responde por qualquer canal.' },
  'booking.created': { label: 'Agendamento recebido', hint: 'Um horário é reservado na agenda pública.' },
  'booking.cancelled': { label: 'Agendamento cancelado', hint: 'Uma reserva é cancelada.' },
  'instagram.comment': { label: 'Comentário no Instagram', hint: 'Alguém comenta em uma publicação da conta conectada. Respostas a comentários e comentários da própria conta são ignorados.' },
  'opportunity.created': { label: 'Negócio criado', hint: 'Um negócio é aberto no funil.' },
  'opportunity.stage_changed': { label: 'Etapa do negócio alterada', hint: 'Um negócio muda de etapa.' },
  'opportunity.won': { label: 'Negócio ganho', hint: 'Uma venda é fechada.' },
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
};

export type Step = {
  conditions?: Conditions;
  kind: string;
  title?: string;
  template_id?: string;
  tag?: string;
  content?: string;
  stage_id?: string;
  delay_minutes: number;
  due_days: number;
};

export const newStep = (kind = 'create_task'): Step => ({ kind, title: '', delay_minutes: 0, due_days: 0 });

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
    case 'send_message': return `Enviar mensagem · ${lookups.template(step.template_id) || 'modelo indisponível'}`;
    case 'reply_comment': return `Responder o comentário: ${step.content || ''}`;
    case 'private_reply': return `Enviar DM ao autor: ${step.content || ''}`;
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
