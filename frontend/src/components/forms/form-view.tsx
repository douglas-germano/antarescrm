'use client';
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { contrastOn, formStyle } from './theme';
import { DEFAULT_DESIGN, isLayout, type Answer, type CaptureField, type PublicForm } from './types';

export type SubmitResult = { message: string; redirect_url?: string };
type Editor = { selected?: string; onSelect: (key: string) => void };
type Props = {
  form: PublicForm;
  /** Extra attribution sent with the submission (funnel id, step id, visitor id). */
  attribution?: Record<string, string>;
  onSuccess?: (result: SubmitResult) => void;
  /** Hide the card, brand and headline: used when the form sits inside a funnel page. */
  embedded?: boolean;
  /** Builder preview: nothing is sent and fields can be selected. */
  editor?: Editor;
  accent?: string;
  buttonLabel?: string;
};

const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
const EMPTY: Answer = '';

export function visibleField(field: CaptureField, fields: CaptureField[], answers: Record<string, Answer>): boolean {
  if (!field.show_if) return true;
  const previous = fields.find((f) => f.key === field.show_if?.field);
  if (!previous || !visibleField(previous, fields, answers)) return false;
  const value = answers[field.show_if.field] ?? (previous.type === 'checkbox' ? false : '');
  return (typeof value === 'string' ? value.trim() : value) === field.show_if.equals;
}

