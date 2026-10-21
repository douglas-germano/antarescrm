'use client';
import { useState } from 'react';
import { Plus, ExternalLink } from 'lucide-react';
import { useList, post, patch, refreshAll } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { Button, DataState, Modal, Badge, EmptyState } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import { AvailabilityEditor, type Availability } from '@/components/settings/availability-editor';
import type { Row } from '@/lib/types';
const weekdays = Object.fromEntries(Array.from({ length: 5 }, (_,i) => [String(i), [{ start: '09:00', end: '18:00' }]]));
export function BookingSettings() {
  const { user, workspace } = useSession(); const { notify } = useNotify();
  const manage = ['owner','admin'].includes(user?.role || '');
  const calendars = useList('/booking-calendars'), staff = useList('/users');
  const [editing, setEditing] = useState<Row | null | false>(false);
  const [availability, setAvailability] = useState<Availability>(weekdays);
  const [busy,setBusy] = useState(false), [error,setError] = useState('');
  function edit(row: Row | null) { setEditing(row); setAvailability(row?.availability || weekdays); setError(''); }
  return <div className="stack"><div className="booking-settings-header"><div><h2>Disponibilidade para reservas</h2></div>{manage && <Button onClick={() => edit(null)}><Plus size={17} />Nova agenda</Button>}</div>
    <DataState loading={calendars.isLoading} error={calendars.error}>
      {!calendars.data?.length ? <EmptyState title="Nenhuma agenda" /> : <div className="account-grid">{calendars.data.map(calendar => <Card key={calendar.id}><CardHeader title={calendar.name} description={calendar.description} actions={<Badge value={calendar.active ? 'completed':'cancelled'} label={calendar.active ? 'Ativa':'Pausada'} />} /><CardBody><p>{calendar.duration_minutes} minutos · {staff.data?.find(u => u.id === calendar.assignee_id)?.name || 'Equipe'}</p><p className="muted">Intervalo: {calendar.buffer_minutes} min · Antecedência: {calendar.lead_minutes} min</p><div className="account-actions">{manage && <Button variant="secondary" onClick={() => edit(calendar)}>Editar disponibilidade</Button>}<a className="btn btn-secondary" href={'/agendar/' + calendar.id} target="_blank" rel="noreferrer"><ExternalLink size={16} />Abrir link</a><Button variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(window.location.origin + '/agendar/' + calendar.id); notify('Link copiado.'); } catch { notify('Abra o link e copie o endereço.', 'error'); } }}>Copiar link</Button></div></CardBody></Card>)}</div>}
    </DataState>
    <Modal open={editing !== false} onClose={() => { if (!busy) setEditing(false); }} title={editing ? 'Editar agenda':'Nova agenda'} wide>
      {editing !== false && <form key={editing?.id || 'new'} className="stack" onSubmit={async event => {
        event.preventDefault(); if (busy) return; setBusy(true); setError(''); const raw = new FormData(event.currentTarget);
        const body = { name: String(raw.get('name')).trim(), description: String(raw.get('description') || '').trim(), assignee_id: raw.get('assignee_id') || null, duration_minutes: Number(raw.get('duration_minutes')), buffer_minutes: Number(raw.get('buffer_minutes')), lead_minutes: Number(raw.get('lead_minutes')), horizon_days: Number(raw.get('horizon_days')), availability, active: raw.get('active') === 'on' };
        try { if (editing) await patch('/booking-calendars/' + editing.id, body); else await post('/booking-calendars', body); await refreshAll(); notify('Agenda salva.'); setEditing(false); } catch(e) { setError((e as Error).message); } finally { setBusy(false); }
      }}><fieldset disabled={busy} className="stack"><div className="form-grid">
        <label>Nome<input name="name" required maxLength={150} defaultValue={editing?.name || ''} /></label><label>Responsável<select name="assignee_id" defaultValue={editing?.assignee_id || user?.id || ''}><option value="">Equipe</option>{staff.data?.filter(u => u.active).map(u => <option value={u.id} key={u.id}>{u.name}</option>)}</select></label>
        <label>Duração (minutos)<input name="duration_minutes" required type="number" min={5} max={480} defaultValue={editing?.duration_minutes ?? 30} /></label><label>Intervalo entre reservas (minutos)<input name="buffer_minutes" required type="number" min={0} max={120} defaultValue={editing?.buffer_minutes ?? 0} /></label>
        <label>Antecedência mínima (minutos)<input name="lead_minutes" required type="number" min={0} max={43200} defaultValue={editing?.lead_minutes ?? 120} /></label><label>Abrir horários para quantos dias<input name="horizon_days" required type="number" min={1} max={180} defaultValue={editing?.horizon_days ?? 60} /></label>
      </div><label>Apresentação<textarea name="description" maxLength={2000} defaultValue={editing?.description || ''} /></label><h3>Disponibilidade semanal</h3><p className="muted">Horários em {workspace?.timezone}. Reservas do mesmo responsável compartilham o controle de conflitos.</p><AvailabilityEditor value={availability} onChange={setAvailability} /><label className="checkbox-label"><input name="active" type="checkbox" defaultChecked={editing?.active || false} />Permitir reservas pelo link público</label></fieldset>
        {error && <p className="form-error" role="alert">{error}</p>}<div className="modal-footer"><Button variant="secondary" disabled={busy} onClick={() => setEditing(false)}>Cancelar</Button><Button disabled={busy} type="submit">{busy ? 'Salvando…':'Salvar agenda'}</Button></div>
      </form>}
    </Modal>
  </div>;
}
