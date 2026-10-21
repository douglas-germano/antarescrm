'use client';
import { useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { post, patch, refreshAll } from '@/lib/api';
import { useNotify } from './providers';
import { Button, Modal } from './ui';
import type { Row } from '@/lib/types';

export type WhatsAppTarget = { name: string; phone: string; contact_id?: string | null; deal?: string };

/** Sends a WhatsApp message to a contact straight from a pipeline card, reusing the inbox conversation. */
export function SendWhatsAppDialog({ target, connected, onClose }: { target: WhatsAppTarget | null; connected: boolean; onClose: () => void }) {
  const { notify } = useNotify();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const attempt = useRef<{ text: string; key: string } | null>(null);
  useEffect(() => {
    if (target) { setText(''); setError(''); attempt.current = null; }
  }, [target]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const content = text.trim();
    if (!target || !content || busy) return;
    setBusy(true);
    setError('');
    if (attempt.current?.text !== content) attempt.current = { text: content, key: crypto.randomUUID() };
    try {
      let conversation: Row = await post('/whatsapp/conversations', {
        phone: target.phone, contact_name: target.name, contact_id: target.contact_id || null,
      });
      if (conversation.status === 'closed') conversation = await patch('/whatsapp/conversations/' + conversation.id, { status: 'open' });
      const message: Row = await post(`/whatsapp/conversations/${conversation.id}/messages`, { content, idempotency_key: attempt.current.key });
      attempt.current = null;
      await refreshAll();
      if (message.status === 'unknown') {
        setError('O envio não foi confirmado. Confira o WhatsApp do aparelho antes de reenviar para evitar duplicação.');
      } else {
        notify('Mensagem enviada pelo WhatsApp.');
        onClose();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open={!!target} onClose={() => { if (!busy) onClose(); }} title={'WhatsApp — ' + (target?.name || '')}
      description={target ? `${target.phone}${target.deal ? ' · ' + target.deal : ''}` : undefined}>
      <form className="stack" onSubmit={submit}>
        {!connected && <p role="status" className="form-error">O WhatsApp não está conectado. Conecte em Caixa de entrada antes de enviar.</p>}
        <div className="field">
          <label htmlFor="wa-quick-text">Mensagem</label>
          <textarea id="wa-quick-text" rows={5} value={text} maxLength={20000} autoFocus onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} />
          <small>A mensagem também aparece na conversa da Caixa de entrada. Ctrl/⌘ + Enter envia.</small>
        </div>
        {error && <p role="alert" className="form-error">{error}</p>}
        <div className="modal-footer">
          <Button variant="secondary" disabled={busy} onClick={onClose}>Cancelar</Button>
          <Button type="submit" disabled={busy || !text.trim() || !connected}><Send size={15} /> {busy ? 'Enviando…' : 'Enviar'}</Button>
        </div>
      </form>
    </Modal>
  );
}
