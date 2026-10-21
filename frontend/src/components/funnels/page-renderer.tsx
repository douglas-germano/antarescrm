'use client';
import { useEffect, useState, type CSSProperties } from 'react';
import { Check, ChevronDown, Circle, ImageOff, Video as VideoIcon } from 'lucide-react';
import { FormView } from '@/components/forms/form-view';
import { FONT_STACKS, contrastOn } from '@/components/forms/theme';
import type { PublicForm } from '@/components/forms/types';
import { embedUrl, type Block, type StepSettings, type Theme } from './types';

type Props = {
  blocks: Block[];
  theme: Theme;
  settings?: StepSettings;
  forms: Record<string, PublicForm>;
  /** 'edit' renders the page inside the editor: nothing navigates or submits, blocks can be selected. */
  mode: 'edit' | 'live';
  selectedId?: string;
  onSelect?: (id: string) => void;
  onNext?: () => void;
  attribution?: Record<string, string>;
  funnelId?: string;
};

export function PageRenderer({ blocks, theme, settings, forms, mode, selectedId, onSelect, onNext, attribution, funnelId }: Props) {
  const style = {
    '--p-accent': theme.accent_color, '--p-on-accent': contrastOn(theme.accent_color), '--p-text': theme.text_color,
    '--p-bg': settings?.background || theme.background, '--p-font': FONT_STACKS[theme.font] || FONT_STACKS.sans, '--p-radius': theme.radius + 'px',
  } as CSSProperties;
  return <div className={'fp-page fp-w-' + (settings?.width || 'normal')} style={style} data-mode={mode}>
    {blocks.length === 0 && mode === 'edit' && <p className="fp-empty">Esta página está vazia. Adicione blocos pela lista à esquerda.</p>}
    {blocks.map((block) => {
      const s = block.style || {};
      return <section key={block.id} className={`fp-block fp-pad-${s.padding || 'md'} fp-bw-${s.width || 'normal'}`}
        style={{ textAlign: s.align || 'left', background: s.background || undefined, color: s.color || undefined }}
        data-selected={mode === 'edit' ? selectedId === block.id : undefined}
        onClickCapture={mode === 'edit' ? (e) => { e.preventDefault(); e.stopPropagation(); onSelect?.(block.id); } : undefined}>
        <div className="fp-inner"><BlockView block={block} forms={forms} mode={mode} onNext={onNext} attribution={attribution} funnelId={funnelId} /></div>
      </section>;
    })}
  </div>;
}

function BlockView({ block, forms, mode, onNext, attribution, funnelId }: { block: Block; forms: Record<string, PublicForm>; mode: 'edit' | 'live'; onNext?: () => void; attribution?: Record<string, string>; funnelId?: string }) {
  const p = block.props;
  const edit = mode === 'edit';
  switch (block.type) {
    case 'heading': {
      const Tag = (['h1', 'h2', 'h3'] as const)[Math.min(Math.max((p.level || 2) - 1, 0), 2)];
      return <Tag className={'fp-heading fp-h' + (p.level || 2)}>{p.text || (edit ? 'Título' : '')}</Tag>;
    }
    case 'text': return <p className={'fp-text fp-text-' + (p.size || 'md')}>{p.text}</p>;
    case 'image': {
      if (!p.src) return edit ? <div className="fp-placeholder"><ImageOff size={24} /><span>Informe o link de uma imagem</span></div> : null;
      // eslint-disable-next-line @next/next/no-img-element
      const img = <img src={p.src} alt={p.alt || ''} className={'fp-image' + (p.rounded ? ' fp-rounded' : '')} loading="lazy" />;
      return p.link && !edit ? <a href={p.link} rel="noopener noreferrer">{img}</a> : img;
    }
    case 'video': {
      const src = p.url ? embedUrl(p.url) : null;
      if (!src) return <div className="fp-placeholder"><VideoIcon size={24} /><span>{p.url ? 'Link de vídeo não reconhecido' : 'Informe um link do YouTube ou Vimeo'}</span></div>;
      return <div className="fp-video"><iframe src={src} title="Vídeo" loading="lazy" allow="accelerometer; encrypted-media; picture-in-picture; fullscreen" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" style={edit ? { pointerEvents: 'none' } : undefined} /></div>;
    }
    case 'button': {
      const cls = `fp-button fp-button-${p.variant || 'primary'}` + (p.full_width ? ' fp-button-full' : '');
      if (p.action === 'url' && p.url) return <a className={cls} href={edit ? undefined : p.url} rel="noopener noreferrer">{p.label}</a>;
      return <button type="button" className={cls} onClick={() => !edit && onNext?.()}>{p.label}</button>;
    }
    case 'form': return <FormBlock block={block} form={forms[p.form_id]} edit={edit} onNext={onNext} attribution={attribution} />;
    case 'list': return <ul className="fp-list">{(p.items || []).map((item: string, i: number) => <li key={i}>{p.icon === 'dot' ? <Circle size={8} fill="currentColor" /> : <Check size={16} />}<span>{item}</span></li>)}</ul>;
    case 'testimonial': return <figure className="fp-testimonial"><blockquote>{p.quote}</blockquote><figcaption>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {p.avatar && <img src={p.avatar} alt="" />}<span><strong>{p.author}</strong>{p.role && <small>{p.role}</small>}</span></figcaption></figure>;
    case 'faq': return <div className="fp-faq">{(p.items || []).map((item: { q: string; a: string }, i: number) => <details key={i}><summary>{item.q}<ChevronDown size={16} /></summary><p>{item.a}</p></details>)}</div>;
    case 'countdown': return <Countdown block={block} edit={edit} funnelId={funnelId} />;
    case 'divider': return <hr className="fp-divider" />;
    case 'spacer': return <div style={{ height: p.height || 32 }} aria-hidden />;
    default: return null;
  }
}

