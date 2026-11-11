import { useState } from 'react';
import useSWR from 'swr';
import { ExternalLink, Film, Images, Pencil, Plus, Send, Trash2, Undo2 } from 'lucide-react';
import { api, post, remove, useData } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button, ConfirmDialog, DataState, EmptyState } from '@/components/ui';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import { Composer, mediaSrc, TYPES } from '@/components/instagram/composer';
import type { Row } from '@/lib/types';

const STATUS: Record<string, { label: string; tone?: string }> = {
  draft: { label: 'Rascunho' },
  scheduled: { label: 'Agendada', tone: 'info' },
  processing: { label: 'Preparando no Instagram', tone: 'info' },
  publishing: { label: 'Publicando', tone: 'info' },
  published: { label: 'Publicada', tone: 'ok' },
  failed: { label: 'Não publicada', tone: 'warn' },
  unknown: { label: 'Sem confirmação', tone: 'warn' },
};
const GROUPS = [
  { title: 'Na fila', statuses: ['processing', 'publishing', 'scheduled'] },
  { title: 'Precisam de atenção', statuses: ['failed', 'unknown'] },
  { title: 'Rascunhos', statuses: ['draft'] },
  { title: 'Publicadas', statuses: ['published'] },
];
const when = (value?: string) => value ? new Date(value).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '';

export function PostsPanel({ accounts, account }: { accounts: Row[]; account: string }) {
  const { notify } = useNotify();
  const { user, workspace } = useSession();
  const manager = ['owner', 'admin'].includes(user?.role || '');
  const path = '/instagram/posts?connection_id=' + account;
  const state = useSWR<{ items: Row[] }>(workspace?.id && account ? ['ig-posts', workspace.id, path] : null, () => api<{ items: Row[] }>(path), {
    // Refresh while the worker is moving posts through Instagram.
    refreshInterval: (data) => data?.items.some(p => ['processing', 'publishing'].includes(p.status) || (p.status === 'scheduled' && Date.parse(p.scheduled_at) < Date.now() + 60_000)) ? 4000 : 0,
  });
  const limit = useData<{ used: number; total: number }>(account && manager ? `/instagram/accounts/${account}/publishing-limit` : null);
  const [composer, setComposer] = useState<{ open: boolean; editing: Row | null }>({ open: false, editing: null });
  const [deleting, setDeleting] = useState<Row | null>(null);
  const current = accounts.find(a => a.id === account);
  const items = state.data?.items || [];
  const act = async (fn: () => Promise<unknown>, message: string) => {
    try { await fn(); notify(message); await state.mutate(); } catch (e) { notify((e as Error).message, 'error'); }
  };
  return <Card as="section">
    <CardHeader title="Publicações" description={limit.data ? `${limit.data.used} de ${limit.data.total} publicações feitas pela API nas últimas 24 horas.` : 'Feed, carrosséis e Reels deste perfil.'}
      actions={<Button disabled={!current?.can_publish} onClick={() => setComposer({ open: true, editing: null })}><Plus size={16} />Nova publicação</Button>} />
    <CardBody>
      {current && !current.can_publish && <p className="ig-warning" role="note">@{current.username} ainda não autorizou publicações. Reautorize o perfil em Configurações → Conexões.</p>}
      <DataState loading={state.isLoading} error={state.error}>
        {items.length ? GROUPS.map(group => {
          const rows = items.filter(p => group.statuses.includes(p.status));
          if (!rows.length) return null;
          return <section key={group.title} className="ig-post-group" aria-label={group.title}>
            <h3>{group.title} <span className="muted">{rows.length}</span></h3>
            <ul className="ig-posts">
              {rows.map(p => {
                const first = p.items?.[0];
                const status = STATUS[p.status] || { label: p.status };
                const editable = ['draft', 'failed'].includes(p.status) || (p.status === 'scheduled' && manager);
                return <li key={p.id} className="ig-post">
                  <span className="ig-thumb">
                    {first && (first.kind === 'video' ? <video src={mediaSrc(first)} muted preload="metadata" /> : <img src={mediaSrc(first)} alt="" loading="lazy" />)}
                    {p.media_type === 'CAROUSEL' && <Images size={14} className="ig-type-icon" />}
                    {p.media_type === 'REELS' && <Film size={14} className="ig-type-icon" />}
                  </span>
                  <div className="ig-post-body">
                    <div className="ig-post-top">
                      <span className={'deal-chip ' + (status.tone || '')}>{status.label}</span>
                      <small className="muted">{TYPES.find(t => t.value === p.media_type)?.label}
                        {p.status === 'published' ? ' · ' + when(p.published_at) : p.scheduled_at && ['scheduled', 'processing', 'publishing'].includes(p.status) ? ' · ' + when(p.scheduled_at) : ' · criada ' + when(p.created_at)}</small>
                    </div>
                    <p className="ig-caption">{p.caption || <span className="muted">Sem legenda</span>}</p>
                    {p.error && <small className={p.status === 'unknown' ? 'text-warning' : 'text-danger'}>{p.error}</small>}
                  </div>
                  <div className="ig-post-actions">
                    {p.permalink && <a className="icon-btn" href={p.permalink} target="_blank" rel="noreferrer" title="Abrir no Instagram" aria-label="Abrir no Instagram"><ExternalLink size={15} /></a>}
                    {editable && <button type="button" className="icon-btn" title="Editar" aria-label="Editar publicação" onClick={() => setComposer({ open: true, editing: p })}><Pencil size={15} /></button>}
                    {manager && ['draft', 'failed'].includes(p.status) && <button type="button" className="icon-btn" title="Publicar agora" aria-label="Publicar agora"
                      onClick={() => act(() => post(`/instagram/posts/${p.id}/schedule`, {}), 'Publicação enviada ao Instagram.')}><Send size={15} /></button>}
                    {manager && p.status === 'scheduled' && <button type="button" className="icon-btn" title="Voltar para rascunho" aria-label="Cancelar agendamento"
                      onClick={() => act(() => post(`/instagram/posts/${p.id}/cancel`, {}), 'Agendamento cancelado.')}><Undo2 size={15} /></button>}
                    {!['processing', 'publishing'].includes(p.status) && (p.status !== 'scheduled' || manager) && <button type="button" className="icon-btn danger" title="Excluir" aria-label="Excluir publicação" onClick={() => setDeleting(p)}><Trash2 size={15} /></button>}
                  </div>
                </li>;
              })}
            </ul>
          </section>;
        }) : <EmptyState icon={<Images />} title="Nenhuma publicação ainda" description="Crie a primeira publicação: publique agora ou deixe agendada." />}
      </DataState>
    </CardBody>
    <Composer open={composer.open} editing={composer.editing} accounts={accounts} account={account}
      onClose={() => setComposer({ open: false, editing: null })} onSaved={() => void state.mutate()} />
    <ConfirmDialog open={!!deleting} onClose={() => setDeleting(null)} title="Excluir esta publicação do Antares?"
      description={deleting?.status === 'published' ? 'O registro sai do Antares, mas o post continua no Instagram. Para apagá-lo, use o aplicativo do Instagram.' : 'O rascunho ou agendamento será removido. Os arquivos enviados continuam disponíveis.'}
      onConfirm={async () => { await remove(`/instagram/posts/${deleting!.id}`); await state.mutate(); notify('Publicação removida do Antares.'); }} />
  </Card>;
}
