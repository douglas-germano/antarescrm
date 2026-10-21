'use client';
import { useEffect, useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { useData, post, patch, remove, refreshAll } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { Button, DataState, FormDialog, ConfirmDialog } from '@/components/ui';
import { Card, CardHeader } from '@/components/blocks';
import type { Row } from '@/lib/types';

/** Stage colours come from the brand palette: red, ink and a neutral/warm range that stays legible on the light board. */
const PALETTE = [
  { value: '#e60000', label: 'Vermelho' },
  { value: '#25282b', label: 'Grafite' },
  { value: '#6b6e71', label: 'Cinza' },
  { value: '#b80000', label: 'Vinho' },
  { value: '#c77d00', label: 'Âmbar' },
  { value: '#2e7d52', label: 'Verde' },
  { value: '#2f6f8f', label: 'Azul' },
];

/** Creation of pipelines and editing of their stages; the pipeline page itself only selects one. */
export function PipelineSettings() {
  const { user } = useSession();
  const { notify } = useNotify();
  const canCreate = ['owner', 'admin'].includes(user?.role || '');
  const pipelines = useData<{ items: Row[] }>('/pipelines');
  const [pipelineId, setPipelineId] = useState('');
  useEffect(() => {
    const items = pipelines.data?.items;
    if (items?.length && !items.some((p) => p.id === pipelineId)) setPipelineId(items[0].id);
  }, [pipelines.data, pipelineId]);
  const stages = useData<{ items: Row[] }>(pipelineId ? '/pipeline/stages?pipeline_id=' + pipelineId : null);
  const list = stages.data?.items || [];
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [deleting, setDeleting] = useState<Row | null>(null);
  return (
    <Card as="section">
      <CardHeader
        title="Funis de vendas"
        description="Crie funis e organize as etapas. Na página do funil você só escolhe qual visualizar."
        actions={
          <div className="header-actions">
            <select aria-label="Funil" value={pipelineId} onChange={(e) => setPipelineId(e.target.value)}>
              {pipelines.data?.items.map((p) => <option value={p.id} key={p.id}>{p.name}</option>)}
            </select>
            {canCreate && <Button variant="secondary" onClick={() => setCreating(true)}><Plus size={16} /> Novo funil</Button>}
          </div>
        }
      />
      <DataState loading={pipelines.isLoading || stages.isLoading} error={pipelines.error || stages.error}>
        <div className="card-body stack">
          {list.map((s) => (
            <div key={s.id} className="stage-setting-row">
              <span className="kanban-dot" style={{ background: s.color }} />
              <strong className="stage-setting-name">{s.name}</strong>
              <small className="muted">{s.probability !== null && s.probability !== undefined ? `${s.probability}% de chance · ` : ''}Ordem {s.position}</small>
              <div className="row-actions">
                <Button variant="ghost" aria-label={'Editar etapa ' + s.name} onClick={() => setEditing(s)}><Pencil size={16} /></Button>
                <Button variant="ghost" aria-label={'Excluir etapa ' + s.name} onClick={() => setDeleting(s)}><Trash2 size={16} /></Button>
              </div>
            </div>
          ))}
          {!list.length && <p className="muted">Este funil ainda não tem etapas.</p>}
          <div><Button onClick={() => setEditing(null)}><Plus size={16} /> Adicionar etapa</Button></div>
        </div>
      </DataState>
      <FormDialog
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
        title={editing ? 'Editar etapa' : 'Nova etapa'}
        fields={[
          { name: 'name', label: 'Nome da etapa', required: true },
          { name: 'position', label: 'Ordem', type: 'number', min: 0, max: 10000 },
          { name: 'probability', label: 'Chance de ganho (%)', type: 'number', min: 0, max: 100, emptyValue: null, help: 'Opcional. Usada na previsão ponderada do funil.' },
          { name: 'color', label: 'Cor da etapa', type: 'select', required: true,
            options: [...PALETTE, ...(editing && !PALETTE.some((c) => c.value === editing.color) ? [{ value: editing.color, label: 'Personalizada (' + editing.color + ')' }] : [])] },
        ]}
        initial={editing || { position: list.length, color: '#e60000', probability: '' }}
        onSubmit={async (data) => {
          await (editing ? patch('/pipeline/stages/' + editing.id, data) : post('/pipeline/stages', { ...data, pipeline_id: pipelineId === 'default' ? null : pipelineId }));
          await refreshAll();
          setEditing(undefined);
          notify('Etapa salva.');
        }}
      />
      <FormDialog
        open={creating}
        title="Novo funil de vendas"
        onClose={() => setCreating(false)}
        fields={[{ name: 'name', label: 'Nome do funil', required: true }]}
        onSubmit={async (body) => {
          const result = await post('/pipelines', body);
          await refreshAll();
          setPipelineId(result.id);
          setCreating(false);
          notify('Funil criado com as etapas iniciais.');
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Excluir etapa?"
        description={`A etapa ${deleting?.name || ''} só poderá ser excluída se não tiver negócios ou histórico vinculados.`}
        onConfirm={async () => {
          await remove('/pipeline/stages/' + deleting!.id);
          await refreshAll();
          setDeleting(null);
          notify('Etapa excluída.');
        }}
      />
    </Card>
  );
}
