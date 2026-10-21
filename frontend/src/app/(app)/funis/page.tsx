'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ExternalLink, Filter, Plus } from 'lucide-react';
import { useSession, useNotify } from '@/components/providers';
import { post, refreshAll, useList } from '@/lib/api';
import { Badge, Button, DataState, EmptyState, Modal, PageHeader } from '@/components/ui';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import { TEMPLATES, type Funnel } from '@/components/funnels/types';

export default function FunnelsPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const router = useRouter();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const { data: funnels, isLoading, error } = useList('/funnels');
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [template, setTemplate] = useState<string>('lead_magnet');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setFailure('');
    try {
      const created = await post<Funnel>('/funnels', { name, template });
      await refreshAll(); notify('Funil criado.'); router.push('/funis/' + created.id);
    } catch (e) { setFailure((e as Error).message); } finally { setBusy(false); }
  }

  return <div className="page">
    <PageHeader title="Funis de páginas">{manage && <Button onClick={() => { setName(''); setFailure(''); setCreating(true); }}><Plus size={17} /> Novo funil</Button>}</PageHeader>
    <DataState loading={isLoading} error={error}>
      {!funnels?.length
        ? <EmptyState icon={<Filter />} title="Nenhum funil" description="Monte páginas de captura e de vendas, conecte formulários e acompanhe a conversão." />
        : <div className="account-grid">{funnels.map((f) => {
          const t = f.totals || { views: 0, conversions: 0, steps: 0 };
          return <Card key={f.id} as="section"><CardHeader title={f.name} description={`${t.steps} ${t.steps === 1 ? 'página' : 'páginas'}`} actions={<Badge value={f.status === 'published' ? 'completed' : 'cancelled'} label={f.status === 'published' ? 'Publicado' : 'Rascunho'} />} />
            <CardBody>
              <p className="muted">{t.views.toLocaleString('pt-BR')} visualizações · {t.conversions.toLocaleString('pt-BR')} conversões</p>
              <div className="account-actions">
                <Link className="btn btn-primary" href={'/funis/' + f.id}>{manage ? 'Editar' : 'Abrir'}</Link>
                {f.status === 'published' && <a className="btn btn-secondary" href={'/p/' + f.id} target="_blank" rel="noreferrer" aria-label={'Abrir ' + f.name}><ExternalLink size={16} /></a>}
              </div>
            </CardBody></Card>;
        })}</div>}
    </DataState>
    <Modal open={creating} onClose={() => { if (!busy) setCreating(false); }} title="Novo funil" wide>
      <form className="stack" onSubmit={create}>
        <label>Nome do funil<input required maxLength={150} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></label>
        <fieldset className="fe-templates" disabled={busy}><legend>Comece por um modelo</legend>
          {TEMPLATES.map((t) => <label key={t.value} className="fe-template" data-active={template === t.value}>
            <input type="radio" name="template" value={t.value} checked={template === t.value} onChange={() => setTemplate(t.value)} />
            <strong>{t.title}</strong><span>{t.text}</span>
          </label>)}
        </fieldset>
        {failure && <p className="form-error" role="alert">{failure}</p>}
        <div className="modal-footer"><Button variant="secondary" disabled={busy} onClick={() => setCreating(false)}>Cancelar</Button><Button type="submit" disabled={busy || !name.trim()}>{busy ? 'Criando…' : 'Criar funil'}</Button></div>
      </form>
    </Modal>
  </div>;
}
