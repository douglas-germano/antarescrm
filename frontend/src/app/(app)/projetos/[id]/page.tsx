'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Building2, CalendarDays, Pencil, Trash2, UserRound } from 'lucide-react';
import { useData, useList, patch, remove, refreshAll } from '@/lib/api';
import { brl, day, rowOptions, today } from '@/lib/format';
import { useNotify, useSession } from '@/components/providers';
import { Badge, Button, ConfirmDialog, DataState, FormDialog } from '@/components/ui';
import { Card, Tabs } from '@/components/blocks';
import { FilesPanel } from '@/components/projects/FilesPanel';
import { ApprovalsPanel } from '@/components/projects/ApprovalsPanel';
import { TimelinePanel } from '@/components/projects/TimelinePanel';
import { STATUS } from '@/components/projects/model';
import type { Row } from '@/lib/types';

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useSession();
  const { notify } = useNotify();
  const project = useData<Row>('/projects/' + id);
  const stages = useData<{ items: Row[] }>('/project-stages');
  const users = useList('/users');
  const [tab, setTab] = useState('summary');
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [request, setRequest] = useState<Row | 'new' | null>(null);
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const p = project.data;
  const stageList = stages.data?.items || [];
  const pending = (p?.approvals || []).filter((a: Row) => a.status === 'pending' && !a.expired).length;

  async function save(body: Record<string, unknown>, message?: string) {
    try { await patch('/projects/' + id, body); await refreshAll(); if (message) notify(message); }
    catch (e) { notify((e as Error).message, 'error'); }
  }

  return (
    <div className="page project-detail">
      <DataState loading={project.isLoading || stages.isLoading} error={project.error}>
        {p && (
          <>
            <header className="proj-head">
              <Link href="/projetos" className="back-link"><ArrowLeft size={16} /> Projetos</Link>
              <div className="proj-title">
                <div>
                  <h1>{p.title}</h1>
                  <p className="muted">{p.contact?.name || p.company_name || 'Sem cliente'}{p.owner_name ? ` · Responsável: ${p.owner_name}` : ''}</p>
                </div>
                <div className="proj-actions">
                  <Badge value={STATUS[p.status]?.badge || 'skipped'} label={STATUS[p.status]?.label || p.status} />
                  <select aria-label="Etapa do projeto" value={p.stage?.id || ''} onChange={(e) => void save({ stage_id: e.target.value }, 'Etapa atualizada.')}>
                    {stageList.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                  <Button variant="secondary" onClick={() => setEditing(true)}><Pencil size={15} /> Editar</Button>
                  {p.status === 'active' && <Button variant="secondary" onClick={() => void save({ status: 'cancelled' }, 'Projeto cancelado.')}>Cancelar projeto</Button>}
                  {p.status === 'cancelled' && <Button variant="secondary" onClick={() => void save({ status: 'active' }, 'Projeto reaberto.')}>Reabrir</Button>}
                  {manage && <Button variant="ghost" aria-label="Excluir projeto" onClick={() => setDeleting(true)}><Trash2 size={16} /></Button>}
                </div>
              </div>
            </header>

            <div className="proj-kpis">
              <div><span>Valor</span><strong>{brl(p.amount)}</strong></div>
              <div><span>Etapa</span><strong><i className="dot" style={{ background: p.stage?.color }} />{p.stage?.name}</strong></div>
              <div className={p.status === 'active' && p.due_date && p.due_date < today() ? 'warn' : ''}><span>Prazo</span><strong>{p.due_date ? day(p.due_date) : '—'}</strong></div>
              <div><span>Aprovações</span><strong>{pending ? `${pending} aguardando` : (p.approvals || []).length ? 'Em dia' : '—'}</strong></div>
              <div><span>Arquivos</span><strong>{p.files.length}</strong></div>
            </div>

            <Tabs variant="line" label="Seções do projeto" value={tab} onChange={setTab} items={[
              { value: 'summary', label: 'Resumo' },
              { value: 'files', label: <>Arquivos <span className="tab-count">{p.files.length}</span></> },
              { value: 'approvals', label: <>Aprovações{pending > 0 && <span className="tab-badge">{pending}</span>}</> },
              { value: 'activity', label: 'Atividade' },
            ]} />

            {tab === 'summary' && (
              <div className="proj-summary">
                <Card as="section">
                  <div className="card-head"><h2>Cliente</h2></div>
                  <div className="card-body proj-info">
                    {p.contact ? (<>
                      <p><UserRound size={15} /> <Link href="/contatos">{p.contact.name}</Link></p>
                      {p.contact.phone && <p><span className="muted">Telefone</span> {p.contact.phone}</p>}
                      {p.contact.email && <p><span className="muted">E-mail</span> {p.contact.email}</p>}
                    </>) : <p className="muted">Nenhum contato vinculado.</p>}
                    {p.company_name && <p><Building2 size={15} /> {p.company_name}</p>}
                  </div>
                </Card>
                <Card as="section">
                  <div className="card-head"><h2>Negócio de origem</h2></div>
                  <div className="card-body proj-info">
                    {p.deal ? (<>
                      <p><Link href={'/crm?opportunity=' + p.deal.id}>{p.deal.title}</Link></p>
                      <p><span className="muted">Valor negociado</span> {brl(p.deal.amount)}</p>
                      <p><span className="muted">Situação</span> {p.deal.status === 'won' ? 'Ganho' : p.deal.status === 'lost' ? 'Perdido' : 'Em aberto'}{p.deal.closed_at ? ` em ${day(p.deal.closed_at)}` : ''}</p>
                      {p.deal.expected_close_date && <p><CalendarDays size={15} /> Previsão de fechamento: {day(p.deal.expected_close_date)}</p>}
                    </>) : <p className="muted">Projeto criado sem negócio vinculado.</p>}
                  </div>
                </Card>
                <Card as="section" className="span-2">
                  <div className="card-head"><h2>Descrição</h2></div>
                  <div className="card-body"><p className={p.description ? '' : 'muted'}>{p.description || 'Sem descrição.'}</p>
                    <p className="muted proj-dates">Início: {p.start_date ? day(p.start_date) : '—'}{p.completed_at ? ` · Concluído em ${day(p.completed_at)}` : ''}</p></div>
                </Card>
              </div>
            )}
            {tab === 'files' && <FilesPanel project={p} onRequestApproval={(file) => { setTab('approvals'); setRequest(file); }} />}
            {tab === 'approvals' && <ApprovalsPanel project={p} request={request} onNew={() => setRequest('new')} onClose={() => setRequest(null)} />}
            {tab === 'activity' && <TimelinePanel project={p} />}

            <FormDialog open={editing} onClose={() => setEditing(false)} title="Editar projeto" initial={{ ...p, amount: p.amount }}
              fields={[
                { name: 'title', label: 'Título', required: true, wide: true },
                { name: 'contact_id', label: 'Cliente', type: 'contact' },
                { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions((users.data || []).filter((u) => u.active)) },
                { name: 'amount', label: 'Valor (R$)', type: 'money', min: 0 },
                { name: 'start_date', label: 'Início', type: 'date' },
                { name: 'due_date', label: 'Prazo de entrega', type: 'date' },
                { name: 'description', label: 'Descrição', type: 'textarea', wide: true },
              ]}
              onSubmit={async (data) => {
                await patch('/projects/' + id, { ...data, contact_id: data.contact_id || null, owner_id: data.owner_id || null, due_date: data.due_date || null, start_date: data.start_date || null, description: data.description || null });
                await refreshAll(); notify('Projeto atualizado.');
              }} />
            <ConfirmDialog open={deleting} onClose={() => setDeleting(false)} title="Excluir o projeto?" description="Arquivos, aprovações e histórico deste projeto serão apagados em definitivo. Esta ação não pode ser desfeita."
              onConfirm={async () => { await remove('/projects/' + id); await refreshAll(); router.push('/projetos'); notify('Projeto excluído.'); }} />
          </>
        )}
      </DataState>
    </div>
  );
}
