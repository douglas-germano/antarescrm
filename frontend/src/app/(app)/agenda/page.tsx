'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { BookingSettings } from '@/components/settings/booking-settings';
import { ChevronLeft, ChevronRight, CalendarDays, ArrowUpRight, Plus } from 'lucide-react';
import { useData, useList, post, refreshAll } from '@/lib/api';
import { PageHeader, Button, DataState, EmptyState, FormDialog, Modal, SearchInput } from '@/components/ui';
import { today, day, getZone, hour, kinds, opts, rowOptions, searchMatch } from '@/lib/format';
import { useSession, useNotify } from '@/components/providers';
import { PagedTable, useElementHeight } from '@/components/fit';
import { Card, Tabs } from '@/components/blocks';
import type { Row } from '@/lib/types';
const ymd = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
export default function Calendar() {
  const { user } = useSession();
  const { notify } = useNotify();
  const [selected, setSelected] = useState<Row | null>(null);
  const [creating, setCreating] = useState(false);
  const contacts = useList('/contacts');
  const users = useList('/users');
  const [current, setCurrent] = useState(() => new Date(today() + 'T12:00:00'));
  const [mode, setMode] = useState('month');
  const [search, setSearch] = useState('');
  useEffect(() => { if (new URLSearchParams(window.location.search).get('view') === 'availability') setMode('availability'); }, []);
  const first = new Date(current.getFullYear(), current.getMonth(), 1);
  const last = new Date(current.getFullYear(), current.getMonth() + 1, 0);
  const { data, isLoading, error } = useData('/calendar?start=' + ymd(first) + '&end=' + ymd(last));
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  const count = Math.ceil((first.getDay() + last.getDate()) / 7) * 7;
  const days = Array.from({ length: count }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
  const contactOf = (event: Row) => contacts.data?.find((c) => c.id === event.contact_id);
  const items: Row[] = (data?.items || []).filter((event: Row) => searchMatch(search, [event.title, event.contact_name, contactOf(event)?.name, contactOf(event)?.phone, event.notes]));
  const { ref: gridRef, height: gridHeight } = useElementHeight();
  const maxEvents = Math.max(1, Math.floor((gridHeight / (count / 7) - 38) / 26));
  const eventDate = (event: Row) =>
    event.date.length === 10
      ? event.date
      : new Intl.DateTimeFormat('en-CA', { timeZone: getZone() }).format(new Date(event.date));
  const eventLink = (event: Row) =>
    event.kind === 'task' ? '/tarefas' : event.opportunity_id ? '/crm' : '/contatos';
  return (
    <div className="page activities-page">
      <PageHeader
        compact
        title="Atividades"
      >
        {mode !== 'availability' && <SearchInput value={search} onChange={setSearch} placeholder="Buscar atividade ou contato" />}
        <Button onClick={() => setCreating(true)}>
          <Plus size={17} /> Nova atividade
        </Button>
        <Tabs
          items={[
            { value: 'month', label: 'Mês' },
            { value: 'list', label: 'Lista' },
            { value: 'availability', label: 'Links de agendamento' },
          ]}
          value={mode}
          onChange={setMode}
        />
      </PageHeader>
      {mode === 'availability' ? <BookingSettings /> : <Card as="section" fill>
        <div className="calendar-header">
          <h2>{current.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}</h2>
          <div className="row-actions">
            <Button variant="secondary" onClick={() => setCurrent(new Date(today() + 'T12:00:00'))}>
              Hoje
            </Button>
            <button
              className="icon-btn"
              aria-label="Mês anterior"
              onClick={() => setCurrent(new Date(current.getFullYear(), current.getMonth() - 1, 1))}
            >
              <ChevronLeft size={19} />
            </button>
            <button
              className="icon-btn"
              aria-label="Próximo mês"
              onClick={() => setCurrent(new Date(current.getFullYear(), current.getMonth() + 1, 1))}
            >
              <ChevronRight size={19} />
            </button>
          </div>
        </div>
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
                  const events = items.filter((e) => eventDate(e) === ymd(d));
                  const visible = events.length > maxEvents ? Math.max(0, maxEvents - 1) : events.length;
                  return (
                    <div
                      className={'calendar-cell ' + (d.getMonth() !== current.getMonth() ? 'outside' : '')}
                      key={ymd(d)}
                    >
                      <span className={'calendar-day ' + (ymd(d) === today() ? 'is-today' : '')}>
                        {d.getDate()}
                      </span>
                      {events.slice(0, visible).map((e) => (
                        <button
                          type="button"
                          title={[e.title, e.contact_name].filter(Boolean).join(' · ')}
                          className={'calendar-event ' + e.kind}
                          onClick={() => setSelected(e)}
                          key={e.kind + e.id}
                        >
                          {e.title}{e.contact_name ? ' · ' + e.contact_name : ''}
                        </button>
                      ))}
                      {events.length > visible && (
                        <span className="calendar-more" title={events.slice(visible).map((e) => e.title).join('\n')}>
                          +{events.length - visible} {events.length - visible === 1 ? 'item' : 'itens'}
                        </span>
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
                  <th>DATA</th>
                  <th>ATIVIDADE / PRAZO</th>
                  <th>TIPO</th>
                  <th />
                </tr>
              }
              renderRow={(e) => (
                <tr key={e.kind + e.id}>
                  <td>{day(e.date)}{e.date.length > 10 ? ' · ' + hour(e.date) : ''}</td>
                  <td>
                    <strong>{e.title}</strong>{e.contact_name && <small className="muted"> · {e.contact_name}</small>}
                  </td>
                  <td className="muted">
                    {e.booking_id ? 'Agendamento' : e.kind === 'task' ? 'Tarefa' : kinds[e.kind] || 'Atividade'}
                  </td>
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
      </Card>}
      <Modal open={Boolean(selected)} onClose={() => setSelected(null)} title={selected?.booking_id ? 'Agendamento' : 'Atividade'}>
        {selected && <div className="stack"><h3>{selected.title}</h3><p>{day(selected.date)}{selected.date.length > 10 ? ' · ' + hour(selected.date) : ''}{selected.ends_at ? ' até ' + hour(selected.ends_at) : ''}</p>{selected.contact_name && <p>{selected.contact_name}</p>}{selected.notes && <p className="record-notes">{selected.notes}</p>}<div className="row-actions"><Link className="btn btn-secondary" href={eventLink(selected)}>Abrir {selected.kind === 'task' ? 'tarefa' : selected.opportunity_id ? 'negócio' : 'contato'}</Link><Button variant="ghost" onClick={() => setSelected(null)}>Fechar</Button></div></div>}
      </Modal>
      <FormDialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Nova atividade"
        fields={[
          { name: 'title', label: 'Atividade', required: true },
          { name: 'kind', label: 'Tipo', type: 'select', options: opts(kinds), defaultValue: 'follow_up' },
          { name: 'scheduled_at', label: 'Data e hora', type: 'datetime-local', required: true },
          { name: 'contact_id', label: 'Contato', type: 'contact' },
          { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions((users.data || []).filter((u) => u.active)) },
          { name: 'notes', label: 'Observações', type: 'textarea', wide: true },
        ]}
        initial={{ kind: 'follow_up', owner_id: user?.id }}
        onSubmit={async (data) => {
          await post('/activities', {
            ...data,
            contact_id: data.contact_id || null,
            owner_id: data.owner_id || null,
            notes: data.notes || null,
          });
          await refreshAll();
          setCreating(false);
          notify('Atividade agendada.');
        }}
      />
    </div>
  );
}
