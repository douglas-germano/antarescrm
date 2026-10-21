import { ArrowLeft, Link2, MessageCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui';
import { initials } from '@/lib/format';
import type { Row } from '@/lib/types';
import { contactName } from './helpers';

export function ChatHeader({
  conversation,
  canSync,
  syncing,
  onBack,
  onDetails,
  onToggleStatus,
  onSync,
}: {
  conversation: Row;
  canSync: boolean;
  syncing: boolean;
  onBack: () => void;
  onDetails: () => void;
  onToggleStatus: () => void;
  onSync: () => void;
}) {
  const name = contactName(conversation);
  return (
    <header className="wa-chat-head">
      <div className="wa-identity">
        <button className="icon-btn wa-back" aria-label="Voltar às conversas" onClick={onBack}>
          <ArrowLeft size={19} />
        </button>
        <span className="wa-avatar">
          <span className="avatar">{initials(name)}</span>
          <span className="wa-channel-badge whatsapp"><MessageCircle size={11} /></span>
        </span>
        <div className="wa-identity-text">
          <h2>{name}</h2>
          <p>
            WhatsApp · +{conversation.phone}
            <span className={'wa-state ' + (conversation.status === 'closed' ? 'closed' : 'open')}>
              {conversation.status === 'closed' ? 'Encerrada' : 'Aberta'}
            </span>
          </p>
        </div>
      </div>
      <div className="wa-chat-actions">
        <Button variant="secondary" onClick={onDetails}>
          <Link2 size={14} />
          Detalhes
        </Button>
        <Button variant="secondary" onClick={onToggleStatus}>
          {conversation.status === 'closed' ? 'Reabrir' : 'Encerrar'}
        </Button>
        <button
          className="icon-btn"
          title="Importar até 500 mensagens do histórico armazenado na Evolution"
          aria-label="Sincronizar histórico"
          disabled={syncing || !canSync}
          onClick={onSync}
        >
          <RefreshCw size={15} className={syncing ? 'spin' : ''} />
        </button>
      </div>
    </header>
  );
}
