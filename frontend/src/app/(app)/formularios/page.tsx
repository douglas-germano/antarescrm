'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus, SlidersHorizontal, ExternalLink, Copy, FileInput } from 'lucide-react';
import { useSession, useNotify } from '@/components/providers';
import { useList, useData, post, refreshAll } from '@/lib/api';
import { PageHeader, Button, DataState, FormDialog, Modal, EmptyState, Badge } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import type { Field, Row } from '@/lib/types';

export default function FormsPage() {
  const { user } = useSession(); const { notify } = useNotify();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const { data: forms, isLoading, error } = useList('/forms');
  const { data: stages } = useData<{ items: Row[] }>('/pipeline/stages');
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [viewing, setViewing] = useState<Row | null>(null);
  const { data: submissions, isLoading: loadingSubmissions, error: submissionsError } = useList(viewing ? `/forms/${viewing.id}/submissions` : null);
  const { data: contacts } = useList('/contacts');
  const fields: Field[] = [
    { name: 'name', label: 'Nome interno', required: true }, { name: 'source', label: 'Origem dos leads', defaultValue: 'Formulário', required: true },
    { name: 'headline', label: 'Título da página', required: true, wide: true },
    { name: 'stage_id', label: 'Etapa para os novos negócios', type: 'select', required: true, options: stages?.items.map((s) => ({ value: s.id, label: (s.pipeline_name || 'Principal') + ' · ' + s.name })) },
  ];
  return <div className="page"><PageHeader title="Formulários">{manage && <Button onClick={() => setCreating(true)}><Plus size={17} /> Novo formulário</Button>}</PageHeader>
    <DataState loading={isLoading} error={error}>
      {!forms?.length ? <EmptyState icon={<FileInput />} title="Nenhum formulário" /> :
      <div className="account-grid">{forms.map((form) => <Card key={form.id} as="section"><CardHeader title={form.name} description={form.headline} actions={<Badge value={form.active ? 'completed' : 'cancelled'} label={form.active ? 'Ativo' : 'Pausado'} />} /><CardBody>
        <p className="muted">Origem: {form.source} · Etapa: {stages?.items.find((s) => s.id === form.stage_id)?.name || '—'}</p>
        <div className="account-actions"><Button variant="secondary" onClick={() => setViewing(form)}>Ver solicitações</Button>
          <a className="btn btn-secondary" href={'/f/' + form.id} target="_blank" rel="noreferrer" aria-label={'Abrir página de ' + form.name}><ExternalLink size={16} /></a>
          <Button variant="ghost" aria-label={'Copiar link de ' + form.name} onClick={async () => { try { await navigator.clipboard.writeText(window.location.origin + '/f/' + form.id); notify('Link copiado.'); } catch { notify('Não foi possível copiar. Abra a página e copie o endereço.', 'error'); } }}><Copy size={16} /></Button>
          {manage && <Link className="btn btn-primary" href={'/formularios/' + form.id}><SlidersHorizontal size={16} /> Personalizar</Link>}
        </div></CardBody></Card>)}</div>}
    </DataState>
    <FormDialog open={creating} onClose={() => setCreating(false)} title="Novo formulário" fields={fields} initial={{}} onSubmit={async (data) => {
      const created = await post('/forms', { ...data, description: '' }); await refreshAll(); notify('Formulário criado. Personalize as perguntas e a aparência.'); router.push('/formularios/' + created.id);
    }} />
    <Modal open={!!viewing} onClose={() => setViewing(null)} title={'Solicitações — ' + (viewing?.name || '')}>
      <DataState loading={loadingSubmissions} error={submissionsError}><div className="stack">{submissions?.map((s) => <div className="account-grant" key={s.id}><span><strong>{s.answers?.name || contacts?.find((c) => c.id === s.contact_id)?.name || 'Contato'}</strong><small>{new Date(s.created_at).toLocaleString('pt-BR')} · Contato autorizado nesta solicitação</small><dl>{Object.entries(s.answers || {}).filter(([key]) => !['name','email','phone'].includes(key)).map(([key,value]) => <div key={key}><dt>{viewing?.fields?.find((f: Row) => f.key === key)?.label || key}</dt><dd>{typeof value === 'boolean' ? (value ? 'Sim' : 'Não') : String(value)}</dd></div>)}{s.attribution?.utm_source && <div><dt>Campanha</dt><dd>{s.attribution.utm_source} · {s.attribution.utm_campaign}</dd></div>}</dl></span><Link className="btn btn-secondary" href={'/crm?opportunity=' + s.opportunity_id}>Ver negócio</Link></div>)}{!submissions?.length && <p className="muted">Nenhuma solicitação recebida.</p>}</div></DataState>
    </Modal>
  </div>;
}
