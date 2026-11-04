import { RecordLink } from '@/components/record-link';
import { useEffect, useState } from 'react';
import { useAppRouter } from '@/lib/navigation';
import { ChevronLeft, ChevronRight, CalendarDays, ArrowUpRight, Plus, SlidersHorizontal, X } from 'lucide-react';
import { useData, useList, post, refreshAll } from '@/lib/api';
import { PageHeader, Button, DataState, EmptyState, FormDialog, Modal, SearchInput, Popover } from '@/components/ui';
import { today, day, getZone, hour, kinds, opts, rowOptions, searchMatch } from '@/lib/format';
import { useSession, useNotify } from '@/components/providers';
import { PagedTable, useElementHeight } from '@/components/fit';
import { Card, Tabs } from '@/components/blocks';
import type { Row } from '@/lib/types';
const KIND_LABELS: Record<string, string> = { ...kinds, task: 'Tarefa', booking: 'Agendamento' };
/** Bookings are meetings someone scheduled through a link; they get their own colour. */
const kindOf = (event: Row) => (event.booking_id ? 'booking' : event.kind);
const ymd = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export default function Calendar() {
  const router = useAppRouter();
  const { user } = useSession();
  const { notify } = useNotify();
  const [selected, setSelected] = useState<Row | null>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const [dayList, setDayList] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState('');
  const [mine, setMine] = useState(false);
  const contacts = useList('/contacts');
  const users = useList('/users');
  const [current, setCurrent] = useState(() => new Date(today() + 'T12:00:00'));
  const [mode, setMode] = useState('month');
  const [search, setSearch] = useState('');
  // Booking links moved to Configurações; old links to the availability view land there.
  useEffect(() => { if (new URLSearchParams(window.location.search).get('view') === 'availability') void router.replace('/configuracoes?tab=agendamento'); }, [router]);
  const first = new Date(current.getFullYear(), current.getMonth(), 1);
  const last = new Date(current.getFullYear(), current.getMonth() + 1, 0);
  const { data, isLoading, error } = useData<{ items: Row[] }>('/calendar?start=' + ymd(first) + '&end=' + ymd(last));
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  const count = Math.ceil((first.getDay() + last.getDate()) / 7) * 7;
  const days = Array.from({ length: count }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
  const contactOf = (event: Row) => contacts.data?.find((c) => c.id === event.contact_id);
  const activeFilters = [kindFilter, mine].filter(Boolean).length;
  const items: Row[] = (data?.items || []).filter((event: Row) =>
    (!kindFilter || kindOf(event) === kindFilter) && (!mine || event.owner_id === user?.id) &&
    searchMatch(search, [event.title, event.contact_name, contactOf(event)?.name, contactOf(event)?.phone, event.notes]));
  const { ref: gridRef, height: gridHeight } = useElementHeight();
  const maxEvents = Math.max(1, Math.floor((gridHeight / (count / 7) - 38) / 26));
  const eventDate = (event: Row) =>
    event.date.length === 10
      ? event.date
      : new Intl.DateTimeFormat('en-CA', { timeZone: getZone() }).format(new Date(event.date));
  const now = new Date().toISOString();
  const isLate = (event: Row) => (event.date.length === 10 ? event.date < today() : event.date < now);
  const eventTitle = (event: Row) => [event.date.length > 10 ? hour(event.date) : '', event.title, event.contact_name].filter(Boolean).join(' · ');
  const monthLabel = current.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  const eventLink = (event: Row) =>
    event.kind === 'task' ? '/tarefas' : event.opportunity_id ? '/crm' : '/contatos';
  return (
    <div className="page activities-page">
      <PageHeader
        compact
        title="Atividades"
      >
        <Button onClick={() => setCreating('new')}>
          <Plus size={17} /> Nova atividade
        </Button>
      </PageHeader>
      <div className="board-bar activities-bar">
        <Tabs
          label="Visualização de atividades"
          items={[
            { value: 'month', label: 'Mês' },
            { value: 'list', label: 'Lista' },
          ]}
          value={mode}
          onChange={setMode}
        />
        <div className="month-nav">
          <button type="button" className="icon-btn" aria-label="Mês anterior" data-tip="Mês anterior"
            onClick={() => setCurrent(new Date(current.getFullYear(), current.getMonth() - 1, 1))}><ChevronLeft size={18} /></button>
          <h2>{monthLabel}</h2>
          <button type="button" className="icon-btn" aria-label="Próximo mês" data-tip="Próximo mês"
            onClick={() => setCurrent(new Date(current.getFullYear(), current.getMonth() + 1, 1))}><ChevronRight size={18} /></button>
          <Button variant="soft" onClick={() => setCurrent(new Date(today() + 'T12:00:00'))}>Hoje</Button>
        </div>
        <div className="toolbar-end">
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar atividade ou contato" />
          <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" align="end" panelClassName="filter-panel"
            badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
            <label className="field"><span>Tipo</span>
              <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
                <option value="">Todos os tipos</option>
                {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select></label>
            <label className="checkbox-label"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />Somente minhas</label>
          </>}</Popover>
          {activeFilters > 0 && <Button variant="ghost" onClick={() => { setKindFilter(''); setMine(false); }}><X size={14} />Limpar</Button>}
        </div>
      </div>
      <Card as="section" fill>
        <DataState loading={isLoading} error={error}>
          {mode === 'month' ? (
            <>
              <div className="calendar-weekdays">
                {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map((d) => (
                  <div key={d}>{d}</div>
                ))}
              </div>
              <div ref={gridRef} className="calendar-grid" style={{ gridTemplateRows: `repeat(${count / 7}, minmax(0, 1fr))` }}>
                {days.map((d) => {
                  const key = ymd(d);
                  const events = items.filter((e) => eventDate(e) === key);
                  const visible = events.length > maxEvents ? Math.max(0, maxEvents - 1) : events.length;
                  return (
                    <div
                      className={'calendar-cell' + (d.getMonth() !== current.getMonth() ? ' outside' : '') + (key === today() ? ' today' : '')}
                      key={key}
                      onClick={() => setCreating(key)}
                    >
                      <span className={'calendar-day ' + (key === today() ? 'is-today' : '')}>
                        {d.getDate()}
                      </span>
                      {events.slice(0, visible).map((e) => (
                        <button
                          type="button"
                          data-tip={eventTitle(e)}
                          aria-label={eventTitle(e)}
                          className={'calendar-event kind-' + kindOf(e) + (isLate(e) ? ' late' : '')}
                          onClick={(event) => { event.stopPropagation(); setSelected(e); }}
                          key={e.kind + e.id}
                        >
                          <i aria-hidden="true" />
                          {e.date.length > 10 && <time>{hour(e.date)}</time>}
                          <span>{e.title}</span>
                        </button>
                      ))}
                      {events.length > visible && (
                        <button type="button" className="calendar-more" onClick={(event) => { event.stopPropagation(); setDayList(key); }}>
                          +{events.length - visible} {events.length - visible === 1 ? 'item' : 'itens'}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          ) : items.length ? (
            <PagedTable
              rows={items}
              header={
                <tr>
                  <th>Data</th>
                  <th>Atividade</th>
                  <th>Tipo</th>
                  <th />
                </tr>
              }
              renderRow={(e) => (
                <tr key={e.kind + e.id}>
                  <td>{day(e.date)}{e.date.length > 10 ? ' · ' + hour(e.date) : ''}</td>
                  <td>
                    <strong>{e.title}</strong>{e.contact_name && <small className="muted"> · {e.contact_name}</small>}
                  </td>
                  <td><span className={'kind-label kind-' + kindOf(e)}><i aria-hidden="true" />{KIND_LABELS[kindOf(e)] || 'Atividade'}</span></td>
                  <td>
                    <button type="button" className="btn btn-ghost" onClick={() => setSelected(e)}>
                      Abrir
                      <ArrowUpRight size={13} />
                    </button>
                  </td>
                </tr>
              )}
            />
          ) : (
            <EmptyState
              icon={<CalendarDays size={25} />}
              title="Nenhuma atividade neste mês"
            />
          )}
        </DataState>
      </Card>
      <Modal open={Boolean(selected)} onClose={() => setSelected(null)} title={selected?.booking_id ? 'Agendamento' : 'Atividade'}>
        {selected && <div className="stack"><h3>{selected.title}</h3><p>{day(selected.date)}{selected.date.length > 10 ? ' · ' + hour(selected.date) : ''}{selected.ends_at ? ' até ' + hour(selected.ends_at) : ''}</p>{selected.contact_name && <p>{selected.contact_name}</p>}{selected.notes && <p className="record-notes">{selected.notes}</p>}<div className="row-actions"><RecordLink className="btn btn-secondary" href={eventLink(selected)}>Abrir {selected.kind === 'task' ? 'tarefa' : selected.opportunity_id ? 'negócio' : 'contato'}</RecordLink><Button variant="ghost" onClick={() => setSelected(null)}>Fechar</Button></div></div>}
      </Modal>
      <Modal open={Boolean(dayList)} onClose={() => setDayList(null)} title={dayList ? day(dayList) : 'Atividades'}>
        <ul className="record-list">
          {items.filter((e) => eventDate(e) === dayList).map((e) => (
            <li key={e.kind + e.id}>
              <span className={'kind-label kind-' + kindOf(e)}><i aria-hidden="true" /></span>
              <div><strong>{e.title}</strong><small>{[e.date.length > 10 ? hour(e.date) : 'Prazo', KIND_LABELS[kindOf(e)], e.contact_name].filter(Boolean).join(' · ')}</small></div>
              <Button variant="ghost" onClick={() => { setDayList(null); setSelected(e); }}>Abrir<ArrowUpRight size={13} /></Button>
            </li>
          ))}
        </ul>
      </Modal>
      <FormDialog
        key={creating || 'closed'}
        open={creating !== null}
        onClose={() => setCreating(null)}
        title="Nova atividade"
        fields={[
          { name: 'title', label: 'Atividade', required: true },
          { name: 'kind', label: 'Tipo', type: 'select', options: opts(kinds), defaultValue: 'follow_up' },
          { name: 'scheduled_at', label: 'Data e hora', type: 'datetime-local', required: true },
          { name: 'contact_id', label: 'Contato', type: 'contact' },
          { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions((users.data || []).filter((u) => u.active)) },
          { name: 'notes', label: 'Observações', type: 'textarea', wide: true },
        ]}
        initial={{ kind: 'follow_up', owner_id: user?.id, scheduled_at: creating && creating !== 'new' ? creating + 'T09:00' : '' }}
        onSubmit={async (data) => {
          await post('/activities', {
            ...data,
            contact_id: data.contact_id || null,
            owner_id: data.owner_id || null,
            notes: data.notes || null,
          });
          await refreshAll();
          setCreating(null);
          notify('Atividade agendada.');
        }}
      />
    </div>
  );
}
