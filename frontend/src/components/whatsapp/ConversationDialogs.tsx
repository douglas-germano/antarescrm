import { patch, post, useList } from '@/lib/api';
import { Button, FormDialog, Modal } from '@/components/ui';
import { EntitySelect } from '@/components/entity-select';
import { useState } from 'react';
import { useNotify } from '@/components/providers';
import { rowOptions } from '@/lib/format';
import type { Row } from '@/lib/types';

export function NewConversationDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (conversation: Row) => Promise<void>;
}) {
  const contacts = useList('/contacts');
  return (
    <FormDialog
      open={open}
      onClose={onClose}
      title="Nova conversa"
      description="Informe o telefone com DDI e DDD."
      fields={[
        { name: 'phone', label: 'Telefone', required: true, placeholder: '5566999990000' },
        { name: 'contact_name', label: 'Nome do contato' },
        {
          name: 'contact_id',
          label: 'Vincular contato existente',
          type: 'contact',
        },
      ]}
      onSubmit={async (data) => onCreated(await post('/whatsapp/conversations', data))}
    />
  );
}

export function ConversationDetailsDialog({
  open,
  onClose,
  conversation,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  conversation: Row | null;
  onSaved: (conversation: Row) => Promise<void>;
}) {
  const users = useList('/users');
  const contacts = useList('/contacts');
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!conversation || busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await onSaved(await patch(`/whatsapp/conversations/${conversation.id}`, {
        contact_name: String(form.get('contact_name')).trim(),
        contact_id: form.get('contact_id') || null,
        assigned_to_id: form.get('assigned_to_id') || null,
      }));
      onClose();
    } catch (e) { notify((e as Error).message, 'error'); }
    finally { setBusy(false); }
  }
  return <Modal open={open} onClose={onClose} title="Detalhes do atendimento">
    {conversation && <div className="wa-settings">
      <form key={conversation.id + String(open)} className="wa-agent-editor" onSubmit={submit}>
        <label>Nome do contato<input name="contact_name" required defaultValue={conversation.contact_name || ''} maxLength={180} /></label>
        <div className="field"><label htmlFor="conv-contact">Contato</label><EntitySelect kind="contacts" id="conv-contact" name="contact_id" defaultValue={conversation.contact_id} placeholder="Sem vínculo. Busque para vincular." /></div>
        <label>Responsável<select name="assigned_to_id" defaultValue={conversation.assigned_to_id || ''}><option value="">Sem responsável</option>{rowOptions((users.data || []).filter((r) => r.active)).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select></label>
        <div className="modal-footer"><Button variant="secondary" onClick={onClose}>Fechar</Button><Button type="submit" disabled={busy}>{busy ? 'Salvando…' : 'Salvar'}</Button></div>
      </form>
    </div>}
  </Modal>;
}
