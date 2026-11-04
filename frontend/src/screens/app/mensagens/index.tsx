import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { useSearchParams } from '@/lib/navigation';
import { MessageCircle, Plus } from 'lucide-react';
import { ChatPane } from '@/components/whatsapp/ChatPane';
import { ConnectionBar } from '@/components/whatsapp/ConnectionBar';
import { ConversationDetailsDialog, NewConversationDialog } from '@/components/whatsapp/ConversationDialogs';
import { OtherThread } from '@/components/whatsapp/OtherThread';
import { ThreadList, type InboxView } from '@/components/whatsapp/ThreadList';
import { CreateInboxOpportunityDialog } from '@/components/inbox/create-opportunity-dialog';
import { MessageNotificationButton } from '@/components/inbox/message-notifications';
import { ContactPanel } from '@/components/inbox/contact-panel';
import { useConnection } from '@/components/whatsapp/hooks';
import { api, useData, useList, post, patch, refreshAll } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { PageHeader, Button, DataState } from '@/components/ui';
import { Card } from '@/components/blocks';
import { searchMatch } from '@/lib/format';
import type { Row } from '@/lib/types';

const PANEL_KEY = 'antares.inbox.panel';

export default function MessagesPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const threads = useSWR<{ items: Row[] }>('/inbox', api, { refreshInterval: 5000 });
  const contacts = useList('/contacts');
  const staff = useList('/users');
  const instagram = useData<{ configured: boolean; connected: boolean }>('/instagram/connection');
  const [channel, setChannel] = useState('all');
  const [status, setStatus] = useState('open');
  const [view, setView] = useState<InboxView>('all');
  const [unassigned, setUnassigned] = useState(false);
  const [search, setSearch] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [dealThread, setDealThread] = useState<Row | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const connection = useConnection(true, false);
  const [selected, setSelected] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const params = useSearchParams();
  const requestedId = params.get('conversation');
  const requestedSource = params.get('source') || 'whatsapp';
  const requestedThread = useData<Row>(requestedId && ['whatsapp', 'inbox'].includes(requestedSource) ? `/inbox/${requestedSource}/${requestedId}` : null);
  const [openedLink, setOpenedLink] = useState('');

  useEffect(() => {
    try { if (localStorage.getItem(PANEL_KEY) === 'closed') setPanelOpen(false); } catch { /* optional preference */ }
  }, []);
  function togglePanel() {
    setPanelOpen((open) => {
      try { localStorage.setItem(PANEL_KEY, open ? 'closed' : 'open'); } catch { /* optional preference */ }
      return !open;
    });
  }
  useEffect(() => {
    if (!requestedId || !['whatsapp', 'inbox'].includes(requestedSource)) return;
    const key = requestedSource + ':' + requestedId;
    if (openedLink === key) return;
    const row = threads.data?.items.find(item => item.source === requestedSource && item.id === requestedId) || requestedThread.data;
    if (row) {
      setSelected(row); setStatus('all'); setChannel('all'); setView('all'); setUnassigned(false); setSearch(''); setOpenedLink(key);
    }
  }, [requestedId, requestedSource, requestedThread.data, threads.data, openedLink]);

  const allThreads = threads.data?.items || [];
  const selectedThread = allThreads.find((item) => item.source === selected?.source && item.id === selected?.id) || selected;
  const contactOf = (thread?: Row | null) => (thread?.contact_id ? contacts.data?.find((c) => c.id === thread.contact_id) : undefined);
  // Unlinked Instagram threads have an internal address; their @ is the readable name.
  const handle = (thread: Row) => (thread.channel === 'instagram' && thread.display_address !== 'Instagram' ? thread.display_address : undefined);
  const nameOf = (thread: Row) => contactOf(thread)?.name || thread.contact_name || handle(thread) || (thread.channel === 'instagram' ? 'Instagram' : thread.address);
  const ownerOf = (thread: Row) => (thread.assigned_to_id ? staff.data?.find((u) => u.id === thread.assigned_to_id)?.name : undefined);

  // Status, unassigned, channel and search narrow everything; the view tabs and their counts apply on top.
  const filtered = allThreads.filter(
    (thread) =>
      (status === 'all' || thread.status === status || (status === 'open' && !thread.status)) &&
      (!unassigned || !thread.assigned_to_id) &&
      searchMatch(search, [thread.contact_name, thread.address, thread.display_address, thread.preview, nameOf(thread), contactOf(thread)?.phone]),
  );
  const inView = (thread: Row, v: InboxView) => v === 'all' || (v === 'unread' ? Number(thread.unread_count || 0) > 0 : thread.assigned_to_id === user?.id);
  const byChannel = filtered.filter((t) => channel === 'all' || t.channel === channel);
  const counts = { all: 0, unread: byChannel.filter((t) => inView(t, 'unread')).length, mine: byChannel.filter((t) => inView(t, 'mine')).length } as Record<InboxView, number>;
  const visibleThreads = byChannel.filter((t) => inView(t, view));
  const channels = Array.from(new Set(allThreads.map((t) => t.channel))).sort().map((c) => ({
    channel: c, unread: filtered.filter((t) => t.channel === c && Number(t.unread_count || 0) > 0).length,
  }));

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
  const updateThread = (thread: Row, data: Record<string, unknown>) => act(async () => {
    const path = thread.source === 'whatsapp' ? `/whatsapp/conversations/${thread.id}` : `/inbox/inbox/${thread.id}`;
    const saved = await patch<Row>(path, data);
    setSelected({ ...thread, ...saved, source: thread.source, channel: thread.channel });
    await threads.mutate();
    if ('status' in data) notify(data.status === 'closed' ? 'Conversa encerrada.' : 'Conversa reaberta.');
    else notify('Responsável atualizado.');
  });
  const staffList = staff.data || [];

  return (
    <div className="page wa-page" data-chat-open={Boolean(selected)}>
      <PageHeader title="Caixa de entrada">
        <ConnectionBar connection={connection.current} instagram={instagram.data} canManage={manage} />
        <MessageNotificationButton />
        <Button onClick={() => setShowNew(true)}>
          <Plus size={16} /> Nova conversa
        </Button>
      </PageHeader>

      {requestedThread.error && <p className="form-error" role="alert">Não foi possível abrir a conversa da notificação. Verifique seu acesso ou selecione uma conversa na lista.</p>}
      <DataState loading={threads.isLoading} error={threads.error}>
        <Card fill className="wa-workspace">
          <div className={'wa-split' + (selectedThread && panelOpen ? ' with-panel' : '')} data-chat-open={Boolean(selected)}>
            <ThreadList
              threads={visibleThreads}
              counts={counts}
              channels={channels}
              nameOf={nameOf}
              ownerOf={ownerOf}
              selected={selected}
              onSelect={setSelected}
              search={search}
              onSearch={setSearch}
              view={view}
              onView={setView}
              status={status}
              onStatus={setStatus}
              channel={channel}
              onChannel={setChannel}
              unassigned={unassigned}
              onUnassigned={setUnassigned}
            />
            {selectedThread ? (
              <div className="wa-chat">
                {selectedThread.source === 'whatsapp' ? (
                  <ChatPane
                    key={selectedThread.id}
                    conversation={selectedThread}
                    connection={connection.current}
                    staff={staffList}
                    contact={contactOf(selectedThread)}
                    panelOpen={panelOpen}
                    onTogglePanel={togglePanel}
                    onBack={() => setSelected(null)}
                    onDetails={() => setShowDetails(true)}
                    onCreateOpportunity={() => setDealThread(selectedThread)}
                    onUpdate={(data) => updateThread(selectedThread, data)}
                    onRefresh={async () => { await connection.refresh(); await threads.mutate(); }}
                    onRead={() => { void threads.mutate(); }}
                  />
                ) : (
                  <OtherThread
                    key={selectedThread.source + selectedThread.id}
                    thread={selectedThread}
                    name={nameOf(selectedThread)}
                    contact={contactOf(selectedThread)}
                    staff={staffList}
                    messages={otherMessages.data || []}
                    loading={otherMessages.isLoading}
                    error={otherMessages.error}
                    canManage={manage}
                    busy={busy}
                    panelOpen={panelOpen}
                    onTogglePanel={togglePanel}
                    onBack={() => setSelected(null)}
                    onUpdate={(data) => updateThread(selectedThread, data)}
                    onCreateOpportunity={() => setDealThread(selectedThread)}
                    onSend={async (content) => {
                      setBusy(true);
                      try {
                        const result = await post<{ status: string; error: string }>(`/inbox/${selectedThread.source}/${selectedThread.id}/messages`, { content, idempotency_key: crypto.randomUUID() });
                        await refreshAll();
                        if (result.status === 'unknown') { notify(result.error, 'error'); return; }
                        notify(selectedThread.channel === 'instagram' ? 'Resposta enviada.' : 'Resposta adicionada à fila.');
                      } catch (error) { notify((error as Error).message, 'error'); throw error; }
                      finally { setBusy(false); }
                    }}
                    onResume={(message) => act(async () => { await post(`/communications/messages/${message.id}/resume`, {}); })}
                  />
                )}
              </div>
            ) : (
              <div className="wa-chat wa-no-chat">
                <span className="wa-no-chat-icon"><MessageCircle size={28} /></span>
                <h2>Selecione uma conversa</h2>
                <p>Escolha um atendimento na lista ou inicie uma nova conversa com um contato.</p>
                <Button variant="secondary" onClick={() => setShowNew(true)}><Plus size={16} /> Nova conversa</Button>
              </div>
            )}
            {selectedThread && panelOpen && (
              <ContactPanel
                contactId={selectedThread.contact_id}
                onCreateOpportunity={() => setDealThread(selectedThread)}
                onLink={selectedThread.source === 'whatsapp' ? () => setShowDetails(true) : undefined}
              />
            )}
          </div>
        </Card>
      </DataState>

      <NewConversationDialog open={showNew} onClose={() => setShowNew(false)} onCreated={async (created) => {
        setSelected({ ...created, source: 'whatsapp', channel: 'whatsapp', address: created.phone });
        setChannel('all');
        setStatus('all');
        setView('all');
        setUnassigned(false);
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
