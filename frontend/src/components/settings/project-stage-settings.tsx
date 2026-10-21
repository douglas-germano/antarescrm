'use client';
import { useState } from 'react';
import { ArrowDown, ArrowUp, Flag, Pencil, Plus, Trash2 } from 'lucide-react';
import { useData, post, patch, remove, refreshAll } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, ConfirmDialog, DataState, FormDialog } from '@/components/ui';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import type { Row } from '@/lib/types';

const PALETTE = [
  { value: '#e60000', label: 'Vermelho' }, { value: '#25282b', label: 'Grafite' }, { value: '#6b6e71', label: 'Cinza' }, { value: '#b80000', label: 'Vinho' },
  { value: '#c77d00', label: 'Âmbar' }, { value: '#2e7d52', label: 'Verde' }, { value: '#2f6f8f', label: 'Azul' },
];

/** Steps every client project moves through; the final step completes the project. */
export function ProjectStageSettings() {
  const { notify } = useNotify();
  const stages = useData<{ items: Row[] }>('/project-stages');
  const list = stages.data?.items || [];
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [deleting, setDeleting] = useState<Row | null>(null);

  async function swap(index: number, direction: -1 | 1) {
    const a = list[index], b = list[index + direction];
    if (!b) return;
    try {
      await patch('/project-stages/' + a.id, { position: b.position });
      await patch('/project-stages/' + b.id, { position: a.position });
      await refreshAll();
    } catch (e) { notify((e as Error).message, 'error'); }
  }

  return (
    <Card as="section">
      <CardHeader title="Etapas dos projetos" description="O caminho de cada projeto de cliente. Ao chegar na etapa marcada como final, o projeto é concluído." />
      <DataState loading={stages.isLoading} error={stages.error}>
        <CardBody className="stack">
          {list.map((s, index) => (
            <div key={s.id} className="stage-setting-row">
              <span className="kanban-dot" style={{ background: s.color }} />
              <strong className="stage-setting-name">{s.name}</strong>
              {s.is_final && <small className="deal-chip"><Flag size={11} /> Etapa final</small>}
              <div className="row-actions">
                <Button variant="ghost" aria-label={'Subir ' + s.name} disabled={index === 0} onClick={() => swap(index, -1)}><ArrowUp size={16} /></Button>
                <Button variant="ghost" aria-label={'Descer ' + s.name} disabled={index === list.length - 1} onClick={() => swap(index, 1)}><ArrowDown size={16} /></Button>
                <Button variant="ghost" aria-label={'Editar etapa ' + s.name} onClick={() => setEditing(s)}><Pencil size={16} /></Button>
                <Button variant="ghost" aria-label={'Excluir etapa ' + s.name} onClick={() => setDeleting(s)}><Trash2 size={16} /></Button>
              </div>
            </div>
          ))}
          <div><Button onClick={() => setEditing(null)}><Plus size={16} /> Adicionar etapa</Button></div>
        </CardBody>
      </DataState>
      <FormDialog open={editing !== undefined} onClose={() => setEditing(undefined)} title={editing ? 'Editar etapa' : 'Nova etapa'}
        fields={[
          { name: 'name', label: 'Nome da etapa', required: true },
          { name: 'color', label: 'Cor', type: 'select', required: true, options: [...PALETTE, ...(editing && !PALETTE.some((c) => c.value === editing.color) ? [{ value: editing.color, label: 'Personalizada (' + editing.color + ')' }] : [])] },
          { name: 'is_final', label: 'Etapa final (conclui o projeto)', type: 'checkbox' },
        ]}
        initial={editing || { color: '#25282b', is_final: false }}
        onSubmit={async (data) => {
          if (editing) await patch('/project-stages/' + editing.id, data);
          else await post('/project-stages', { ...data, position: list.length });
          await refreshAll(); notify('Etapa salva.');
        }} />
      <ConfirmDialog open={!!deleting} onClose={() => setDeleting(null)} title="Excluir etapa?" description={`A etapa ${deleting?.name || ''} só pode ser excluída se nenhum projeto estiver nela.`}
        onConfirm={async () => { await remove('/project-stages/' + deleting!.id); await refreshAll(); setDeleting(null); notify('Etapa excluída.'); }} />
    </Card>
  );
}
