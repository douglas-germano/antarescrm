import { RecordLink } from '@/components/record-link';
import type { ReactNode } from 'react';
import { BarChart3 } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from 'recharts';
import { brl, day, initials, kinds } from '@/lib/format';
import type { Row } from '@/lib/types';
import { durationLabel } from '@/components/whatsapp/ThreadList';

export const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;
const compactBrl = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1 }).format(value);

/** Change against the previous period: percent, or percentage points for rates. */
function trend(now: number, before: number, points: boolean) {
  if (!before && !now) return { tone: '', text: 'sem variação' };
  if (!before) return { tone: 'up', text: 'novo no período' };
  const diff = points ? now - before : ((now - before) / before) * 100;
  const tone = diff > 0.05 ? 'up' : diff < -0.05 ? 'down' : '';
  const sign = diff > 0.05 ? '▲ ' : diff < -0.05 ? '▼ ' : '';
  return { tone, text: `${sign}${Math.abs(diff).toFixed(points ? 1 : 0)}${points ? ' p.p.' : '%'}` };
}

/** A KPI card in the Visão geral style; with `href` the whole card opens the matching list. */
export function Kpi({ label, value, now, before, points = false, detail, href }: {
  label: string; value: ReactNode; now: number; before: number; points?: boolean; detail?: string; href?: string;
}) {
  const t = trend(now, before, points);
  const body = <>
    <div className="stat-top"><span>{label}</span></div>
    <strong className="stat-value">{value}</strong>
    {detail && <span className="stat-detail">{detail}</span>}
    <span className={'stat-trend ' + t.tone}>{t.text} <span>vs. período anterior</span></span>
  </>;
  return href ? <RecordLink href={href} className="stat-card rep-kpi-link">{body}</RecordLink> : <div className="stat-card">{body}</div>;
}

const SERIES: Record<string, string> = { won_amount: 'Vendido', new_deals: 'Novos negócios', new_contacts: 'Novos contatos' };

function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as Row;
  return (
    <div className="rep-tooltip">
      <strong>{point.title || label}</strong>
      {payload.map((item) => (
        <p key={String(item.dataKey)}><i style={{ background: item.color }} />{SERIES[String(item.dataKey)]}<b>{item.dataKey === 'won_amount' ? brl(Number(item.value)) : item.value}</b></p>
      ))}
    </div>
  );
}

