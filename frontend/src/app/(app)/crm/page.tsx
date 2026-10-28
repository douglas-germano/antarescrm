'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, Pencil, CalendarPlus, MessageCircle, Phone, Mail, Check, Handshake, X, LayoutGrid, List, SlidersHorizontal, ArrowRightLeft } from 'lucide-react';
import { useList, usePage, useData, post, patch, refreshAll } from '@/lib/api';
import { brl, day, hour, rowOptions, opts, kinds, toLocalInput, today } from '@/lib/format';
import type { Field, Opportunity, OpportunityPage, Pipeline, PipelineStage, User, Activity } from '@/lib/types';
import { RecordActivityDialog, type ActivityRecord } from '@/components/contacts/record-activity-dialog';
import { SendWhatsAppDialog, type WhatsAppTarget } from '@/components/whatsapp/send-whatsapp-dialog';
import { useSession, useNotify } from '@/components/providers';
import { Button, Badge, PageHeader, EmptyState, DataState, SearchInput, FormDialog, Modal, Popover } from '@/components/ui';
import { DealViews } from '@/components/crm/deal-views';
import type { SortKey } from '@/components/crm/model';
import { Pager } from '@/components/fit';
import {
  Card,
  Tabs,
  Toolbar,
  ToolbarEnd,
} from '@/components/blocks';

