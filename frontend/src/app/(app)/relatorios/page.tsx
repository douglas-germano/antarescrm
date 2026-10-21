'use client';
import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { useData } from '@/lib/api';
import { brl, day, kinds, today } from '@/lib/format';
import { PageHeader, DataState, EmptyState } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import type { Row } from '@/lib/types';

const PERIODS = [
  { value: '7', label: 'Últimos 7 dias' },
  { value: '30', label: 'Últimos 30 dias' },
  { value: '90', label: 'Últimos 90 dias' },
  { value: 'month', label: 'Este mês' },
  { value: 'last_month', label: 'Mês passado' },
  { value: 'year', label: 'Este ano' },
  { value: 'custom', label: 'Personalizado' },
];
const addDays = (iso: string, n: number) => new Date(Date.parse(iso + 'T12:00:00Z') + n * 86400000).toISOString().slice(0, 10);

function range(period: string, custom: { start: string; end: string }) {
  const t = today();
  if (period === 'custom') return custom;
  if (period === 'month') return { start: t.slice(0, 8) + '01', end: t };
  if (period === 'year') return { start: t.slice(0, 4) + '-01-01', end: t };
  if (period === 'last_month') {
    const first = new Date(Date.parse(t.slice(0, 8) + '01T12:00:00Z'));
    const lastDay = new Date(first.getTime() - 86400000).toISOString().slice(0, 10);
    return { start: lastDay.slice(0, 8) + '01', end: lastDay };
  }
  return { start: addDays(t, -(Number(period) - 1)), end: t };
}

/** "▲ 12%" against the previous period; `invert` flips the colour for metrics where lower is better. */
function Delta({ now, before, points = false }: { now: number; before: number; points?: boolean }) {
  if (!before && !now) return <span className="delta flat"><Minus size={12} /> sem variação</span>;
  if (!before) return <span className="delta up"><ArrowUpRight size={12} /> novo no período</span>;
  const diff = points ? now - before : ((now - before) / before) * 100;
  const up = diff > 0.05, down = diff < -0.05;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  return <span className={'delta ' + (up ? 'up' : down ? 'down' : 'flat')}><Icon size={12} /> {Math.abs(diff).toFixed(points ? 1 : 0)}{points ? ' p.p.' : '%'} vs. anterior</span>;
}

function Kpi({ label, value, children }: { label: string; value: ReactNode; children?: ReactNode }) {
  return <div className="stat-card"><div className="stat-top"><span>{label}</span></div><strong className="stat-value">{value}</strong><span className="stat-detail">{children}</span></div>;
}

function Bars({ rows, label, value, format = (v: number) => String(v), sub }: { rows: Row[]; label: string; value: string; format?: (v: number) => string; sub?: (r: Row) => string }) {
  const max = Math.max(1, ...rows.map((r) => Number(r[value])));
  return (
    <ul className="rep-bars">
      {rows.map((r) => (
        <li key={r[label]}>
          <div className="rep-bar-top"><span title={r[label]}>{r[label]}</span><strong>{format(Number(r[value]))}</strong></div>
          <div className="dash-bar"><span style={{ width: `${Math.max(2, (Number(r[value]) / max) * 100)}%`, background: 'var(--ink)' }} /></div>
          {sub && <small>{sub(r)}</small>}
        </li>
      ))}
    </ul>
  );
}

