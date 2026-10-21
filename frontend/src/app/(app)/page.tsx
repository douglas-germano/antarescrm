'use client';
import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import { useData, useList } from '@/lib/api';
import { brl, day, hour, kinds, today } from '@/lib/format';
import { DataState, StatCard, PageHeader, Button } from '@/components/ui';
import { useFitCount } from '@/components/fit';
import { Card, CardHeader } from '@/components/blocks';
import { RecordActivityDialog, type ActivityRecord } from '@/components/contacts/record-activity-dialog';
import { followUpReasons } from '@/components/contacts/follow-up-queue';
import { Users, CheckSquare, TrendingUp, ArrowUpRight, Clock3, Handshake, Percent, Receipt, CalendarPlus, CheckCircle2 } from 'lucide-react';
import type { Row } from '@/lib/types';

/** Rows that fill the panel height exactly; whatever does not fit is summarised by a link, so nothing scrolls. */
function FitRows<T>({ items, size, render, empty, more }: {
  items: T[]; size: number; render: (item: T) => ReactNode; empty: ReactNode; more: { href: string; label: string };
}) {
  const { ref, count } = useFitCount(size, { fallback: 4 });
  const hidden = Math.max(0, items.length - count);
  const shown = hidden ? count - 1 : count;
  return (
    <div ref={ref} className="dash-rows">
      {items.length === 0 ? empty : <>
        {items.slice(0, Math.max(1, hidden ? shown : count)).map(render)}
        {hidden > 0 && <Link href={more.href} className="dash-more">{more.label} (+{items.length - Math.max(1, shown)})<ArrowUpRight size={13} /></Link>}
      </>}
    </div>
  );
}

const monthLabel = (key: string) =>
  new Date(key + '-15T12:00:00').toLocaleString('pt-BR', { month: 'short' }).replace('.', '');

function lastMonths(items: Row[]) {
  const map = new Map(items.map((r) => [r.month as string, r]));
  const base = new Date(today().slice(0, 7) + '-15T12:00:00');
  const out: { key: string; amount: number; count: number }[] = [];
  for (let i = 5; i >= 0; i--) {
    const d = new Date(base.getFullYear(), base.getMonth() - i, 15);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    const row = map.get(key);
    out.push({ key, amount: Number(row?.amount || 0), count: Number(row?.count || 0) });
  }
  return out;
}

