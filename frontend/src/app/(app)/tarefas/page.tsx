'use client';
import { useEffect, useState } from 'react';
import { Plus, Pencil, Trash2, CheckSquare, Check, SlidersHorizontal, X, CalendarDays } from 'lucide-react';
import { useData, useList, usePage, post, patch, remove, refreshAll } from '@/lib/api';
import { day, today, initials, rowOptions, opts, priorities, taskStatuses } from '@/lib/format';
import type { Field, Task, User } from '@/lib/types';
import { useSession, useNotify } from '@/components/providers';
import { Button, PageHeader, EmptyState, DataState, SearchInput, FormDialog, ConfirmDialog, Popover } from '@/components/ui';
import { Pager } from '@/components/fit';
import { Card, Tabs, Toolbar } from '@/components/blocks';

const WEEKDAYS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
const dayIndex = (value: string) => Date.UTC(+value.slice(0, 4), +value.slice(5, 7) - 1, +value.slice(8, 10)) / 86400000;
/** "Hoje", "Amanhã", "Ontem", the weekday within the coming week, otherwise the short date. */
function relativeDay(value: string, t0: string) {
  const diff = dayIndex(value) - dayIndex(t0);
  if (diff === 0) return 'Hoje';
  if (diff === 1) return 'Amanhã';
  if (diff === -1) return 'Ontem';
  if (diff > 1 && diff < 7) return WEEKDAYS[new Date(value + 'T12:00:00Z').getUTCDay()];
  return value.slice(8, 10) + '/' + value.slice(5, 7);
}
const GROUPS = [
  { key: 'overdue', label: 'Atrasadas' },
  { key: 'today', label: 'Hoje' },
  { key: 'week', label: 'Próximos 7 dias' },
  { key: 'later', label: 'Depois' },
  { key: 'none', label: 'Sem prazo' },
] as const;
function groupOf(task: Task, t0: string) {
  if (!task.due_date) return 'none';
  const diff = dayIndex(task.due_date) - dayIndex(t0);
  return diff < 0 ? 'overdue' : diff === 0 ? 'today' : diff <= 7 ? 'week' : 'later';
}

