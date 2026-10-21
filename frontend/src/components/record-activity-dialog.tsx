'use client';
import { FormDialog } from './ui';
import { useNotify, useSession } from './providers';
import { post, refreshAll } from '@/lib/api';
import { rowOptions, toLocalInput } from '@/lib/format';
import type { Field, Row } from '@/lib/types';

export type ActivityRecord = { label: string; contact_id?: string | null; company_id?: string | null; opportunity_id?: string | null; owner_id?: string | null };
export function RecordActivityDialog({ record, mode = 'follow_up', onClose, opportunities = [] }: {
  record: ActivityRecord | null; mode?: 'follow_up' | 'note'; onClose: () => void; opportunities?: Row[];
}) {
  const { user } = useSession();
  const { notify } = useNotify();
  const note = mode === 'note';
  const fields: Field[] = [
    { name: 'title', label: note ? 'Título da nota' : 'Próximo passo', required: true, wide: true },
    ...(!note ? [{ name: 'scheduled_at', label: 'Data e horário', type: 'datetime-local' as const, required: true, help: 'Horário local deste dispositivo.' }] : []),
    ...(!record?.opportunity_id && opportunities.length ? [{ name: 'opportunity_id', label: 'Vincular ao negócio', type: 'select' as const, options: rowOptions(opportunities, 'title') }] : []),
    { name: 'notes', label: note ? 'Anotação' : 'Contexto para o retorno', type: 'textarea', required: note, wide: true },
  ];
  return <FormDialog open={!!record} onClose={onClose} title={note ? 'Registrar nota' : 'Agendar retorno'} description={record?.label}
    fields={fields} submitLabel={note ? 'Salvar nota' : 'Agendar retorno'}
    initial={{ title: note ? '' : `Retorno · ${record?.label || ''}`.slice(0, 180), scheduled_at: toLocalInput(new Date(Date.now() + 86400000).toISOString()) }}
    onSubmit={async data => {
      await post('/activities', {
        title: data.title, notes: data.notes || null, kind: mode,
        scheduled_at: note ? new Date().toISOString() : data.scheduled_at,
        status: note ? 'completed' : 'pending',
        contact_id: record?.contact_id || null, company_id: record?.company_id || null,
        opportunity_id: record?.opportunity_id || data.opportunity_id || null,
        owner_id: record?.owner_id || user?.id || null,
      });
      await refreshAll();
      notify(note ? 'Nota registrada no histórico.' : 'Retorno agendado e incluído na agenda.');
    }} />;
}
