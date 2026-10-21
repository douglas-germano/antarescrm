'use client';
import { AlignCenter, AlignLeft, AlignRight, Plus, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui';
import { ColorInput, RangeInput, Section, Segmented, SelectInput, TextAreaInput, TextInput, ToggleInput } from '@/components/builder/controls';
import type { Row } from '@/lib/types';
import { embedUrl, type Block, type BlockStyle } from './types';

type Props = {
  block: Block; forms: Row[]; onProps: (patch: Record<string, any>) => void; onStyle: (patch: Partial<BlockStyle>) => void; onNewForm: () => Promise<void>; busy: boolean;
};

export function BlockInspector({ block, forms, onProps, onStyle, onNewForm, busy }: Props) {
  const p = block.props;
  const s = block.style || {};
  const hasText = ['heading', 'text', 'list', 'testimonial', 'faq', 'button', 'countdown'].includes(block.type);
  return <>
    <Section title="Conteúdo">
      {block.type === 'heading' && <>
        <TextInput label="Texto" value={p.text || ''} maxLength={200} onChange={(text) => onProps({ text })} />
        <Segmented label="Tamanho" value={String(p.level || 2) as '1' | '2' | '3'} onChange={(v) => onProps({ level: Number(v) })} options={[{ value: '1', label: 'Grande' }, { value: '2', label: 'Médio' }, { value: '3', label: 'Pequeno' }]} />
      </>}
      {block.type === 'text' && <>
        <TextAreaInput label="Texto" value={p.text || ''} rows={6} maxLength={5000} onChange={(text) => onProps({ text })} />
        <Segmented label="Tamanho da letra" value={p.size || 'md'} onChange={(size) => onProps({ size })} options={[{ value: 'sm', label: 'Pequena' }, { value: 'md', label: 'Normal' }, { value: 'lg', label: 'Grande' }]} />
      </>}
      {block.type === 'image' && <>
        <TextInput label="Link da imagem (https://…)" type="url" value={p.src || ''} maxLength={500} onChange={(src) => onProps({ src })} help="Use uma imagem hospedada na web." />
        <TextInput label="Descrição (acessibilidade)" value={p.alt || ''} maxLength={200} onChange={(alt) => onProps({ alt })} />
        <TextInput label="Link ao clicar (opcional)" type="url" value={p.link || ''} maxLength={500} onChange={(link) => onProps({ link })} />
        <ToggleInput label="Bordas arredondadas" checked={!!p.rounded} onChange={(rounded) => onProps({ rounded })} />
      </>}
      {block.type === 'video' && <TextInput label="Link do vídeo" type="url" value={p.url || ''} maxLength={500} placeholder="https://www.youtube.com/watch?v=…" onChange={(url) => onProps({ url })} help={p.url && !embedUrl(p.url) ? 'Link não reconhecido: use YouTube ou Vimeo.' : 'YouTube ou Vimeo.'} />}
      {block.type === 'button' && <>
        <TextInput label="Texto do botão" value={p.label || ''} maxLength={80} onChange={(label) => onProps({ label })} />
        <Segmented label="Ao clicar" value={p.action || 'next'} onChange={(action) => onProps({ action })} options={[{ value: 'next', label: 'Próxima página' }, { value: 'url', label: 'Abrir link' }]} />
        {p.action === 'url' && <TextInput label="Link" type="url" value={p.url || ''} maxLength={500} placeholder="https://" onChange={(url) => onProps({ url })} help="Aceita https://, mailto: e tel:." />}
        <Segmented label="Estilo" value={p.variant || 'primary'} onChange={(variant) => onProps({ variant })} options={[{ value: 'primary', label: 'Destaque' }, { value: 'secondary', label: 'Contorno' }]} />
        <ToggleInput label="Largura total" checked={!!p.full_width} onChange={(full_width) => onProps({ full_width })} />
      </>}
      {block.type === 'form' && <>
        <SelectInput label="Formulário" value={p.form_id || ''} onChange={(form_id) => onProps({ form_id })} options={[{ value: '', label: 'Selecione…' }, ...forms.map((f) => ({ value: f.id, label: f.name }))]} />
        <div className="bld-grid-2">
          <Button variant="secondary" disabled={busy} onClick={onNewForm}><Plus size={14} /> Novo</Button>
          {p.form_id && <Link className="btn btn-secondary" href={'/formularios/' + p.form_id} target="_blank">Personalizar</Link>}
        </div>
        <Segmented label="Depois do envio" value={p.on_submit || 'next'} onChange={(on_submit) => onProps({ on_submit })} options={[{ value: 'next', label: 'Próxima página' }, { value: 'message', label: 'Mensagem' }, { value: 'url', label: 'Link' }]} />
        {p.on_submit === 'url' && <TextInput label="Link de destino" type="url" value={p.url || ''} maxLength={500} placeholder="https://" onChange={(url) => onProps({ url })} />}
        <small className="bld-hint">O formulário é ativado ao publicar o funil. Campos, cores e botão são editados em Formulários.</small>
      </>}
      {block.type === 'list' && <>
        <TextAreaInput label="Itens, um por linha" value={(p.items || []).join('\n')} rows={6} onChange={(value) => onProps({ items: value.split('\n').slice(0, 20) })} />
        <Segmented label="Marcador" value={p.icon || 'check'} onChange={(icon) => onProps({ icon })} options={[{ value: 'check', label: 'Check' }, { value: 'dot', label: 'Ponto' }]} />
      </>}
      {block.type === 'testimonial' && <>
        <TextAreaInput label="Depoimento" value={p.quote || ''} maxLength={500} onChange={(quote) => onProps({ quote })} />
        <TextInput label="Nome" value={p.author || ''} maxLength={100} onChange={(author) => onProps({ author })} />
        <TextInput label="Cargo / empresa" value={p.role || ''} maxLength={100} onChange={(role) => onProps({ role })} />
        <TextInput label="Foto (link https://…)" type="url" value={p.avatar || ''} maxLength={500} onChange={(avatar) => onProps({ avatar })} />
      </>}
      {block.type === 'faq' && <>
        {(p.items || []).map((item: { q: string; a: string }, i: number) => <div key={i} className="bld-card">
          <TextInput label={`Pergunta ${i + 1}`} value={item.q} maxLength={200} onChange={(q) => onProps({ items: p.items.map((x: any, n: number) => (n === i ? { ...x, q } : x)) })} />
          <TextAreaInput label="Resposta" value={item.a} maxLength={1500} rows={3} onChange={(a) => onProps({ items: p.items.map((x: any, n: number) => (n === i ? { ...x, a } : x)) })} />
          <Button variant="ghost" onClick={() => onProps({ items: p.items.filter((_: any, n: number) => n !== i) })}><Trash2 size={14} /> Remover</Button>
        </div>)}
        <Button variant="secondary" disabled={(p.items || []).length >= 15} onClick={() => onProps({ items: [...(p.items || []), { q: '', a: '' }] })}><Plus size={14} /> Adicionar pergunta</Button>
      </>}
      {block.type === 'countdown' && <>
        <Segmented label="Tipo" value={p.mode || 'evergreen'} onChange={(mode) => onProps({ mode })} options={[{ value: 'evergreen', label: 'Por visitante' }, { value: 'fixed', label: 'Data fixa' }]} />
        {p.mode === 'fixed'
          ? <TextInput label="Termina em" type="datetime-local" value={(p.target || '').slice(0, 16)} onChange={(v) => onProps({ target: v ? new Date(v).toISOString() : '' })} />
          : <RangeInput label="Duração para cada visitante" min={5} max={1440} step={5} value={p.minutes || 60} unit=" min" onChange={(minutes) => onProps({ minutes })} />}
        <TextInput label="Texto ao terminar" value={p.expired_text || ''} maxLength={200} onChange={(expired_text) => onProps({ expired_text })} />
      </>}
      {block.type === 'spacer' && <RangeInput label="Altura" min={8} max={160} step={8} value={p.height || 32} unit="px" onChange={(height) => onProps({ height })} />}
      {block.type === 'divider' && <p className="bld-hint">Linha divisória. Ajuste o espaçamento em Aparência.</p>}
    </Section>
    <Section title="Aparência">
      {hasText || block.type === 'image' ? <Segmented label="Alinhamento" value={s.align || 'left'} onChange={(align) => onStyle({ align })} options={[{ value: 'left', label: <AlignLeft size={14} />, title: 'Esquerda' }, { value: 'center', label: <AlignCenter size={14} />, title: 'Centro' }, { value: 'right', label: <AlignRight size={14} />, title: 'Direita' }]} /> : null}
      <Segmented label="Espaçamento" value={s.padding || 'md'} onChange={(padding) => onStyle({ padding })} options={[{ value: 'none', label: 'Nenhum' }, { value: 'sm', label: 'P' }, { value: 'md', label: 'M' }, { value: 'lg', label: 'G' }]} />
      <Segmented label="Largura do conteúdo" value={s.width || 'normal'} onChange={(width) => onStyle({ width })} options={[{ value: 'narrow', label: 'Estreita' }, { value: 'normal', label: 'Normal' }, { value: 'wide', label: 'Larga' }]} />
      <ColorInput label="Cor de fundo" value={s.background || ''} allowEmpty onChange={(background) => onStyle({ background })} />
      <ColorInput label="Cor do texto" value={s.color || ''} allowEmpty fallback="#25282b" onChange={(color) => onStyle({ color })} />
    </Section>
  </>;
}
