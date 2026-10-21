'use client';
import { useEffect, useState } from 'react';
import { publicApi } from '@/lib/public-api';
import { DataState } from './ui';
export function BookingSlots({ calendarId, timezone, selected, onSelect }: { calendarId: string; timezone: string; selected: string; onSelect: (value: string) => void }) {
  const min = new Intl.DateTimeFormat('en-CA', { timeZone: timezone }).format(new Date());
  const [date, setDate] = useState(min), [slots,setSlots] = useState<string[]>([]), [loading,setLoading] = useState(true), [error,setError] = useState<Error>();
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(undefined); setSlots([]); onSelect('');
    publicApi('calendars/' + calendarId + '/slots?date=' + date, undefined, controller.signal).then(data => { if (!controller.signal.aborted) setSlots(data.items); }).catch(e => { if (e.name !== 'AbortError') setError(e); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
    // onSelect is a React state setter in the parent; the selected value must not refetch slots.
  }, [calendarId, date, onSelect]);
  return <div className="stack"><label>Escolha a data<input type="date" required min={min} value={date} onChange={e => { if (e.target.value) setDate(e.target.value); }} /></label><small>Horários em {timezone}</small><DataState loading={loading} error={error}><div className="booking-slots" role="group" aria-label="Horários disponíveis">{slots.map(slot => <button type="button" className={'btn btn-secondary' + (selected === slot ? ' selected':'')} aria-pressed={selected === slot} key={slot} onClick={() => onSelect(slot)}>{new Date(slot).toLocaleTimeString('pt-BR',{ timeZone: timezone, hour:'2-digit',minute:'2-digit' })}</button>)}{!slots.length && <p className="muted">Nenhum horário disponível nesta data. Escolha outro dia.</p>}</div></DataState></div>;
}
