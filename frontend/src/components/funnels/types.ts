import { AlignLeft, CircleHelp, Clock, Heading1, Image as ImageIcon, ListChecks, MousePointerClick, Minus, MoveVertical, Quote, TextCursorInput, Video } from 'lucide-react';
import type { ComponentType } from 'react';

export type BlockType = 'heading' | 'text' | 'image' | 'video' | 'button' | 'form' | 'list' | 'testimonial' | 'faq' | 'countdown' | 'divider' | 'spacer';
export type BlockStyle = { align?: 'left' | 'center' | 'right'; background?: string; color?: string; padding?: 'none' | 'sm' | 'md' | 'lg'; width?: 'narrow' | 'normal' | 'wide' };
export type Block = { id: string; type: BlockType; props: Record<string, any>; style: BlockStyle };
export type StepSettings = { title?: string; description?: string; background?: string; width?: 'narrow' | 'normal' | 'wide' };
export type StepKind = 'landing' | 'optin' | 'sales' | 'upsell' | 'thankyou' | 'custom';
export type Step = { id: string; funnel_id: string; name: string; slug: string; kind: StepKind; position: number; blocks: Block[]; settings: StepSettings };
export type Theme = { accent_color: string; background: string; text_color: string; font: 'sans' | 'serif' | 'mono' | 'rounded'; radius: number };
export type Funnel = { id: string; name: string; description: string; status: 'draft' | 'published'; theme: Theme; steps?: Step[]; totals?: { views: number; conversions: number; steps: number } };
export type StepStats = { step_id: string; name: string; slug: string; kind: StepKind; views: number; visitors: number; conversions: number; conversion_rate: number; drop_off: number };
export type FunnelStats = { steps: StepStats[]; visitors: number; conversions: number; conversion_rate: number };

export const KIND_LABELS: Record<StepKind, string> = {
  landing: 'Página inicial', optin: 'Captura', sales: 'Vendas', upsell: 'Oferta extra', thankyou: 'Obrigado', custom: 'Outra',
};
export const TEMPLATES = [
  { value: 'lead_magnet', title: 'Captura de leads', text: 'Página de captura com formulário e página de obrigado.' },
  { value: 'sales', title: 'Página de vendas', text: 'Oferta com vídeo, benefícios, depoimento, perguntas e formulário.' },
  { value: 'blank', title: 'Em branco', text: 'Comece do zero com uma página vazia.' },
] as const;

export const newId = () => 'b' + crypto.randomUUID().replace(/-/g, '').slice(0, 9);

export const BLOCK_DEFS: { type: BlockType; label: string; icon: ComponentType<{ size?: number }>; make: () => Pick<Block, 'props' | 'style'> }[] = [
  { type: 'heading', label: 'Título', icon: Heading1, make: () => ({ props: { text: 'Título da seção', level: 2 }, style: { align: 'center' } }) },
  { type: 'text', label: 'Texto', icon: AlignLeft, make: () => ({ props: { text: 'Escreva aqui o texto da sua página.', size: 'md' }, style: {} }) },
  { type: 'image', label: 'Imagem', icon: ImageIcon, make: () => ({ props: { src: '', alt: '', link: '', rounded: true }, style: { align: 'center' } }) },
  { type: 'video', label: 'Vídeo', icon: Video, make: () => ({ props: { url: '' }, style: {} }) },
  { type: 'button', label: 'Botão', icon: MousePointerClick, make: () => ({ props: { label: 'Quero saber mais', action: 'next', url: '', variant: 'primary', full_width: false }, style: { align: 'center' } }) },
  { type: 'form', label: 'Formulário', icon: TextCursorInput, make: () => ({ props: { form_id: '', on_submit: 'next', url: '' }, style: {} }) },
  { type: 'list', label: 'Lista', icon: ListChecks, make: () => ({ props: { items: ['Primeiro benefício', 'Segundo benefício'], icon: 'check' }, style: {} }) },
  { type: 'testimonial', label: 'Depoimento', icon: Quote, make: () => ({ props: { quote: 'Texto do depoimento.', author: 'Nome', role: 'Cargo, empresa', avatar: '' }, style: {} }) },
  { type: 'faq', label: 'Perguntas', icon: CircleHelp, make: () => ({ props: { items: [{ q: 'Pergunta frequente?', a: 'Resposta.' }] }, style: {} }) },
  { type: 'countdown', label: 'Contagem', icon: Clock, make: () => ({ props: { mode: 'evergreen', minutes: 60, target: '', expired_text: 'A oferta terminou.' }, style: { align: 'center' } }) },
  { type: 'divider', label: 'Divisória', icon: Minus, make: () => ({ props: {}, style: {} }) },
  { type: 'spacer', label: 'Espaço', icon: MoveVertical, make: () => ({ props: { height: 32 }, style: {} }) },
];
export const blockLabel = (type: string) => BLOCK_DEFS.find((d) => d.type === type)?.label || type;

/** Turns a YouTube/Vimeo link into an embeddable address; anything else yields null. */
export function embedUrl(value: string): string | null {
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^www\./, '');
    if (host === 'youtu.be') return `https://www.youtube-nocookie.com/embed/${url.pathname.slice(1)}`;
    if (host === 'youtube.com') {
      const id = url.searchParams.get('v') || url.pathname.match(/\/(?:embed|shorts)\/([\w-]+)/)?.[1];
      return id ? `https://www.youtube-nocookie.com/embed/${id}` : null;
    }
    if (host === 'vimeo.com' || host === 'player.vimeo.com') {
      const id = url.pathname.match(/(\d+)/)?.[1];
      return id ? `https://player.vimeo.com/video/${id}` : null;
    }
  } catch { /* not a URL */ }
  return null;
}
