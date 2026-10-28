import { Check, CheckCheck, Clock, Loader2, Send, TriangleAlert } from 'lucide-react';
import { Fragment, useRef, useState } from 'react';
import { useReadIncomingMessages } from '@/components/inbox/message-notifications';
import { ConversationHeader, TemplatePicker, WindowChip, instagramWindow } from '@/components/inbox/inbox-tools';
import { Button, DataState } from '@/components/ui';
import type { Row } from '@/lib/types';
import { clockTime, dayLabel, messageDay } from '@/components/whatsapp/helpers';
import { useStickToBottom } from '@/components/whatsapp/use-stick-to-bottom';

const statusName: Record<string, string> = {
  queued: 'Na fila', sending: 'Em envio', blocked: 'Configuração pendente', unknown: 'Verificar no provedor', sent: 'Enviada',
  cancelled: 'Cancelada', pending: 'Pendente', delivered: 'Entregue', read: 'Lida',
};

/** Ticks like WhatsApp's; problems keep their words so nobody misses them. */
function StatusMark({ message }: { message: Row }) {
  const label = statusName[message.status] || message.status;
  if (message.status === 'read' || message.status === 'delivered') return <CheckCheck size={14} className={message.status === 'read' ? 'wa-tick-read' : ''} aria-label={label} />;
  if (message.status === 'sent') return <Check size={14} aria-label={label} />;
  if (message.status === 'queued' || message.status === 'sending' || message.status === 'pending') return <Clock size={12} aria-label={label} />;
  return <span className="wa-unconfirmed" title={message.error || ''}><TriangleAlert size={12} />{label}</span>;
}

/** An Instagram, e-mail or SMS conversation, laid out like the WhatsApp chat. */
export function OtherThread({
  thread, name, contact, staff, messages, loading, error, canManage, busy, panelOpen,
  onTogglePanel, onBack, onSend, onResume, onUpdate, onCreateOpportunity,
}: {
  thread: Row;
  name: string;
  contact?: Row | null;
  staff: Row[];
  messages: Row[];
  loading: boolean;
  error?: Error;
  canManage: boolean;
  busy: boolean;
  panelOpen: boolean;
  onTogglePanel: () => void;
  onBack: () => void;
  onSend: (content: string) => Promise<void>;
  onResume: (message: Row) => void;
  onUpdate: (data: Record<string, unknown>) => void;
  onCreateOpportunity?: () => void;
}) {
  useReadIncomingMessages(thread.source, thread.id, messages);
  const [content, setContent] = useState('');
  const field = useRef<HTMLTextAreaElement>(null);
  const ordered = [...messages].reverse();
  const box = useStickToBottom(thread.source + thread.id, ordered[ordered.length - 1]?.id, !loading);
  const instagram = thread.channel === 'instagram';
  // The list's last inbound time may lag a just-loaded message; take the newest of both.
  const lastIn = [thread.last_inbound_at, ...ordered.filter((m) => m.direction === 'in').map((m) => m.created_at)].filter(Boolean).sort().pop();
  const replyWindow = instagramWindow(lastIn);
  const closed = thread.status === 'closed';
  const blocked = instagram && !replyWindow.open;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = content.trim();
    if (!text || busy || blocked) return;
    try { await onSend(text); setContent(''); }
    catch { /* The parent displays the error; keep the draft for correction. */ }
  }
  return (
    <>
      <ConversationHeader thread={thread} name={name} address={thread.display_address || thread.address} staff={staff}
        panelOpen={panelOpen} onTogglePanel={onTogglePanel} onBack={onBack} onUpdate={onUpdate} onCreateOpportunity={onCreateOpportunity}
        extra={instagram ? <WindowChip lastInboundAt={lastIn} /> : undefined} />
      <div className="wa-messages" ref={box}>
        <DataState loading={loading} error={error}>
          {ordered.map((message, index) => {
            const outgoing = message.direction === 'out';
            const newDay = index === 0 || messageDay(ordered[index - 1].created_at) !== messageDay(message.created_at);
            return (
              <Fragment key={message.id}>
                {newDay && <div className="wa-day"><span>{dayLabel(message.created_at)}</span></div>}
                <article className={'wa-bubble' + (outgoing ? ' outgoing' : '')}>
                  <p>{message.content}</p>
                  <div className="wa-bubble-foot">
                    <time dateTime={message.created_at}>{clockTime(message.created_at)}</time>
                    {outgoing && <StatusMark message={message} />}
                  </div>
                  {message.error && message.status !== 'sent' && <small className="wa-bubble-error">{message.error}</small>}
                  {canManage && message.status === 'blocked' && thread.source === 'inbox' && (
                    <Button variant="secondary" disabled={busy} onClick={() => onResume(message)}>Retomar envio</Button>
                  )}
                </article>
              </Fragment>
            );
          })}
        </DataState>
      </div>
      <div className="wa-composer">
        {blocked ? (
          <div className="wa-banner wa-banner-warning" role="status">
            A janela de resposta do Instagram encerrou: só é possível responder até 24 horas depois da última mensagem do contato. Aguarde o contato escrever de novo.
          </div>
        ) : (
          <form onSubmit={submit}>
            <TemplatePicker channel={thread.channel} contact={contact} disabled={busy || closed} onPick={(text) => { setContent(text); field.current?.focus(); }} />
            <textarea ref={field} aria-label="Responder" placeholder={closed ? 'Reabra a conversa para responder' : 'Escreva sua resposta…'} rows={1}
              maxLength={instagram ? 1000 : 20000} value={content} disabled={closed}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
            <button className="wa-send" type="submit" aria-label="Enviar resposta" disabled={busy || closed || !content.trim()}>
              {busy ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
            </button>
          </form>
        )}
      </div>
    </>
  );
}