export default function TasksPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const [view, setView] = useState('open');
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState('');
  const [priority, setPriority] = useState('');
  const [completing, setCompleting] = useState<string[]>([]);
  const tasks = usePage<Task>('/tasks?' + new URLSearchParams({ mine: String(mine), view, search, priority }));
  const openCount = useData<{ total: number }>('/tasks?' + new URLSearchParams({ mine: String(mine), view: 'open', per_page: '1' }));
  const activeFilters = [mine, priority].filter(Boolean).length;
  const users = useList<User>('/users');
  const [editing, setEditing] = useState<Task | null | undefined>();
  const [deleting, setDeleting] = useState<Task | null>(null);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('new') === 'true') setEditing(null);
  }, []);
  const fields: Field[] = [
    { name: 'title', label: 'Tarefa', required: true },
    { name: 'due_date', label: 'Prazo', type: 'date' },
    { name: 'priority', label: 'Prioridade', type: 'select', options: opts(priorities), defaultValue: 'medium' },
    { name: 'status', label: 'Situação', type: 'select', options: taskStatuses, defaultValue: 'todo' },
    { name: 'assignee_id', label: 'Responsável', type: 'select', options: rowOptions((users.data || []).filter((u) => u.active)) },
    { name: 'contact_id', label: 'Contato', type: 'contact' },
    { name: 'description', label: 'Detalhes', type: 'textarea', wide: true },
  ];
  const t0 = today();
  const rows = tasks.data?.items || [];
  async function toggle(task: Task) {
    const finishing = task.status !== 'done';
    // A short strike-through before the row leaves the open list, so the click visibly worked.
    if (finishing) { setCompleting((ids) => [...ids, task.id]); await new Promise((resolve) => setTimeout(resolve, 350)); }
    try {
      await patch('/tasks/' + task.id, { status: finishing ? 'done' : 'todo' });
      await refreshAll();
    } catch (e) {
      notify((e as Error).message, 'error');
    } finally {
      setCompleting((ids) => ids.filter((id) => id !== task.id));
    }
  }
  const renderTask = (t: Task) => {
    const done = t.status === 'done' || completing.includes(t.id);
    const late = !done && t.due_date && t.due_date < t0;
    return (
      <li key={t.id} className={'task-row' + (done ? ' task-done' : '')} onClick={() => setEditing(t)}>
        <button type="button" className="task-check" aria-pressed={done} aria-label={(t.status === 'done' ? 'Reabrir ' : 'Concluir ') + t.title}
          data-tip={t.status === 'done' ? 'Reabrir' : 'Concluir'} data-tip-align="start"
          onClick={(e) => { e.stopPropagation(); void toggle(t); }}><Check size={12} strokeWidth={3} /></button>
        <div className="task-main">
          <strong>{t.title}</strong>
          {t.contact_name && <small>{t.contact_name}</small>}
        </div>
        {['high', 'urgent'].includes(t.priority) && <span className={'deal-chip ' + (t.priority === 'urgent' ? 'danger' : 'warn')}>{priorities[t.priority]}</span>}
        {t.due_date && <span className={'task-due' + (late ? ' late' : '')} data-tip={'Prazo: ' + day(t.due_date)} data-tip-align="end"><CalendarDays size={12} />{relativeDay(t.due_date, t0)}</span>}
        {t.assignee_name && <span className="owner-avatar" data-tip={t.assignee_name} data-tip-align="end" aria-label={'Responsável: ' + t.assignee_name}>{initials(t.assignee_name)}</span>}
        <div className="row-actions task-actions" onClick={(e) => e.stopPropagation()}>
          <Button variant="ghost" aria-label={'Editar ' + t.title} data-tip="Editar" data-tip-align="end" onClick={() => setEditing(t)}><Pencil size={15} /></Button>
          <Button variant="ghost" aria-label={'Excluir ' + t.title} data-tip="Excluir" data-tip-align="end" onClick={() => setDeleting(t)}><Trash2 size={15} /></Button>
        </div>
      </li>
    );
  };
  return (
    <div className="page">
      <PageHeader compact title="Tarefas">
        <Button onClick={() => setEditing(null)}>
          <Plus size={17} /> Nova tarefa
        </Button>
      </PageHeader>
      <Toolbar>
        <Tabs
          label="Situação das tarefas"
          value={view}
          onChange={setView}
          items={[
            { value: 'open', label: <>Abertas <span className="tab-count">{openCount.data?.total ?? '…'}</span></> },
            { value: 'closed', label: 'Encerradas' },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Buscar tarefa ou contato" />
        <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" panelClassName="filter-panel"
          badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
          <label className="field"><span>Prioridade</span>
            <select value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="">Todas as prioridades</option>
              {Object.entries(priorities).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
          <label className="checkbox-label"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Somente minhas</label>
        </>}</Popover>
        {(search || activeFilters > 0) && <Button variant="ghost" onClick={() => { setSearch(''); setPriority(''); setMine(false); }}><X size={14} />Limpar</Button>}
      </Toolbar>
      <Card fill={rows.length > 0} className="task-card">
        <DataState loading={tasks.isLoading} error={tasks.error}>
          {rows.length ? <>
            <div className="task-scroll">
              {view === 'open' ? GROUPS.map((group) => {
                const items = rows.filter((t) => groupOf(t, t0) === group.key);
                return items.length ? (
                  <section key={group.key} className={'task-group task-group-' + group.key}>
                    <h3>{group.label} <span className="tab-count">{items.length}</span></h3>
                    <ul className="task-list">{items.map(renderTask)}</ul>
                  </section>
                ) : null;
              }) : <ul className="task-list">{rows.map(renderTask)}</ul>}
            </div>
            {tasks.data && tasks.data.pages > 1 && <Pager page={tasks.page - 1} pages={tasks.data.pages} onChange={(page) => tasks.setPage(page + 1)} total={tasks.data.total}
              from={(tasks.page - 1) * tasks.size + 1} to={Math.min(tasks.data.total, tasks.page * tasks.size)} />}
          </> : (
            <EmptyState
              icon={<CheckSquare />}
              title={search || activeFilters ? 'Nenhuma tarefa encontrada' : view === 'open' ? 'Tudo em dia' : 'Nenhuma tarefa encerrada'}
              description={search || activeFilters ? 'Ajuste a busca ou os filtros.' : view === 'open' ? 'Crie uma tarefa para não esquecer o próximo passo com um cliente.' : undefined}
              action={!search && !activeFilters && view === 'open' ? <Button onClick={() => setEditing(null)}><Plus size={16} />Nova tarefa</Button> : undefined}
            />
          )}
        </DataState>
      </Card>
      <FormDialog
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
        title={editing ? 'Editar tarefa' : 'Nova tarefa'}
        fields={fields}
        initial={editing || { assignee_id: user?.id }}
        onSubmit={async (data) => {
          const body = {
            ...data,
            due_date: data.due_date || null,
            assignee_id: data.assignee_id || null,
            contact_id: data.contact_id || null,
            description: data.description || null,
          };
          await (editing ? patch('/tasks/' + editing.id, body) : post('/tasks', body));
          await refreshAll();
          setEditing(undefined);
          notify('Tarefa salva.');
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Excluir tarefa?"
        description={`“${deleting?.title || ''}” será removida definitivamente.`}
        onConfirm={async () => {
          await remove('/tasks/' + deleting!.id);
          await refreshAll();
          notify('Tarefa excluída.');
          setDeleting(null);
        }}
      />
    </div>
  );
}
