'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Copy, MoreVertical, Pencil, Play, Plus, SlidersHorizontal, Trash2, Workflow, X } from 'lucide-react';
import { useSession, useNotify } from '@/components/providers';
import { useList, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { PageHeader, Button, DataState, EmptyState, Badge, ConfirmDialog, Popover, SearchInput } from '@/components/ui';
import { Card, Tabs, Toolbar, ToolbarEnd } from '@/components/blocks';
import { ACTIONS, BRANCH_LABEL, EVENTS, RECIPES, RUN_STATUS, countSteps, stepsOf } from '@/components/automations/model';
import { eventIcon, isInstagram } from '@/components/automations/icons';
import { searchMatch } from '@/lib/format';
import type { Row } from '@/lib/types';

const dateTime = (iso: string) => new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
const shortDate = (iso?: string | null) => iso ? new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: 'short', year: '2-digit', hour: '2-digit', minute: '2-digit' }).replace('.', '') : '—';
const SORTS: Record<string, { label: string; compare: (a: Row, b: Row) => number }> = {
  recent: { label: 'Mais recentes', compare: (a, b) => String(b.created_at).localeCompare(String(a.created_at)) },
  name: { label: 'Nome', compare: (a, b) => a.name.localeCompare(b.name, 'pt-BR') },
  runs: { label: 'Mais execuções', compare: (a, b) => (b.stats?.runs || 0) - (a.stats?.runs || 0) },
};
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
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [eventFilter, setEventFilter] = useState('');
  const [sort, setSort] = useState('recent');
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
  const activeFilters = [statusFilter, eventFilter].filter(Boolean).length;
  const visibleRules = ruleList
    .filter((r) => (!statusFilter || (statusFilter === 'active') === Boolean(r.active)) && (!eventFilter || r.event === eventFilter))
    .filter((r) => searchMatch(search, [r.name, EVENTS[r.event]?.label, ...stepsOf(r).map((step) => step.title || step.content || step.tag)]))
    .sort(SORTS[sort].compare);

  const visibleRuns = (runs.data || []).filter((r) => (!runStatus || r.status === runStatus) && (!runRule || r.rule_id === runRule));
  const visibleJobs = (jobs.data || []).filter((j) => !jobStatus || j.status === jobStatus);

  return (
    <div className="page automations-page">
      <PageHeader title="Automações">
        {manage && (
          <>
            <Link className="btn btn-primary" href="/automacoes/nova"><Plus size={17} /> Nova automação</Link>
          </>
        )}
      </PageHeader>

      <Toolbar>
        <Tabs label="Automações" value={tab} onChange={setTab} items={[
          { value: 'rules', label: <>Automações <span className="tab-count">{ruleList.length}</span></> },
          { value: 'runs', label: <>Execuções{failures > 0 && <span className="tab-badge">{failures}</span>}</> },
          { value: 'jobs', label: <>Etapas agendadas{pendingJobs > 0 && <span className="tab-count">{pendingJobs}</span>}</> },
        ]} />
        {tab === 'rules' && <>
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar automações" />
          <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" panelClassName="filter-panel"
            badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
            <label className="field"><span>Status</span>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">Ativas e inativas</option><option value="active">Ativas</option><option value="inactive">Inativas</option>
              </select></label>
            <label className="field"><span>Gatilho</span>
              <select value={eventFilter} onChange={(e) => setEventFilter(e.target.value)}>
                <option value="">Todos os gatilhos</option>{Object.entries(EVENTS).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}
              </select></label>
          </>}</Popover>
          {(search || activeFilters > 0) && <Button variant="ghost" onClick={() => { setSearch(''); setStatusFilter(''); setEventFilter(''); }}><X size={14} />Limpar</Button>}
          <ToolbarEnd>
            <label className="sort-select"><span className="muted">Ordenar</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)}>{Object.entries(SORTS).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}</select>
            </label>
          </ToolbarEnd>
        </>}
        {tab === 'jobs' && manage && <ToolbarEnd>
          <Button variant="soft" disabled={busy} onClick={() => act(async () => { const result = await post<{ items: unknown[] }>('/automations/process', {}); notify(result.items.length === 1 ? '1 etapa processada.' : `${result.items.length} etapas processadas.`); })}>
            <Play size={15} /> Processar pendentes
          </Button>
        </ToolbarEnd>}
      </Toolbar>

      {tab === 'rules' ? (
        <DataState loading={rules.isLoading} error={rules.error}>
          {!ruleList.length ? (
            <Card className="card-body automations-empty">
              <EmptyState icon={<Workflow />} title="Nenhuma automação" description="Automatize tarefas, retornos, mensagens e movimentações do funil a partir de eventos da conta. Comece por um modelo:" />
              {manage && (
                <div className="recipe-list">
                  {RECIPES.map((recipe, index) => <button type="button" key={recipe.name} className="recipe" onClick={() => router.push('/automacoes/nova?modelo=' + index)}><strong>{recipe.name}</strong><small>{ACTIONS[recipe.steps[0].kind]}</small></button>)}
                </div>
              )}
            </Card>
          ) : (
            <Card className="flow-list">
              {visibleRules.map((rule) => {
                const stats = rule.stats || { runs: 0, failed: 0, last_run_at: null };
                const steps = countSteps(stepsOf(rule));
                return (
                  <div key={rule.id} className={'flow-list-row' + (rule.active ? '' : ' paused')} onClick={() => manage && router.push('/automacoes/' + rule.id)}>
                    <span className={'flow-row-icon' + (isInstagram(rule.event) ? ' ig' : '')}>{eventIcon(rule.event)}</span>
                    <div className="flow-list-name">
                      <strong>{rule.name}</strong>
                      <span><span className="deal-chip">{EVENTS[rule.event]?.label || rule.event}</span><small>{steps} {steps === 1 ? 'passo' : 'passos'}</small></span>
                    </div>
                    <div className="flow-list-stat"><strong>{shortDate(rule.created_at)}</strong><small>Criada</small></div>
                    <div className="flow-list-stat"><strong>{shortDate(stats.last_run_at)}</strong><small>Última execução</small></div>
                    <div className="flow-list-stat"><strong>{stats.runs}{stats.failed > 0 && <em className="text-danger"> · {stats.failed} com falha</em>}</strong><small>Execuções</small></div>
                    <label className="flow-active" onClick={(e) => e.stopPropagation()}>
                      <button type="button" role="switch" aria-checked={rule.active} aria-label={(rule.active ? 'Desativar ' : 'Ativar ') + rule.name} className={'switch' + (rule.active ? ' on' : '')}
                        disabled={!manage || busy} onClick={() => act(async () => { await patch('/automations/' + rule.id, { active: !rule.active }); }, rule.active ? 'Automação pausada.' : 'Automação ativada.')}><span /></button>
                      {rule.active ? 'Ativa' : 'Inativa'}
                    </label>
                    {manage && <div onClick={(e) => e.stopPropagation()}>
                      <Popover label="" ariaLabel={'Mais ações para ' + rule.name} icon={<MoreVertical size={16} />} variant="ghost" align="end" panelClassName="menu-panel row-menu">{(close) => <>
                        <button type="button" onClick={() => { close(); router.push('/automacoes/' + rule.id); }}><Pencil size={15} />Editar</button>
                        <button type="button" onClick={() => { close(); router.push('/automacoes/nova?copiar=' + rule.id); }}><Copy size={15} />Duplicar</button>
                        <button type="button" className="danger" onClick={() => { close(); setDeleting(rule); }}><Trash2 size={15} />Excluir</button>
                      </>}</Popover>
                    </div>}
                  </div>
                );
              })}
              {!visibleRules.length && <EmptyState title="Nenhuma automação encontrada" description="Ajuste a busca ou os filtros." />}
            </Card>
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
                      <td>{job.action.kind === 'branch' ? BRANCH_LABEL : ACTIONS[job.action.kind]}{job.action.title ? ': ' + job.action.title : ''}{job.action.tag ? ': ' + job.action.tag : ''}</td>
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

      <ConfirmDialog open={!!deleting} onClose={() => setDeleting(null)} title="Excluir automação?"
        description={deleting?.stats?.runs ? 'Esta automação já foi executada e mantém histórico, então não pode ser excluída. Pause-a para interromper novos disparos.' : `A automação “${deleting?.name || ''}” será removida.`}
        onConfirm={async () => { if (deleting?.stats?.runs) throw new Error('Pause a automação em vez de excluir.'); await remove('/automations/' + deleting!.id); await refreshAll(); setDeleting(null); notify('Automação excluída.'); }} />
    </div>
  );
}
