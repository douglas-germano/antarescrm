import { RecordLink } from '@/components/record-link';
import { useId, useRef, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { ExternalLink, Handshake } from 'lucide-react';
import { EntitySelect } from '@/components/contacts/entity-select';
import { Button, DataState, Modal } from '@/components/ui';
import { useSession } from '@/components/providers';
import { post, useData, useList } from '@/lib/api';
import styles from './create-opportunity-dialog.module.css';
import type { Contact, Opportunity, Pipeline, PipelineStage, Row, User } from '@/lib/types';

export type InboxOpportunityResult = { opportunity: Opportunity; conversation: Row };

/** Mounted only while open so each conversation starts with its own draft and request ID. */
export function CreateInboxOpportunityDialog({ thread, label, onClose, onCreated }: {
  thread: Row; label: string; onClose: () => void; onCreated: (result: InboxOpportunityResult) => Promise<void>;
}) {
  const { user } = useSession();
  const id = useId();
  const pipelines = useData<{ items: Pipeline[] }>('/pipelines');
  const stages = useData<{ items: PipelineStage[] }>('/pipeline/stages');
  const users = useList<User>('/users');
  const contact = useData<Contact>(thread.contact_id ? '/contacts/' + thread.contact_id : null);
  const [pipelineId, setPipelineId] = useState('default');
  const [stageId, setStageId] = useState('');
  const [mode, setMode] = useState<'existing' | 'new'>('new');
  const [contactId, setContactId] = useState('');
  const [newName, setNewName] = useState(thread.contact_name || (thread.display_address?.startsWith('@') ? thread.display_address : label));
  const [title, setTitle] = useState(('Negócio · ' + label).slice(0, 180));
  const autoTitle = useRef(true);
  const [requestId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState<Opportunity | null>(null);
  const submitting = useRef(false);
  const filteredStages = (stages.data?.items || []).filter(stage => (stage.pipeline_id || 'default') === pipelineId);
  const selectedStage = filteredStages.some(stage => stage.id === stageId) ? stageId : filteredStages[0]?.id || '';
  const fieldId = (field: string) => id + '-' + field;
  const channel = thread.channel || thread.source;
  const canManage = ['owner', 'admin'].includes(user?.role || '');
  function suggestTitle(name: string) { if (autoTitle.current) setTitle(('Negócio · ' + name).slice(0, 180)); }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || created) return;
    const form = new FormData(event.currentTarget);
    submitting.current = true; setBusy(true); setError('');
    try {
      const body = {
        idempotency_key: requestId, title: title.trim(), stage_id: selectedStage,
        amount: String(form.get('amount') || '0'), owner_id: form.get('owner_id') || null,
        expected_close_date: form.get('expected_close_date') || null, description: String(form.get('description') || '').trim() || null,
        ...(thread.contact_id ? { contact_id: thread.contact_id } : mode === 'existing' ? { contact_id: contactId } : {
          contact: { name: newName.trim(), email: String(form.get('contact_email') || '').trim() || null, phone: String(form.get('contact_phone') || '').trim() || null },
        }),
      };
      const result = await post<InboxOpportunityResult>(`/inbox/${thread.source}/${thread.id}/opportunities`, body);
      setCreated(result.opportunity);
      await onCreated(result);
    } catch (reason) { setError((reason as Error).message); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <Modal open onClose={() => { if (!busy) onClose(); }} title={created ? 'Negócio criado' : 'Criar negócio'} description={label}>
    {created ? <div className="stack" role="status">
      <p><strong>{created.title}</strong> foi vinculado ao contato desta conversa e adicionado ao funil.</p>
      {error && <p className="form-error" role="alert">O negócio foi criado. Não foi possível atualizar a conversa: {error}</p>}
      <div className="row-actions"><RecordLink className="btn btn-secondary" href={'/crm?opportunity=' + created.id}><ExternalLink size={16} />Ver negócio no funil</RecordLink><Button disabled={busy} onClick={onClose}>Continuar conversa</Button></div>
    </div> : <DataState loading={pipelines.isLoading || stages.isLoading || users.isLoading || Boolean(thread.contact_id && contact.isLoading)} error={pipelines.error || stages.error || users.error || contact.error}>
      <form className="stack" onSubmit={submit}>
        <fieldset disabled={busy} className="form-grid">
          {thread.contact_id ? <div className="field field-wide"><span className="small-caps">Contato da conversa</span><strong>{contact.data?.name || label}</strong><small className="muted">O negócio será vinculado a este contato{contact.data?.company_id ? ' e à empresa cadastrada nele' : ''}.</small>{contact.data?.archived && <p className="form-error" role="alert">Este contato está arquivado. Reative-o em Contatos antes de criar o negócio.</p>}</div> : <>
            <div className="field field-wide"><span className="small-caps">Contato da conversa</span><div className={styles.contactOptions}><label className="checkbox-label"><input type="radio" name="contact_mode" checked={mode === 'new'} onChange={() => setMode('new')} />Cadastrar contato</label><label className="checkbox-label"><input type="radio" name="contact_mode" checked={mode === 'existing'} onChange={() => setMode('existing')} />Usar contato cadastrado</label></div><small className="muted">O contato também será vinculado a esta conversa.</small></div>
            {mode === 'existing' ? <div className="field field-wide"><label htmlFor={fieldId('contact')}>Contato *</label><EntitySelect kind="contacts" id={fieldId('contact')} required defaultValue={contactId} onChange={(value, row) => { setContactId(value); if (row) suggestTitle(row.name); }} /></div> : <>
              <div className="field field-wide"><label htmlFor={fieldId('name')}>Nome do contato *</label><input id={fieldId('name')} required maxLength={180} value={newName} onChange={event => { setNewName(event.target.value); suggestTitle(event.target.value); }} /></div>
              <div className="field"><label htmlFor={fieldId('email')}>E-mail do contato</label><input id={fieldId('email')} type="email" name="contact_email" maxLength={254} defaultValue={channel === 'email' ? thread.address : ''} /></div>
              <div className="field"><label htmlFor={fieldId('phone')}>Telefone do contato</label><input id={fieldId('phone')} type="tel" name="contact_phone" maxLength={30} defaultValue={channel === 'whatsapp' || channel === 'sms' ? thread.phone || thread.address || '' : ''} /></div>
            </>}
          </>}
          <div className="field field-wide"><label htmlFor={fieldId('title')}>Título do negócio *</label><input id={fieldId('title')} required maxLength={180} value={title} onChange={event => { autoTitle.current = false; setTitle(event.target.value); }} /></div>
          <div className="field"><label htmlFor={fieldId('pipeline')}>Funil *</label><select id={fieldId('pipeline')} required value={pipelineId} onChange={event => { setPipelineId(event.target.value); setStageId(''); }}>{pipelines.data?.items.map(pipeline => <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>)}</select></div>
          <div className="field"><label htmlFor={fieldId('stage')}>Etapa *</label><select id={fieldId('stage')} required value={selectedStage} onChange={event => setStageId(event.target.value)}><option value="">Selecione a etapa</option>{filteredStages.map(stage => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></div>
          <div className="field"><label htmlFor={fieldId('amount')}>Valor estimado (R$)</label><input id={fieldId('amount')} type="number" name="amount" min="0" max="999999999999.99" step="0.01" inputMode="decimal" defaultValue="0" /></div>
          <div className="field"><label htmlFor={fieldId('owner')}>Responsável</label><select id={fieldId('owner')} name="owner_id" defaultValue={user?.id || ''}><option value="">Sem responsável</option>{users.data?.filter(person => person.active).map(person => <option key={person.id} value={person.id}>{person.name}</option>)}</select></div>
          <div className="field field-wide"><label htmlFor={fieldId('date')}>Previsão de fechamento</label><input id={fieldId('date')} type="date" name="expected_close_date" /></div>
          <div className="field field-wide"><label htmlFor={fieldId('description')}>Descrição</label><textarea id={fieldId('description')} name="description" rows={3} maxLength={5000} /></div>
        </fieldset>
        {!filteredStages.length && <p role="status">Este funil não possui etapas. Selecione outro funil{canManage ? <> ou <Link to="/configuracoes" search={{"tab": "funis"}}>configure as etapas</Link></> : ' ou peça a um administrador para configurá-lo'}.</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="row-actions"><Button type="submit" disabled={busy || !selectedStage || Boolean(contact.data?.archived) || (!thread.contact_id && mode === 'existing' && !contactId)}><Handshake size={16} />{busy ? 'Criando…' : 'Criar negócio'}</Button><Button variant="secondary" disabled={busy} onClick={onClose}>Cancelar</Button></div>
      </form>
    </DataState>}
  </Modal>;
}
