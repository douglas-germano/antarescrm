'use client';
import Link from 'next/link';
import { useState } from 'react';
import { Check, CalendarDays, FileText, Handshake, CheckSquare } from 'lucide-react';
import { patch, refreshAll } from '@/lib/api';
import { brl, day, hour, kinds } from '@/lib/format';
import { Button } from '@/components/ui';
import { useNotify } from '@/components/providers';
import type { Row } from '@/lib/types';
export function ContactTimeline({ data }: { data?: Row }) {
  const { notify } = useNotify();
  const [busy, setBusy] = useState<string | null>(null);
  const entries = [
    ...(data?.activities || []).map((row: Row) => ({ ...row, type: 'activity', date: row.scheduled_at, subtitle: kinds[row.kind] || 'Atividade', icon: row.kind === 'note' ? FileText : CalendarDays })),
    ...(data?.tasks || []).map((row: Row) => ({ ...row, type: 'task', date: row.due_date || row.created_at, subtitle: 'Tarefa', icon: CheckSquare })),
    ...(data?.opportunities || []).map((row: Row) => ({ ...row, type: 'deal', date: row.updated_at || row.created_at, subtitle: 'Negócio · ' + brl(row.amount), icon: Handshake })),
  ].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
  if (!entries.length) return <p className="muted">Nenhuma interação registrada.</p>;
  return <ol className="contact-timeline">
    {entries.map(entry => <li key={entry.type + entry.id}>
      <span className="timeline-symbol"><entry.icon size={16} /></span>
      <div className="timeline-copy"><small>{entry.subtitle}{entry.date ? ' · ' + day(entry.date) : ''}{entry.type === 'activity' && entry.date ? ' às ' + hour(entry.date) : ''}</small>
        <strong>{entry.type === 'deal' ? <Link href={'/crm?opportunity=' + entry.id}>{entry.title}</Link> : entry.title}</strong>
        {entry.notes && <p>{entry.notes}</p>}
        <span className="timeline-status">{entry.status === 'pending' ? 'Agendado' : entry.status === 'completed' || entry.status === 'done' ? 'Concluído' : entry.status === 'cancelled' ? 'Cancelado' : entry.status === 'won' ? 'Ganho' : entry.status === 'lost' ? 'Perdido' : entry.status === 'open' ? 'Em aberto' : 'Pendente'}</span>
      </div>
      {entry.type === 'activity' && entry.status === 'pending' && <Button variant="ghost" disabled={busy === entry.id} aria-label={'Concluir ' + entry.title} onClick={async () => {
        setBusy(entry.id);
        try { await patch('/activities/' + entry.id, { status: 'completed' }); await refreshAll(); notify('Atividade concluída.'); }
        catch (error) { notify((error as Error).message, 'error'); }
        finally { setBusy(null); }
      }}><Check size={15} />Concluir</Button>}
    </li>)}
  </ol>;
}
