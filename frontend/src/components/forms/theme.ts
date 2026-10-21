import type { CSSProperties } from 'react';
import { DEFAULT_DESIGN, type FormDesign } from './types';

export const FONT_STACKS: Record<FormDesign['font'], string> = {
  sans: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif",
  serif: "Georgia, 'Times New Roman', serif",
  mono: "ui-monospace, 'SF Mono', Menlo, monospace",
  rounded: "'Trebuchet MS', 'Segoe UI', system-ui, sans-serif",
};
export const FONT_LABELS: Record<FormDesign['font'], string> = { sans: 'Moderna', serif: 'Clássica', mono: 'Técnica', rounded: 'Amigável' };

export function formStyle(design: Partial<FormDesign> | undefined, accent: string): CSSProperties {
  const d = { ...DEFAULT_DESIGN, ...design };
  return {
    '--f-bg': d.background, '--f-card': d.card_color, '--f-text': d.text_color, '--f-accent': accent,
    '--f-radius': d.radius + 'px', '--f-font': FONT_STACKS[d.font] || FONT_STACKS.sans, '--f-width': d.max_width + 'px',
    '--f-button-radius': d.button_style === 'pill' ? '60px' : d.button_style === 'rounded' ? d.radius + 'px' : '0',
  } as CSSProperties;
}

/** Readable text color (black/white) for a hex background, used on accent-colored buttons. */
export function contrastOn(hex: string) {
  const n = parseInt(hex.replace('#', ''), 16);
  if (Number.isNaN(n)) return '#fff';
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return (r * 299 + g * 587 + b * 114) / 1000 > 150 ? '#25282b' : '#fff';
}
