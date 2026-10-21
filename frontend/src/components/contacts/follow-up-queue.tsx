'use client';
import Link from 'next/link';
import { useState } from 'react';
import { ArrowUpRight, CalendarPlus, CheckCircle2 } from 'lucide-react';
import { useData } from '@/lib/api';
import { brl, day, hour } from '@/lib/format';
import { Card, CardHeader } from '@/components/blocks';
import { Button, DataState } from '@/components/ui';
import { RecordActivityDialog, type ActivityRecord } from '@/components/contacts/record-activity-dialog';
import type { Row } from '@/lib/types';
export const followUpReasons: Record<string, string> = {
  overdue_action: 'Retorno em atraso', overdue_close: 'Previsão de fechamento vencida', no_next_action: 'Sem próxima ação agendada',
};
export function FollowUpQueue() {
  const [mine, setMine] = useState(false);
  const [record, setRecord] = useState<ActivityRecord | null>(null);
  const report = useData<{ items: Row[]; total: number }>('/reports/follow-ups' + (mine ? '?mine=true' : ''));
  return <>
    <Card as="section" className="followup-queue">
      <CardHeader title={<span>Precisa de atenção <span className="tab-count">{report.data?.total ?? '…'}</span></span>}
        actions={<label className="checkbox-label"><input type="checkbox" checked={mine} onChange={e => setMine(e.target.checked)} />Só meus negócios</label>} />
      <DataState loading={report.isLoading} error={report.error}>
        {report.data?.items.length ? <div className="followup-list">
          {report.data.items.slice(0, 5).map(row => <div className="followup-row" key={row.id}>
            <div className="followup-context"><span className={'followup-reason ' + row.reason}>{followUpReasons[row.reason]}</span>
              <Link href={'/crm?opportunity=' + row.id} className="followup-title">{row.title}<ArrowUpRight size={13} /></Link>
              <p>{[row.contact_name || row.company_name, row.owner_name || 'Sem responsável', brl(row.amount)].filter(Boolean).join(' · ')}</p>
              {row.next_action && <small>{row.next_action.title} · {day(row.next_action.scheduled_at)}{row.next_action.type === 'activity' ? ' às ' + hour(row.next_action.scheduled_at) : ''}</small>}
              {row.reason === 'overdue_close' && <small>Revise a previsão de fechamento no negócio.</small>}
            </div>
            <Button variant="secondary" onClick={() => setRecord({ label: row.title, opportunity_id: row.id, contact_id: row.contact_id, company_id: row.company_id, owner_id: row.owner_id })}><CalendarPlus size={15} />Agendar retorno</Button>
          </div>)}
          {report.data.total > 5 && <Link href="/crm?attention=true" className="card-footer card-link">Ver os {report.data.total} negócios no funil<ArrowUpRight size={14} /></Link>}
        </div> : <div className="followup-clear"><CheckCircle2 size={18} /><span>Nenhum negócio pendente de acompanhamento nesta visão.</span></div>}
      </DataState>
    </Card>
    <RecordActivityDialog record={record} onClose={() => setRecord(null)} />
  </>;
}
