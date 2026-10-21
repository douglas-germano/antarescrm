'use client';
import { useState } from 'react';
import { Plus, Pencil, Trash2, CheckSquare } from 'lucide-react';
import { useList, post, patch, remove, refreshAll } from '@/lib/api';
import { day, today, rowOptions, opts, priorities, taskStatuses, searchMatch } from '@/lib/format';
import type { Field, Row } from '@/lib/types';
import { useSession, useNotify } from '@/components/providers';
import { Button, Badge, PageHeader, EmptyState, DataState, SearchInput, FormDialog, ConfirmDialog } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { Card, Tabs, Toolbar } from '@/components/blocks';

export default function TasksPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const [view, setView] = useState('open');
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState('');
  const tasks = useList('/tasks' + (mine ? '?mine=true' : ''));
  const contacts = useList('/contacts');
  const users = useList('/users');
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [deleting, setDeleting] = useState<Row | null>(null);
  const contactName = (id?: string) => (contacts.data || []).find((c) => c.id === id)?.name;
  const userName = (id?: string) => (users.data || []).find((u) => u.id === id)?.name;
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
  const rows = (tasks.data || [])
    .filter((t) => (view === 'open' ? ['todo', 'doing'].includes(t.status) : ['done', 'cancelled'].includes(t.status)))
    .filter((t) => searchMatch(search, [t.title, contactName(t.contact_id), contacts.data?.find((c) => c.id === t.contact_id)?.phone]));
  async function toggle(task: Row) {
    try {
      await patch('/tasks/' + task.id, { status: task.status === 'done' ? 'todo' : 'done' });
      await refreshAll();
    } catch (e) {
      notify((e as Error).message, 'error');
    }
  }
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
            { value: 'open', label: 'Abertas' },
            { value: 'closed', label: 'Encerradas' },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Buscar tarefa ou contato" />
        <label className="checkbox-label">
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          Somente minhas
        </label>
      </Toolbar>
      <Card fill>
        <DataState loading={tasks.isLoading} error={tasks.error}>
          {rows.length ? (
            <PagedTable
              rows={rows}
              header={
                <tr>
                  <th />
                  <th>Tarefa</th>
                  <th>Contato</th>
                  <th>Responsável</th>
                  <th>Prazo</th>
                  <th>Prioridade</th>
                  <th className="text-right">Ações</th>
                </tr>
              }
              renderRow={(t) => (
                <tr key={t.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={'Concluir ' + t.title}
                      checked={t.status === 'done'}
                      onChange={() => void toggle(t)}
                    />
                  </td>
                  <td>
                    <strong>{t.title}</strong>
                  </td>
                  <td>{contactName(t.contact_id) || '—'}</td>
                  <td>{userName(t.assignee_id) || '—'}</td>
                  <td className={t.due_date && t.due_date < t0 && ['todo', 'doing'].includes(t.status) ? 'due-bad' : ''}>
                    {day(t.due_date)}
                  </td>
                  <td>
                    <Badge value={t.priority} />
                  </td>
                  <td>
                    <div className="row-actions">
                      <Button variant="ghost" aria-label={'Editar ' + t.title} onClick={() => setEditing(t)}>
                        <Pencil size={16} />
                      </Button>
                      <Button variant="ghost" aria-label={'Excluir ' + t.title} onClick={() => setDeleting(t)}>
                        <Trash2 size={16} />
                      </Button>
                    </div>
                  </td>
                </tr>
              )}
            />
          ) : (
            <EmptyState
              icon={<CheckSquare />}
              title={view === 'open' ? 'Nada pendente' : 'Nenhuma tarefa encerrada'}
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
