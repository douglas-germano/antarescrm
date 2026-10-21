'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, Pencil, CalendarDays, CalendarPlus, MessageCircle, Phone, Mail, Check, Handshake, X, ChevronsUpDown, ArrowUp, ArrowDown, LayoutGrid, List } from 'lucide-react';
import { useList, useData, post, patch, refreshAll } from '@/lib/api';
import { brl, day, hour, rowOptions, opts, kinds, toLocalInput, today, searchMatch } from '@/lib/format';
import type { Field, Row } from '@/lib/types';
import { RecordActivityDialog, type ActivityRecord } from '@/components/record-activity-dialog';
import { SendWhatsAppDialog, type WhatsAppTarget } from '@/components/send-whatsapp-dialog';
import { followUpReasons } from '@/components/follow-up-queue';
import { useSession, useNotify } from '@/components/providers';
import { Button, Badge, PageHeader, EmptyState, DataState, SearchInput, FormDialog, Modal } from '@/components/ui';
import {
  Card,
  KanbanBoard,
  KanbanColumn,
  KanbanCard,
  KanbanCardTitle,
  KanbanCardText,
  KanbanCardMeta,
  Tabs,
  Toolbar,
  ToolbarEnd,
} from '@/components/blocks';

const DAY = 86400000;
const PERIODS = [
  { value: '', label: 'Qualquer previsão' },
  { value: 'overdue', label: 'Previsão vencida' },
  { value: 'week', label: 'Próximos 7 dias' },
  { value: 'month', label: 'Neste mês' },
  { value: 'none', label: 'Sem previsão' },
];
const addDays = (iso: string, n: number) => new Date(Date.parse(iso + 'T12:00:00Z') + n * DAY).toISOString().slice(0, 10);
/** Days since the last sign of life on a deal: its latest completed activity or stage move. */
const staleDays = (row: Row) => {
  const times = [row.last_contact_at, row.stage_changed_at].filter(Boolean).map((v: string) => Date.parse(v));
  return times.length ? Math.max(0, Math.floor((Date.now() - Math.max(...times)) / DAY)) : null;
};
const inStageDays = (row: Row) => (row.stage_changed_at ? Math.max(0, Math.floor((Date.now() - Date.parse(row.stage_changed_at)) / DAY)) : null);
type SortKey = 'title' | 'stage' | 'amount' | 'close' | 'owner' | 'stale';

