'use client';
import { SelectInput, TextAreaInput, TextInput, ToggleInput, Section, Segmented } from '@/components/builder/controls';
import { FIELD_TYPES, hasOptions, isLayout, type BaseFieldConfig, type CaptureField, type FieldType } from './types';

const CONDITION_TYPES = ['select', 'radio', 'checkbox', 'text'];
export type DraftField = CaptureField & { auto?: boolean };

export function FieldInspector({ field, index, fields, onChange, onKeyEdit }: {
  field: DraftField; index: number; fields: DraftField[]; onChange: (patch: Partial<DraftField>) => void; onKeyEdit: (key: string) => void;
}) {
  const layout = isLayout(field.type);
  const earlier = fields.slice(0, index).filter((f) => CONDITION_TYPES.includes(f.type));
  const source = fields.find((f) => f.key === field.show_if?.field);
  return <>
    <Section title={layout ? 'Conteúdo' : 'Pergunta'}>
      {field.type === 'paragraph'
        ? <TextAreaInput label="Texto" value={field.label} onChange={(label) => onChange({ label })} maxLength={120} rows={3} />
        : <TextInput label={layout ? 'Texto' : 'Pergunta'} value={field.label} onChange={(label) => onChange({ label })} maxLength={120} required />}
      {!layout && <>
        <SelectInput<FieldType> label="Tipo" value={field.type} onChange={(type) => onChange({ type, options: hasOptions(type) && !field.options.length ? ['Opção 1', 'Opção 2'] : field.options })}
          options={FIELD_TYPES.filter((t) => t.group !== 'layout').map((t) => ({ value: t.value, label: t.label }))} />
        {!['checkbox', 'radio', 'multiselect'].includes(field.type) && <TextInput label="Texto de exemplo" value={field.placeholder || ''} onChange={(placeholder) => onChange({ placeholder })} maxLength={120} />}
        <TextInput label="Texto de ajuda" help="Aparece abaixo do campo." value={field.help_text || ''} onChange={(help_text) => onChange({ help_text })} maxLength={300} />
        <ToggleInput label="Resposta obrigatória" checked={field.required} onChange={(required) => onChange({ required })} />
      </>}
      {hasOptions(field.type) && <TextAreaInput label="Opções, uma por linha" value={field.options.join('\n')} rows={5} onChange={(value) => onChange({ options: value.split('\n') })} />}
    </Section>
    {!field.type.startsWith('divider') && <Section title="Layout">
      <Segmented label="Largura" value={field.width || 'full'} onChange={(width) => onChange({ width })} options={[{ value: 'full', label: 'Linha inteira' }, { value: 'half', label: 'Meia linha' }]} />
    </Section>}
    {index > 0 && <Section title="Condição">
      <SelectInput label="Mostrar somente quando" value={field.show_if?.field || ''} options={[{ value: '', label: 'Sempre mostrar' }, ...earlier.map((f) => ({ value: f.key, label: f.label || f.key }))]}
        onChange={(value) => onChange({ show_if: value ? { field: value, equals: fields.find((f) => f.key === value)?.type === 'checkbox' ? true : '' } : undefined })} />
      {field.show_if && source && (source.type === 'checkbox'
        ? <SelectInput label="Resposta esperada" value={String(field.show_if.equals)} options={[{ value: 'true', label: 'Marcado' }, { value: 'false', label: 'Desmarcado' }]} onChange={(v) => onChange({ show_if: { field: source.key, equals: v === 'true' } })} />
        : hasOptions(source.type)
          ? <SelectInput label="Resposta esperada" value={String(field.show_if.equals)} options={[{ value: '', label: 'Selecione…' }, ...source.options.filter(Boolean).map((o) => ({ value: o, label: o }))]} onChange={(equals) => onChange({ show_if: { field: source.key, equals } })} />
          : <TextInput label="Resposta esperada" value={String(field.show_if.equals)} onChange={(equals) => onChange({ show_if: { field: source.key, equals } })} />)}
    </Section>}
    <Section title="Avançado">
      <TextInput label="Identificador" help="Usado nos relatórios e integrações. Apenas letras minúsculas, números e _." value={field.key} maxLength={40} onChange={(v) => onKeyEdit(v.toLowerCase().replace(/[^a-z0-9_]/g, ''))} />
      {!layout && <TextInput label="Campo personalizado do contato (opcional)" help="Grava a resposta neste campo do contato." value={field.map_to || ''} maxLength={40} onChange={(v) => onChange({ map_to: v.toLowerCase().replace(/[^a-z0-9_]/g, '') })} />}
    </Section>
  </>;
}

export function BaseFieldInspector({ name, config, fallback, canHide, canRequire, onChange }: {
  name: string; config: BaseFieldConfig; fallback: string; canHide?: boolean; canRequire?: boolean; onChange: (patch: BaseFieldConfig) => void;
}) {
  return <Section title={name}>
    <TextInput label="Rótulo" value={config.label ?? fallback} maxLength={120} onChange={(label) => onChange({ label })} />
    <TextInput label="Texto de exemplo" value={config.placeholder ?? ''} maxLength={120} onChange={(placeholder) => onChange({ placeholder })} />
    {canHide && <ToggleInput label="Exibir este campo" checked={config.visible !== false} onChange={(visible) => onChange({ visible })} />}
    {canRequire && config.visible !== false && <ToggleInput label="Obrigatório" checked={!!config.required} onChange={(required) => onChange({ required })} />}
  </Section>;
}
