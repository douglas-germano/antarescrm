'use client';
import { useState } from 'react';
import { Play, Plus, Workflow } from 'lucide-react';
import { useSession, useNotify } from '@/components/providers';
import { useList, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { PageHeader, Button, DataState, EmptyState, Badge, ConfirmDialog, StatCard } from '@/components/ui';
import { Card, Tabs } from '@/components/blocks';
import { RuleCard } from '@/components/automations/RuleCard';
import { RuleEditor, type RuleDraft } from '@/components/automations/RuleEditor';
import { ACTIONS, RECIPES, RUN_STATUS, stepsOf } from '@/components/automations/model';
import type { Row } from '@/lib/types';

const dateTime = (iso: string) => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
const statusBadge = (status: string) => <Badge value={RUN_STATUS[status]?.badge || 'skipped'} label={RUN_STATUS[status]?.label || status} />;

export default function AutomationsPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const rules = useList('/automations');
  const runs = useList('/automations/runs');
  const jobs = useList('/automations/jobs');
  const staff = useList('/users');
  const templates = useList('/message-templates');
  const stages = useData<{ items: Row[] }>('/pipeline/stages');
  const [tab, setTab] = useState('rules');
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [runStatus, setRunStatus] = useState('');
  const [runRule, setRunRule] = useState('');
  const [jobStatus, setJobStatus] = useState('pending');

  const ruleList = rules.data || [];
  const lookups = {
    template: (id?: string) => templates.data?.find((t) => t.id === id)?.name,
    stage: (id?: string) => stages.data?.items.find((s) => s.id === id)?.name,
  };
  const ruleName = (id?: string) => ruleList.find((r) => r.id === id)?.name || 'Automação removida';
  const pendingJobs = (jobs.data || []).filter((j) => j.status === 'pending').length;
  const failures = (runs.data || []).filter((r) => r.status === 'failed').length;
  const activeCount = ruleList.filter((r) => r.active).length;

  async function act(work: () => Promise<void>, success?: string) {
    setBusy(true);
    try {
      await work();
      await refreshAll();
      if (success) notify(success);
    } catch (error) {
      notify((error as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }
  const duplicate = (rule: Row) => setDraft({ ...rule, id: undefined, name: rule.name + ' (cópia)', active: false, steps: stepsOf(rule) });
  const fromRecipe = (recipe: (typeof RECIPES)[number]) => setDraft({ name: recipe.name, event: recipe.event, steps: recipe.steps, conditions: recipe.conditions });

  const visibleRuns = (runs.data || []).filter((r) => (!runStatus || r.status === runStatus) && (!runRule || r.rule_id === runRule));
  const visibleJobs = (jobs.data || []).filter((j) => !jobStatus || j.status === jobStatus);

  return (
    <div className="page automations-page">
      <PageHeader title="Automações">
        {manage && (
          <>
            <Button variant="secondary" disabled={busy} onClick={() => act(async () => { const result = await post('/automations/process', {}); notify(`${result.items.length} etapa(s) processada(s).`); })}>
              <Play size={15} /> Processar pendentes
            </Button>
            <Button onClick={() => setDraft({})}><Plus size={17} /> Nova automação</Button>
          </>
        )}
      </PageHeader>

      <div className="stat-grid">
        <StatCard label="Automações ativas" value={activeCount} detail={`${ruleList.length} no total`} />
        <StatCard label="Execuções" value={(runs.data || []).length} detail="Registradas na conta" />
        <StatCard label="Etapas pendentes" value={pendingJobs} detail="Aguardando o horário" />
        <StatCard label="Falhas" value={failures} detail={failures ? 'Veja em Execuções' : 'Nenhuma falha'} />
      </div>

      <Tabs variant="line" label="Automações" value={tab} onChange={setTab} items={[
        { value: 'rules', label: 'Regras' },
        { value: 'runs', label: <>Execuções{failures > 0 && <span className="tab-badge">{failures}</span>}</> },
        { value: 'jobs', label: <>Etapas agendadas{pendingJobs > 0 && <span className="tab-count">{pendingJobs}</span>}</> },
      ]} />

      {tab === 'rules' ? (
        <DataState loading={rules.isLoading} error={rules.error}>
          {!ruleList.length ? (
            <Card className="card-body automations-empty">
              <EmptyState icon={<Workflow />} title="Nenhuma automação" description="Automatize tarefas, retornos, mensagens e movimentações do funil a partir de eventos da conta. Comece por um modelo:" />
              {manage && (
                <div className="recipe-list">
                  {RECIPES.map((recipe) => <button type="button" key={recipe.name} className="recipe" onClick={() => fromRecipe(recipe)}><strong>{recipe.name}</strong><small>{ACTIONS[recipe.steps[0].kind]}</small></button>)}
                </div>
              )}
            </Card>
          ) : (
            <div className="rule-grid">
              {ruleList.map((rule) => (
                <RuleCard key={rule.id} rule={rule} manage={manage} lookups={lookups} owner={staff.data?.find((u) => u.id === rule.assignee_id)?.name}
                  onToggle={(active) => act(async () => { await patch('/automations/' + rule.id, { active }); }, active ? 'Automação ativada.' : 'Automação pausada.')}
                  onEdit={() => setDraft(rule)} onDuplicate={() => duplicate(rule)} onDelete={() => setDeleting(rule)} />
              ))}
            </div>
          )}
        </DataState>
      ) : tab === 'runs' ? (
        <DataState loading={runs.isLoading} error={runs.error}>
          <Card as="section" className="card-fill">
            <div className="card-head auto-filters">
              <select aria-label="Situação" value={runStatus} onChange={(e) => setRunStatus(e.target.value)}>
                <option value="">Todas as situações</option>
                {['queued', 'completed', 'failed', 'skipped', 'cancelled'].map((s) => <option key={s} value={s}>{RUN_STATUS[s].label}</option>)}
              </select>
              <select aria-label="Automação" value={runRule} onChange={(e) => setRunRule(e.target.value)}>
                <option value="">Todas as automações</option>
                {ruleList.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
            <div className="table-wrap fill">
              <table className="data-table">
                <thead><tr><th>Quando</th><th>Automação</th><th>Contato</th><th>Situação</th><th>Detalhe</th>{manage && <th className="text-right">Ações</th>}</tr></thead>
                <tbody>
                  {visibleRuns.map((run) => (
                    <tr key={run.id}>
                      <td>{dateTime(run.created_at)}</td>
                      <td><strong>{ruleName(run.rule_id)}</strong></td>
                      <td>{run.contact_name || '—'}</td>
                      <td>{statusBadge(run.status)}</td>
                      <td className="muted">{run.detail}</td>
                      {manage && <td className="text-right">{run.status === 'queued' && <Button variant="secondary" disabled={busy} onClick={() => act(async () => { await post(`/automations/runs/${run.id}/cancel`, {}); }, 'Execução cancelada.')}>Cancelar</Button>}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visibleRuns.length && <EmptyState title="Nenhuma execução" description="As execuções aparecem aqui quando um gatilho dispara uma automação." />}
            </div>
          </Card>
        </DataState>
      ) : (
        <DataState loading={jobs.isLoading} error={jobs.error}>
          <Card as="section" className="card-fill">
            <div className="card-head auto-filters">
              <select aria-label="Situação da etapa" value={jobStatus} onChange={(e) => setJobStatus(e.target.value)}>
                <option value="">Todas as situações</option>
                {['pending', 'completed', 'failed', 'skipped', 'cancelled'].map((s) => <option key={s} value={s}>{RUN_STATUS[s].label}</option>)}
              </select>
            </div>
            <div className="table-wrap fill">
              <table className="data-table">
                <thead><tr><th>Agendada para</th><th>Automação</th><th>Contato</th><th>Ação</th><th>Situação</th>{manage && <th className="text-right">Ações</th>}</tr></thead>
                <tbody>
                  {visibleJobs.map((job) => (
                    <tr key={job.id}>
                      <td>{dateTime(job.scheduled_at)}</td>
                      <td><strong>{ruleName(job.rule_id)}</strong><small>Etapa {job.position + 1}</small></td>
                      <td>{job.contact_name || '—'}</td>
                      <td>{ACTIONS[job.action.kind]}{job.action.title ? ': ' + job.action.title : ''}{job.action.tag ? ': ' + job.action.tag : ''}</td>
                      <td>{statusBadge(job.status)}{job.detail && job.status !== 'pending' && <small>{job.detail}</small>}</td>
                      {manage && (
                        <td className="text-right">
                          {job.status === 'pending' && <Button variant="secondary" disabled={busy} onClick={() => act(async () => { await post(`/automations/jobs/${job.id}/cancel`, {}); }, 'Etapa cancelada.')}>Cancelar</Button>}
                          {(job.status === 'failed' || job.status === 'skipped') && <Button variant="secondary" disabled={busy} onClick={() => act(async () => { await post(`/automations/jobs/${job.id}/retry`, {}); }, 'Etapa reagendada.')}>Tentar novamente</Button>}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visibleJobs.length && <EmptyState title="Nenhuma etapa" description="As etapas agendadas das automações aparecem aqui." />}
            </div>
          </Card>
        </DataState>
      )}

      <RuleEditor draft={draft} onClose={() => setDraft(null)} staff={staff.data || []} templates={templates.data || []} stages={stages.data?.items || []} />
      <ConfirmDialog open={!!deleting} onClose={() => setDeleting(null)} title="Excluir automação?"
        description={deleting?.stats?.runs ? 'Esta automação já foi executada e mantém histórico, então não pode ser excluída. Pause-a para interromper novos disparos.' : `A automação “${deleting?.name || ''}” será removida.`}
        onConfirm={async () => { if (deleting?.stats?.runs) throw new Error('Pause a automação em vez de excluir.'); await remove('/automations/' + deleting!.id); await refreshAll(); setDeleting(null); notify('Automação excluída.'); }} />
    </div>
  );
}
