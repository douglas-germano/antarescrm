'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Copy, Trash2 } from 'lucide-react';
import { Button, ConfirmDialog } from '@/components/ui';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import { useNotify } from '@/components/providers';
import { post, refreshAll, remove } from '@/lib/api';
import { ColorInput, RangeInput, SelectInput, TextAreaInput, TextInput } from '@/components/builder/controls';
import { FONT_LABELS } from '@/components/forms/theme';
import type { Funnel, Theme } from './types';

export function FunnelSettings({ funnel, onChange }: { funnel: Funnel; onChange: (values: Partial<Funnel>) => void }) {
  const router = useRouter();
  const { notify } = useNotify();
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const theme = (values: Partial<Theme>) => onChange({ theme: { ...funnel.theme, ...values } });
  return <div className="fe-settings">
    <Card as="section"><CardHeader title="Identificação" /><CardBody>
      <div className="bld-fields">
        <TextInput label="Nome" value={funnel.name} maxLength={150} required onChange={(name) => onChange({ name })} />
        <TextAreaInput label="Descrição interna" value={funnel.description} maxLength={1000} onChange={(description) => onChange({ description })} />
      </div>
    </CardBody></Card>
    <Card as="section"><CardHeader title="Aparência das páginas" /><CardBody>
      <div className="bld-fields">
        <ColorInput label="Cor de destaque (botões e ícones)" value={funnel.theme.accent_color} fallback="#e60000" onChange={(accent_color) => theme({ accent_color })} />
        <ColorInput label="Fundo" value={funnel.theme.background} onChange={(background) => theme({ background })} />
        <ColorInput label="Cor do texto" value={funnel.theme.text_color} fallback="#25282b" onChange={(text_color) => theme({ text_color })} />
        <SelectInput label="Fonte" value={funnel.theme.font} onChange={(font) => theme({ font })} options={Object.entries(FONT_LABELS).map(([value, label]) => ({ value: value as Theme['font'], label }))} />
        <RangeInput label="Arredondamento" min={0} max={32} value={funnel.theme.radius} unit="px" onChange={(radius) => theme({ radius })} />
      </div>
    </CardBody></Card>
    <Card as="section"><CardHeader title="Ações" /><CardBody>
      <div className="bld-grid-2">
        <Button variant="secondary" disabled={busy} onClick={async () => {
          setBusy(true);
          try { const copy = await post<Funnel>(`/funnels/${funnel.id}/duplicate`, {}); await refreshAll(); notify('Funil duplicado.'); router.push('/funis/' + copy.id); }
          catch (e) { notify((e as Error).message, 'error'); } finally { setBusy(false); }
        }}><Copy size={14} /> Duplicar funil</Button>
        <Button variant="danger" onClick={() => setDeleting(true)}><Trash2 size={14} /> Excluir funil</Button>
      </div>
      <p className="muted">Salve as alterações pelo botão no topo. Ao duplicar, os formulários das páginas também são copiados e ficam inativos até a publicação.</p>
    </CardBody></Card>
    <ConfirmDialog open={deleting} onClose={() => setDeleting(false)} title="Excluir funil" description={`O funil "${funnel.name}", suas páginas e métricas serão removidos. Os formulários e contatos já capturados continuam salvos.`}
      onConfirm={async () => { await remove('/funnels/' + funnel.id); await refreshAll(); notify('Funil excluído.'); router.push('/funis'); }} />
  </div>;
}
