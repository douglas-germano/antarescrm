'use client';
import { useState } from 'react';
import { Pencil, Play, Plus, Search, Send } from 'lucide-react';
import { searchMatch } from '@/lib/format';
import { post } from '@/lib/api';
import { useNotify } from './providers';
import { Button, DataState, EmptyState } from './ui';
import { Card, CardBody, CardHeader } from './blocks';
import { ChannelIcon, channelName } from './whatsapp/ThreadList';
import type { Row } from '@/lib/types';

/** Queue controls, channel health and the broadcast composer. */
export function BroadcastsPanel({ channels, templates, contacts, busy, act }: {
  channels: Row[]; templates: Row[]; contacts: Row[]; busy: boolean; act: (work: () => Promise<void>) => Promise<void>;
}) {
  const { notify } = useNotify();
  const [composing, setComposing] = useState(false);
  const [templateId, setTemplateId] = useState('');
  const [chosen, setChosen] = useState<string[]>([]);
  const [needle, setNeedle] = useState('');
  const visible = contacts.filter((contact) => searchMatch(needle, [contact.name, contact.phone, contact.email]));
  return (
    <section className="inbox-panels" aria-label="Disparos">
      <Card>
        <CardHeader title="Canais e fila de envio" description="Disparos entram na fila e saem pelos canais configurados."
          actions={<div className="header-actions">
            <Button variant="secondary" disabled={busy} onClick={() => act(async () => { const result = await post('/communications/dispatch', {}); notify(`${result.items.length} envio(s) processado(s).`); })}><Play size={15} /> Processar fila</Button>
            <Button onClick={() => setComposing(true)}><Plus size={16} /> Novo disparo</Button>
          </div>} />
        <CardBody>
          <ul className="channel-list">
            {channels.map((channel) => (
              <li key={channel.channel} className={channel.configured ? 'ok' : 'pending'}>
                <ChannelIcon channel={channel.channel} size={15} />
                <strong>{channelName[channel.channel]}</strong>
                <span>{channel.configured ? 'Configurado' : 'Configuração pendente'}</span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
      {composing && (
        <Card>
          <CardHeader title="Novo disparo" description="Até 100 contatos por disparo." />
          <CardBody>
            <form className="stack" onSubmit={(e) => {
              e.preventDefault();
              if (busy) return;
              act(async () => {
                const result = await post('/communications/broadcasts', { contact_ids: chosen, template_id: templateId, idempotency_key: crypto.randomUUID() });
                notify(`${result.total} mensagem(ns) na fila.`);
                setComposing(false);
                setChosen([]);
              });
            }}>
              <div className="field">
                <label htmlFor="broadcast-template">Modelo</label>
                <select id="broadcast-template" required value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                  <option value="">Selecione</option>
                  {templates.map((template) => <option key={template.id} value={template.id}>{template.name} · {channelName[template.channel]}</option>)}
                </select>
              </div>
              <fieldset className="field">
                <legend className="small-caps">Destinatários ({chosen.length}/100)</legend>
                <div className="search"><Search size={16} /><input aria-label="Buscar destinatário" placeholder="Buscar por nome, telefone ou e-mail" value={needle} onChange={(e) => setNeedle(e.target.value)} /></div>
                <div className="recipient-list">
                  {visible.map((contact) => (
                    <label className="checkbox-label" key={contact.id}>
                      <input type="checkbox" checked={chosen.includes(contact.id)} disabled={!chosen.includes(contact.id) && chosen.length >= 100}
                        onChange={(e) => setChosen((previous) => (e.target.checked ? [...previous, contact.id] : previous.filter((id) => id !== contact.id)))} />
                      {contact.name}
                    </label>
                  ))}
                  {!visible.length && <p className="muted">Nenhum contato encontrado.</p>}
                </div>
              </fieldset>
              <div className="row-actions">
                <Button type="submit" disabled={busy || !chosen.length || !templateId}><Send size={15} /> Adicionar {chosen.length} envio(s) à fila</Button>
                <Button variant="secondary" onClick={() => setComposing(false)}>Cancelar</Button>
              </div>
            </form>
          </CardBody>
        </Card>
      )}
    </section>
  );
}

/** Message templates as a grid of cards. */
export function TemplatesPanel({ templates, loading, error, canManage, onEdit }: {
  templates: Row[]; loading: boolean; error?: Error; canManage: boolean; onEdit: (template: Row | null) => void;
}) {
  return (
    <DataState loading={loading} error={error}>
      <section className="inbox-panels" aria-label="Modelos">
        {canManage && <div><Button onClick={() => onEdit(null)}><Plus size={16} /> Criar modelo</Button></div>}
        {templates.length ? (
          <div className="template-grid">
            {templates.map((template) => (
              <Card key={template.id} className="template-card">
                <CardBody>
                  <div className="template-top">
                    <span className="deal-chip"><ChannelIcon channel={template.channel} size={12} /> {channelName[template.channel]}</span>
                    {canManage && <button type="button" className="icon-btn" aria-label={'Editar modelo ' + template.name} onClick={() => onEdit(template)}><Pencil size={15} /></button>}
                  </div>
                  <h3>{template.name}</h3>
                  {template.subject && <p className="template-subject">{template.subject}</p>}
                  <p className="template-body">{template.content}</p>
                </CardBody>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState title="Nenhum modelo" description="Crie modelos para reutilizar mensagens em conversas e disparos." />
        )}
      </section>
    </DataState>
  );
}
