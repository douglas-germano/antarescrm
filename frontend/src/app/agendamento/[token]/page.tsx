'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { publicApi } from '@/lib/public-api';
import { Button, DataState, ConfirmDialog } from '@/components/ui';
import { BookingSlots } from '@/components/booking-slots';
import type { Row } from '@/lib/types';
export default function ManageBooking() {
  const { token } = useParams<{ token: string }>(); const [data,setData] = useState<Row>(), [error,setError] = useState<Error>();
  const [editing,setEditing] = useState(false), [selected,setSelected] = useState(''), [cancel,setCancel] = useState(false), [busy,setBusy] = useState(false), [message,setMessage] = useState('');
  async function reload() { setData(await publicApi('bookings/' + token)); }
  useEffect(() => { const c = new AbortController(); publicApi('bookings/' + token, undefined, c.signal).then(setData).catch(e => { if (e.name !== 'AbortError') setError(e); }); return () => c.abort(); }, [token]);
  return <main className="capture-page"><section className="capture-card booking-card"><DataState loading={!data && !error} error={error}>{data && <div className="stack"><h1>{data.name}</h1><p>{new Date(data.starts_at).toLocaleString('pt-BR', { timeZone: data.timezone })}</p><small>Fuso: {data.timezone}</small><strong>{data.status === 'confirmed' ? 'Confirmado':'Cancelado'}</strong>
    {data.status === 'confirmed' && new Date(data.starts_at) > new Date() && <><Button variant="secondary" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? 'Fechar alteração':'Alterar horário'}</Button><Button variant="danger" disabled={busy} onClick={() => setCancel(true)}>Cancelar agendamento</Button>
      {editing && <><BookingSlots calendarId={data.calendar_id} timezone={data.timezone} selected={selected} onSelect={setSelected} /><Button disabled={!selected || busy} onClick={async () => { setBusy(true); setMessage(''); try { const result = await publicApi('bookings/' + token + '/reschedule', { starts_at: selected }); setMessage(result.message); await reload(); setEditing(false); } catch(e) { setMessage((e as Error).message); } finally { setBusy(false); } }}>Confirmar novo horário</Button></>}
    </>}{message && <p role="status">{message}</p>}
    <ConfirmDialog open={cancel} title="Cancelar este agendamento?" description="O horário será liberado para outras pessoas." onClose={() => setCancel(false)} onConfirm={async () => { const result = await publicApi('bookings/' + token + '/cancel', {}); setMessage(result.message); await reload(); setCancel(false); }} />
  </div>}</DataState></section></main>;
}
