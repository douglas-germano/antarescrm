import { useEffect, useState } from 'react';
import { post } from '@/lib/api';
import { useNotify } from '@/components/providers';
import type { Row } from '@/lib/types';
import { ChatHeader } from '@/components/whatsapp/ChatHeader';
import { Composer } from '@/components/whatsapp/Composer';
import { useMessages } from '@/components/whatsapp/hooks';
import { MessageList } from '@/components/whatsapp/MessageList';

/** One open conversation. Mount it with `key={conversation.id}` so per-conversation state resets on switch. */
export function ChatPane({
  conversation,
  connection,
  onBack,
  onDetails,
  onUpdate,
  onRefresh,
  onRead,
}: {
  conversation: Row;
  connection?: Row;
  onBack: () => void;
  onDetails: () => void;
  onUpdate: (data: Record<string, any>) => void;
  /** Reloads connection and conversation list. */
  onRefresh: () => Promise<void>;
  onRead: () => void;
}) {
  const { notify } = useNotify();
  const messages = useMessages(conversation.id);
  const [syncing, setSyncing] = useState(false);
  const closed = conversation.status === 'closed';
  const connected = Boolean(connection?.connected);
  useEffect(() => {
    post(`/whatsapp/conversations/${conversation.id}/read`, {})
      .then(onRead)
      .catch(() => {});
  }, [conversation.id]);
  async function refresh() {
    await onRefresh();
    await messages.mutate();
  }
  async function sync() {
    setSyncing(true);
    try {
      const result = await post(`/whatsapp/conversations/${conversation.id}/sync`, {});
      notify(`${result.imported} mensagens importadas.`);
      messages.clearOlder();
      await refresh();
    } catch (e) {
      notify((e as Error).message, 'error');
    } finally {
      setSyncing(false);
    }
  }
  return (
    <>
      <ChatHeader
        conversation={conversation}
        canSync={connected}
        syncing={syncing}
        onBack={onBack}
        onDetails={onDetails}
        onToggleStatus={() => onUpdate({ status: closed ? 'open' : 'closed' })}
        onSync={sync}
      />
      {!connected && (
        <div className="wa-banner wa-banner-warning" role="status">
          WhatsApp desconectado: você pode ler o histórico, mas só envia mensagens depois de reconectar.
        </div>
      )}
      <MessageList
        messages={messages.messages}
        latestId={messages.latestId}
        loading={messages.loading}
        error={messages.error}
        hasOlder={messages.hasOlder}
        onLoadOlder={messages.loadOlder}
      />
      <Composer
        conversationId={conversation.id}
        connected={connected}
        closed={closed}
        onSent={async () => {
          messages.clearOlder();
          await refresh();
        }}
      />
    </>
  );
}