export default function Dashboard() {
  const { data: stats, isLoading, error } = useData<Row>('/dashboard');
  const { data: funnel } = useData<{ items: Row[] }>('/reports/funnel');
  const { data: monthly } = useData<{ items: Row[] }>('/reports/won-by-month');
  const { data: attention } = useData<{ items: Row[]; total: number }>('/reports/follow-ups');
  const { data: tasks } = useList('/tasks?mine=true&status=todo');
  const [record, setRecord] = useState<ActivityRecord | null>(null);
  const start = today();
  const end = (() => {
    const d = new Date(start + 'T12:00:00Z');
    d.setUTCDate(d.getUTCDate() + 14);
    return d.toISOString().slice(0, 10);
  })();
  const { data: calendar } = useData<{ items: Row[] }>(`/calendar?start=${start}&end=${end}`);
  const sales = stats?.sales;
  const stages = funnel?.items || [];
  const maxStage = Math.max(1, ...stages.map((s) => s.count));
  const months = lastMonths(monthly?.items || []);
  const maxMonth = Math.max(1, ...months.map((m) => m.amount));
  const monthTotal = months.reduce((sum, m) => sum + m.amount, 0);
  const upcoming = calendar?.items || [];
  const myTasks = tasks || [];
  const attentionItems = attention?.items || [];
  return (
    <div className="page dashboard-page">
      <PageHeader title="Visão geral">
        <Link href="/crm" className="btn btn-secondary"><TrendingUp size={16} /> Funil</Link>
        <Link href="/tarefas" className="btn btn-primary"><CheckSquare size={16} /> Minhas tarefas</Link>
      </PageHeader>
      <DataState loading={isLoading} error={error}>
        <div className="stat-grid dash-stats">
          <StatCard label="Em negociação" value={brl(sales?.open_amount)} detail={`${sales?.open_count || 0} negócios em aberto`} icon={<TrendingUp />} />
          <StatCard label="Vendido" value={brl(sales?.won_amount)} detail={`${sales?.won_count || 0} negócios ganhos`} icon={<Handshake />} />
          <StatCard label="Conversão" value={`${sales?.conversion_rate ?? 0}%`} detail={`${sales?.won_count || 0} ganhos · ${sales?.lost_count || 0} perdidos`} icon={<Percent />} />
          <StatCard label="Ticket médio" value={brl(sales?.average_ticket)} detail="Por negócio ganho" icon={<Receipt />} />
          <StatCard label="Tarefas atrasadas" value={stats?.overdue_tasks || 0} detail={`${stats?.open_tasks || 0} abertas · ${stats?.my_tasks || 0} minhas`} icon={<Clock3 />} />
          <StatCard label="Contatos" value={stats?.contacts || 0} detail={`${stats?.companies || 0} ${stats?.companies === 1 ? 'empresa' : 'empresas'}`} icon={<Users />} />
        </div>
        <div className="dash-grid">
          <Card as="section" className="card-fill dash-attention">
            <CardHeader title={<span className="dash-title">Precisa de atenção <span className="tab-count">{attention?.total ?? '…'}</span></span>}
              actions={<Link href="/crm?attention=true" className="btn btn-ghost">Ver no funil<ArrowUpRight size={13} /></Link>} />
            <FitRows items={attentionItems} size={66} more={{ href: '/crm?attention=true', label: 'Ver todos no funil' }}
              empty={<div className="followup-clear"><CheckCircle2 size={18} /><span>Nenhum negócio pendente de acompanhamento.</span></div>}
              render={(row) => (
                <div className="dash-row dash-followup" key={row.id}>
                  <div className="dash-main">
                    <span className={'followup-reason ' + row.reason}>{followUpReasons[row.reason]}</span>
                    <Link href={'/crm?opportunity=' + row.id} className="dash-name">{row.title}</Link>
                    <small>{[row.contact_name || row.company_name, row.owner_name || 'Sem responsável', brl(row.amount)].filter(Boolean).join(' · ')}</small>
                  </div>
                  <Button variant="secondary" onClick={() => setRecord({ label: row.title, opportunity_id: row.id, contact_id: row.contact_id, company_id: row.company_id, owner_id: row.owner_id })}>
                    <CalendarPlus size={15} />Agendar
                  </Button>
                </div>
              )} />
          </Card>
          <Card as="section" className="card-fill">
            <CardHeader title="Funil" actions={<Link href="/crm" className="btn btn-ghost">Abrir<ArrowUpRight size={13} /></Link>} />
            <div className="dash-funnel">
              {stages.map((s) => (
                <div className="dash-stage" key={s.stage_id}>
                  <div className="dash-stage-top"><span>{s.name}</span><strong>{s.count}</strong></div>
                  <div className="dash-bar"><span style={{ width: `${Math.max(2, (s.count / maxStage) * 100)}%`, background: s.color }} /></div>
                  <small>{brl(s.amount)}</small>
                </div>
              ))}
              {!stages.length && <p className="muted">Nenhuma etapa configurada.</p>}
            </div>
          </Card>
          <Card as="section" className="card-fill">
            <CardHeader title="Próximos 14 dias" actions={<Link href="/agenda" className="btn btn-ghost">Atividades<ArrowUpRight size={13} /></Link>} />
            <FitRows items={upcoming} size={52} more={{ href: '/agenda', label: 'Ver agenda' }}
              empty={<p className="dash-empty">Nenhuma atividade ou prazo nos próximos dias.</p>}
              render={(e) => (
                <Link href={e.kind === 'task' ? '/tarefas' : '/agenda'} key={e.kind + e.id} className="dash-row dash-event">
                  <span className="date-tile">
                    {new Date(e.date.slice(0, 10) + 'T12:00:00').toLocaleString('pt-BR', { month: 'short' }).replace('.', '').toUpperCase()}
                    <strong>{e.date.slice(8, 10)}</strong>
                  </span>
                  <div className="dash-main">
                    <span className="dash-name">{e.title}</span>
                    <small>{e.kind === 'task' ? 'Tarefa' : kinds[e.kind] || 'Atividade'}{e.date.length > 10 ? ' · ' + hour(e.date) : ''}{e.contact_name ? ' · ' + e.contact_name : ''}</small>
                  </div>
                </Link>
              )} />
          </Card>
          <Card as="section" className="card-fill">
            <CardHeader title="Vendas por mês" description="Últimos 6 meses" actions={<strong className="dash-total">{brl(monthTotal)}</strong>} />
            <div className="dash-chart">
              {months.map((m) => (
                <div className="dash-col" key={m.key} title={`${brl(m.amount)} · ${m.count} ${m.count === 1 ? 'venda' : 'vendas'}`}>
                  <small className="dash-col-value">{m.count || ''}</small>
                  <span style={{ height: `max(3px, ${(m.amount / maxMonth) * 100}%)` }} className={m.amount ? '' : 'empty-col'} />
                  <small>{monthLabel(m.key)}</small>
                </div>
              ))}
            </div>
          </Card>
          <Card as="section" className="card-fill">
            <CardHeader title="Minhas tarefas" actions={<Link href="/tarefas" className="btn btn-ghost">Todas<ArrowUpRight size={13} /></Link>} />
            <FitRows items={myTasks} size={44} more={{ href: '/tarefas', label: 'Ver tarefas' }}
              empty={<p className="dash-empty">Nenhuma tarefa pendente para você.</p>}
              render={(t) => (
                <Link href="/tarefas" key={t.id} className="dash-row dash-task">
                  <span className="dash-name">{t.title}</span>
                  <strong className={t.due_date && t.due_date < start ? 'text-danger' : ''}>{day(t.due_date)}</strong>
                </Link>
              )} />
          </Card>
        </div>
      </DataState>
      <RecordActivityDialog record={record} onClose={() => setRecord(null)} />
    </div>
  );
}
