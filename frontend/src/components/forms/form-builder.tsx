'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowDown, ArrowLeft, ArrowUp, Copy, ExternalLink, GripVertical, Monitor, Plus, Smartphone, Trash2 } from 'lucide-react';
import { Button, ConfirmDialog } from '@/components/ui';
import { useNotify } from '@/components/providers';
import { patch, refreshAll, remove as removeRecord } from '@/lib/api';
import { usePublicOrigin } from '@/lib/public-origin';
import { Section, SelectInput, TextAreaInput, TextInput, ToggleInput } from '@/components/builder/controls';
import { FormPage } from './form-view';
import { AfterSubmitPanel, DesignPanel } from './design-panel';
import { BaseFieldInspector, FieldInspector, type DraftField } from './field-inspector';
import { DEFAULT_CONSENT, DEFAULT_DESIGN, FIELD_TYPES, hasOptions, isLayout, typeLabel, type BaseFieldConfig, type BaseFields, type FieldType, type FormDesign, type FormSettings, type PublicForm } from './types';
import type { Row } from '@/lib/types';

const RESERVED = ['name', 'email', 'phone', 'consent', 'website'];
type Draft = {
  name: string; headline: string; description: string; brand_name: string; accent_color: string; success_message: string;
  stage_id: string; source: string; active: boolean; fields: DraftField[]; design: FormDesign; settings: FormSettings;
};
type Tab = 'element' | 'design' | 'page';

export function slugKey(label: string, taken: string[]) {
  const base = label.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 34);
  let key = /^[a-z]/.test(base) ? base : 'campo_' + base;
  if (key === 'campo_') key = 'campo';
  if (RESERVED.includes(key)) key = 'campo_' + key;
  let candidate = key, n = 2;
  while (taken.includes(candidate)) candidate = `${key}_${n++}`;
  return candidate;
}
/** A condition must point at an earlier field; reordering or deleting can break that, so drop what no longer applies. */
export function fixConditions(fields: DraftField[]): DraftField[] {
  return fields.map((f, i) => (f.show_if && !fields.slice(0, i).some((p) => p.key === f.show_if!.field) ? { ...f, show_if: undefined } : f));
}
function makeField(type: FieldType, fields: DraftField[]): DraftField {
  const label = FIELD_TYPES.find((t) => t.value === type)!.label;
  const text = isLayout(type) ? (type === 'heading' ? 'Título da seção' : type === 'paragraph' ? 'Texto explicativo' : 'Divisória') : 'Nova pergunta';
  return { key: slugKey(isLayout(type) ? label : text, fields.map((f) => f.key)), label: text, type, required: false, options: hasOptions(type) ? ['Opção 1', 'Opção 2'] : [], width: 'full', auto: !isLayout(type) };
}
function toDraft(form: Row): Draft {
  return {
    name: form.name, headline: form.headline, description: form.description || '', brand_name: form.brand_name || '', accent_color: form.accent_color,
    success_message: form.success_message, stage_id: form.stage_id, source: form.source, active: !!form.active,
    fields: (form.fields || []).map((f: DraftField) => ({ ...f, options: f.options || [], width: f.width || 'full' })),
    design: { ...DEFAULT_DESIGN, ...form.design }, settings: form.settings || {},
  };
}
function toPayload(d: Draft) {
  const fields = d.fields.map(({ auto: _auto, ...f }) => ({
    ...f, required: isLayout(f.type) ? false : f.required, options: hasOptions(f.type) ? f.options.map((o) => o.trim()).filter(Boolean) : [],
    map_to: f.map_to || undefined, show_if: f.show_if?.field ? f.show_if : undefined, placeholder: f.placeholder || '', help_text: f.help_text || '',
  }));
  const clean = (c?: BaseFieldConfig) => c && Object.fromEntries(Object.entries(c).filter(([, v]) => v !== '' && v !== undefined));
  const base = Object.fromEntries((['name', 'email', 'phone'] as const).flatMap((k) => { const v = clean(d.settings.base_fields?.[k]); return v && Object.keys(v).length ? [[k, v]] : []; }));
  const settings: FormSettings = { ...(d.settings.consent_text ? { consent_text: d.settings.consent_text } : {}), ...(Object.keys(base).length ? { base_fields: base as BaseFields } : {}), ...(d.settings.after_submit ? { after_submit: d.settings.after_submit } : {}) };
  return { ...d, fields, settings };
}