export function EvolutionChart({ timeline, granularity }: { timeline: Row[]; granularity: string }) {
  const empty = timeline.every((p) => !p.won_amount && !p.new_deals && !p.new_contacts);
  if (empty) return <div className="rep-empty"><BarChart3 size={22} /><p>Sem vendas, negócios ou contatos novos neste período.</p></div>;
  const data = timeline.map((p) => ({
    ...p,
    label: granularity === 'month' ? new Date(p.date + 'T12:00:00').toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }) : p.date.slice(5).split('-').reverse().join('/'),
    title: granularity === 'month' ? new Date(p.date + 'T12:00:00').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
      : (granularity === 'week' ? 'Semana de ' : '') + new Date(p.date + 'T12:00:00').toLocaleDateString('pt-BR', { day: 'numeric', month: 'long' }),
  }));
  return (
    <div className="rep-chart">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ebebeb" />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#8a8d90' }} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24} />
          <YAxis yAxisId="money" tick={{ fontSize: 11, fill: '#8a8d90' }} tickLine={false} axisLine={false} tickFormatter={(v) => compactBrl(Number(v))} width={64} />
          <YAxis yAxisId="count" orientation="right" allowDecimals={false} tick={{ fontSize: 11, fill: '#8a8d90' }} tickLine={false} axisLine={false} width={28} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f4f4f5' }} />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} formatter={(value) => <span style={{ color: '#5f6266' }}>{value}</span>} />
          <Bar yAxisId="money" dataKey="won_amount" name="Vendido" fill="#ef2f70" radius={[4, 4, 0, 0]} maxBarSize={36} />
          <Line yAxisId="count" dataKey="new_deals" name="Novos negócios" stroke="#25282b" strokeWidth={2} dot={false} />
          <Line yAxisId="count" dataKey="new_contacts" name="Novos contatos" stroke="#9a9c9e" strokeWidth={2} dot={false} strokeDasharray="4 3" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Funnel-shaped bars: each stage centred and as wide as its share, with the pass-through rate between stages. */
export function FunnelChart({ funnel }: { funnel: Row[] }) {
  const max = Math.max(1, ...funnel.map((s) => s.entered));
  return (
    <ol className="rep-funnel">
      {funnel.map((s, index) => (
        <li key={s.stage_id}>
          {index > 0 && s.step_rate !== null && s.step_rate <= 100 && <span className="rep-step-rate">↓ {s.step_rate}% passaram</span>}
          <div className="rep-funnel-row">
            <span className="rep-funnel-name" title={s.name}>{s.name}</span>
            <div className="rep-funnel-track"><span style={{ width: `${Math.max(4, (s.entered / max) * 100)}%`, background: s.color || 'var(--primary)' }}>{s.entered}</span></div>
          </div>
          <small>{plural(s.open_count, 'aberto agora', 'abertos agora')} · {brl(s.open_amount)}</small>
        </li>
      ))}
    </ol>
  );
}

export function Bars({ rows, label, value, format, sub, href }: {
  rows: Row[]; label: string; value: string; format: (v: number) => string; sub?: (r: Row) => string; href?: (r: Row) => string;
}) {
  const max = Math.max(1, ...rows.map((r) => Number(r[value])));
  return (
    <ul className="rep-bars">
      {rows.map((r) => {
        const content = <>
          <div className="rep-bar-top"><span title={r[label]}>{r[label]}</span><strong>{format(Number(r[value]))}</strong></div>
          <div className="dash-bar"><span style={{ width: `${Math.max(2, (Number(r[value]) / max) * 100)}%` }} /></div>
          {sub && <small>{sub(r)}</small>}
        </>;
        return <li key={r[label]}>{href ? <RecordLink href={href(r)} className="rep-bar-link">{content}</RecordLink> : content}</li>;
      })}
    </ul>
  );
}

export function TeamTable({ team }: { team: Row[] }) {
  const rows = [...team].sort((a, b) => b.won_amount - a.won_amount || b.won_count - a.won_count);
  const total = rows.reduce((sum, m) => sum + Number(m.won_amount), 0);
  return (
    <div className="table-wrap">
      <table className="data-table rep-team">
        <thead><tr><th>Responsável</th><th>Vendido</th><th className="text-right">Ganhos</th><th className="text-right">Perdidos</th><th className="text-right">Conversão</th><th className="text-right">Em aberto</th><th className="text-right">Atividades</th><th className="text-right">Tarefas</th></tr></thead>
        <tbody>
          {rows.map((m) => {
            const share = total ? (Number(m.won_amount) / total) * 100 : 0;
            return (
              <tr key={m.owner_id || 'none'}>
                <td><span className="rep-person"><span className="owner-avatar">{m.owner_id ? initials(m.name) : '—'}</span><strong>{m.name}</strong></span></td>
                <td>
                  <div className="rep-share"><strong>{brl(m.won_amount)}</strong><small>{share.toFixed(0)}%</small></div>
                  <div className="dash-bar"><span style={{ width: `${Math.max(share ? 2 : 0, share)}%` }} /></div>
                </td>
                <td className="text-right">{m.won_count}</td><td className="text-right">{m.lost_count}</td>
                <td className="text-right">{m.conversion_rate}%</td>
                <td className="text-right">{plural(m.open_count, 'negócio', 'negócios')}<small className="rep-sub">{brl(m.open_amount)}</small></td>
                <td className="text-right">{m.activities_done}</td><td className="text-right">{m.tasks_done}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);

/** Contacts that arrived in the period, by origin, followed until today: talked, became a deal, bought. */
export function JourneyTable({ items, total }: { items: Row[]; total: Row }) {
  const cells = (r: Row) => <>
    <td className="text-right">{r.contacts}</td>
    {(['conversation', 'deal', 'won'] as const).map((key) => (
      <td key={key} className="text-right">{r[key]}<small className="rep-sub">{pct(r[key], r.contacts)}%</small></td>
    ))}
    <td className="text-right">{brl(r.won_amount)}</td>
  </>;
  return (
    <div className="table-wrap">
      <table className="data-table rep-journey">
        <thead><tr><th>Origem</th><th className="text-right">Novos contatos</th><th className="text-right">Conversaram</th><th className="text-right">Viraram negócio</th><th className="text-right">Compraram</th><th className="text-right">Vendido</th></tr></thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.source}>
              <td><RecordLink href={'/contatos?origem=' + encodeURIComponent(r.source)}><strong>{r.source}</strong></RecordLink></td>
              {cells(r)}
            </tr>
          ))}
        </tbody>
        {items.length > 1 && <tfoot><tr><td><strong>Total</strong></td>{cells(total)}</tr></tfoot>}
      </table>
    </div>
  );
}

/** Median wait for the team's first reply, or a dash when nobody was answered in the window. */
export const firstResponseLabel = (seconds: number | null) => (seconds === null ? '—' : durationLabel(seconds));

const CHANNELS: Record<string, string> = { whatsapp: 'WhatsApp', instagram: 'Instagram', email: 'E-mail', sms: 'SMS' };
export const channelName = (channel: string) => CHANNELS[channel] || channel;

/** Every section of the report as CSV (semicolon separated, as Brazilian spreadsheets expect). */
export function exportCsv(r: Row, funnelName: string) {
  const cell = (v: unknown) => {
    const text = typeof v === 'number' ? String(v).replace('.', ',') : String(v ?? '');
    return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines: unknown[][] = [
    ['Relatório Antares CRM', `${day(r.period.start)} a ${day(r.period.end)}`],
    ['Comparado com', `${day(r.period.previous_start)} a ${day(r.period.previous_end)}`],
    [],
    ['Indicador', 'Período', 'Período anterior'],
    ['Vendido (R$)', r.current.won_amount, r.previous.won_amount],
    ['Negócios ganhos', r.current.won_count, r.previous.won_count],
    ['Negócios perdidos', r.current.lost_count, r.previous.lost_count],
    ['Conversão (%)', r.current.conversion_rate, r.previous.conversion_rate],
    ['Ticket médio (R$)', r.current.average_ticket, r.previous.average_ticket],
    ['Novos negócios', r.current.new_deals, r.previous.new_deals],
    ['Novos contatos', r.current.new_contacts, r.previous.new_contacts],
    [],
    [`Funil: ${funnelName}`, 'Entraram na etapa', 'Passagem (%)', 'Abertos agora', 'Em aberto (R$)'],
    ...r.funnel.map((s: Row) => [s.name, s.entered, s.step_rate ?? '', s.open_count, s.open_amount]),
    [],
    ['Responsável', 'Vendido (R$)', 'Ganhos', 'Perdidos', 'Conversão (%)', 'Em aberto', 'Em aberto (R$)', 'Atividades', 'Tarefas'],
    ...r.team.map((m: Row) => [m.name, m.won_amount, m.won_count, m.lost_count, m.conversion_rate, m.open_count, m.open_amount, m.activities_done, m.tasks_done]),
    [],
    ['Da origem à venda (contatos que chegaram no período)', 'Novos contatos', 'Conversaram', 'Viraram negócio', 'Compraram', 'Vendido (R$)'],
    ...(r.journey?.items || []).map((s: Row) => [s.source, s.contacts, s.conversation, s.deal, s.won, s.won_amount]),
    ...(r.journey ? [['Total', r.journey.total.contacts, r.journey.total.conversation, r.journey.total.deal, r.journey.total.won, r.journey.total.won_amount]] : []),
    [],
    ['1ª resposta (mediana, minutos)', r.first_response?.current.median_seconds == null ? '' : Math.round(r.first_response.current.median_seconds / 60), r.first_response?.previous.median_seconds == null ? '' : Math.round(r.first_response.previous.median_seconds / 60)],
    [],
    ['Origem', 'Novos contatos', 'Negócios', 'Ganhos', 'Vendido (R$)'],
    ...r.sources.map((s: Row) => [s.source, s.contacts, s.deals, s.won_count, s.won_amount]),
    [],
    ['Motivo de perda', 'Negócios', 'Valor (R$)'],
    ...r.loss_reasons.map((l: Row) => [l.reason, l.count, l.amount]),
    [],
    ['Atividade', 'Concluídas', 'Pendentes'],
    ...r.activities.map((a: Row) => [kinds[a.kind] || a.kind, a.completed, a.pending]),
    [],
    ['Canal', 'Mensagens recebidas', 'Mensagens enviadas'],
    ...(r.messages.channels || []).map((c: Row) => [channelName(c.channel), c.received, c.sent]),
  ];
  const csv = '﻿' + lines.map((line) => line.map(cell).join(';')).join('\r\n');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  link.download = `relatorio-${r.period.start}-a-${r.period.end}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}
