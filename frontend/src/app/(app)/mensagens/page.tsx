'use client';
import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { useSearchParams } from 'next/navigation';
import { MessageCircle, Plus } from 'lucide-react';
import { ChatPane } from '@/components/whatsapp/ChatPane';
import { ConnectionBar } from '@/components/whatsapp/ConnectionBar';
import { ConversationDetailsDialog, NewConversationDialog } from '@/components/whatsapp/ConversationDialogs';
import { OtherThread } from '@/components/whatsapp/OtherThread';
import { ThreadList } from '@/components/whatsapp/ThreadList';
import { CreateInboxOpportunityDialog } from '@/components/inbox/create-opportunity-dialog';
import { MessageNotificationButton } from '@/components/inbox/message-notifications';
import { useConnection } from '@/components/whatsapp/hooks';
import { api, useData, useList, post, patch, refreshAll } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { PageHeader, Button, DataState } from '@/components/ui';
import { Card } from '@/components/blocks';
import { searchMatch } from '@/lib/format';
import type { Row } from '@/lib/types';

export default function MessagesPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const threads = useSWR<{ items: Row[] }>('/inbox', api, { refreshInterval: 5000 });
  const contacts = useList('/contacts');
  const [channel, setChannel] = useState('all');
  const [status, setStatus] = useState('open');
  const [search, setSearch] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [dealThread, setDealThread] = useState<Row | null>(null);
  const connection = useConnection(true, false);
  const [selected, setSelected] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const params = useSearchParams();
  const requestedId = params.get('conversation');
  const requestedSource = params.get('source') || 'whatsapp';
  const requestedThread = useData<Row>(requestedId && ['whatsapp', 'inbox'].includes(requestedSource) ? `/inbox/${requestedSource}/${requestedId}` : null);
  const [openedLink, setOpenedLink] = useState('');

  useEffect(() => {
    if (!requestedId || !['whatsapp', 'inbox'].includes(requestedSource)) return;
    const key = requestedSource + ':' + requestedId;
    if (openedLink === key) return;
    const row = threads.data?.items.find(item => item.source === requestedSource && item.id === requestedId) || requestedThread.data;
    if (row) {
      setSelected(row); setStatus('all'); setChannel('all'); setSearch(''); setOpenedLink(key);
    }
  }, [requestedId, requestedSource, requestedThread.data, threads.data, openedLink]);

  const allThreads = threads.data?.items || [];
  const selectedThread = allThreads.find((item) => item.source === selected?.source && item.id === selected?.id) || selected;
  const nameOf = (thread: Row) => contacts.data?.find((contact) => contact.id === thread.contact_id)?.name || thread.contact_name || thread.address;
  const visibleThreads = allThreads.filter(
    (thread) =>
      (channel === 'all' || channel === thread.channel) &&
      (status === 'all' || thread.status === status || (status === 'open' && !thread.status)) &&
      searchMatch(search, [thread.contact_name, thread.address, thread.display_address, thread.preview, nameOf(thread), contacts.data?.find((c) => c.id === thread.contact_id)?.phone]),
  );
  const otherMessages = useList(selected && selected.source !== 'whatsapp' ? `/inbox/${selected.source}/${selected.id}/messages` : null);
  useEffect(() => {
    if (!selected || selected.source === 'whatsapp') return;
    const timer = setInterval(() => { void otherMessages.mutate(); }, 5000);
    return () => clearInterval(timer);
  }, [selected?.id, selected?.source, otherMessages.mutate]);

  async function act(work: () => Promise<void>) {
    setBusy(true);
    try {
      await work();
      await refreshAll();
    } catch (error) {
      notify((error as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page wa-page" data-chat-open={Boolean(selected)}>
      <PageHeader title="Caixa de entrada">
        <MessageNotificationButton />
        <ConnectionBar connection={connection.current} canManage={manage} />
        <Button onClick={() => setShowNew(true)}>
          <Plus size={16} /> Nova conversa
        </Button>
      </PageHeader>

      {requestedThread.error && <p className="form-error" role="alert">Não foi possível abrir a conversa da notificação. Verifique seu acesso ou selecione uma conversa na lista.</p>}
      <DataState loading={threads.isLoading} error={threads.error}>
        <Card fill className="wa-workspace">
          <div className="wa-split" data-chat-open={Boolean(selected)}>
            <ThreadList
              threads={visibleThreads}
              nameOf={nameOf}
              selected={selected}
              onSelect={setSelected}
              search={search}
              onSearch={setSearch}
              status={status}
              onStatus={setStatus}
              channel={channel}
              onChannel={setChannel}
            />
            {selectedThread?.source === 'whatsapp' ? (
              <div className="wa-chat">
                <ChatPane
                  key={selectedThread.id}
                  conversation={selectedThread}
                  connection={connection.current}
                  onBack={() => setSelected(null)}
                  onDetails={() => setShowDetails(true)}
                  onCreateOpportunity={() => setDealThread(selectedThread)}
                  onUpdate={(data) => act(async () => { setSelected({ ...(await patch<Row>(`/whatsapp/conversations/${selectedThread.id}`, data)), source: 'whatsapp', channel: 'whatsapp' }); })}
                  onRefresh={async () => { await connection.refresh(); await threads.mutate(); }}
                  onRead={() => { void threads.mutate(); }}
                />
              </div>
            ) : selected ? (
              <OtherThread
                key={selected.source + selected.id}
                thread={selected}
                name={nameOf(selected)}
                messages={otherMessages.data || []}
                loading={otherMessages.isLoading}
                error={otherMessages.error}
                canManage={manage}
                busy={busy}
                onBack={() => setSelected(null)}
                onCreateOpportunity={() => setDealThread(selectedThread || selected)}
                onSend={async (content) => {
                  setBusy(true);
                  try {
                    const result = await post<{ status: string; error: string }>(`/inbox/${selected.source}/${selected.id}/messages`, { content, idempotency_key: crypto.randomUUID() });
                    await refreshAll();
                    if (result.status === 'unknown') { notify(result.error, 'error'); return; }
                    notify(selected.channel === 'instagram' ? 'Resposta enviada.' : 'Resposta adicionada à fila.');
                  } catch (error) { notify((error as Error).message, 'error'); throw error; }
                  finally { setBusy(false); }
                }}
                onResume={(message) => act(async () => { await post(`/communications/messages/${message.id}/resume`, {}); })}
              />
            ) : (
              <div className="wa-chat wa-no-chat">
                <span className="wa-no-chat-icon"><MessageCircle size={28} /></span>
                <h2>Selecione uma conversa</h2>
                <p>Escolha um atendimento na lista ou inicie uma nova conversa com um contato.</p>
                <Button variant="secondary" onClick={() => setShowNew(true)}><Plus size={16} /> Nova conversa</Button>
              </div>
            )}
          </div>
        </Card>
      </DataState>

      <NewConversationDialog open={showNew} onClose={() => setShowNew(false)} onCreated={async (created) => {
        setSelected({ ...created, source: 'whatsapp', channel: 'whatsapp', address: created.phone });
        setChannel('all');
        setStatus('all');
        setSearch('');
        await threads.mutate();
      }} />
      {dealThread && <CreateInboxOpportunityDialog key={dealThread.source + dealThread.id} thread={dealThread} label={nameOf(dealThread)} onClose={() => setDealThread(null)} onCreated={async result => {
        setSelected(current => current?.id === dealThread.id && current.source === dealThread.source ? { ...current, ...result.conversation } : current);
        await refreshAll();
        notify('Negócio criado e vinculado ao contato.');
      }} />}
      <ConversationDetailsDialog open={showDetails} onClose={() => setShowDetails(false)} conversation={selectedThread} onSaved={async (updated) => {
        setSelected({ ...updated, source: 'whatsapp', channel: 'whatsapp', address: updated.phone });
        await threads.mutate();
        notify('Atendimento atualizado.');
      }} />
    </div>
  );
}
