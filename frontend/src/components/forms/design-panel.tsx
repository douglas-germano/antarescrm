'use client';
import { AlignCenter, AlignLeft } from 'lucide-react';
import { ColorInput, RangeInput, Section, SelectInput, Segmented, TextInput, TextAreaInput, ToggleInput } from '@/components/builder/controls';
import { FONT_LABELS } from './theme';
import type { FormDesign, FormSettings } from './types';

export function DesignPanel({ design, accent, onChange, onAccent }: {
  design: FormDesign; accent: string; onChange: (patch: Partial<FormDesign>) => void; onAccent: (v: string) => void;
}) {
  return <>
    <Section title="Cores">
      <ColorInput label="Fundo da página" value={design.background} onChange={(background) => onChange({ background })} />
      <ColorInput label="Cor do cartão" value={design.card_color} onChange={(card_color) => onChange({ card_color })} />
      <ColorInput label="Cor do texto" value={design.text_color} onChange={(text_color) => onChange({ text_color })} />
      <ColorInput label="Cor de destaque (botão)" value={accent} onChange={onAccent} fallback="#e60000" />
    </Section>
    <Section title="Tipografia e forma">
      <SelectInput label="Fonte" value={design.font} onChange={(font) => onChange({ font })} options={Object.entries(FONT_LABELS).map(([value, label]) => ({ value: value as FormDesign['font'], label }))} />
      <RangeInput label="Arredondamento" min={0} max={32} value={design.radius} unit="px" onChange={(radius) => onChange({ radius })} />
      <Segmented label="Estilo da página" value={design.layout} onChange={(layout) => onChange({ layout })} options={[{ value: 'card', label: 'Com cartão' }, { value: 'plain', label: 'Sem cartão' }]} />
    </Section>
    <Section title="Layout">
      <RangeInput label="Largura máxima" min={320} max={960} step={20} value={design.max_width} unit="px" onChange={(max_width) => onChange({ max_width })} />
      <Segmented label="Alinhamento do cabeçalho" value={design.align} onChange={(align) => onChange({ align })} options={[{ value: 'left', label: <AlignLeft size={14} />, title: 'Esquerda' }, { value: 'center', label: <AlignCenter size={14} />, title: 'Centro' }]} />
    </Section>
    <Section title="Botão">
      <TextInput label="Texto do botão" value={design.button_label} maxLength={60} onChange={(button_label) => onChange({ button_label })} />
      <Segmented label="Formato" value={design.button_style} onChange={(button_style) => onChange({ button_style })} options={[{ value: 'pill', label: 'Pílula' }, { value: 'rounded', label: 'Arredondado' }, { value: 'square', label: 'Reto' }]} />
      <Segmented label="Largura" value={design.button_width} onChange={(button_width) => onChange({ button_width })} options={[{ value: 'auto', label: 'Automática' }, { value: 'full', label: 'Total' }]} />
    </Section>
    <Section title="Marca">
      <TextInput label="Link do logotipo (https://…)" value={design.logo_url} type="url" onChange={(logo_url) => onChange({ logo_url })} maxLength={500} help="Imagem hospedada na web. Vazio usa o nome da empresa." />
      <ToggleInput label="Exibir marca no topo" checked={design.show_brand} onChange={(show_brand) => onChange({ show_brand })} />
    </Section>
  </>;
}

export function AfterSubmitPanel({ settings, success, onSettings, onSuccess }: {
  settings: FormSettings; success: string; onSettings: (patch: Partial<FormSettings>) => void; onSuccess: (v: string) => void;
}) {
  const after = settings.after_submit || { type: 'message', url: '' };
  return <Section title="Depois do envio">
    <Segmented label="O que acontece" value={after.type} onChange={(type) => onSettings({ after_submit: { ...after, type } })} options={[{ value: 'message', label: 'Mostrar mensagem' }, { value: 'redirect', label: 'Ir para outra página' }]} />
    {after.type === 'message'
      ? <TextAreaInput label="Mensagem de agradecimento" value={success} maxLength={500} onChange={onSuccess} />
      : <TextInput label="Link de destino" type="url" value={after.url} placeholder="https://" onChange={(url) => onSettings({ after_submit: { ...after, url } })} />}
  </Section>;
}
