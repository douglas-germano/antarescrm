'use client';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, ArrowRight } from 'lucide-react';
import { Button, DataState } from '@/components/ui';
import type { CaptureField } from '@/components/form-fields-editor';
import type { CSSProperties } from 'react';

type PublicForm = { headline: string; description: string; consent_text: string; fields: CaptureField[]; brand_name: string; accent_color: string };
export default function CapturePage() {
  const { formId } = useParams<{ formId: string }>();
  const [data, setData] = useState<PublicForm | null>(null);
  const [error, setError] = useState<Error>();
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState('');
  const [success, setSuccess] = useState('');
  const [answers, setAnswers] = useState<Record<string, string | boolean>>({});
  const submissionKey = useRef('');
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    pending.current?.abort(); pending.current = null;
    setData(null); setError(undefined); setSuccess(''); setSendError(''); setSending(false); setAnswers({}); submissionKey.current = '';
    fetch('/api/public/forms/' + formId, { signal: controller.signal, cache: 'no-store' })
      .then(async (r) => { const body = await r.json(); if (!r.ok) throw new Error(body?.error?.message || 'Formulário indisponível.'); return body; })
      .then(setData).catch((e) => { if (e.name !== 'AbortError') setError(e); });
    return () => { controller.abort(); pending.current?.abort(); };
  }, [formId]);
  const visible = (field: CaptureField): boolean => {
    if (!field.show_if) return true;
    const previous = data?.fields.find(f => f.key === field.show_if?.field);
    if (!previous || !visible(previous)) return false;
    const value = answers[field.show_if.field] ?? (previous.type === 'checkbox' ? false : '');
    return (typeof value === 'string' ? value.trim() : value) === field.show_if.equals;
  };
  return <main className="capture-page"><section className="capture-card" style={data ? { '--brand': data.accent_color } as CSSProperties : undefined}>
    <div className="capture-brand"><img src="/mark.svg" width="28" height="28" alt="" /><span>{data?.brand_name || 'antares'}</span></div>
    <DataState loading={!data && !error} error={error}>
      {success ? <div className="capture-success" role="status"><CheckCircle2 size={40} /><h1>Solicitação recebida</h1><p>{success}</p></div> : data && <>
        <h1>{data.headline}</h1><p className="capture-description">{data.description}</p>
        <form className="stack" onSubmit={async (event) => {
          event.preventDefault(); if (pending.current) return;
          const controller = new AbortController(); pending.current = controller;
          setSending(true); setSendError('');
          const raw = new FormData(event.currentTarget);
          try {
            if (!submissionKey.current) submissionKey.current = crypto.randomUUID();
            const response = await fetch(`/api/public/forms/${formId}/submit`, { method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
              answers: Object.fromEntries((data.fields || []).filter(visible).map(f => [f.key, answers[f.key] ?? (f.type === 'checkbox' ? false : '')])),
              attribution: Object.fromEntries(['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].flatMap(key => { const value = new URLSearchParams(window.location.search).get(key); return value ? [[key, value.slice(0,300)]] : []; })),
              submission_key: submissionKey.current, name: raw.get('name'), email: raw.get('email'), phone: raw.get('phone'), consent: raw.get('consent') === 'on', website: raw.get('website'),
            }) });
            const body = await response.json();
            if (!response.ok) throw new Error(body?.error?.message || 'Confira os campos e tente novamente.');
            if (!controller.signal.aborted) setSuccess(body.message);
          } catch (e) { if (!controller.signal.aborted) setSendError((e as Error).message); } finally {
            if (pending.current === controller) { pending.current = null; setSending(false); }
          }
        }}>
          <fieldset className="stack" disabled={sending}>
            <div className="field"><label htmlFor="lead-name">Nome</label><input id="lead-name" name="name" required maxLength={180} autoComplete="name" /></div>
            <div className="field"><label htmlFor="lead-email">E-mail</label><input id="lead-email" name="email" type="email" required maxLength={254} autoComplete="email" /></div>
            <div className="field"><label htmlFor="lead-phone">Telefone / WhatsApp <span className="muted">(opcional)</span></label><input id="lead-phone" name="phone" type="tel" maxLength={30} autoComplete="tel" /></div>
            {(data.fields || []).filter(visible).map(field => <div className="field" key={field.key}>
              {field.type === 'checkbox' ? <label className="checkbox-label"><input type="checkbox" checked={Boolean(answers[field.key])} required={field.required} onChange={e => setAnswers(old => ({ ...old, [field.key]: e.target.checked }))} />{field.label}{field.required && ' *'}</label> : <><label htmlFor={'extra-' + field.key}>{field.label}{field.required && ' *'}</label>
              {field.type === 'select' ? <select id={'extra-' + field.key} required={field.required} value={String(answers[field.key] || '')} onChange={e => setAnswers(old => ({ ...old, [field.key]: e.target.value }))}><option value="">Selecione…</option>{field.options.map(option => <option key={option} value={option}>{option}</option>)}</select> : field.type === 'textarea' ? <textarea id={'extra-' + field.key} required={field.required} maxLength={2000} value={String(answers[field.key] || '')} onChange={e => setAnswers(old => ({ ...old, [field.key]: e.target.value }))} /> : <input id={'extra-' + field.key} required={field.required} type={['number','date'].includes(field.type) ? field.type : 'text'} step={field.type === 'number' ? 'any' : undefined} maxLength={2000} value={String(answers[field.key] || '')} onChange={e => setAnswers(old => ({ ...old, [field.key]: e.target.value }))} />}</>}
            </div>)}
            <div className="capture-honeypot" aria-hidden="true"><label htmlFor="lead-website">Website</label><input id="lead-website" name="website" tabIndex={-1} autoComplete="off" /></div>
            <label className="checkbox-label"><input type="checkbox" name="consent" required />{data.consent_text}</label>
          </fieldset>
          {sendError && <p className="form-error" role="alert">{sendError}</p>}
          <Button type="submit" disabled={sending}>{sending ? 'Enviando…' : 'Enviar solicitação'}<ArrowRight size={17} /></Button>
        </form>
      </>}
    </DataState>
  </section></main>;
}
