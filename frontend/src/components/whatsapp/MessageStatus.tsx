import { Check, CheckCheck, Loader2 } from 'lucide-react';
import type { Row } from '@/lib/types';

/** Delivery ticks for outgoing messages. */
export function MessageStatus({ message }: { message: Row }) {
  switch (message.status) {
    case 'read':
      return <CheckCheck size={14} className="wa-tick-read" aria-label="Lida" />;
    case 'delivered':
      return <CheckCheck size={14} aria-label="Entregue" />;
    case 'pending':
      return <Loader2 size={12} className="spin" aria-label="Enviando" />;
    case 'unknown':
      return (
        <span className="wa-unconfirmed" title={message.error || ''}>
          Envio não confirmado
        </span>
      );
    default:
      return <Check size={14} aria-label="Enviada" />;
  }
}
