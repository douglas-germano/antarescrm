'use client';
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { publicApi } from '@/lib/public-api';
import { Button, DataState } from '@/components/ui';
import { BookingSlots } from '@/components/booking-slots';
import type { Row } from '@/lib/types';
export default function PublicBooking() {
  const { calendarId } = useParams<{ calendarId: string }>();
  const [calendar,setCalendar] = useState<Row>(), [error,setError] = useState<Error>(), [selected,setSelected] = useState(''), [busy,setBusy] = useState(false), [failure,setFailure] = useState(''), [token,setToken] = useState('');
  const key = useRef(''), pending = useRef(false);
  useEffect(() => { const controller = new AbortController(); setCalendar(undefined); setError(undefined); setToken(''); key.current = '';
    publicApi('calendars/' + calendarId, undefined, controller.signal).then(setCalendar).catch(e => { if (e.name !== 'AbortError') setError(e); }); return () => controller.abort();
  }, [calendarId]);
  return <main className="capture-page"><section className="capture-card booking-card"><div className="capture-brand"><img src="/mark.svg" width="28" height="28" alt="" /><span>antares</span></div><DataState loading={!calendar && !error} error={error}>
    {token ? <div role="status" className="capture-success"><h1>Agendamento confirmado</h1><p>Guarde o link abaixo para consultar, alterar ou cancelar sua reserva.</p><Link className="btn btn-primary" href={'/agendamento/' + token}>Ver meu agendamento</Link></div> : calendar && <><h1>{calendar.name}</h1><p>{calendar.description}</p><p className="muted">Duração: {calendar.duration_minutes} minutos</p><BookingSlots calendarId={calendarId} timezone={calendar.timezone} selected={selected} onSelect={setSelected} />
      <form className="stack" onSubmit={async event => { event.preventDefault(); if (pending.current || !selected) return; pending.current = true; setBusy(true); setFailure(''); const raw = new FormData(event.currentTarget);
        try { if (!key.current) key.current = crypto.randomUUID(); const data = await publicApi('calendars/' + calendarId + '/book', { submission_key: key.current, starts_at: selected, name: raw.get('name'), email: raw.get('email'), phone: raw.get('phone'), consent: raw.get('consent') === 'on', website: raw.get('website') }); setToken(data.token); }
        catch(e) { setFailure((e as Error).message); } finally { pending.current = false; setBusy(false); }
      }}><fieldset disabled={busy} className="stack"><label>Nome<input name="name" required maxLength={180} autoComplete="name" /></label><label>E-mail<input name="email" type="email" required maxLength={254} autoComplete="email" /></label><label>Telefone (opcional)<input name="phone" type="tel" maxLength={30} autoComplete="tel" /></label><div className="capture-honeypot" aria-hidden="true"><input name="website" tabIndex={-1} autoComplete="off" /></div><label className="checkbox-label"><input name="consent" type="checkbox" required />{calendar.consent_text}</label></fieldset>{failure && <p className="form-error" role="alert">{failure}</p>}<Button type="submit" disabled={busy || !selected}>{busy ? 'Confirmando…':'Confirmar agendamento'}</Button></form>
    </>}
  </DataState></section></main>;
}