export default function ReportsPage() {
  const [period, setPeriod] = useState('30');
  const [custom, setCustom] = useState({ start: addDays(today(), -29), end: today() });
  const [pipeline, setPipeline] = useState('all');
  const { start, end } = useMemo(() => range(period, custom), [period, custom]);
  const pipelines = useData<{ items: Row[] }>('/pipelines');
  const report = useData<Row>(start && end && start <= end ? `/reports/overview?start=${start}&end=${end}&pipeline_id=${pipeline}` : null);
  const r = report.data;
  const cur = r?.current, prev = r?.previous;
  const timeline = (r?.timeline || []).map((p: Row) => ({ ...p, label: r?.period.granularity === 'month' ? p.date.slice(0, 7) : p.date.slice(5).split('-').reverse().join('/') }));
  const pl = r?.pipeline;
  const hasFunnel = (r?.funnel || []).length > 0;

  return (
    <div className="page reports-page">
      <PageHeader title="Relatórios">
        <div className="rep-filters">
          <select aria-label="Período" value={period} onChange={(e) => setPeriod(e.target.value)}>{PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select>
          {period === 'custom' && (
            <>
              <input type="date" aria-label="Data inicial" value={custom.start} max={custom.end} onChange={(e) => setCustom({ ...custom, start: e.target.value })} />
              <input type="date" aria-label="Data final" value={custom.end} min={custom.start} onChange={(e) => setCustom({ ...custom, end: e.target.value })} />
            </>
          )}
          <select aria-label="Funil" value={pipeline} onChange={(e) => setPipeline(e.target.value)}>
            <option value="all">Todos os funis</option>
            {pipelines.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </PageHeader>
      {r && <p className="rep-range">{day(r.period.start)} a {day(r.period.end)} · comparado com {day(r.period.previous_start)} a {day(r.period.previous_end)}</p>}

      <DataState loading={report.isLoading} error={report.error}>
        {r && cur && prev && pl && (
          <>
            <div className="stat-grid rep-kpis">
              <Kpi label="Vendido" value={brl(cur.won_amount)}><Delta now={cur.won_amount} before={prev.won_amount} /></Kpi>
              <Kpi label="Negócios ganhos" value={cur.won_count}><Delta now={cur.won_count} before={prev.won_count} /></Kpi>
              <Kpi label="Conversão" value={`${cur.conversion_rate}%`}><Delta now={cur.conversion_rate} before={prev.conversion_rate} points /></Kpi>
              <Kpi label="Ticket médio" value={brl(cur.average_ticket)}><Delta now={cur.average_ticket} before={prev.average_ticket} /></Kpi>
              <Kpi label="Novos negócios" value={cur.new_deals}><Delta now={cur.new_deals} before={prev.new_deals} /></Kpi>
              <Kpi label="Novos contatos" value={cur.new_contacts}><Delta now={cur.new_contacts} before={prev.new_contacts} /></Kpi>
            </div>

            <div className="rep-grid rep-main">
              <Card as="section">
                <CardHeader title="Evolução no período" description={`Vendas (R$) e novos negócios · por ${({ day: 'dia', week: 'semana', month: 'mês' } as Record<string, string>)[r.period.granularity]}`} />
                <CardBody>
                  <div className="rep-chart">
                    <ResponsiveContainer>
                      <ComposedChart data={timeline}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e1e1e1" />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" minTickGap={24} />
                        <YAxis yAxisId="money" tick={{ fontSize: 11 }} tickFormatter={(v) => brl(v).replace(',00', '')} width={84} />
                        <YAxis yAxisId="count" orientation="right" allowDecimals={false} tick={{ fontSize: 11 }} width={28} />
                        <Tooltip formatter={(v, name) => (name === 'Vendido' ? brl(v) : v)} />
                        <Bar yAxisId="money" dataKey="won_amount" name="Vendido" fill="#e60000" radius={[4, 4, 0, 0]} />
                        <Line yAxisId="count" dataKey="new_deals" name="Novos negócios" stroke="#25282b" strokeWidth={2} dot={false} />
                        <Line yAxisId="count" dataKey="new_contacts" name="Novos contatos" stroke="#9a9c9e" strokeWidth={2} dot={false} strokeDasharray="4 3" />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="rep-legend"><span><i style={{ background: '#e60000' }} /> Vendido</span><span><i style={{ background: '#25282b' }} /> Novos negócios</span><span><i style={{ background: '#9a9c9e' }} /> Novos contatos</span></div>
                </CardBody>
              </Card>

              <Card as="section">
                <CardHeader title="Funil no período" description={hasFunnel ? `${pipeline === 'all' ? 'Funil principal' : pipelines.data?.items.find((p) => p.id === pipeline)?.name || ''} · negócios que chegaram a cada etapa` : 'Escolha um funil para ver a conversão por etapa'} />
                <CardBody>
                  {hasFunnel ? (
                    <ul className="rep-funnel">
                      {r.funnel.map((s: Row) => {
                        const max = Math.max(1, ...r.funnel.map((x: Row) => x.entered));
                        return (
                          <li key={s.stage_id}>
                            <div className="rep-bar-top"><span>{s.name}</span><strong>{s.entered}</strong></div>
                            <div className="dash-bar"><span style={{ width: `${Math.max(2, (s.entered / max) * 100)}%`, background: s.color }} /></div>
                            <small>{s.step_rate !== null && s.step_rate <= 100 ? `${s.step_rate}% da etapa anterior · ` : ''}{s.open_count} aberto(s) · {brl(s.open_amount)}</small>
                          </li>
                        );
                      })}
                    </ul>
                  ) : <EmptyState title="Selecione um funil" description="A conversão por etapa é calculada por funil." />}
                </CardBody>
              </Card>
            </div>

            <Card as="section">
              <CardHeader title="Saúde do funil agora" description="Posição atual, sem relação com o período escolhido" />
              <CardBody>
                <div className="rep-health">
                  <div><span>Em aberto</span><strong>{brl(pl.open_amount)}</strong><small>{pl.open_count} negócio(s)</small></div>
                  <div><span>Previsão ponderada</span><strong>{brl(pl.weighted_amount)}</strong><small>pela chance de cada etapa</small></div>
                  <div><span>A fechar em 30 dias</span><strong>{brl(pl.closing_30d_amount)}</strong><small>pela previsão de fechamento</small></div>
                  <div className={pl.overdue_close ? 'warn' : ''}><span>Previsão vencida</span><strong>{pl.overdue_close}</strong><small>negócio(s) para revisar</small></div>
                  <div className={pl.stale_count ? 'warn' : ''}><span>Parados há 14+ dias</span><strong>{pl.stale_count}</strong><small>{brl(pl.stale_amount)} em risco</small></div>
                  <div><span>Ciclo médio de venda</span><strong>{cur.sales_cycle_days === null ? '—' : `${cur.sales_cycle_days} dias`}</strong><small>da criação ao ganho</small></div>
                </div>
              </CardBody>
            </Card>

            <div className="rep-grid rep-two">
              <Card as="section">
                <CardHeader title="Desempenho da equipe" description="Negócios fechados e atividades no período" />
                <div className="table-wrap">
                  <table className="data-table">
                    <thead><tr><th>Responsável</th><th className="text-right">Vendido</th><th className="text-right">Ganhos</th><th className="text-right">Perdidos</th><th className="text-right">Conv.</th><th className="text-right">Em aberto</th><th className="text-right">Ativ.</th><th className="text-right">Tarefas</th></tr></thead>
                    <tbody>
                      {r.team.map((m: Row) => (
                        <tr key={m.owner_id || 'none'}>
                          <td><strong>{m.name}</strong></td>
                          <td className="text-right">{brl(m.won_amount)}</td><td className="text-right">{m.won_count}</td><td className="text-right">{m.lost_count}</td>
                          <td className="text-right">{m.conversion_rate}%</td><td className="text-right">{m.open_count} · {brl(m.open_amount)}</td>
                          <td className="text-right">{m.activities_done}</td><td className="text-right">{m.tasks_done}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!r.team.length && <EmptyState title="Sem dados da equipe" description="Negócios e atividades aparecem aqui conforme forem registrados." />}
                </div>
              </Card>

              <Card as="section">
                <CardHeader title="Origem dos contatos" description="Novos contatos, negócios e vendas por origem" />
                <CardBody>
                  {r.sources.length ? <Bars rows={r.sources} label="source" value="contacts" format={(v) => `${v} contato(s)`} sub={(s) => `${s.deals} negócio(s) · ${s.won_count} ganho(s) · ${brl(s.won_amount)}`} /> : <EmptyState title="Sem novos contatos" description="Nenhum contato novo no período." />}
                </CardBody>
              </Card>
            </div>

            <div className="rep-grid rep-three">
              <Card as="section">
                <CardHeader title="Maiores negócios em aberto" actions={<Link href="/crm" className="btn btn-ghost">Funil</Link>} />
                <CardBody className="rep-list">
                  {r.top_open.length ? r.top_open.map((d: Row) => (
                    <Link href={'/crm?opportunity=' + d.id} key={d.id} className="rep-deal"><div><strong>{d.title}</strong><small>{d.contact || 'Sem contato'} · {d.stage}</small></div><span>{brl(d.amount)}</span></Link>
                  )) : <p className="muted">Nenhum negócio em aberto.</p>}
                </CardBody>
              </Card>
              <Card as="section">
                <CardHeader title="Negócios parados" description="Mais tempo sem atividade ou mudança de etapa" />
                <CardBody className="rep-list">
                  {r.top_stale.length ? r.top_stale.map((d: Row) => (
                    <Link href={'/crm?opportunity=' + d.id} key={d.id} className="rep-deal"><div><strong>{d.title}</strong><small>{d.owner || 'Sem responsável'} · {brl(d.amount)}</small></div><span className="text-danger">{d.idle_days} dias</span></Link>
                  )) : <p className="muted">Nenhum negócio parado há 14 dias ou mais.</p>}
                </CardBody>
              </Card>
              <Card as="section">
                <CardHeader title="Motivos de perda" />
                <CardBody>
                  {r.loss_reasons.length ? <Bars rows={r.loss_reasons} label="reason" value="count" format={(v) => `${v}`} sub={(l) => brl(l.amount) + ' perdidos'} /> : <p className="muted">Nenhum negócio perdido no período.</p>}
                </CardBody>
              </Card>
            </div>

            <Card as="section">
              <CardHeader title="Operação do dia a dia" description="Atividades, tarefas, mensagens e automações no período" />
              <CardBody>
                <div className="rep-ops">
                  <div>
                    <h3>Atividades</h3>
                    {r.activities.length ? r.activities.map((a: Row) => <p key={a.kind}><span>{kinds[a.kind] || a.kind}</span><strong>{a.completed} concluída(s) · {a.pending} pendente(s)</strong></p>) : <p className="muted">Nenhuma atividade.</p>}
                  </div>
                  <div>
                    <h3>Tarefas</h3>
                    <p><span>Criadas</span><strong>{r.tasks.created}</strong></p><p><span>Concluídas</span><strong>{r.tasks.done}</strong></p>
                    <p><span>Em aberto agora</span><strong>{r.tasks.open}</strong></p><p><span>Atrasadas agora</span><strong className={r.tasks.overdue ? 'text-danger' : ''}>{r.tasks.overdue}</strong></p>
                  </div>
                  <div>
                    <h3>WhatsApp</h3>
                    <p><span>Mensagens recebidas</span><strong>{r.messages.received}</strong></p><p><span>Mensagens enviadas</span><strong>{r.messages.sent}</strong></p>
                  </div>
                  <div>
                    <h3>Automações</h3>
                    <p><span>Execuções</span><strong>{r.automations.runs}</strong></p><p><span>Com falha</span><strong className={r.automations.failed ? 'text-danger' : ''}>{r.automations.failed}</strong></p>
                  </div>
                </div>
              </CardBody>
            </Card>
          </>
        )}
      </DataState>
    </div>
  );
}
