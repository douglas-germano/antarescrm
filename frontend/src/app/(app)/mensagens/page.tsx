'use client';
import { useEffect, useRef, useState } from 'react';
import useSWR from 'swr';
import { MessageCircle, Plus } from 'lucide-react';
import { ChatPane } from '@/components/whatsapp/ChatPane';
import { ConnectionBar } from '@/components/whatsapp/ConnectionBar';
import { ConversationDetailsDialog, NewConversationDialog } from '@/components/whatsapp/ConversationDialogs';
import { OtherThread } from '@/components/whatsapp/OtherThread';
import { ThreadList, channelName } from '@/components/whatsapp/ThreadList';
import { useConnection } from '@/components/whatsapp/hooks';
import { BroadcastsPanel, TemplatesPanel } from '@/components/inbox/inbox-panels';
import { api, useList, useData, post, patch, refreshAll } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { PageHeader, Button, FormDialog, DataState } from '@/components/ui';
import { Card, Tabs } from '@/components/blocks';
import { searchMatch } from '@/lib/format';
import type { Field, Row } from '@/lib/types';

const templateFields: Field[] = [
  { name: 'name', label: 'Nome do modelo', required: true },
  { name: 'channel', label: 'Canal', type: 'select', required: true, options: Object.entries(channelName).filter(([value]) => value !== 'instagram').map(([value, label]) => ({ value, label })) },
  { name: 'subject', label: 'Assunto do e-mail', wide: true },
  { name: 'content', label: 'Mensagem', type: 'textarea', wide: true, required: true, help: 'Personalize com {{name}}, {{email}} ou {{phone}}.' },
];

export default function MessagesPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const manage = ['owner', 'admin'].includes(user?.role || '');
  const threads = useSWR<{ items: Row[] }>('/inbox', api, { refreshInterval: 5000 });
  const templates = useList('/message-templates');
  const contacts = useList('/contacts');
  const channels = useData<{ items: Row[] }>('/communications/channels');
  const [tab, setTab] = useState('inbox');
  const [channel, setChannel] = useState('all');
  const [status, setStatus] = useState('open');
  const [search, setSearch] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const connection = useConnection(true, false);
  const [selected, setSelected] = useState<Row | null>(null);
  const [editing, setEditing] = useState<Row | null | false>(false);
  const [busy, setBusy] = useState(false);
  const openedLink = useRef(false);

  useEffect(() => {
    if (openedLink.current) return;
    const id = new URLSearchParams(window.location.search).get('conversation');
    const row = threads.data?.items.find((item) => item.source === 'whatsapp' && item.id === id);
    if (row) {
      setSelected(row);
      setStatus('all');
      openedLink.current = true;
    }
  }, [threads.data]);

  const allThreads = threads.data?.items || [];
  const selectedThread = allThreads.find((item) => item.source === selected?.source && item.id === selected?.id) || selected;
  const nameOf = (thread: Row) => contacts.data?.find((contact) => contact.id === thread.contact_id)?.name || thread.contact_name || thread.address;
  const visibleThreads = allThreads.filter(
    (thread) =>
      (channel === 'all' || channel === thread.channel) &&
      (status === 'all' || thread.status === status || (status === 'open' && !thread.status)) &&
      searchMatch(search, [thread.contact_name, thread.address, thread.display_address, thread.preview, nameOf(thread), contacts.data?.find((c) => c.id === thread.contact_id)?.phone]),
  );
  const unreadTotal = allThreads.reduce((sum, thread) => sum + (thread.status === 'closed' ? 0 : Number(thread.unread_count || 0)), 0);
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
    <div className="page wa-page" data-chat-open={tab === 'inbox' && Boolean(selected)}>
      <PageHeader title="Caixa de entrada">
        <ConnectionBar connection={connection.current} canManage={manage} />
        {tab === 'inbox' && (
          <Button onClick={() => setShowNew(true)}>
            <Plus size={16} /> Nova conversa
          </Button>
        )}
      </PageHeader>

      <Tabs
        variant="line"
        value={tab}
        onChange={setTab}
        label="Comunicação"
        items={[
          { value: 'inbox', label: <>Conversas{unreadTotal > 0 && <span className="tab-badge">{unreadTotal}</span>}</> },
          ...(manage ? [{ value: 'broadcasts', label: 'Disparos' }] : []),
          { value: 'templates', label: 'Modelos' },
        ]}
      />

      {tab === 'broadcasts' && manage ? (
        <BroadcastsPanel channels={channels.data?.items || []} templates={templates.data || []} contacts={contacts.data || []} busy={busy} act={act} />
      ) : tab === 'templates' ? (
        <TemplatesPanel templates={templates.data || []} loading={templates.isLoading} error={templates.error} canManage={manage} onEdit={(template) => setEditing(template)} />
      ) : (
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
                  onSend={async (content) => {
                    setBusy(true);
                    try {
                      const result = await post(`/inbox/${selected.source}/${selected.id}/messages`, { content, idempotency_key: crypto.randomUUID() });
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
      )}

      <NewConversationDialog open={showNew} onClose={() => setShowNew(false)} onCreated={async (created) => {
        setTab('inbox');
        setSelected({ ...created, source: 'whatsapp', channel: 'whatsapp', address: created.phone });
        setChannel('all');
        setStatus('all');
        setSearch('');
        await threads.mutate();
      }} />
      <ConversationDetailsDialog open={showDetails} onClose={() => setShowDetails(false)} conversation={selectedThread} onSaved={async (updated) => {
        setSelected({ ...updated, source: 'whatsapp', channel: 'whatsapp', address: updated.phone });
        await threads.mutate();
        notify('Atendimento atualizado.');
      }} />
      <FormDialog open={editing !== false} onClose={() => setEditing(false)} title={editing ? 'Editar modelo' : 'Novo modelo'} fields={templateFields} initial={editing || { channel: 'email' }}
        onSubmit={async (data) => {
          const body = { ...data, subject: data.subject || '' };
          if (editing) await patch('/message-templates/' + editing.id, body);
          else await post('/message-templates', body);
          await refreshAll();
          notify('Modelo salvo.');
        }} />
    </div>
  );
}
