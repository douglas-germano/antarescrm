import { useState } from 'react';
import { Check, Send, X } from 'lucide-react';
import { post, useData } from '@/lib/api';
import { Badge, Button, ConfirmDialog } from '@/components/ui';
import { ACTIONS, formatDelay } from '@/components/automations/model';

/** One predicate as the backend evaluated it, with the value it actually saw. */
export type Check = { field: string; operator: string; value: string; actual: unknown; passed: boolean };
export type Gate = { label: string; passed: boolean; actual?: unknown; checks?: Check[] };
export type PreviewStep = {
  kind: string; outcome: string; title?: string; checks?: Check[]; delay_minutes?: number; sends_message?: boolean;
};
export type PreviewResult = { eligible: boolean; gates?: Gate[]; steps: PreviewStep[] };

const FIELDS: Record<string, string> = {
  source: 'Origem', name: 'Nome', email: 'E-mail', phone: 'Telefone', tag: 'Tags', 'deal.stage_id': 'Etapa do negócio',
  'deal.status': 'Estado do negócio', 'deal.amount': 'Valor do negócio', 'comment.text': 'Texto do comentário',
  'comment.media_id': 'Publicação do comentário', 'reply.text': 'Resposta do contato', 'task.title': 'Título da tarefa',
};
const OPERATORS: Record<string, string> = {
  equals: 'é igual a', not_equals: 'é diferente de', contains: 'contém', exists: 'está preenchido', gte: 'é maior ou igual a', lt: 'é menor que',
};
// Fields that only exist when the real event happens (a comment, a reply, a completed task).
const EVENT_ONLY = ['comment.', 'reply.', 'task.'];

function shown(value: unknown) {
  if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) return 'vazio';
  return Array.isArray(value) ? value.join(', ') : String(value);
}

function CheckLine({ check }: { check: Check }) {
  const field = FIELDS[check.field] || (check.field.startsWith('custom.') ? 'Campo ' + check.field.slice(7) : check.field);
  const eventOnly = EVENT_ONLY.some((prefix) => check.field.startsWith(prefix));
  return (
    <li className={'flow-check ' + (check.passed ? 'pass' : 'fail')}>
      {check.passed ? <Check size={13} aria-label="Passou" /> : <X size={13} aria-label="Não passou" />}
      <span>
        {field} {OPERATORS[check.operator] || check.operator}{check.operator !== 'exists' && <> “{check.value}”</>}
        <small> · encontrado: {eventOnly && !check.actual ? 'só existe quando o evento acontece' : shown(check.actual)}</small>
      </span>
    </li>
  );
}

/** The result of a test run: why the contact entered the flow and what each step would do. Nothing is executed. */
export function PreviewReport({ preview }: { preview: PreviewResult }) {
  const sends = preview.steps.filter((step) => step.sends_message).length;
  return (
    <div role="status" className="flow-report">
      {!!preview.gates?.length && <>
        <h4>{preview.eligible ? 'Entraria no fluxo' : 'Não entraria no fluxo'}</h4>
        <ul className="flow-checks">
          {preview.gates.map((gate, index) => gate.checks
            ? <li key={index}><span className={'flow-gate ' + (gate.passed ? 'pass' : 'fail')}>{gate.label}</span><ul className="flow-checks">{gate.checks.map((check, i) => <CheckLine key={i} check={check} />)}</ul></li>
            : <li key={index} className={'flow-check ' + (gate.passed ? 'pass' : 'fail')}>
                {gate.passed ? <Check size={13} aria-label="Passou" /> : <X size={13} aria-label="Não passou" />}
                <span>{gate.label}<small> · encontrado: {shown(gate.actual)}</small></span>
              </li>)}
        </ul>
      </>}
      {!preview.gates && !preview.eligible && <p>O negócio e o contato não atendem aos filtros do gatilho.</p>}
      {preview.eligible && <>
        <h4>Passos</h4>
        <ol className="flow-report-steps">
          {preview.steps.map((step, index) => (
            <li key={index}>
              <b>{step.title || ACTIONS[step.kind] || 'Ramificação'}</b> · {step.outcome}
              {!!step.delay_minutes && <small> · depois de {formatDelay(step.delay_minutes)}</small>}
              {step.sends_message && <span className="flow-sends"><Send size={12} /> enviaria mensagem ao contato</span>}
              {!!step.checks?.length && <ul className="flow-checks">{step.checks.map((check, i) => <CheckLine key={i} check={check} />)}</ul>}
            </li>
          ))}
        </ol>
        {sends > 0 && <small>No teste nenhuma mensagem é enviada. Com a automação ativa, {sends === 1 ? '1 passo enviaria' : sends + ' passos enviariam'} mensagem de verdade.</small>}
      </>}
    </div>
  );
}

type Version = {
  id: string; number: number; created_at: string; author_name?: string | null; note?: string | null; changes: string[]; current: boolean;
};

const when = (iso: string) => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });

/** Saved versions of a rule; restoring one saves it again as the newest version, so nothing is lost. */
export function VersionHistory({ ruleId, dirty, onRestored }: { ruleId: string; dirty: boolean; onRestored: () => void | Promise<void> }) {
  const versions = useData<{ items: Version[] }>('/automations/' + ruleId + '/versions');
  const [restoring, setRestoring] = useState<Version | null>(null);
  const items = versions.data?.items || [];
  return (
    <section className="flow-preview flow-versions" aria-label="Versões">
      {versions.isLoading && <small>Carregando versões…</small>}
      {!versions.isLoading && !items.length && <small>O histórico começa no próximo salvamento.</small>}
      <ol>
        {items.map((version) => (
          <li key={version.id}>
            <span>
              <b>Versão {version.number}</b>{version.current && <> <Badge value="active" label="Em uso" /></>}
              <small> · {when(version.created_at)}{version.author_name ? ' · ' + version.author_name : ''}</small>
              <br />
              <small>{version.note || (version.changes.length ? 'Alterou ' + version.changes.join(', ') : 'Sem alterações de configuração')}</small>
            </span>
            {!version.current && <Button variant="ghost" onClick={() => setRestoring(version)}>Restaurar</Button>}
          </li>
        ))}
      </ol>
      <ConfirmDialog open={restoring !== null} onClose={() => setRestoring(null)} title={'Restaurar a versão ' + (restoring?.number ?? '') + '?'}
        description={(dirty ? 'As alterações não salvas serão descartadas. ' : '') + 'A configuração atual continua guardada no histórico. Se a automação estiver ativa, as próximas execuções já usam a versão restaurada.'}
        onConfirm={async () => {
          if (!restoring) return;
          await post('/automations/' + ruleId + '/versions/' + restoring.number + '/restore', {});
          await onRestored();
        }} />
    </section>
  );
}