export function FormView({ form, attribution, onSuccess, embedded = false, editor, accent, buttonLabel }: Props) {
  const design = { ...DEFAULT_DESIGN, ...form.design };
  const color = accent || form.accent_color;
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState<SubmitResult | null>(null);
  const key = useRef('');
  const pending = useRef<AbortController | null>(null);
  const base = form.base_fields || {};
  const baseField = (name: 'name' | 'email' | 'phone', label: string) => ({ label, placeholder: '', visible: true, required: name !== 'phone', ...base[name] });
  const set = (field: string, value: Answer) => setAnswers((old) => ({ ...old, [field]: value }));
  useEffect(() => () => pending.current?.abort(), []);
  const select = (id: string) => editor && { 'data-selected': editor.selected === id, onClickCapture: (e: React.MouseEvent) => { e.preventDefault(); e.stopPropagation(); editor.onSelect(id); } };
  const bits = useMemo(() => new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search), []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (editor || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setSending(true); setError('');
    const raw = new FormData(event.currentTarget);
    try {
      if (!key.current) key.current = crypto.randomUUID();
      const response = await fetch(`/api/public/forms/${form.id}/submit`, {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answers: Object.fromEntries(form.fields.filter((f) => !isLayout(f.type) && visibleField(f, form.fields, answers))
            .map((f) => [f.key, answers[f.key] ?? (f.type === 'checkbox' ? false : f.type === 'multiselect' ? [] : '')])),
          attribution: {
            ...Object.fromEntries(UTM_KEYS.flatMap((k) => (bits.get(k) ? [[k, bits.get(k)!.slice(0, 300)]] : []))),
            ...attribution,
          },
          submission_key: key.current, name: raw.get('name'), email: raw.get('email'), phone: raw.get('phone') || '',
          consent: raw.get('consent') === 'on', website: raw.get('website') || '',
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body?.error?.message || 'Confira os campos e tente novamente.');
      if (controller.signal.aborted) return;
      setSuccess(body);
      if (onSuccess) onSuccess(body);
      else if (body.redirect_url) window.location.assign(body.redirect_url);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (pending.current === controller) { pending.current = null; setSending(false); }
    }
  }

  if (success && !onSuccess) {
    return <div className="fv-success" role="status"><CheckCircle2 size={40} /><h2>Solicitação recebida</h2><p>{success.message}</p></div>;
  }
  const name = baseField('name', 'Nome'), email = baseField('email', 'E-mail'), phone = baseField('phone', 'Telefone / WhatsApp');
  return <form className={'fv-form' + (embedded ? ' fv-embedded' : '')} style={{ '--f-on-accent': contrastOn(color) } as CSSProperties} onSubmit={submit}>
    {!embedded || form.headline ? <header className="fv-head"><h1>{form.headline}</h1>{form.description && <p>{form.description}</p>}</header> : null}
    <fieldset className="fv-fields" disabled={sending}>
      <div className="fv-field fv-full" {...select('base:name')}>
        <label htmlFor={form.id + '-name'}>{name.label}</label>
        <input id={form.id + '-name'} name="name" required maxLength={180} autoComplete="name" placeholder={name.placeholder} />
      </div>
      <div className="fv-field fv-full" {...select('base:email')}>
        <label htmlFor={form.id + '-email'}>{email.label}</label>
        <input id={form.id + '-email'} name="email" type="email" required maxLength={254} autoComplete="email" placeholder={email.placeholder} />
      </div>
      {phone.visible !== false && <div className="fv-field fv-full" {...select('base:phone')}>
        <label htmlFor={form.id + '-phone'}>{phone.label}{phone.required ? ' *' : <span className="fv-optional"> (opcional)</span>}</label>
        <input id={form.id + '-phone'} name="phone" type="tel" required={!!phone.required} maxLength={30} autoComplete="tel" placeholder={phone.placeholder} />
      </div>}
      {form.fields.filter((f) => visibleField(f, form.fields, answers)).map((field) => <FieldControl key={field.key} field={field} id={form.id + '-' + field.key}
        value={answers[field.key] ?? EMPTY} onChange={(v) => set(field.key, v)} wrap={select(field.key)} />)}
      <div className="fv-honeypot" aria-hidden="true"><label htmlFor={form.id + '-site'}>Website</label><input id={form.id + '-site'} name="website" tabIndex={-1} autoComplete="off" /></div>
      <label className="fv-check fv-full" {...select('consent')}><input type="checkbox" name="consent" required defaultChecked={!!editor} /><span>{form.consent_text}</span></label>
    </fieldset>
    {error && <p className="fv-error" role="alert">{error}</p>}
    <button type="submit" className={'fv-button' + (design.button_width === 'full' ? ' fv-button-full' : '')} disabled={sending} {...select('design:button')}>
      {sending ? 'Enviando…' : buttonLabel ?? design.button_label}<ArrowRight size={16} />
    </button>
  </form>;
}

function FieldControl({ field, id, value, onChange, wrap }: { field: CaptureField; id: string; value: Answer; onChange: (v: Answer) => void; wrap: object | undefined }) {
  const cls = 'fv-field ' + (field.width === 'half' ? 'fv-half' : 'fv-full');
  const label = <>{field.label}{field.required && ' *'}</>;
  const help = field.help_text ? <small className="fv-help">{field.help_text}</small> : null;
  if (field.type === 'heading') return <h2 className={cls + ' fv-heading'} {...wrap}>{field.label}</h2>;
  if (field.type === 'paragraph') return <p className={cls + ' fv-paragraph'} {...wrap}>{field.label}</p>;
  if (field.type === 'divider') return <hr className={cls + ' fv-divider'} {...wrap} />;
  if (field.type === 'checkbox') return <div className={cls} {...wrap}><label className="fv-check"><input type="checkbox" checked={value === true} required={field.required} onChange={(e) => onChange(e.target.checked)} /><span>{label}</span></label>{help}</div>;
  if (field.type === 'radio') return <fieldset className={cls + ' fv-group'} {...wrap}><legend>{label}</legend>{field.options.map((o) => <label className="fv-check" key={o}><input type="radio" name={id} required={field.required} checked={value === o} onChange={() => onChange(o)} /><span>{o}</span></label>)}{help}</fieldset>;
  if (field.type === 'multiselect') {
    const chosen = Array.isArray(value) ? value : [];
    return <fieldset className={cls + ' fv-group'} {...wrap}><legend>{label}</legend>{field.options.map((o) => <label className="fv-check" key={o}><input type="checkbox" checked={chosen.includes(o)} onChange={(e) => onChange(e.target.checked ? [...chosen, o] : chosen.filter((x) => x !== o))} /><span>{o}</span></label>)}{help}</fieldset>;
  }
  const text = typeof value === 'string' ? value : '';
  const common = { id, required: field.required, value: text, placeholder: field.placeholder, onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => onChange(e.target.value) };
  return <div className={cls} {...wrap}><label htmlFor={id}>{label}</label>
    {field.type === 'select' ? <select {...common}><option value="">Selecione…</option>{field.options.map((o) => <option key={o} value={o}>{o}</option>)}</select>
      : field.type === 'textarea' ? <textarea {...common} maxLength={2000} rows={4} />
      : <input {...common} maxLength={2000} type={({ number: 'number', date: 'date', email: 'email', url: 'url', phone: 'tel' } as Record<string, string>)[field.type] || 'text'} step={field.type === 'number' ? 'any' : undefined} />}
    {help}</div>;
}

/** Page chrome around the form: background, card, logo/brand, width and alignment from the design settings. */
export function FormPage({ form, ...rest }: Props) {
  const design = { ...DEFAULT_DESIGN, ...form.design };
  const accent = rest.accent || form.accent_color;
  return <main className={'fv-page fv-' + design.layout + ' fv-align-' + design.align} style={formStyle(design, accent)}>
    <section className="fv-card">
      {(design.logo_url || design.show_brand) && <div className="fv-brand">
        {design.logo_url ? <img src={design.logo_url} alt={form.brand_name || ''} /> : <><img src="/mark.svg" width="28" height="28" alt="" /><span>{form.brand_name || 'antares'}</span></>}
      </div>}
      <FormView form={form} {...rest} />
    </section>
  </main>;
}
