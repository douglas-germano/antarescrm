import { RecordLink } from '@/components/record-link';
import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import { AtSign, CalendarPlus, Handshake, Mail, Phone, Tag, UserRound } from 'lucide-react';
import { useData, post, refreshAll } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button, FormDialog } from '@/components/ui';
import { brl, day, formatPhone, hasRealName, kinds, opts } from '@/lib/format';
import type { Row } from '@/lib/types';

/** Who the conversation is with, beside the chat: data, open deals, what's scheduled, and quick actions. */
export function ContactPanel({ contactId, onCreateOpportunity, onLink }: { contactId?: string | null; onCreateOpportunity: () => void; onLink?: () => void }) {
  const { user } = useSession();
  const { notify } = useNotify();
  const contact = useData<Row>(contactId ? '/contacts/' + contactId : null);
  const timeline = useData<Row>(contactId ? '/contacts/' + contactId + '/timeline' : null);
  const stages = useData<{ items: Row[] }>(contactId ? '/pipeline/stages' : null);
  const [scheduling, setScheduling] = useState(false);
  if (!contactId) {
    return (
      <aside className="contact-panel">
        <div className="contact-panel-empty">
          <UserRound size={22} />
          <p>Esta conversa ainda não está ligada a um contato.</p>
          {onLink && <Button variant="soft" onClick={onLink}>Vincular contato</Button>}
          <Button variant="soft" onClick={onCreateOpportunity}><Handshake size={15} />Criar negócio e contato</Button>
        </div>
      </aside>
    );
  }
  const c = contact.data;
  const t = timeline.data;
  const deals = (t?.opportunities || []).filter((o: Row) => o.status === 'open');
  const tasks = (t?.tasks || []).filter((x: Row) => x.status === 'todo' || x.status === 'doing').slice(0, 4);
  const activities = (t?.activities || []).filter((a: Row) => a.status === 'pending').sort((a: Row, b: Row) => a.scheduled_at.localeCompare(b.scheduled_at)).slice(0, 4);
  const stageName = (id: string) => stages.data?.items.find((s) => s.id === id)?.name || '';
  const username = c?.custom_fields?.instagram_username;
  return (
    <aside className="contact-panel">
      <header>
        <strong>{c ? (hasRealName(c.name) ? c.name : 'Sem nome') : '…'}</strong>
        {c?.source && <small>Origem: {c.source}</small>}
      </header>
      <ul className="contact-facts">
        {c?.phone && <li><Phone size={14} />{formatPhone(c.phone)}</li>}
        {c?.email && <li><Mail size={14} /><span>{c.email}</span></li>}
        {username && <li><AtSign size={14} />{username}</li>}
        {!!c?.tags?.length && <li className="contact-tags"><Tag size={14} />{c.tags.map((tag: string) => <span key={tag} className="deal-chip">{tag}</span>)}</li>}
      </ul>
      <div className="contact-actions">
        <RecordLink href={'/contatos?contato=' + contactId} className="btn btn-soft">Abrir contato</RecordLink>
        <Button variant="soft" onClick={onCreateOpportunity}><Handshake size={15} />Criar negócio</Button>
        <Button variant="soft" onClick={() => setScheduling(true)}><CalendarPlus size={15} />Agendar retorno</Button>
      </div>
      <section>
        <h3>Negócios em aberto</h3>
        {deals.length ? deals.map((o: Row) => (
          <RecordLink key={o.id} href={'/crm?opportunity=' + o.id} className="contact-row"><span><strong>{o.title}</strong><small>{stageName(o.stage_id) || 'Etapa'}</small></span><b>{brl(o.amount)}</b></RecordLink>
        )) : <p className="muted">Nenhum negócio em aberto.</p>}
      </section>
      <section>
        <h3>Próximos compromissos</h3>
        {activities.map((a: Row) => <div key={a.id} className="contact-row"><span><strong>{a.title}</strong><small>{kinds[a.kind] || 'Atividade'} · {day(a.scheduled_at)}</small></span></div>)}
        {tasks.map((x: Row) => <Link key={x.id} to="/tarefas" className="contact-row"><span><strong>{x.title}</strong><small>Tarefa{x.due_date ? ' · ' + day(x.due_date) : ''}</small></span></Link>)}
        {!activities.length && !tasks.length && <p className="muted">Nada agendado.</p>}
      </section>
      <FormDialog
        open={scheduling}
        onClose={() => setScheduling(false)}
        title="Agendar retorno"
        fields={[
          { name: 'title', label: 'Atividade', required: true },
          { name: 'kind', label: 'Tipo', type: 'select', options: opts(kinds), defaultValue: 'follow_up' },
          { name: 'scheduled_at', label: 'Data e hora', type: 'datetime-local', required: true },
          { name: 'notes', label: 'Observações', type: 'textarea', wide: true },
        ]}
        initial={{ kind: 'follow_up', title: 'Retornar conversa' }}
        onSubmit={async (data) => {
          await post('/activities', { ...data, contact_id: contactId, owner_id: user?.id || null, notes: data.notes || null });
          await refreshAll();
          setScheduling(false);
          notify('Retorno agendado.');
        }}
      />
    </aside>
  );
}
