'use client';
import { useId, type ReactNode } from 'react';

type Common = { label: string; help?: string };
const Wrap = ({ label, help, htmlFor, children }: Common & { htmlFor?: string; children: ReactNode }) => (
  <div className="bld-control"><label htmlFor={htmlFor}>{label}</label>{children}{help && <small>{help}</small>}</div>
);

export function TextInput({ label, help, value, onChange, placeholder, maxLength = 200, type = 'text', required }: Common & {
  value: string; onChange: (v: string) => void; placeholder?: string; maxLength?: number; type?: string; required?: boolean;
}) {
  const id = useId();
  return <Wrap label={label} help={help} htmlFor={id}><input id={id} type={type} value={value} placeholder={placeholder} maxLength={maxLength} required={required} onChange={(e) => onChange(e.target.value)} /></Wrap>;
}
export function TextAreaInput({ label, help, value, onChange, rows = 3, maxLength = 2000, placeholder }: Common & {
  value: string; onChange: (v: string) => void; rows?: number; maxLength?: number; placeholder?: string;
}) {
  const id = useId();
  return <Wrap label={label} help={help} htmlFor={id}><textarea id={id} value={value} rows={rows} maxLength={maxLength} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /></Wrap>;
}
export function SelectInput<T extends string | number>({ label, help, value, onChange, options }: Common & {
  value: T; onChange: (v: T) => void; options: { value: T; label: string }[];
}) {
  const id = useId();
  return <Wrap label={label} help={help} htmlFor={id}><select id={id} value={String(value)} onChange={(e) => {
    const picked = options.find((o) => String(o.value) === e.target.value); if (picked) onChange(picked.value);
  }}>{options.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}</select></Wrap>;
}
export function ToggleInput({ label, help, checked, onChange }: Common & { checked: boolean; onChange: (v: boolean) => void }) {
  return <div className="bld-control"><label className="bld-toggle"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><span>{label}</span></label>{help && <small>{help}</small>}</div>;
}
export function ColorInput({ label, value, onChange, allowEmpty = false, fallback = '#ffffff' }: Common & {
  value: string; onChange: (v: string) => void; allowEmpty?: boolean; fallback?: string;
}) {
  const id = useId();
  return <Wrap label={label} htmlFor={id}><div className="bld-color">
    <input id={id} type="color" value={/^#[0-9a-f]{6}$/i.test(value) ? value : fallback} onChange={(e) => onChange(e.target.value)} aria-label={label} />
    <input type="text" value={value} maxLength={7} placeholder={allowEmpty ? 'Padrão' : '#000000'} aria-label={label + ' (código)'} onChange={(e) => {
      const next = e.target.value.trim(); if (next === '' ? allowEmpty : /^#[0-9a-f]{0,6}$/i.test(next)) onChange(next);
    }} onBlur={(e) => { if (e.target.value && !/^#[0-9a-f]{6}$/i.test(e.target.value)) onChange(allowEmpty ? '' : fallback); }} />
    {allowEmpty && value && <button type="button" className="bld-link" onClick={() => onChange('')}>Limpar</button>}
  </div></Wrap>;
}
export function RangeInput({ label, value, onChange, min, max, step = 1, unit = '' }: Common & {
  value: number; onChange: (v: number) => void; min: number; max: number; step?: number; unit?: string;
}) {
  const id = useId();
  return <Wrap label={`${label}: ${value}${unit}`} htmlFor={id}><input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} /></Wrap>;
}
export function Segmented<T extends string>({ label, value, onChange, options }: Common & {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; title?: string }[];
}) {
  return <div className="bld-control"><span className="bld-label" id={label}>{label}</span><div className="bld-segmented" role="radiogroup" aria-labelledby={label}>
    {options.map((o) => <button key={o.value} type="button" role="radio" aria-checked={value === o.value} title={o.title} className={value === o.value ? 'active' : ''} onClick={() => onChange(o.value)}>{o.label}</button>)}
  </div></div>;
}
export function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="bld-section"><h3>{title}</h3><div className="bld-fields">{children}</div></section>;
}