export function FormBuilder({ form, stages }: { form: Row; stages: Row[] }) {
  const { notify } = useNotify();
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [draft, setDraft] = useState<Draft>(() => toDraft(form));
  const [saved, setSaved] = useState(() => JSON.stringify(toPayload(toDraft(form))));
  const [selected, setSelected] = useState<string>('');
  const [tab, setTab] = useState<Tab>('element');
  const [mobile, setMobile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [drag, setDrag] = useState<{ from: number; over: number } | null>(null);
  const dirty = JSON.stringify(toPayload(draft)) !== saved;
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const set = (patchValues: Partial<Draft>) => setDraft((d) => ({ ...d, ...patchValues }));
  const setFields = (fn: (f: DraftField[]) => DraftField[]) => setDraft((d) => ({ ...d, fields: fixConditions(fn(d.fields)) }));
  const setBase = (key: 'name' | 'email' | 'phone', values: BaseFieldConfig) => setDraft((d) => ({ ...d, settings: { ...d.settings, base_fields: { ...d.settings.base_fields, [key]: { ...d.settings.base_fields?.[key], ...values } } } }));
  const choose = (id: string) => { setSelected(id); setTab(id === 'design:button' ? 'design' : 'element'); };
  const index = draft.fields.findIndex((f) => f.key === selected);
  const field = index >= 0 ? draft.fields[index] : undefined;

  const preview: PublicForm = useMemo(() => ({
    id: form.id, headline: draft.headline, description: draft.description, consent_text: draft.settings.consent_text || DEFAULT_CONSENT,
    fields: draft.fields.filter((f) => f.label || f.type === 'divider'), brand_name: draft.brand_name, accent_color: draft.accent_color,
    design: draft.design, base_fields: draft.settings.base_fields || {},
  }), [draft, form.id]);

  const changeField = (key: string, values: Partial<DraftField>) => setFields((fs) => fs.map((f) => {
    if (f.key !== key) return f;
    const next = { ...f, ...values };
    if (values.label !== undefined && f.auto && !isLayout(f.type)) next.key = slugKey(values.label || 'campo', fs.filter((x) => x.key !== key).map((x) => x.key));
    return next;
  }));
  const renameKey = (key: string, value: string) => {
    if (!value || RESERVED.includes(value) || draft.fields.some((f) => f.key === value && f.key !== key) || !/^[a-z]/.test(value)) return;
    setFields((fs) => fs.map((f) => (f.key === key ? { ...f, key: value, auto: false } : f.show_if?.field === key ? { ...f, show_if: { ...f.show_if, field: value } } : f)));
    setSelected(value);
  };
  const move = (from: number, to: number) => {
    if (to < 0 || to >= draft.fields.length || from === to) return;
    setFields((fs) => { const next = [...fs]; const [item] = next.splice(from, 1); next.splice(to, 0, item); return next; });
  };
  const add = (type: FieldType) => { const created = makeField(type, draft.fields); setFields((fs) => [...fs, created]); choose(created.key); };
  const duplicate = (i: number) => {
    const source = draft.fields[i]; const copy = { ...source, key: slugKey(source.key, draft.fields.map((f) => f.key)), show_if: source.show_if, auto: false };
    setFields((fs) => [...fs.slice(0, i + 1), copy, ...fs.slice(i + 1)]); choose(copy.key);
  };
  const remove = (i: number) => { setFields((fs) => fs.filter((_, n) => n !== i)); setSelected(''); };

  async function save() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const payload = toPayload(draft);
      await patch('/forms/' + form.id, payload);
      setSaved(JSON.stringify(payload));
      setDraft((d) => ({ ...d, fields: d.fields.map((f) => ({ ...f, auto: false })) }));
      await refreshAll(); notify('Formulário salvo.');
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const link = usePublicOrigin() + '/f/' + form.id;

  return <div className="page">
    <div className="bld-toolbar">
      <Link className="btn btn-ghost" href="/formularios"><ArrowLeft size={16} /> Formulários</Link>
      <strong>{draft.name}</strong>
      <span className="spacer" />
      <span className="bld-status" data-dirty={dirty} role="status">{dirty ? 'Alterações não salvas' : 'Tudo salvo'}</span>
      <Button variant="ghost" aria-label="Copiar link" onClick={async () => { try { await navigator.clipboard.writeText(link); notify('Link copiado.'); } catch { notify('Não foi possível copiar.', 'error'); } }}><Copy size={16} /></Button>
      <a className="btn btn-secondary" href={'/f/' + form.id} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Abrir</a>
      <Button variant="ghost" aria-label="Excluir formulário" disabled={busy} onClick={() => setDeleting(true)}><Trash2 size={16} /></Button>
      <Button disabled={!dirty || busy} onClick={save}>{busy ? 'Salvando…' : 'Salvar'}</Button>
    </div>
    <ConfirmDialog open={deleting} onClose={() => setDeleting(false)} title="Excluir formulário"
      description={`O formulário "${draft.name}" e o link público dele serão removidos. Se ele já recebeu solicitações ou está em uso em um funil, a exclusão é recusada.`}
      onConfirm={async () => { await removeRecord('/forms/' + form.id); setSaved(JSON.stringify(toPayload(draft))); await refreshAll(); notify('Formulário excluído.'); router.push('/formularios'); }} />
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="bld">
      <aside className="bld-panel bld-sticky" aria-label="Estrutura do formulário">
        <header><h2>Campos</h2></header>
        <div className="bld-panel-body">
          <ul className="bld-list">
            {[['base:name', 'Nome', 'Obrigatório'], ['base:email', 'E-mail', 'Obrigatório'], ['base:phone', 'Telefone', draft.settings.base_fields?.phone?.visible === false ? 'Oculto' : 'Opcional']].map(([id, label, note]) => (
              <li key={id}><button type="button" className="bld-item" aria-current={selected === id} onClick={() => choose(id)} style={{ width: '100%' }}><span className="name">{draft.settings.base_fields?.[id.slice(5) as 'name']?.label || label}</span><small>{note}</small></button></li>
            ))}
            {draft.fields.map((f, i) => (
              <li key={f.key} draggable onDragStart={() => setDrag({ from: i, over: i })} onDragOver={(e) => { e.preventDefault(); if (drag && drag.over !== i) setDrag({ ...drag, over: i }); }}
                onDrop={(e) => { e.preventDefault(); if (drag) move(drag.from, i); setDrag(null); }} onDragEnd={() => setDrag(null)}>
                <div className="bld-item" role="button" tabIndex={0} aria-current={selected === f.key} data-dragging={drag?.from === i} data-over={drag ? drag.over === i && drag.from !== i : false}
                  onClick={() => choose(f.key)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(f.key); } }}>
                  <GripVertical size={14} className="grip" aria-hidden />
                  <span className="name">{f.label || '(sem texto)'}<small>{typeLabel(f.type)}</small></span>
                  <span className="actions" onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" aria-label="Mover para cima" disabled={i === 0} onClick={() => move(i, i - 1)}><ArrowUp size={14} /></Button>
                    <Button variant="ghost" aria-label="Mover para baixo" disabled={i === draft.fields.length - 1} onClick={() => move(i, i + 1)}><ArrowDown size={14} /></Button>
                  </span>
                </div>
              </li>
            ))}
            <li><button type="button" className="bld-item" aria-current={selected === 'consent'} onClick={() => choose('consent')} style={{ width: '100%' }}><span className="name">Consentimento</span><small>Obrigatório</small></button></li>
          </ul>
          <Section title="Adicionar">
            <div className="bld-palette">{FIELD_TYPES.map((t) => <button type="button" key={t.value} disabled={draft.fields.length >= 60} onClick={() => add(t.value)}><Plus size={14} />{t.label}</button>)}</div>
          </Section>
        </div>
      </aside>

      <div className="bld-canvas">
        <div className="bld-toolbar" style={{ marginBottom: 'var(--space-3)' }}>
          <div className="bld-segmented" role="group" aria-label="Tamanho da prévia">
            <button type="button" className={!mobile ? 'active' : ''} onClick={() => setMobile(false)}><Monitor size={14} /> Computador</button>
            <button type="button" className={mobile ? 'active' : ''} onClick={() => setMobile(true)}><Smartphone size={14} /> Celular</button>
          </div>
          <span className="bld-status">Clique em um elemento da prévia para editá-lo.</span>
        </div>
        <div className="bld-canvas-frame" style={{ width: mobile ? 390 : '100%', maxWidth: '100%' }}>
          <FormPage form={preview} editor={{ selected, onSelect: choose }} />
        </div>
      </div>

      <aside className="bld-panel bld-sticky" aria-label="Propriedades">
        <header><div className="tabs" role="tablist">
          {([['element', 'Elemento'], ['design', 'Aparência'], ['page', 'Página']] as [Tab, string][]).map(([id, label]) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={'tab' + (tab === id ? ' active' : '')} onClick={() => setTab(id)}>{label}</button>)}
        </div></header>
        <div className="bld-panel-body">
          {tab === 'element' && (field
            ? <>
              <FieldInspector field={field} index={index} fields={draft.fields} onChange={(values) => changeField(field.key, values)} onKeyEdit={(value) => renameKey(field.key, value)} />
              <div className="bld-grid-2"><Button variant="secondary" onClick={() => duplicate(index)}><Copy size={14} /> Duplicar</Button><Button variant="danger" onClick={() => remove(index)}><Trash2 size={14} /> Remover</Button></div>
            </>
            : selected === 'base:name' ? <BaseFieldInspector name="Nome" config={draft.settings.base_fields?.name || {}} fallback="Nome" onChange={(v) => setBase('name', v)} />
            : selected === 'base:email' ? <BaseFieldInspector name="E-mail" config={draft.settings.base_fields?.email || {}} fallback="E-mail" onChange={(v) => setBase('email', v)} />
            : selected === 'base:phone' ? <BaseFieldInspector name="Telefone" config={draft.settings.base_fields?.phone || {}} fallback="Telefone / WhatsApp" canHide canRequire onChange={(v) => setBase('phone', v)} />
            : selected === 'consent' ? <Section title="Consentimento"><TextAreaInput label="Texto exibido ao lado da caixa" help="Fica registrado em cada solicitação, como prova do aceite." value={draft.settings.consent_text ?? DEFAULT_CONSENT} maxLength={255} onChange={(consent_text) => set({ settings: { ...draft.settings, consent_text } })} /></Section>
            : <p className="bld-empty">Selecione um campo na lista ou na prévia para editar suas propriedades.</p>)}
          {tab === 'design' && <DesignPanel design={draft.design} accent={draft.accent_color} onChange={(values) => set({ design: { ...draft.design, ...values } })} onAccent={(accent_color) => set({ accent_color })} />}
          {tab === 'page' && <>
            <Section title="Página">
              <TextInput label="Nome interno" value={draft.name} maxLength={150} required onChange={(name) => set({ name })} />
              <TextInput label="Título" value={draft.headline} maxLength={180} required onChange={(headline) => set({ headline })} />
              <TextAreaInput label="Apresentação" value={draft.description} maxLength={2000} rows={4} onChange={(description) => set({ description })} />
              <TextInput label="Nome da empresa" value={draft.brand_name} maxLength={120} onChange={(brand_name) => set({ brand_name })} />
            </Section>
            <AfterSubmitPanel settings={draft.settings} success={draft.success_message} onSettings={(values) => set({ settings: { ...draft.settings, ...values } })} onSuccess={(success_message) => set({ success_message })} />
            <Section title="Contatos gerados">
              <SelectInput label="Etapa do funil para novos negócios" value={draft.stage_id} onChange={(stage_id) => set({ stage_id })} options={stages.map((s) => ({ value: s.id, label: (s.pipeline_name || 'Principal') + ' · ' + s.name }))} />
              <TextInput label="Origem dos leads" value={draft.source} maxLength={100} required onChange={(source) => set({ source })} />
              <ToggleInput label="Formulário público ativo" help="Desativado, o link deixa de aceitar envios." checked={draft.active} onChange={(active) => set({ active })} />
            </Section>
          </>}
        </div>
      </aside>
    </div>
  </div>;
}
