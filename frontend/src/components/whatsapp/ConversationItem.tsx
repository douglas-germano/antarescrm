import { initials } from '@/lib/format';
import type { Row } from '@/lib/types';
import { clockTime, contactName } from './helpers';

export function ConversationItem({
  conversation,
  selected,
  onSelect,
}: {
  conversation: Row;
  selected: boolean;
  onSelect: (conversation: Row) => void;
}) {
  const name = contactName(conversation);
  return (
    <button
      type="button"
      className={'wa-item' + (selected ? ' selected' : '')}
      aria-current={selected || undefined}
      onClick={() => onSelect(conversation)}
    >
      <span className="avatar">{initials(name)}</span>
      <span className="wa-item-body">
        <span className="wa-item-top">
          <strong>{name}</strong>
          <time>{conversation.last_message_at ? clockTime(conversation.last_message_at) : ''}</time>
        </span>
        <span className="wa-item-bottom">
          <span className="wa-item-preview">{conversation.last_message_preview || 'Conversa iniciada'}</span>
          {conversation.unread_count > 0 && (
            <span className="wa-unread" aria-label={`${conversation.unread_count} não lidas`}>
              {conversation.unread_count}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}