export default function CRMPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const router = useRouter();
  const [pipelineId, setPipelineId] = useState('default');
  const pipelines = useData<{ items: Row[] }>('/pipelines');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('open');
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [requestedDeal, setRequestedDeal] = useState<string | null>(null);
  const followups = useData<{ items: Row[]; total: number }>('/reports/follow-ups');
  const attention = new Map((followups.data?.items || []).map(row => [row.id, row]));
  useEffect(() => {
    try { if (localStorage.getItem('antares.crm.view') === 'list') setView('list'); } catch { /* optional preference */ }
  }, []);
  function changeView(next: 'board' | 'list') {
    setView(next);
    try { localStorage.setItem('antares.crm.view', next); } catch { /* optional preference */ }
  }
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setAttentionOnly(params.get('attention') === 'true');
    setRequestedDeal(params.get('opportunity'));
  }, []);
  const opportunities = useList('/opportunities?status=' + status + '&pipeline_id=' + pipelineId);
  const contacts = useList('/contacts');
  const companies = useList('/companies');
  const users = useList('/users');
  const stages = useData<{ items: Row[] }>('/pipeline/stages?pipeline_id=' + pipelineId);
  const connection = useData<Row>('/whatsapp/connection');
  const [whatsapp, setWhatsapp] = useState<WhatsAppTarget | null>(null);
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [newStage, setNewStage] = useState<string | null>(null);
  const [view, setView] = useState<'board' | 'list'>('board');
  const [owner, setOwner] = useState('');
  const [origin, setOrigin] = useState('');
  const [period, setPeriod] = useState('');
  const [minValue, setMinValue] = useState('');
  const [maxValue, setMaxValue] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'stale', dir: -1 });
  const [followup, setFollowup] = useState<ActivityRecord | null>(null);
  const [closeRow, setCloseRow] = useState<Row | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overZone, setOverZone] = useState<'won' | 'lost' | null>(null);
  const [selected, setSelected] = useState<Row | null>(null);
  const requestedRecord = useData<Row>(requestedDeal ? '/opportunities/' + requestedDeal : null);
  useEffect(() => {
    if (!requestedDeal) return;
    if (requestedRecord.data) {
      setStatus(requestedRecord.data.status);
      setPipelineId(requestedRecord.data.pipeline_id || 'default');
      setSelected(requestedRecord.data);
      setRequestedDeal(null);
    } else if (requestedRecord.error) {
      notify('Não foi possível abrir o negócio solicitado.', 'error');
      setRequestedDeal(null);
    }
  }, [requestedDeal, requestedRecord.data, requestedRecord.error, notify]);
  const [closing, setClosing] = useState<'won' | 'lost' | null>(null);
  const [loss, setLoss] = useState('');
  const [busy, setBusy] = useState(false);
  const [closeError, setCloseError] = useState('');
  const [activityEdit, setActivityEdit] = useState<Row | null | undefined>();
  const activities = useList(selected ? '/activities?opportunity_id=' + selected.id : null);
  const detail = useData<Row>(selected ? '/opportunities/' + selected.id : null);
  const linkedProject = useData<{ items: Row[] }>(selected?.status === 'won' ? '/projects?opportunity_id=' + selected.id : null);
  const projectOf = linkedProject.data?.items?.[0];
  const stagesList = stages.data?.items || [];
  const contactList = contacts.data || [];
  const companyList = companies.data || [];
  const userList = (users.data || []).filter((r) => r.active);
  const contactName = (id?: string) => contactList.find((c) => c.id === id)?.name;
  const companyName = (id?: string) => companyList.find((c) => c.id === id)?.name;
  const waTarget = (r: Row): WhatsAppTarget | null => {
    const contact = contactList.find((c) => c.id === r.contact_id);
    return contact?.phone ? { name: contact.name, phone: contact.phone, contact_id: contact.id, deal: r.title } : null;
  };
  const who = (r: Row) => [companyName(r.company_id), contactName(r.contact_id)].filter(Boolean).join(' · ') || 'Sem contato';
  const allRows = opportunities.data || [];
  const sources = [...new Set<string>(contactList.map((c) => c.source).filter(Boolean))].sort();
  const t0 = today();
  const matchesPeriod = (r: Row) => {
    const d: string | null = r.expected_close_date;
    if (period === 'overdue') return !!d && d < t0;
    if (period === 'week') return !!d && d >= t0 && d <= addDays(t0, 7);
    if (period === 'month') return !!d && d.slice(0, 7) === t0.slice(0, 7);
    if (period === 'none') return !d;
    return true;
  };
  const filtered = allRows
    .filter(row => !attentionOnly || status !== 'open' || !followups.data || attention.has(row.id))
    .filter((r) => searchMatch(search, [r.title, who(r), contactList.find((c) => c.id === r.contact_id)?.phone, contactList.find((c) => c.id === r.contact_id)?.email]))
    .filter((r) => !owner || (owner === 'none' ? !r.owner_id : r.owner_id === owner))
    .filter((r) => !origin || contactList.find((c) => c.id === r.contact_id)?.source === origin)
    .filter((r) => (minValue === '' || Number(r.amount) >= Number(minValue)) && (maxValue === '' || Number(r.amount) <= Number(maxValue)))
    .filter(matchesPeriod);
  const rows = filtered;
  const hasFilters = !!(owner || origin || period || minValue || maxValue || search);
  const stageName = (id: string) => stagesList.find((s) => s.id === id)?.name || '';
  const ownerName = (id?: string) => userList.find((u) => u.id === id)?.name || '';
  const probability = new Map(stagesList.map((s) => [s.id, s.probability as number | null]));
  const anyProbability = stagesList.some((s) => s.probability !== null && s.probability !== undefined);
  const weighted = (items: Row[]) => items.reduce((sum, r) => sum + Number(r.amount) * ((probability.get(r.stage_id) ?? 0) / 100), 0);
  const sortValue = (r: Row): string | number => ({
    title: r.title.toLowerCase(), stage: stagesList.findIndex((s) => s.id === r.stage_id), amount: Number(r.amount),
    close: r.expected_close_date || '9999', owner: ownerName(r.owner_id).toLowerCase(), stale: staleDays(r) ?? -1,
  })[sort.key];
  const sortedRows = [...rows].sort((a, b) => (sortValue(a) < sortValue(b) ? -1 : sortValue(a) > sortValue(b) ? 1 : 0) * sort.dir);
  function sortBy(key: SortKey) { setSort((c) => (c.key === key ? { key, dir: (c.dir * -1) as 1 | -1 } : { key, dir: key === 'amount' || key === 'stale' ? -1 : 1 })); }
  const closeTarget = closeRow || selected;
  const fields: Field[] = [
    { name: 'title', label: 'Título do negócio', required: true, placeholder: 'Plano anual — Empresa X' },
    { name: 'contact_id', label: 'Contato', type: 'contact' },
    { name: 'company_id', label: 'Empresa', type: 'company', help: 'Se vazio, usa a empresa do contato.' },
    { name: 'stage_id', label: 'Etapa', type: 'select', required: true, options: rowOptions(stagesList) },
    { name: 'amount', label: 'Valor estimado (R$)', type: 'money', min: 0 },
    { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions(userList) },
    { name: 'expected_close_date', label: 'Previsão de fechamento', type: 'date' },
    { name: 'description', label: 'Descrição', type: 'textarea', wide: true },
  ];
  const activityFields: Field[] = [
    { name: 'title', label: 'Atividade', required: true },
    { name: 'kind', label: 'Tipo', type: 'select', options: opts(kinds), defaultValue: 'follow_up' },
    { name: 'scheduled_at', label: 'Data e hora', type: 'datetime-local', required: true },
    { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions(userList) },
    { name: 'notes', label: 'Observações', type: 'textarea', wide: true },
  ];
  async function move(row: Row, stage_id: string) {
    try {
      await patch('/opportunities/' + row.id, { stage_id });
      await refreshAll();
      notify('Etapa atualizada.');
    } catch (e) {
      notify((e as Error).message, 'error');
    }
  }
  function moveBy(row: Row, direction: -1 | 1) {
    if (row.status !== 'open') return;
    const next = stagesList[stagesList.findIndex((s) => s.id === row.stage_id) + direction];
    if (next) void move(row, next.id);
  }
  function startClose(row: Row, kind: 'won' | 'lost') {
    setCloseError('');
    setLoss('');
    setCloseRow(row);
    setClosing(kind);
  }
  function renderActions(row: Row, stop = false) {
    const contact = contactList.find((c) => c.id === row.contact_id);
    const wa = waTarget(row);
    const open = row.status === 'open';
    const click = (fn: () => void) => (e: React.MouseEvent) => { if (stop) e.stopPropagation(); fn(); };
    return (
      <div className="deal-actions" onClick={stop ? (e) => e.stopPropagation() : undefined}>
        {wa && <button type="button" className="icon-btn wa" title="Enviar WhatsApp" aria-label={'Enviar WhatsApp para ' + contact?.name} onClick={click(() => setWhatsapp(wa))}><MessageCircle size={15} /></button>}
        {contact?.phone && <a className="icon-btn" href={'tel:' + contact.phone} title="Ligar" aria-label={'Ligar para ' + contact.name}><Phone size={15} /></a>}
        {contact?.email && <a className="icon-btn" href={'mailto:' + contact.email} title="Enviar e-mail" aria-label={'Enviar e-mail para ' + contact.name}><Mail size={15} /></a>}
        {open && <button type="button" className="icon-btn" title="Agendar retorno" aria-label={'Agendar retorno de ' + row.title}
          onClick={click(() => setFollowup({ label: row.title, opportunity_id: row.id, contact_id: row.contact_id, company_id: row.company_id, owner_id: row.owner_id }))}><CalendarPlus size={15} /></button>}
        <span className="spacer" />
        {open && <button type="button" className="icon-btn win" title="Fechar venda" aria-label={'Fechar venda de ' + row.title} onClick={click(() => startClose(row, 'won'))}><Check size={15} /></button>}
        {open && <button type="button" className="icon-btn lose" title="Marcar como perdido" aria-label={'Marcar ' + row.title + ' como perdido'} onClick={click(() => startClose(row, 'lost'))}><X size={15} /></button>}
      </div>
    );
  }
  async function closeDeal() {
    if (!closeTarget || !closing) return;
    setBusy(true);
    setCloseError('');
    try {
      const result = await post(
        '/opportunities/' + closeTarget.id + '/close',
        closing === 'won' ? { status: 'won' } : { status: 'lost', loss_reason: loss.trim() },
      );
      await refreshAll();
      if (closeRow) setCloseRow(null); else setSelected(result);
      setClosing(null);
      notify(closing === 'won' ? 'Venda fechada.' : 'Negócio encerrado.');
    } catch (e) {
      setCloseError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <PageHeader compact title="Funil de vendas">
        <select aria-label="Funil de vendas" value={pipelineId} onChange={e => { setPipelineId(e.target.value); setSelected(null); }}>{pipelines.data?.items.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}</select>
        <Button disabled={!stagesList.length} onClick={() => { setNewStage(null); setEditing(null); }}>
          <Plus size={17} /> Novo negócio
        </Button>
      </PageHeader>
      <Toolbar>
        <Tabs
          label="Situação dos negócios"
          value={status}
          onChange={setStatus}
          items={[
            { value: 'open', label: 'Em aberto' },
            { value: 'won', label: 'Ganhos' },
            { value: 'lost', label: 'Perdidos' },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Buscar negócio, contato ou empresa" />
        <Tabs
          label="Visualização"
          value={view}
          onChange={changeView}
          items={[
            { value: 'board', label: 'Quadro', icon: <LayoutGrid size={14} /> },
            { value: 'list', label: 'Lista', icon: <List size={14} /> },
          ]}
        />
        <ToolbarEnd>
          <div className="summary-inline">
            <span>
              <strong>{rows.length}</strong> {rows.length === 1 ? 'negócio' : 'negócios'}
            </span>
            <span>
              {status === 'open' ? 'Em negociação' : status === 'won' ? 'Vendido' : 'Perdido'}{' '}
              <strong>{brl(rows.reduce((s, r) => s + Number(r.amount), 0))}</strong>
            </span>
            {status === 'open' && anyProbability && (
              <span title="Valor de cada etapa multiplicado pela sua probabilidade de ganho">
                Previsão ponderada <strong>{brl(weighted(rows))}</strong>
              </span>
            )}
          </div>
        </ToolbarEnd>
      </Toolbar>
      <div className="crm-filters">
        <select aria-label="Responsável" value={owner} onChange={(e) => setOwner(e.target.value)}>
          <option value="">Todos os responsáveis</option>
          <option value="none">Sem responsável</option>
          {userList.map((u) => <option value={u.id} key={u.id}>{u.name}</option>)}
        </select>
        <select aria-label="Origem" value={origin} onChange={(e) => setOrigin(e.target.value)}>
          <option value="">Todas as origens</option>
          {sources.map((o) => <option value={o} key={o}>{o}</option>)}
        </select>
        <select aria-label="Previsão de fechamento" value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option value={p.value} key={p.value}>{p.label}</option>)}
        </select>
        <span className="money-range">
          <input type="number" inputMode="decimal" min={0} aria-label="Valor mínimo" placeholder="Valor mín." value={minValue} onChange={(e) => setMinValue(e.target.value)} />
          <input type="number" inputMode="decimal" min={0} aria-label="Valor máximo" placeholder="Valor máx." value={maxValue} onChange={(e) => setMaxValue(e.target.value)} />
        </span>
        {status === 'open' && (
          <label className="checkbox-label"><input type="checkbox" checked={attentionOnly} disabled={!followups.data || !!followups.error} onChange={e => setAttentionOnly(e.target.checked)} />Precisam de acompanhamento{followups.data ? ` (${followups.data.total})` : ''}</label>
        )}
        {(hasFilters || attentionOnly) && (
          <button type="button" className="link-btn" onClick={() => { setOwner(''); setOrigin(''); setPeriod(''); setMinValue(''); setMaxValue(''); setSearch(''); setAttentionOnly(false); }}>Limpar filtros</button>
        )}
        {followups.error && <span role="status" className="crm-hint">Não foi possível carregar os alertas de acompanhamento.</span>}
        {!contactList.length && !contacts.isLoading && <span className="crm-hint">Cadastre o primeiro contato em <Link href="/contatos">Contatos</Link> para iniciar uma negociação.</span>}
      </div>
      <DataState
        loading={opportunities.isLoading || stages.isLoading || contacts.isLoading}
        error={opportunities.error || stages.error || contacts.error}
      >
        {!stagesList.length ? (
          <EmptyState
            icon={<Handshake />}
            title="Configure seu funil"
            action={<Link className="btn btn-primary" href="/configuracoes?tab=funis">Configurar etapas</Link>}
          />
        ) : view === 'list' ? (
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
                  {sortedRows.map((r) => {
                    const stale = r.status === 'open' ? staleDays(r) : null;
                    const overdue = r.status === 'open' && r.expected_close_date && r.expected_close_date < t0;
                    return (
                      <tr key={r.id} onClick={() => setSelected(r)}>
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
          <KanbanBoard>
            {stagesList.map((stage) => {
              const cards = rows.filter((r) => r.stage_id === stage.id);
              const total = cards.reduce((s, r) => s + Number(r.amount), 0);
              const chance = stage.probability as number | null | undefined;
              return (
                <KanbanColumn
                  key={stage.id}
                  title={stage.name}
                  dot={stage.color}
                  count={cards.length}
                  meta={<>
                    <span>{brl(total)}</span>
                    {status === 'open' && chance !== null && chance !== undefined && <small>{chance}% · ponderado {brl(total * chance / 100)}</small>}
                  </>}
                  items={cards}
                  empty="Nenhum negócio"
                  onAdd={status === 'open' ? () => { setNewStage(stage.id); setEditing(null); } : undefined}
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
                    return (
                      <KanbanCard key={row.id} id={row.id} draggable={open} onOpen={() => setSelected(row)} onMove={(d) => moveBy(row, d)} onDragState={(d) => setDragId(d ? row.id : null)}>
                        <KanbanCardTitle title={row.title} onClick={() => setSelected(row)} />
                        <KanbanCardText>{who(row)}</KanbanCardText>
                        {(reason || stale !== null) && (
                          <div className="deal-chips">
                            {reason && <span className={'deal-attention ' + reason} title={followUpReasons[reason]}>{followUpReasons[reason]}</span>}
                            {stale !== null && stale >= 7
                              ? <span className={'deal-chip ' + (stale >= 14 ? 'danger' : 'warn')} title="Dias desde a última atividade ou mudança de etapa">Parado há {stale} dias</span>
                              : inStage !== null && <span className="deal-chip" title="Tempo nesta etapa">{inStage === 0 ? 'Na etapa hoje' : `${inStage} ${inStage === 1 ? 'dia' : 'dias'} na etapa`}</span>}
                          </div>
                        )}
                        <KanbanCardMeta>
                          <strong>{brl(row.amount)}</strong>
                          <small title="Previsão de fechamento" className={'deal-date' + (overdue ? ' overdue' : '')}>
                            <CalendarDays size={13} /> {overdue ? 'Vencida · ' : ''}{day(row.expected_close_date)}
                          </small>
                          {open && (
                            <label className="stage-menu" title="Mover para outra etapa">
                              <ChevronsUpDown size={15} />
                              <select aria-label={'Etapa de ' + row.title} value={row.stage_id} onChange={(e) => void move(row, e.target.value)}>
                                {stagesList.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}
                              </select>
                            </label>
                          )}
                        </KanbanCardMeta>
                        {renderActions(row)}
                      </KanbanCard>
                    );
                  }}
                />
              );
            })}
          </KanbanBoard>
        )}
      </DataState>
      {dragId && status === 'open' && view === 'board' && (
        <div className="drop-zones" aria-hidden="true">
          {(['won', 'lost'] as const).map((kind) => (
            <div key={kind} className={'drop-zone ' + (kind === 'won' ? 'win' : 'lose') + (overZone === kind ? ' over' : '')}
              onDragOver={(e) => { e.preventDefault(); setOverZone(kind); }}
              onDragLeave={() => setOverZone(null)}
              onDrop={(e) => {
                e.preventDefault();
                const row = rows.find((r) => r.id === e.dataTransfer.getData('text/plain'));
                setOverZone(null); setDragId(null);
                if (row) startClose(row, kind);
              }}>
              {kind === 'won' ? <><Check size={16} /> Fechar venda</> : <><X size={16} /> Marcar como perdido</>}
            </div>
          ))}
        </div>
      )}
      <RecordActivityDialog record={followup} onClose={() => setFollowup(null)} />
      <SendWhatsAppDialog target={whatsapp} connected={!!connection.data?.connected} onClose={() => setWhatsapp(null)} />
      <FormDialog
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
        title={editing ? 'Editar negócio' : 'Novo negócio'}
        fields={fields}
        initial={editing || { stage_id: newStage || stagesList[0]?.id, amount: '0.00', owner_id: user?.id }}
        onSubmit={async (data) => {
          const body = {
            ...data,
            contact_id: data.contact_id || null,
            company_id: data.company_id || null,
            owner_id: data.owner_id || null,
            description: data.description || null,
            expected_close_date: data.expected_close_date || null,
          };
          await (editing ? patch('/opportunities/' + editing.id, body) : post('/opportunities', body));
          await refreshAll();
          if (editing && selected?.id === editing.id) setSelected({ ...selected, ...body } as Row);
          setEditing(undefined);
          notify('Negócio salvo.');
        }}
      />
      <Modal open={!!selected} onClose={() => setSelected(null)} title={selected?.title || 'Negócio'} wide>
        <div className="stack">
          <div className="record-summary">
            <Badge value={selected?.status || 'open'} />
            <strong className="crm-detail-value">{brl(selected?.amount)}</strong>
            {selected?.status === 'won' && (projectOf
              ? <Link className="btn btn-secondary" href={'/projetos/' + projectOf.id}>Abrir projeto</Link>
              : <Button variant="secondary" onClick={async () => { try { const created = await post('/projects', { opportunity_id: selected.id }); await refreshAll(); router.push('/projetos/' + created.id); } catch (e) { notify((e as Error).message, 'error'); } }}>Criar projeto</Button>)}
            {selected && waTarget(selected) && (
              <Button variant="secondary" onClick={() => setWhatsapp(waTarget(selected))}>
                <MessageCircle size={15} /> WhatsApp
              </Button>
            )}
            {selected?.status === 'open' && (
              <Button variant="secondary" onClick={() => setEditing(detail.data || selected)}>
                <Pencil size={15} /> Editar
              </Button>
            )}
          </div>
          <dl className="record-details">
            <div><dt>Contato</dt><dd>{contactName(selected?.contact_id) || 'Não informado'}</dd></div>
            <div><dt>Empresa</dt><dd>{companyName(selected?.company_id) || 'Não informada'}</dd></div>
            <div><dt>Responsável</dt><dd>{userList.find((u) => u.id === selected?.owner_id)?.name || 'Sem responsável'}</dd></div>
            <div><dt>Previsão de fechamento</dt><dd>{day(selected?.expected_close_date)}</dd></div>
            <div><dt>Etapa atual</dt><dd>{stagesList.find((s) => s.id === selected?.stage_id)?.name || 'Não informada'}</dd></div>
          </dl>
          {selected?.description && (
            <section className="record-section">
              <h3>Descrição</h3>
              <p className="record-notes muted">{selected.description}</p>
            </section>
          )}
          {selected?.loss_reason && <p>Motivo da perda: {selected.loss_reason}</p>}
          {selected?.status === 'open' && (
            <div className="toolbar">
              <Button
                onClick={() => {
                  setCloseError('');
                  setClosing('won');
                }}
              >
                <Check size={16} /> Fechar venda
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setCloseError('');
                  setLoss('');
                  setClosing('lost');
                }}
              >
                <X size={16} /> Marcar como perdido
              </Button>
            </div>
          )}
          <section className="record-section">
            <div className="toolbar">
              <h3>Atividades</h3>
              <Button variant="secondary" onClick={() => setActivityEdit(null)}>
                <Plus size={16} /> Agendar atividade
              </Button>
            </div>
            <DataState loading={activities.isLoading} error={activities.error}>
              {!(activities.data || []).length ? (
                <p className="muted">Nenhuma atividade agendada.</p>
              ) : (
                activities.data!.map((a) => (
                  <Card className="card-body stack" key={a.id}>
                    <div className="toolbar">
                      <strong>{a.title}</strong>
                      <Badge value={a.status} />
                      <Button variant="ghost" aria-label={'Editar atividade ' + a.title} onClick={() => setActivityEdit(a)}>
                        <Pencil size={15} />
                      </Button>
                    </div>
                    <p className="muted">
                      {kinds[a.kind] || a.kind} · {day(a.scheduled_at)} às {hour(a.scheduled_at)}
                    </p>
                    {a.notes && <p>{a.notes}</p>}
                    {a.status === 'pending' && (
                      <div className="row-actions">
                        <Button
                          variant="secondary"
                          onClick={async () => {
                            try {
                              await patch('/activities/' + a.id, { status: 'completed' });
                              await refreshAll();
                              notify('Atividade concluída.');
                            } catch (e) {
                              notify((e as Error).message, 'error');
                            }
                          }}
                        >
                          <Check size={15} /> Concluir
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={async () => {
                            try {
                              await patch('/activities/' + a.id, { status: 'cancelled' });
                              await refreshAll();
                              notify('Atividade cancelada.');
                            } catch (e) {
                              notify((e as Error).message, 'error');
                            }
                          }}
                        >
                          Cancelar
                        </Button>
                      </div>
                    )}
                  </Card>
                ))
              )}
            </DataState>
          </section>
          <section className="record-section">
            <h3>Histórico de etapas</h3>
            <DataState loading={detail.isLoading} error={detail.error}>
              {(detail.data?.history || []).map((h: Row) => (
                <p key={h.id} className="muted">
                  {day(h.created_at)} · {stagesList.find((s) => s.id === h.to_stage_id)?.name || 'Etapa'}
                </p>
              ))}
            </DataState>
          </section>
        </div>
      </Modal>
      <Modal
        open={!!closing}
        onClose={() => {
          if (!busy) { setClosing(null); setCloseRow(null); }
        }}
        title={closing === 'won' ? 'Fechar venda' : 'Encerrar negócio'}
      >
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            void closeDeal();
          }}
        >
          {closing === 'won' ? (
            <p>O negócio {closeTarget?.title ? `“${closeTarget.title}” ` : ''}será marcado como ganho com o valor de {brl(closeTarget?.amount)}.</p>
          ) : (
            <div className="field">
              <label htmlFor="loss-reason">
                Motivo da perda <span className="required">*</span>
              </label>
              <textarea id="loss-reason" value={loss} onChange={(e) => setLoss(e.target.value)} required maxLength={2000} rows={4} />
            </div>
          )}
          {closeError && (
            <p role="alert" className="form-error">
              {closeError}
            </p>
          )}
          <div className="modal-footer">
            <Button variant="secondary" disabled={busy} onClick={() => { setClosing(null); setCloseRow(null); }}>
              Cancelar
            </Button>
            <Button type="submit" disabled={busy || (closing === 'lost' && !loss.trim())}>
              {busy ? 'Salvando…' : closing === 'won' ? 'Confirmar venda' : 'Confirmar perda'}
            </Button>
          </div>
        </form>
      </Modal>
      <FormDialog
        open={activityEdit !== undefined}
        onClose={() => setActivityEdit(undefined)}
        title={activityEdit ? 'Editar atividade' : 'Agendar atividade'}
        fields={activityFields}
        initial={
          activityEdit
            ? { ...activityEdit, scheduled_at: toLocalInput(activityEdit.scheduled_at) }
            : { kind: 'follow_up', owner_id: user?.id }
        }
        onSubmit={async (data) => {
          const body = { ...data, owner_id: data.owner_id || null, notes: data.notes || null };
          await (activityEdit
            ? patch('/activities/' + activityEdit.id, body)
            : post('/activities', {
                ...body,
                opportunity_id: selected!.id,
                contact_id: selected!.contact_id || null,
                company_id: selected!.company_id || null,
              }));
          await refreshAll();
          setActivityEdit(undefined);
          notify('Atividade salva.');
        }}
      />
    </div>
  );
}
