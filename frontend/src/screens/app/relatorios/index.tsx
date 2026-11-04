import { RecordLink } from '@/components/record-link';
import { useEffect, useMemo, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { BarChart3, CalendarRange, Download, ListChecks, MessageCircle, Users, Workflow } from 'lucide-react';
import { useData } from '@/lib/api';
import { brl, day, kinds, today } from '@/lib/format';
import { PageHeader, DataState, EmptyState, Button, Popover } from '@/components/ui';
import { Card, CardHeader, CardBody, Tabs } from '@/components/blocks';
import { Bars, EvolutionChart, FunnelChart, Kpi, TeamTable, channelName, exportCsv, plural } from '@/components/reports/report-parts';
import type { Row } from '@/lib/types';

const PERIODS = [
  { value: '7', label: '7 dias' },
  { value: '30', label: '30 dias' },
  { value: 'month', label: 'Este mês' },
  { value: 'last_month', label: 'Mês passado' },
  { value: 'year', label: 'Este ano' },
];
const SECTIONS = [
  { value: 'vendas', label: 'Vendas' },
  { value: 'equipe', label: 'Equipe' },
  { value: 'operacao', label: 'Operação' },
] as const;
type Section = (typeof SECTIONS)[number]['value'];
const addDays = (iso: string, n: number) => new Date(Date.parse(iso + 'T12:00:00Z') + n * 86400000).toISOString().slice(0, 10);
const isDate = (value: string | null) => !!value && /^\d{4}-\d{2}-\d{2}$/.test(value);

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

export default function ReportsPage() {
  const [period, setPeriod] = useState('30');
  const [custom, setCustom] = useState({ start: addDays(today(), -29), end: today() });
  const [pipeline, setPipeline] = useState('all');
  const [section, setSection] = useState<Section>('vendas');
  const [ready, setReady] = useState(false);

  // The filters live in the address, so going back or sharing the link keeps the same view.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const p = q.get('periodo');
    if (p === 'custom' && isDate(q.get('inicio')) && isDate(q.get('fim'))) {
      setPeriod('custom');
      setCustom({ start: q.get('inicio')!, end: q.get('fim')! });
    } else if (p && PERIODS.some((x) => x.value === p)) setPeriod(p);
    if (q.get('funil')) setPipeline(q.get('funil')!);
    const s = q.get('aba');
    if (SECTIONS.some((x) => x.value === s)) setSection(s as Section);
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const q = new URLSearchParams({ periodo: period, ...(period === 'custom' ? { inicio: custom.start, fim: custom.end } : {}), funil: pipeline, aba: section });
    window.history.replaceState(null, '', '/relatorios?' + q);
  }, [ready, period, custom, pipeline, section]);

  const { start, end } = useMemo(() => range(period, custom), [period, custom]);
  const pipelines = useData<{ items: Row[] }>('/pipelines');
  const report = useData<Row>(ready && start && end && start <= end ? `/reports/overview?start=${start}&end=${end}&pipeline_id=${pipeline}` : null);
  const r = report.data;
  const cur = r?.current, prev = r?.previous, pl = r?.pipeline;
  const pipelineList = pipelines.data?.items || [];
  const funnelName = pipeline === 'all' || pipeline === 'default' ? 'Principal' : pipelineList.find((p) => p.id === pipeline)?.name || 'Funil';
  const crmLink = (status?: string) => '/crm?' + new URLSearchParams({ ...(status ? { status } : {}), ...(pipeline !== 'all' ? { pipeline } : {}) });
  const decided = (cur?.won_count || 0) + (cur?.lost_count || 0);

  return (
    <div className="page reports-page">
      <PageHeader title="Relatórios">
        <Button variant="soft" disabled={!r} onClick={() => r && exportCsv(r, funnelName)}><Download size={16} />Exportar</Button>
      </PageHeader>

      <div className="board-bar rep-bar">
        <Tabs label="Seção do relatório" variant="line" items={[...SECTIONS]} value={section} onChange={setSection} />
        <div className="toolbar-end">
          <Tabs label="Período" items={PERIODS} value={period} onChange={setPeriod} />
          <Popover label={period === 'custom' ? `${day(custom.start)} – ${day(custom.end)}` : 'Personalizado'} icon={<CalendarRange size={15} />}
            variant={period === 'custom' ? 'secondary' : 'soft'} align="end" panelClassName="filter-panel">{() => <>
            <label className="field"><span>De</span><input type="date" value={custom.start} max={custom.end} onChange={(e) => { setCustom({ ...custom, start: e.target.value }); setPeriod('custom'); }} /></label>
            <label className="field"><span>Até</span><input type="date" value={custom.end} min={custom.start} max={today()} onChange={(e) => { setCustom({ ...custom, end: e.target.value }); setPeriod('custom'); }} /></label>
          </>}</Popover>
          <select aria-label="Funil" value={pipeline} onChange={(e) => setPipeline(e.target.value)}>
            <option value="all">Todos os funis</option>
            {pipelineList.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      </div>
      {r && <p className="rep-range">{day(r.period.start)} a {day(r.period.end)} · comparado com {day(r.period.previous_start)} a {day(r.period.previous_end)}</p>}

      <DataState loading={report.isLoading || !ready} error={report.error}>
        {r && cur && prev && pl && (
          <>
            {section === 'vendas' && <>
              <div className="stat-grid rep-kpis">
                <Kpi label="Vendido" value={brl(cur.won_amount)} now={cur.won_amount} before={prev.won_amount} href={crmLink('won')} />
                <Kpi label="Negócios ganhos" value={cur.won_count} now={cur.won_count} before={prev.won_count} detail={plural(cur.lost_count, 'perdido', 'perdidos')} href={crmLink('won')} />
                <Kpi label="Conversão" value={`${cur.conversion_rate}%`} now={cur.conversion_rate} before={prev.conversion_rate} points detail={`dos ${plural(decided, 'negócio fechado', 'negócios fechados')}`} />
                <Kpi label="Ticket médio" value={brl(cur.average_ticket)} now={cur.average_ticket} before={prev.average_ticket} detail="por negócio ganho" />
                <Kpi label="Novos negócios" value={cur.new_deals} now={cur.new_deals} before={prev.new_deals} href={crmLink()} />
                <Kpi label="Novos contatos" value={cur.new_contacts} now={cur.new_contacts} before={prev.new_contacts} href="/contatos" />
              </div>

              <div className="rep-grid rep-main">
                <Card as="section">
                  <CardHeader title="Evolução no período" description={`Vendas e entradas por ${({ day: 'dia', week: 'semana', month: 'mês' } as Record<string, string>)[r.period.granularity]}`} />
                  <CardBody><EvolutionChart timeline={r.timeline} granularity={r.period.granularity} /></CardBody>
                </Card>
                <Card as="section">
                  <CardHeader title="Funil no período" description={`${funnelName} · negócios que entraram em cada etapa`} />
                  <CardBody>
                    {r.funnel.length ? <FunnelChart funnel={r.funnel} /> : <EmptyState title="Funil sem etapas" description="Crie as etapas em Configurações › Funil." />}
                    <div className="rep-funnel-foot">
                      <span><b className="text-success">{decided ? Math.round((cur.won_count / decided) * 100) : 0}%</b> ganhos</span>
                      <span><b className="text-danger">{decided ? Math.round((cur.lost_count / decided) * 100) : 0}%</b> perdidos</span>
                      <span>{plural(decided, 'negócio fechado', 'negócios fechados')} no período</span>
                    </div>
                  </CardBody>
                </Card>
              </div>

              <Card as="section">
                <CardHeader title="Saúde do funil agora" description="Posição atual, sem relação com o período escolhido" />
                <CardBody>
                  <div className="rep-health">
                    <div><span>Em aberto</span><strong>{brl(pl.open_amount)}</strong><small>{plural(pl.open_count, 'negócio', 'negócios')}</small></div>
                    <div><span>Previsão ponderada</span><strong>{brl(pl.weighted_amount)}</strong><small>pela chance de cada etapa</small></div>
                    <div><span>A fechar em 30 dias</span><strong>{brl(pl.closing_30d_amount)}</strong><small>pela previsão de fechamento</small></div>
                    <div className={pl.overdue_close ? 'warn' : ''}><span>Previsão vencida</span><strong>{pl.overdue_close}</strong><small>{pl.overdue_close === 1 ? 'negócio para revisar' : 'negócios para revisar'}</small></div>
                    <div className={pl.stale_count ? 'warn' : ''}><span>Parados há 14+ dias</span><strong>{pl.stale_count}</strong><small>{brl(pl.stale_amount)} em risco</small></div>
                    <div><span>Ciclo médio de venda</span><strong>{cur.sales_cycle_days === null ? '—' : plural(cur.sales_cycle_days, 'dia', 'dias')}</strong><small>da criação ao ganho</small></div>
                  </div>
                </CardBody>
              </Card>

              <div className="rep-grid rep-three">
                <Card as="section">
                  <CardHeader title="Maiores negócios em aberto" actions={<RecordLink href={crmLink()} className="btn btn-ghost">Ver funil</RecordLink>} />
                  <CardBody className="rep-list">
                    {r.top_open.length ? r.top_open.map((d: Row) => (
                      <RecordLink href={'/crm?opportunity=' + d.id} key={d.id} className="rep-deal"><div><strong>{d.title}</strong><small>{d.contact || 'Sem contato'} · {d.stage}</small></div><span>{brl(d.amount)}</span></RecordLink>
                    )) : <p className="muted">Nenhum negócio em aberto.</p>}
                  </CardBody>
                </Card>
                <Card as="section">
                  <CardHeader title="Negócios parados" description="Mais tempo sem atividade ou mudança de etapa" />
                  <CardBody className="rep-list">
                    {r.top_stale.length ? r.top_stale.map((d: Row) => (
                      <RecordLink href={'/crm?opportunity=' + d.id} key={d.id} className="rep-deal"><div><strong>{d.title}</strong><small>{d.owner || 'Sem responsável'} · {brl(d.amount)}</small></div><span className="text-danger">{plural(d.idle_days, 'dia', 'dias')}</span></RecordLink>
                    )) : <p className="muted">Nenhum negócio parado há 14 dias ou mais.</p>}
                  </CardBody>
                </Card>
                <Card as="section">
                  <CardHeader title="Motivos de perda" />
                  <CardBody>
                    {r.loss_reasons.length ? <Bars rows={r.loss_reasons} label="reason" value="count" format={(v) => plural(v, 'negócio', 'negócios')} sub={(l) => brl(l.amount) + ' perdidos'} /> : <p className="muted">Nenhum negócio perdido no período.</p>}
                  </CardBody>
                </Card>
              </div>
            </>}

            {section === 'equipe' && <>
              <Card as="section">
                <CardHeader title="Desempenho da equipe" description="Negócios fechados e atividades no período, do maior para o menor em vendas" />
                {r.team.length ? <TeamTable team={r.team} /> : <CardBody><EmptyState icon={<Users />} title="Sem dados da equipe" description="Negócios e atividades aparecem aqui conforme forem registrados." /></CardBody>}
              </Card>
              <Card as="section">
                <CardHeader title="Origem dos contatos" description="Novos contatos, negócios e vendas por origem · clique para ver os contatos" />
                <CardBody>
                  {r.sources.length ? <Bars rows={r.sources} label="source" value="contacts" format={(v) => plural(v, 'contato', 'contatos')}
                    sub={(s) => `${plural(s.deals, 'negócio', 'negócios')} · ${plural(s.won_count, 'ganho', 'ganhos')} · ${brl(s.won_amount)}`}
                    href={(s) => '/contatos?origem=' + encodeURIComponent(s.source)} /> : <EmptyState icon={<BarChart3 />} title="Sem novos contatos" description="Nenhum contato novo no período." />}
                </CardBody>
              </Card>
            </>}

            {section === 'operacao' && (
              <div className="rep-grid rep-ops">
                <Card as="section">
                  <CardHeader title="Atividades" />
                  <CardBody className="rep-ops-list">
                    {r.activities.length ? r.activities.map((a: Row) => <p key={a.kind}><span>{kinds[a.kind] || a.kind}</span><strong>{plural(a.completed, 'concluída', 'concluídas')} · {plural(a.pending, 'pendente', 'pendentes')}</strong></p>) : <p className="muted">Nenhuma atividade no período.</p>}
                  </CardBody>
                </Card>
                <Card as="section">
                  <CardHeader title="Tarefas" actions={<Link to="/tarefas" className="btn btn-ghost"><ListChecks size={15} />Abrir</Link>} />
                  <CardBody className="rep-ops-list">
                    <p><span>Criadas no período</span><strong>{r.tasks.created}</strong></p>
                    <p><span>Concluídas no período</span><strong>{r.tasks.done}</strong></p>
                    <p><span>Em aberto agora</span><strong>{r.tasks.open}</strong></p>
                    <p><span>Atrasadas agora</span><strong className={r.tasks.overdue ? 'text-danger' : ''}>{r.tasks.overdue}</strong></p>
                  </CardBody>
                </Card>
                <Card as="section">
                  <CardHeader title="Mensagens" actions={<Link to="/mensagens" className="btn btn-ghost"><MessageCircle size={15} />Abrir</Link>} />
                  <CardBody className="rep-ops-list">
                    {(r.messages.channels || []).length ? r.messages.channels.map((c: Row) => (
                      <p key={c.channel}><span>{channelName(c.channel)}</span><strong>{plural(c.received, 'recebida', 'recebidas')} · {plural(c.sent, 'enviada', 'enviadas')}</strong></p>
                    )) : <p className="muted">Nenhuma mensagem no período.</p>}
                  </CardBody>
                </Card>
                <Card as="section">
                  <CardHeader title="Automações" actions={<Link to="/automacoes" className="btn btn-ghost"><Workflow size={15} />Abrir</Link>} />
                  <CardBody className="rep-ops-list">
                    <p><span>Execuções no período</span><strong>{r.automations.runs}</strong></p>
                    <p><span>Com falha</span><strong className={r.automations.failed ? 'text-danger' : ''}>{r.automations.failed}</strong></p>
                  </CardBody>
                </Card>
              </div>
            )}
          </>
        )}
      </DataState>
    </div>
  );
}
