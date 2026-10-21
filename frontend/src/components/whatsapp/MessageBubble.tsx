import type { Row } from '@/lib/types';
import { clockTime } from '@/components/whatsapp/helpers';
import { MessageMedia } from '@/components/whatsapp/MessageMedia';
import { MessageStatus } from '@/components/whatsapp/MessageStatus';

export function MessageBubble({ message }: { message: Row }) {
  const outgoing = message.direction === 'out';
  return (
    <article className={'wa-bubble' + (outgoing ? ' outgoing' : '')}>
      {message.kind !== 'text' && <MessageMedia message={message} />}
      {message.content && <p>{message.content}</p>}
      <div className="wa-bubble-foot">
        <time dateTime={message.occurred_at}>{clockTime(message.occurred_at)}</time>
        {outgoing && <MessageStatus message={message} />}
      </div>
    </article>
  );
}