function FormBlock({ block, form, edit, onNext, attribution }: { block: Block; form?: PublicForm; edit: boolean; onNext?: () => void; attribution?: Record<string, string> }) {
  const p = block.props;
  const [done, setDone] = useState<string>('');
  if (!form) return <div className="fp-placeholder"><span>{p.form_id ? 'Este formulário está indisponível ou desativado.' : 'Escolha um formulário nas propriedades do bloco.'}</span></div>;
  if (done) return <div className="fp-done" role="status"><Check size={32} /><p>{done}</p></div>;
  return <FormView form={form} embedded attribution={attribution} editor={edit ? { onSelect: () => undefined } : undefined}
    onSuccess={(result) => {
      if (result.redirect_url) { window.location.assign(result.redirect_url); return; }
      if (p.on_submit === 'url' && p.url) { window.location.assign(p.url); return; }
      if (p.on_submit === 'next' && onNext) { onNext(); return; }
      setDone(result.message);
    }} />;
}

function Countdown({ block, edit, funnelId }: { block: Block; edit: boolean; funnelId?: string }) {
  const p = block.props;
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    let deadline: number;
    if (p.mode === 'fixed' && p.target) deadline = new Date(p.target).getTime();
    else {
      const key = `antares:cd:${funnelId || 'edit'}:${block.id}`;
      let started = Number.NaN;
      try { started = Number(localStorage.getItem(key)); if (!started) { started = Date.now(); localStorage.setItem(key, String(started)); } } catch { started = Date.now(); }
      deadline = started + (p.minutes || 60) * 60000;
    }
    const tick = () => setLeft(Math.max(0, deadline - Date.now()));
    tick();
    if (edit) return;
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [p.mode, p.target, p.minutes, block.id, funnelId, edit]);
  if (left === null) return <div className="fp-countdown" aria-hidden>&nbsp;</div>;
  if (left === 0 && !edit) return <p className="fp-text">{p.expired_text}</p>;
  const total = Math.floor(left / 1000);
  const parts = [['dias', Math.floor(total / 86400)], ['horas', Math.floor((total % 86400) / 3600)], ['min', Math.floor((total % 3600) / 60)], ['seg', total % 60]] as const;
  return <div className="fp-countdown" role="timer" aria-label="Contagem regressiva">{parts.filter(([label, v]) => label !== 'dias' || v > 0).map(([label, v]) => <div key={label}><strong>{String(v).padStart(2, '0')}</strong><small>{label}</small></div>)}</div>;
}
