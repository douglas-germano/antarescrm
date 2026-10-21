'use client';
import { useState } from 'react';
import { Modal, Button } from './ui';
import { patch, refreshAll } from '@/lib/api';
import { useNotify } from './providers';
import type { Row } from '@/lib/types';
export type CaptureField = { key: string; label: string; type: string; required: boolean; options: string[]; map_to?: string; show_if?: { field: string; equals: string | boolean } };
const types: Record<string,string> = { text: 'Texto', textarea: 'Texto longo', number: 'Número', date: 'Data', select: 'Seleção', checkbox: 'Caixa de seleção' };
export function FormFieldsEditor({ form, onClose }: { form: Row; onClose: () => void }) {
  const [fields, setFields] = useState<CaptureField[]>(form.fields || []);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const { notify } = useNotify();
  const change = (index: number, values: Partial<CaptureField>) => setFields(old => old.map((field,i) => i === index ? { ...field, ...values } : field));
  return <Modal open onClose={() => { if (!busy) onClose(); }} title={'Campos — ' + form.name} wide>
    <form className="stack" onSubmit={async event => { event.preventDefault(); if (busy) return; setBusy(true); setError('');
      try { await patch('/forms/' + form.id, { fields: fields.map(field => ({ ...field, options: field.options.map(option => option.trim()).filter(Boolean), map_to: field.map_to || undefined, show_if: field.show_if?.field ? field.show_if : undefined })) }); await refreshAll(); notify('Campos salvos.'); onClose(); }
      catch (e) { setError((e as Error).message); } finally { setBusy(false); }
    }}>
      <p className="muted">Nome, e-mail e telefone já estão incluídos.</p>
      <fieldset disabled={busy} className="stack">
      {fields.map((field,index) => <section className="workflow-step stack" key={index}>
        <div className="form-grid">
          <label>Pergunta<input required maxLength={120} value={field.label} onChange={e => change(index, { label: e.target.value })} /></label>
          <label>Identificador<input required pattern="[a-z][a-z0-9_]{0,39}" maxLength={40} value={field.key} onChange={e => change(index, { key: e.target.value })} /><small>Exemplo: interesse, cidade ou valor_estimado.</small></label>
          <label>Tipo<select value={field.type} onChange={e => change(index, { type: e.target.value })}>{Object.entries(types).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Campo personalizado do contato (opcional)<input maxLength={40} pattern="[a-z][a-z0-9_]{0,39}" value={field.map_to || ''} onChange={e => change(index, { map_to: e.target.value })} /></label>
        </div>
        {field.type === 'select' && <label>Opções, uma por linha<textarea required value={field.options.join('\n')} onChange={e => change(index, { options: e.target.value.split('\n') })} /></label>}
        <label className="checkbox-label"><input type="checkbox" checked={field.required} onChange={e => change(index, { required: e.target.checked })} />Resposta obrigatória</label>
        {index > 0 && <div className="form-grid"><label>Mostrar somente quando<select value={field.show_if?.field || ''} onChange={e => change(index, { show_if: e.target.value ? { field: e.target.value, equals: fields.find(f => f.key === e.target.value)?.type === 'checkbox' ? true : '' } : undefined })}><option value="">Sempre mostrar</option>{fields.slice(0,index).filter(f => ['select', 'checkbox', 'text'].includes(f.type)).map(previous => <option value={previous.key} key={previous.key}>{previous.label || previous.key}</option>)}</select></label>
          {field.show_if?.field && (fields.find(f => f.key === field.show_if?.field)?.type === 'checkbox' ? <label>Resposta esperada<select value={String(field.show_if.equals)} onChange={e => change(index, { show_if: { field: field.show_if!.field, equals: e.target.value === 'true' } })}><option value="true">Marcado</option><option value="false">Desmarcado</option></select></label> : <label>Resposta esperada<input required value={String(field.show_if.equals)} onChange={e => change(index, { show_if: { field: field.show_if!.field, equals: e.target.value } })} /></label>)}</div>}
        <Button variant="danger" onClick={() => setFields(old => old.filter((_,i) => i !== index).map(next => next.show_if?.field === field.key ? { ...next, show_if:undefined }:next))}>Remover pergunta</Button>
      </section>)}
      <Button variant="secondary" disabled={fields.length >= 30} onClick={() => setFields(old => { let next = old.length + 1; while (old.some(field => field.key === 'campo_' + next)) next++; return [...old, { key: 'campo_' + next, label: '', type: 'text', required: false, options: [] }]; })}>Adicionar pergunta</Button>
      </fieldset>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-footer"><Button variant="secondary" disabled={busy} onClick={onClose}>Cancelar</Button><Button disabled={busy} type="submit">{busy ? 'Salvando…' : 'Salvar campos'}</Button></div>
    </form>
  </Modal>;
}
