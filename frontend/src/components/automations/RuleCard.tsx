import { Copy, Pencil, Trash2 } from 'lucide-react';
import type { Row } from '@/lib/types';
import { EVENTS, ACTIONS, describeStep, formatDelay, stepsOf } from './model';

function ago(iso?: string | null) {
  if (!iso) return 'nunca executou';
  const minutes = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 60000));
  if (minutes < 60) return `há ${Math.max(1, minutes)} min`;
  if (minutes < 1440) return `há ${Math.floor(minutes / 60)} h`;
  const days = Math.floor(minutes / 1440);
  return `há ${days} ${days === 1 ? 'dia' : 'dias'}`;
}

export function RuleCard({ rule, manage, owner, lookups, onToggle, onEdit, onDuplicate, onDelete }: {
  rule: Row; manage: boolean; owner?: string;
  lookups: { template: (id?: string) => string | undefined; stage: (id?: string) => string | undefined };
  onToggle: (active: boolean) => void; onEdit: () => void; onDuplicate: () => void; onDelete: () => void;
}) {
  const steps = stepsOf(rule);
  const filters = [
    rule.source && `Origem: ${rule.source}`,
    rule.required_tag && `Tag: ${rule.required_tag}`,
    rule.conditions?.items?.length && `${rule.conditions.items.length} ${rule.conditions.items.length === 1 ? 'condição' : 'condições'}`,
    rule.stop_on_reply && 'Para se o contato responder',
  ].filter(Boolean) as string[];
  const stats = rule.stats || { runs: 0, failed: 0, last_run_at: null };
  return (
    <article className={'rule-card' + (rule.active ? '' : ' paused')}>
      <header className="rule-card-head">
        <div className="rule-card-title">
          <h3>{rule.name}</h3>
          <span className="deal-chip">{EVENTS[rule.event]?.label || rule.event}</span>
        </div>
        <button type="button" role="switch" aria-checked={rule.active} aria-label={(rule.active ? 'Pausar ' : 'Ativar ') + rule.name} className={'switch' + (rule.active ? ' on' : '')}
          disabled={!manage} onClick={() => onToggle(!rule.active)}><span /></button>
      </header>
      {filters.length > 0 && <div className="rule-filters">{filters.map((f) => <span key={f} className="deal-chip">{f}</span>)}</div>}
      <ol className="rule-timeline">
        {steps.map((step, index) => (
          <li key={index}>
            <span className="rule-dot" aria-hidden />
            <div>
              {step.delay_minutes > 0 && <small className="rule-wait">Após {formatDelay(step.delay_minutes)}</small>}
              <p title={ACTIONS[step.kind]}>{describeStep(step, lookups)}</p>
            </div>
          </li>
        ))}
      </ol>
      <footer className="rule-card-foot">
        <span className="muted">
          {stats.runs} {stats.runs === 1 ? 'execução' : 'execuções'} · {ago(stats.last_run_at)}
          {stats.failed > 0 && <strong className="text-danger"> · {stats.failed} com falha</strong>}
          {owner ? ` · ${owner}` : ''}
        </span>
        {manage && (
          <span className="rule-tools">
            <button type="button" className="icon-btn" aria-label={'Editar ' + rule.name} title="Editar" onClick={onEdit}><Pencil size={15} /></button>
            <button type="button" className="icon-btn" aria-label={'Duplicar ' + rule.name} title="Duplicar" onClick={onDuplicate}><Copy size={15} /></button>
            <button type="button" className="icon-btn" aria-label={'Excluir ' + rule.name} title={stats.runs ? 'Já executou: pause em vez de excluir' : 'Excluir'} onClick={onDelete}><Trash2 size={15} /></button>
          </span>
        )}
      </footer>
    </article>
  );
}

