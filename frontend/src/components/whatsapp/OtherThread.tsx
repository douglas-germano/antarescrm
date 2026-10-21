import { ArrowLeft, Loader2, Send } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button, DataState } from '@/components/ui';
import type { Row } from '@/lib/types';
import { ChannelIcon, ThreadAvatar, channelName } from './ThreadList';

const statusName: Record<string, string> = {
  queued: 'Na fila', sending: 'Em envio', blocked: 'Configuração pendente', unknown: 'Verificar no provedor', sent: 'Enviada',
  received: 'Recebida', cancelled: 'Cancelada', pending: 'Pendente', delivered: 'Entregue', read: 'Lida',
};

/** A non-WhatsApp (e-mail or SMS) thread, shown with the same chat layout as WhatsApp. */
export function OtherThread({
  thread,
  name,
  messages,
  loading,
  error,
  canManage,
  busy,
  onBack,
  onSend,
  onResume,
}: {
  thread: Row;
  name: string;
  messages: Row[];
  loading: boolean;
  error?: Error;
  canManage: boolean;
  busy: boolean;
  onBack: () => void;
  onSend: (content: string) => Promise<void>;
  onResume: (message: Row) => void;
}) {
  const [content, setContent] = useState('');
  const end = useRef<HTMLDivElement>(null);
  const ordered = [...messages].reverse();
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [ordered.length]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = content.trim();
    if (!text || busy) return;
    try { await onSend(text); setContent(''); }
    catch { /* The parent displays the error; keep the draft for correction. */ }
  }
  return (
    <div className="wa-chat">
      <header className="wa-chat-head">
        <div className="wa-identity">
          <button className="icon-btn wa-back" aria-label="Voltar às conversas" onClick={onBack}><ArrowLeft size={19} /></button>
          <ThreadAvatar name={name} channel={thread.channel} />
          <div className="wa-identity-text">
            <h2>{name}</h2>
            <p><ChannelIcon channel={thread.channel} size={12} /> {channelName[thread.channel]} · {thread.display_address || thread.address}</p>
          </div>
        </div>
      </header>
      <div className="wa-messages">
        <DataState loading={loading} error={error}>
          {ordered.map((message) => {
            const outgoing = message.direction === 'out';
            return (
              <article key={message.id} className={'wa-bubble' + (outgoing ? ' outgoing' : '')}>
                <p>{message.content}</p>
                <div className="wa-bubble-foot">
                  <time>{new Date(message.created_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</time>
                  <span>{statusName[message.status] || message.status}{message.error ? ' · ' + message.error : ''}</span>
                </div>
                {canManage && message.status === 'blocked' && thread.source === 'inbox' && (
                  <Button variant="secondary" disabled={busy} onClick={() => onResume(message)}>Retomar envio</Button>
                )}
              </article>
            );
          })}
          <div ref={end} />
        </DataState>
      </div>
      <div className="wa-composer">
        <form onSubmit={submit}>
          <textarea aria-label="Responder" placeholder="Escreva sua resposta…" rows={1} maxLength={thread.channel === 'instagram' ? 1000 : 20000} value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
          <button className="wa-send" type="submit" aria-label="Enviar resposta" disabled={busy || !content.trim()}>
            {busy ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
}
