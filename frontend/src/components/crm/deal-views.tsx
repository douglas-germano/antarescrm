'use client';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { Handshake, ArrowUp, ArrowDown, CalendarDays, AlertCircle } from 'lucide-react';
import { brl, day } from '@/lib/format';
import type { Opportunity, OpportunityPage, PipelineStage } from '@/lib/types';
import { EmptyState } from '@/components/ui';
import { followUpReasons } from '@/components/contacts/follow-up-queue';
import { Card, KanbanBoard, KanbanColumn, KanbanCard, KanbanCardTitle, KanbanCardText, KanbanCardMeta } from '@/components/blocks';
import { staleDays, inStageDays, type SortKey } from './model';
type Props = {
  view: 'board' | 'list'; rows: Opportunity[]; stagesList: PipelineStage[];
  sort: { key: SortKey; dir: 1 | -1 }; sortBy: (key: SortKey) => void;
  onSelect: (row: Opportunity) => void; onAdd: (stage: string) => void; onDrag: (id: string | null) => void;
  move: (row: Opportunity, stage: string) => Promise<void>; moveBy: (row: Opportunity, direction: -1 | 1) => void;
  renderActions: (row: Opportunity, stop?: boolean) => ReactNode;
  who: (row: Opportunity) => string; stageName: (id: string) => string; ownerName: (id?: string | null) => string;
  t0: string; hasFilters: boolean; summary?: OpportunityPage['summary']; status: string;
  attention: Map<string, Opportunity & { reason: string }>;
  dragging?: boolean;
};
/** "23/10" for the compact card date; the year only matters in the list view and the detail. */
const shortDay = (value?: string | null) => (value ? value.slice(8, 10) + '/' + value.slice(5, 7) : '');
export function DealViews({ view, rows, stagesList, sort, sortBy, onSelect, onAdd, onDrag, move, moveBy,
  renderActions, who, stageName, ownerName, t0, hasFilters, summary, status, attention, dragging = false }: Props) {
  return view === 'list' ? (
          <Card as="section" className="card-fill">
            <div className="table-wrap fill">
              <table className="data-table deal-table">
                <thead>
                  <tr>
                    {([['title', 'Negócio'], ['stage', 'Etapa'], ['amount', 'Valor'], ['close', 'Previsão'], ['owner', 'Responsável'], ['stale', 'Parado há']] as [SortKey, string][]).map(([key, label]) => (
                      <th key={key} aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                        <button type="button" onClick={() => sortBy(key)}>{label}{sort.key === key && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
                      </th>
                    ))}
                    <th className="text-right">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const stale = r.status === 'open' ? staleDays(r) : null;
                    const overdue = r.status === 'open' && r.expected_close_date && r.expected_close_date < t0;
                    return (
                      <tr key={r.id} onClick={() => onSelect(r)}>
                        <td><strong>{r.title}</strong><small>{who(r)}</small></td>
                        <td>{stageName(r.stage_id)}</td>
                        <td>{brl(r.amount)}</td>
                        <td className={overdue ? 'text-danger' : ''}>{overdue ? 'Vencida · ' : ''}{day(r.expected_close_date)}</td>
                        <td>{ownerName(r.owner_id) || 'Sem responsável'}</td>
                        <td className={stale !== null && stale >= 14 ? 'text-danger' : ''}>{stale === null ? '—' : stale === 0 ? 'Hoje' : `${stale} ${stale === 1 ? 'dia' : 'dias'}`}</td>
                        <td>{renderActions(r, true)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {!rows.length && <EmptyState icon={<Handshake />} title="Nenhum negócio encontrado" description={hasFilters ? 'Ajuste ou limpe os filtros.' : undefined} />}
            </div>
          </Card>
        ) : (
          <KanbanBoard dragging={dragging}>
            {stagesList.map((stage) => {
              const cards = rows.filter((r) => r.stage_id === stage.id);
              const total = Number(summary?.stages[stage.id]?.amount || 0);
              const chance = stage.probability as number | null | undefined;
              return (
                <KanbanColumn
                  key={stage.id}
                  title={stage.name}
                  dot={stage.color}
                  count={summary?.stages[stage.id]?.count || 0}
                  total={brl(total)}
                  meta={status === 'open' && chance !== null && chance !== undefined ? <small>{chance}% · ponderado {brl(total * chance / 100)}</small> : undefined}
                  items={cards}
                  empty={(summary?.stages[stage.id]?.count || 0) > 0 ? 'Nenhum negócio nesta página' : 'Nenhum negócio'}
                  onAdd={status === 'open' ? () => onAdd(stage.id) : undefined}
                  addLabel={'Novo negócio em ' + stage.name}
                  onDropId={
                    status === 'open'
                      ? (id) => {
                          const row = rows.find((r) => r.id === id);
                          if (row && row.stage_id !== stage.id && row.status === 'open') void move(row, stage.id);
                        }
                      : undefined
                  }
                  render={(row) => {
                    const open = row.status === 'open';
                    const stale = open ? staleDays(row) : null;
                    const inStage = open ? inStageDays(row) : null;
                    const overdue = open && row.expected_close_date && row.expected_close_date < t0;
                    const reason = open ? attention.get(row.id)?.reason : undefined;
                    const people = who(row).split(' · ').filter((part) => part !== row.title).join(' · ');
                    const days = stale !== null && stale >= 7
                      ? { value: stale, tone: stale >= 14 ? 'danger' : 'warn', label: `Parado há ${stale} dias` }
                      : inStage !== null ? { value: inStage, tone: '', label: inStage === 0 ? 'Na etapa desde hoje' : `${inStage} ${inStage === 1 ? 'dia' : 'dias'} na etapa` } : null;
                    return (
                      <KanbanCard key={row.id} id={row.id} draggable={open} attention={reason} onOpen={() => onSelect(row)} onMove={(d) => moveBy(row, d)} onDragState={(d) => onDrag(d ? row.id : null)}>
                        <KanbanCardTitle title={row.title} onClick={() => onSelect(row)} />
                        {people && <KanbanCardText>{people}</KanbanCardText>}
                        <KanbanCardMeta>
                          <strong>{brl(row.amount)}</strong>
                          {row.expected_close_date && (
                            <small data-tip={(overdue ? 'Previsão de fechamento vencida: ' : 'Previsão de fechamento: ') + day(row.expected_close_date)} className={'deal-date' + (overdue ? ' overdue' : '')}>
                              <CalendarDays size={12} />{shortDay(row.expected_close_date)}
                            </small>
                          )}
                          {days && <small className={'deal-days ' + days.tone} data-tip={days.label} aria-label={days.label}>{days.value}d</small>}
                          {reason && <span className={'deal-flag ' + reason} data-tip={followUpReasons[reason]} aria-label={followUpReasons[reason]}><AlertCircle size={13} /></span>}
                        </KanbanCardMeta>
                        {renderActions(row)}
                      </KanbanCard>
                    );
                  }}
                />
              );
            })}
          </KanbanBoard>
        );
}
