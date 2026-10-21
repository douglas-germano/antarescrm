import { useEffect, useRef, useState } from 'react';
import { Loader2, Paperclip, Send, X } from 'lucide-react';
import { post } from '@/lib/api';
import { useNotify } from '@/components/providers';
import type { Row } from '@/lib/types';

const MAX_FILE_BYTES = 10 * 1024 * 1024;

export function Composer({
  conversationId,
  connected,
  closed,
  onSent,
}: {
  conversationId: string;
  connected: boolean;
  closed: boolean;
  /** Runs after a successful send so lists and messages can refresh before the composer unlocks. */
  onSent: () => Promise<void>;
}) {
  const { notify } = useNotify();
  const [input, setInput] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const upload = useRef<HTMLInputElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
  }, [input]);
  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (sending || (!input.trim() && !file)) return;
    setSending(true);
    setError('');
    const content = input.trim();
    const fingerprint = `${conversationId}:${content}:${file?.name || ''}:${file?.size || 0}:${file?.lastModified || 0}`;
    if (attempt.current?.fingerprint !== fingerprint) attempt.current = { fingerprint, key: crypto.randomUUID() };
    try {
      let result: Row;
      if (file) {
        const body = new FormData();
        body.set('file', file);
        body.set('content', content);
        body.set('idempotency_key', attempt.current.key);
        const response = await fetch(`/api/backend/whatsapp/conversations/${conversationId}/messages`, {
          method: 'POST',
          body,
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data?.error?.message || 'Não foi possível enviar o arquivo.');
        result = data;
      } else {
        result = await post(`/whatsapp/conversations/${conversationId}/messages`, {
          content,
          idempotency_key: attempt.current.key,
        });
      }
      setInput('');
      setFile(null);
      attempt.current = null;
      await onSent();
      if (result.status === 'unknown')
        setError('O envio não foi confirmado. Confira o WhatsApp do aparelho antes de reenviar para evitar duplicação.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  }
  return (
    <div className="wa-composer">
      {error && (
        <div className="wa-banner wa-banner-error" role="alert">
          {error}
        </div>
      )}
      {file && (
        <div className="wa-file-chip">
          <Paperclip size={15} />
          <span>{file.name}</span>
          <button className="icon-btn" type="button" aria-label="Remover arquivo" onClick={() => setFile(null)}>
            <X size={15} />
          </button>
        </div>
      )}
      <form onSubmit={send}>
        <input
          ref={upload}
          type="file"
          hidden
          onChange={(e) => {
            const chosen = e.target.files?.[0];
            if (chosen) {
              if (chosen.size > MAX_FILE_BYTES) notify('O arquivo deve ter até 10 MB.', 'error');
              else setFile(chosen);
            }
            e.target.value = '';
          }}
        />
        <button
          className="icon-btn wa-attach"
          type="button"
          aria-label="Anexar arquivo"
          onClick={() => upload.current?.click()}
          disabled={sending || !connected || closed}
        >
          <Paperclip size={20} />
        </button>
        <textarea
          ref={field}
          aria-label="Mensagem para o cliente"
          placeholder={closed ? 'Reabra a conversa para responder' : 'Escreva sua mensagem…'}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={1}
          maxLength={20000}
          disabled={sending || closed}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button
          className="wa-send"
          type="submit"
          aria-label="Enviar mensagem"
          disabled={sending || (!input.trim() && !file) || !connected || closed}
        >
          {sending ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
        </button>
      </form>
    </div>
  );
}
