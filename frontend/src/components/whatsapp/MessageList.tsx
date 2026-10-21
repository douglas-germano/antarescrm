import { Fragment, useEffect, useRef } from 'react';
import { Button, DataState, EmptyState } from '@/components/ui';
import type { Row } from '@/lib/types';
import { dayLabel, messageDay } from '@/components/whatsapp/helpers';
import { MessageBubble } from '@/components/whatsapp/MessageBubble';

export function MessageList({
  messages,
  latestId,
  loading,
  error,
  hasOlder,
  onLoadOlder,
}: {
  messages: Row[];
  latestId?: string;
  loading: boolean;
  error?: Error;
  hasOlder: boolean;
  onLoadOlder: () => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [latestId]);
  return (
    <div className="wa-messages">
      <DataState loading={loading} error={error}>
        {hasOlder && (
          <Button className="wa-load-older" variant="ghost" onClick={onLoadOlder}>
            Carregar mensagens anteriores
          </Button>
        )}
        {messages.length ? (
          messages.map((message, index) => (
            <Fragment key={message.id}>
              {(index === 0 || messageDay(messages[index - 1].occurred_at) !== messageDay(message.occurred_at)) && (
                <div className="wa-day">
                  <span>{dayLabel(message.occurred_at)}</span>
                </div>
              )}
              <MessageBubble message={message} />
            </Fragment>
          ))
        ) : (
          <EmptyState title="Nenhuma mensagem ainda" description="Envie a primeira mensagem para iniciar a conversa." />
        )}
        <div ref={end} />
      </DataState>
    </div>
  );
}