const PERIODS = [
  { value: '', label: 'Qualquer previsão' }, { value: 'overdue', label: 'Previsão vencida' },
  { value: 'week', label: 'Próximos 7 dias' }, { value: 'month', label: 'Neste mês' }, { value: 'none', label: 'Sem previsão' },
];
export default function CRMPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const router = useRouter();
  const [pipelineId, setPipelineId] = useState('default');
  const pipelines = useData<{ items: Pipeline[] }>('/pipelines');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<Opportunity['status']>('open');
  const [attentionOnly, setAttentionOnly] = useState(false);
  const [requestedDeal, setRequestedDeal] = useState<string | null>(null);
  const followups = useData<{ items: (Opportunity & { reason: string })[]; total: number }>('/reports/follow-ups');
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
    if (params.get('new') === 'true') setEditing(null);
    // Links from Relatórios open the board on a status and funnel.
    const linked = params.get('status');
    if (linked === 'open' || linked === 'won' || linked === 'lost') setStatus(linked);
    if (params.get('pipeline')) setPipelineId(params.get('pipeline')!);
  }, []);
  const users = useList<User>('/users');
  const stages = useData<{ items: PipelineStage[] }>('/pipeline/stages?pipeline_id=' + pipelineId);
  const connection = useData<{ connected: boolean }>('/whatsapp/connection');
  const [whatsapp, setWhatsapp] = useState<WhatsAppTarget | null>(null);
  const [editing, setEditing] = useState<Opportunity | null | undefined>();
  const [newStage, setNewStage] = useState<string | null>(null);
  const [view, setView] = useState<'board' | 'list'>('board');
  const [owner, setOwner] = useState('');
  const [origin, setOrigin] = useState('');
  const [period, setPeriod] = useState('');
  const [minValue, setMinValue] = useState('');
  const [maxValue, setMaxValue] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'stale', dir: -1 });
  const [followup, setFollowup] = useState<ActivityRecord | null>(null);
  const [closeRow, setCloseRow] = useState<Opportunity | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overZone, setOverZone] = useState<'won' | 'lost' | null>(null);
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const requestedRecord = useData<Opportunity>(requestedDeal ? '/opportunities/' + requestedDeal : null);
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
  const [activityEdit, setActivityEdit] = useState<Activity | null | undefined>();
  const activities = useList<Activity>(selected ? '/activities?opportunity_id=' + selected.id : null);
  const detail = useData<Opportunity>(selected ? '/opportunities/' + selected.id : null);
  const linkedProject = useData<{ items: { id: string }[] }>(selected?.status === 'won' ? '/projects?opportunity_id=' + selected.id : null);
  const projectOf = linkedProject.data?.items?.[0];
  const stagesList = stages.data?.items || [];
  const userList = (users.data || []).filter((r) => r.active);
  const params = new URLSearchParams({ status, pipeline_id: pipelineId, search, owner_id: owner,
    source: origin, period, min_amount: minValue, max_amount: maxValue,
    attention: String(attentionOnly), sort: sort.key, direction: sort.dir === 1 ? 'asc' : 'desc' });
  const opportunities = usePage<Opportunity, OpportunityPage>('/opportunities?' + params);
  const rows = opportunities.data?.items || [];
  const sources = opportunities.data?.sources || [];
  const records = [...rows, ...(selected ? [detail.data || selected] : [])];
  const contactName = (id?: string | null) => records.find(r => r.contact_id === id)?.contact_name;
  const companyName = (id?: string | null) => records.find(r => r.company_id === id)?.company_name;
  const waTarget = (r: Opportunity): WhatsAppTarget | null => r.contact_phone
    ? { name: r.contact_name || r.title, phone: r.contact_phone, contact_id: r.contact_id || undefined, deal: r.title } : null;
  const who = (r: Opportunity) => [r.company_name, r.contact_name].filter(Boolean).join(' · ') || 'Sem contato';
  const t0 = today();
  const hasFilters = !!(owner || origin || period || minValue || maxValue || search);
  const activeFilters = [owner, origin, period, minValue || maxValue, attentionOnly].filter(Boolean).length;
  const stageName = (id: string) => stagesList.find((s) => s.id === id)?.name || '';
  const ownerName = (id?: string | null) => userList.find((u) => u.id === id)?.name || '';
  const anyProbability = stagesList.some((s) => s.probability !== null && s.probability !== undefined);
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
  async function move(row: Opportunity, stage_id: string) {
    try {
      await patch('/opportunities/' + row.id, { stage_id });
      await refreshAll();
      notify('Etapa atualizada.');
    } catch (e) {
      notify((e as Error).message, 'error');
    }
  }
  function moveBy(row: Opportunity, direction: -1 | 1) {
    if (row.status !== 'open') return;
    const next = stagesList[stagesList.findIndex((s) => s.id === row.stage_id) + direction];
    if (next) void move(row, next.id);
  }
  function startClose(row: Opportunity, kind: 'won' | 'lost') {
    setCloseError('');
    setLoss('');
    setCloseRow(row);
    setClosing(kind);
  }
  function renderActions(row: Opportunity, stop = false) {
    const contact = { name: row.contact_name, phone: row.contact_phone, email: row.contact_email };
    const wa = waTarget(row);
    const open = row.status === 'open';
    const click = (fn: () => void) => (e: React.MouseEvent) => { if (stop) e.stopPropagation(); fn(); };
    return (
      <div className="deal-actions" onClick={stop ? (e) => e.stopPropagation() : undefined}>
        {wa && <button type="button" className="icon-btn wa" data-tip="Enviar WhatsApp" aria-label={'Enviar WhatsApp para ' + contact?.name} onClick={click(() => setWhatsapp(wa))}><MessageCircle size={15} /></button>}
        {contact?.phone && <a className="icon-btn" href={'tel:' + contact.phone} data-tip="Ligar" aria-label={'Ligar para ' + contact.name}><Phone size={15} /></a>}
        {contact?.email && <a className="icon-btn" href={'mailto:' + contact.email} data-tip="Enviar e-mail" aria-label={'Enviar e-mail para ' + contact.name}><Mail size={15} /></a>}
        {open && <button type="button" className="icon-btn" data-tip="Agendar retorno" aria-label={'Agendar retorno de ' + row.title}
          onClick={click(() => setFollowup({ label: row.title, opportunity_id: row.id, contact_id: row.contact_id, company_id: row.company_id, owner_id: row.owner_id }))}><CalendarPlus size={15} /></button>}
        {open && !stop && <label className="stage-menu" data-tip="Mover para outra etapa">
          <ArrowRightLeft size={14} />
          <select aria-label={'Mover ' + row.title + ' para outra etapa'} value={row.stage_id} onChange={(e) => void move(row, e.target.value)}>
            <option disabled value="">Mover para…</option>
            {stagesList.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}
          </select>
        </label>}
        <span className="spacer" />
        {open && <button type="button" className="icon-btn win" data-tip="Fechar venda" aria-label={'Fechar venda de ' + row.title} onClick={click(() => startClose(row, 'won'))}><Check size={15} /></button>}
        {open && <button type="button" className="icon-btn lose" data-tip="Marcar como perdido" aria-label={'Marcar ' + row.title + ' como perdido'} onClick={click(() => startClose(row, 'lost'))}><X size={15} /></button>}
      </div>
    );
  }
  async function closeDeal() {
    if (!closeTarget || !closing) return;
    setBusy(true);
    setCloseError('');
    try {
      const result = await post<Opportunity>(
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
      <PageHeader compact title="Funil de vendas"
        aside={(pipelines.data?.items.length || 0) > 1
          ? <select className="pipeline-select" aria-label="Funil de vendas" value={pipelineId} onChange={e => { setPipelineId(e.target.value); setSelected(null); }}>{pipelines.data?.items.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}</select>
          : pipelines.data?.items[0] && <span className="pipeline-name">{pipelines.data.items[0].name}</span>}>
        <Button disabled={!stagesList.length} onClick={() => { setNewStage(null); setEditing(null); }}>
          <Plus size={17} /> Novo negócio
        </Button>
      </PageHeader>
      <Toolbar>
        <Tabs
          label="Situação dos negócios"
          value={status}
          onChange={value => setStatus(value as Opportunity['status'])}
          items={[
            { value: 'open', label: 'Em aberto' },
            { value: 'won', label: 'Ganhos' },
            { value: 'lost', label: 'Perdidos' },
          ]}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Buscar negócio, contato ou empresa" />
        <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" panelClassName="filter-panel"
          badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
          <label className="field"><span>Responsável</span>
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">Todos os responsáveis</option>
              <option value="none">Sem responsável</option>
              {userList.map((u) => <option value={u.id} key={u.id}>{u.name}</option>)}
            </select></label>
          <label className="field"><span>Origem</span>
            <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
              <option value="">Todas as origens</option>
              {sources.map((o) => <option value={o} key={o}>{o}</option>)}
            </select></label>
          <label className="field"><span>Previsão de fechamento</span>
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {PERIODS.map((p) => <option value={p.value} key={p.value}>{p.label}</option>)}
            </select></label>
          <div className="field"><span>Valor</span>
            <span className="money-range">
              <input type="number" inputMode="decimal" min={0} aria-label="Valor mínimo" placeholder="Mínimo" value={minValue} onChange={(e) => setMinValue(e.target.value)} />
              <input type="number" inputMode="decimal" min={0} aria-label="Valor máximo" placeholder="Máximo" value={maxValue} onChange={(e) => setMaxValue(e.target.value)} />
            </span></div>
          {status === 'open' && (
            <label className="checkbox-label"><input type="checkbox" checked={attentionOnly} disabled={!followups.data || !!followups.error} onChange={e => setAttentionOnly(e.target.checked)} />Precisam de acompanhamento{followups.data ? ` (${followups.data.total})` : ''}</label>
          )}
        </>}</Popover>
        {(hasFilters || attentionOnly) && (
          <Button variant="ghost" onClick={() => { setOwner(''); setOrigin(''); setPeriod(''); setMinValue(''); setMaxValue(''); setSearch(''); setAttentionOnly(false); }}><X size={14} />Limpar</Button>
        )}
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
              <strong>{opportunities.data?.total || 0}</strong> {opportunities.data?.total === 1 ? 'negócio' : 'negócios'}
            </span>
            <span>
              {status === 'open' ? 'Em negociação' : status === 'won' ? 'Vendido' : 'Perdido'}{' '}
              <strong>{brl(opportunities.data?.summary.amount)}</strong>
            </span>
            {status === 'open' && anyProbability && (
              <span title="Valor de cada etapa multiplicado pela sua probabilidade de ganho">
                Previsão ponderada <strong>{brl(opportunities.data?.summary.weighted)}</strong>
              </span>
            )}
          </div>
        </ToolbarEnd>
      </Toolbar>
      {(followups.error || opportunities.data?.total === 0) && <div className="crm-filters">
        {followups.error && <span role="status" className="crm-hint">Não foi possível carregar os alertas de acompanhamento.</span>}
        {opportunities.data?.total === 0 && <span className="crm-hint">Cadastre o primeiro contato em <Link href="/contatos">Contatos</Link> para iniciar uma negociação.</span>}
      </div>}
      <DataState
        loading={opportunities.isLoading || stages.isLoading}
        error={opportunities.error || stages.error}
      >
        {!stagesList.length ? (
          <EmptyState
            icon={<Handshake />}
            title="Configure seu funil"
            action={<Link className="btn btn-primary" href="/configuracoes?tab=funis">Configurar etapas</Link>}
          />
        ) : <DealViews view={view} rows={rows} stagesList={stagesList} sort={sort} sortBy={sortBy}
          onSelect={setSelected} onAdd={stage => { setNewStage(stage); setEditing(null); }} onDrag={setDragId}
          move={move} moveBy={moveBy} renderActions={renderActions} who={who} stageName={stageName} ownerName={ownerName}
          t0={t0} hasFilters={hasFilters} summary={opportunities.data?.summary} status={status} attention={attention} dragging={!!dragId} /> }
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
      {opportunities.data && opportunities.data.pages > 1 && <Pager page={opportunities.page - 1} pages={Math.max(1, opportunities.data.pages)}
        onChange={page => opportunities.setPage(page + 1)} total={opportunities.data.total}
        from={opportunities.data.total ? (opportunities.page - 1) * opportunities.size + 1 : 0}
        to={Math.min(opportunities.data.total, opportunities.page * opportunities.size)} />}
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
          if (editing && selected?.id === editing.id) setSelected({ ...selected, ...body } as Opportunity);
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
              : <Button variant="secondary" onClick={async () => { try { const created = await post<{ id: string }>('/projects', { opportunity_id: selected.id }); await refreshAll(); router.push('/projetos/' + created.id); } catch (e) { notify((e as Error).message, 'error'); } }}>Criar projeto</Button>)}
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
              {(detail.data?.history || []).map((h) => (
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
