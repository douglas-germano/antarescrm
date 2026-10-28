'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Plus, Mail, MessageCircle, RefreshCw, Send, Eye, Copy, Pencil, Pause, Lock, PenLine, Users } from 'lucide-react';
import { useData, useList, usePage, post, patch, refreshAll } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { Button, PageHeader, DataState, FormDialog, Modal, EmptyState, Badge, Popover } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { Card, CardBody, Tabs, Toolbar, ToolbarEnd } from '@/components/blocks';
import type { Field, Row } from '@/lib/types';
import styles from './page.module.css';

type Channel = 'email' | 'whatsapp';
type Campaign = { id: string; channel: Channel; name: string; subject: string; content: string; status: string; audience: { tag?: string; source?: string }; recipient_count: number; audience_hash: string; error?: string; metrics: Record<string, number> };
type Audience = { total: number; limit: number; excluded: Record<string, number>; sample: { contact_id: string; name: string; email?: string; phone?: string }[] };
type Composer = { id?: string; channel: Channel; name: string; subject: string; content: string; tag: string; source: string; template: string };
const channelNames = { email: 'E-mail', whatsapp: 'WhatsApp' };
const channelIcons = { email: <Mail size={14} />, whatsapp: <MessageCircle size={14} /> };
const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

/** Lets the person pick a channel before creating a campaign or a template. */
function ChannelMenu({ label, variant, onPick }: { label: string; variant: 'primary' | 'soft'; onPick: (channel: Channel) => void }) {
  return <Popover label={label} icon={<Plus size={16} />} variant={variant} align="end" panelClassName="menu-panel">{close => <>
    <button type="button" onClick={() => { close(); onPick('email'); }}><Mail size={15} />E-mail</button>
    <button type="button" onClick={() => { close(); onPick('whatsapp'); }}><MessageCircle size={15} />WhatsApp</button>
  </>}</Popover>;
}
const labels: Record<string, string> = { draft: 'Rascunho', preparing: 'Preparando', importing: 'Importando público', ready: 'Pronta para envio', sending: 'Em envio', sent: 'Enviada', failed: 'Falha na importação', unknown: 'Verificar envio', suspended: 'Suspensa', completed_with_issues: 'Concluída com pendências' };
const emailMetrics = { delivered: 'Entregues', opened: 'Com abertura registrada', click: 'Com clique registrado', hard_bounce: 'Falhas permanentes', soft_bounce: 'Falhas temporárias', spam: 'Reclamações', unsubscribed: 'Descadastros' };
const whatsappMetrics = { queued: 'Na fila', sending: 'Em processamento', sent: 'Enviadas', unknown: 'Sem confirmação', blocked: 'Bloqueadas', cancelled: 'Canceladas' };

export default function CampaignsPage() {
  const { user } = useSession();
  const canManage = ['owner', 'admin'].includes(user?.role || '');
  const { notify } = useNotify();
  const campaigns = usePage<Campaign>('/campaigns');
  const templates = useList(canManage ? '/message-templates' : null);
  const connection = useData<{ connection: { configured: boolean; webhook_id: number | null } | null }>(canManage ? '/brevo/connection' : null);
  const channels = useData<{ items: { channel: string; configured: boolean }[] }>(canManage ? '/communications/channels' : null);
  const contacts = useData<{ tags: string[]; sources: string[] }>(canManage ? '/contacts?per_page=1' : null);
  const [tab, setTab] = useState('campaigns');
  const [composer, setComposer] = useState<Composer | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [templateEditor, setTemplateEditor] = useState<{ channel: Channel; row: Row | null } | null>(null);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [audience, setAudience] = useState<Audience | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [consent, setConsent] = useState(false);
  const paused = useRef(false);
  useEffect(() => () => { paused.current = true; }, []);
  const emailReady = Boolean(connection.data?.connection?.configured && connection.data.connection.webhook_id);
  const whatsappReady = Boolean(channels.data?.items.find(item => item.channel === 'whatsapp')?.configured);
  const isWhatsApp = selected?.channel === 'whatsapp';

  function compose(channel: Channel, row?: Campaign, edit = false) {
    setFormError('');
    setComposer({ channel, id: edit ? row?.id : undefined, name: row ? row.name + (edit ? '' : ' (cópia)') : '', subject: row?.subject || '', content: row?.content || '', tag: row?.audience.tag || '', source: row?.audience.source || '', template: '' });
  }
  async function act(action: string) {
    if (!selected || busy) return;
    setBusy(true); setError(''); paused.current = false;
    try {
      let updated = await post<Campaign>(`/campaigns/${selected.id}/${action}`, action === 'send' ? { audience_hash: selected.audience_hash, consent_confirmed: consent } : {});
      setSelected(updated); setConfirming(false); setConsent(false);
      if (updated.channel === 'whatsapp' && (action === 'send' || action === 'process')) {
        if (updated.metrics.unknown > selected.metrics.unknown) setError('Um envio ficou sem confirmação. Confira a conversa antes de reenviá-lo.');
        const initialUnknown = selected.metrics.unknown;
        while (updated.metrics.queued > 0 && updated.metrics.unknown <= initialUnknown && !paused.current) {
          const unknown = updated.metrics.unknown;
          updated = await post<Campaign>(`/campaigns/${updated.id}/process`, {});
          setSelected(updated);
          if (updated.metrics.unknown > unknown) { setError('Um envio ficou sem confirmação. Confira a conversa antes de reenviá-lo. Você pode continuar os demais destinatários.'); break; }
        }
        notify(updated.metrics.queued ? 'Envio pausado. Use “Continuar envio” para processar os destinatários restantes.' : 'Processamento da campanha concluído. Confira os resultados.');
      } else if (!updated.error) notify(action === 'send' ? 'Solicitação de envio registrada.' : 'Campanha atualizada.');
      if (updated.error) setError(updated.error);
      await refreshAll();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  const templateFields: Field[] = [
    { name: 'name', label: 'Nome do modelo', required: true, wide: true },
    ...(templateEditor?.channel === 'email' ? [{ name: 'subject', label: 'Assunto do e-mail', required: true, wide: true }] : []),
    { name: 'content', label: 'Mensagem', type: 'textarea', required: true, wide: true, help: templateEditor?.channel === 'whatsapp' ? 'Personalize com {{name}}, {{email}} ou {{phone}}.' : 'O assunto e a mensagem serão copiados para a campanha e poderão ser editados.' },
  ];
  if (!canManage) return <div className="page"><PageHeader title="Campanhas" /><Card><EmptyState icon={<Lock />} title="Acesso restrito" description="Somente administradores podem gerenciar campanhas desta conta." /></Card></div>;
  const templateRows = (templates.data || []).filter(row => row.channel === 'email' || row.channel === 'whatsapp');
  const newTemplate = (channel: Channel) => setTemplateEditor({ channel, row: null });
  const openCampaign = (row: Campaign) => { setSelected(row); setAudience(null); setError(''); };
  return <div className="page">
    <PageHeader title="Campanhas">
      <ChannelMenu label="Nova campanha" variant="primary" onPick={channel => compose(channel)} />
    </PageHeader>
    <Toolbar>
      <Tabs value={tab} onChange={setTab} label="Campanhas e modelos" items={[
        { value: 'campaigns', label: <>Campanhas <span className="tab-count">{campaigns.data?.total ?? 0}</span></> },
        { value: 'templates', label: <>Modelos <span className="tab-count">{templateRows.length}</span></> },
      ]} />
      {tab === 'templates' && <ToolbarEnd><ChannelMenu label="Novo modelo" variant="soft" onPick={newTemplate} /></ToolbarEnd>}
    </Toolbar>
    {tab === 'templates' ? <DataState loading={templates.isLoading} error={templates.error}>
      {templateRows.length ? <div className="template-grid">{templateRows.map(row => <Card key={row.id} className="template-card"><CardBody>
        <div className="template-top"><span className="deal-chip">{channelNames[row.channel as Channel]}</span><button className="icon-btn" aria-label={'Editar modelo ' + row.name} onClick={() => setTemplateEditor({ channel: row.channel, row })}><Pencil size={16} /></button></div>
        <h3>{row.name}</h3>{row.subject && <p className="template-subject">{row.subject}</p>}<p className="template-body">{row.content}</p>
        <Button variant="secondary" disabled={busy} onClick={() => { compose(row.channel); setComposer(previous => previous && ({ ...previous, template: row.id, subject: row.subject || '', content: row.content })); }}>Usar em campanha</Button>
      </CardBody></Card>)}</div> : <Card><EmptyState icon={<PenLine />} title="Nenhum modelo" description="Crie um modelo de e-mail ou WhatsApp para reutilizar em suas campanhas."
        action={<div className="row-actions empty-actions"><Button variant="secondary" onClick={() => newTemplate('email')}><Mail size={15} />Modelo de e-mail</Button><Button variant="secondary" onClick={() => newTemplate('whatsapp')}><MessageCircle size={15} />Modelo de WhatsApp</Button></div>} /></Card>}
    </DataState> : <>
      <Card><DataState loading={campaigns.isLoading} error={campaigns.error}>
        {campaigns.data?.items.length ? <PagedTable rows={campaigns.data.items} pagination={{ ...campaigns.data, onChange: campaigns.setPage }}
          header={<tr><th>Campanha</th><th>Canal</th><th>Situação</th><th>Destinatários</th><th className="text-right">Ações</th></tr>}
          renderRow={row => <tr key={row.id} className="clickable" onClick={() => openCampaign(row)}>
            <td><button type="button" className="client-identity" onClick={event => { event.stopPropagation(); openCampaign(row); }}>{row.name}</button>{row.subject && <small className="muted">{row.subject}</small>}</td>
            <td><span className="channel-cell">{channelIcons[row.channel]}{channelNames[row.channel]}</span></td>
            <td><Badge value={row.status === 'sent' ? 'completed' : 'doing'} label={labels[row.status] || row.status} /></td>
            <td>{row.recipient_count ? plural(row.recipient_count, 'contato', 'contatos') : <span className="muted">Público a revisar</span>}</td>
            <td><div className="row-actions"><Button variant="ghost" aria-label={'Abrir ' + row.name} data-tip="Abrir campanha" data-tip-align="end" onClick={event => { event.stopPropagation(); openCampaign(row); }}><Eye size={15} /></Button></div></td></tr>} />
          : <div className="campaign-empty">
            <h3>Nenhuma campanha ainda</h3>
            <p>Uma campanha leva a mesma mensagem a um grupo de contatos, por e-mail ou WhatsApp. Nada é enviado sem a sua revisão.</p>
            <ol className="campaign-steps">
              <li><span><PenLine size={18} /></span><strong>Escreva a mensagem</strong><small>Do zero ou a partir de um modelo.</small></li>
              <li><span><Users size={18} /></span><strong>Revise o público</strong><small>Filtre por tag ou origem e confira quem recebe.</small></li>
              <li><span><Send size={18} /></span><strong>Envie</strong><small>Confirme e acompanhe entregas e respostas.</small></li>
            </ol>
            <div className="row-actions empty-actions"><Button onClick={() => compose('email')}><Mail size={15} />Campanha de e-mail</Button><Button variant="secondary" onClick={() => compose('whatsapp')}><MessageCircle size={15} />Campanha de WhatsApp</Button></div>
          </div>}
      </DataState></Card>
      <Modal wide open={Boolean(selected) && !composer && !confirming} onClose={() => { if (!busy) setSelected(null); }} title={selected?.name || 'Campanha'}>
        {selected && <div className="stack">
          <div className="campaign-detail-head">
            <span className="channel-cell">{channelIcons[selected.channel]}{channelNames[selected.channel]}</span>
            <Badge value={selected.status === 'sent' ? 'completed' : 'doing'} label={labels[selected.status] || selected.status} />
            <div className="row-actions">{selected.status === 'draft' && <Button variant="secondary" disabled={busy} onClick={() => compose(selected.channel, selected, true)}><Pencil size={15} />Editar rascunho</Button>}<Button variant="ghost" disabled={busy} onClick={() => compose(selected.channel, selected)}><Copy size={15} />Copiar para novo rascunho</Button></div>
          </div>
          {((isWhatsApp && !whatsappReady) || (!isWhatsApp && !emailReady)) && <div className="account-summary"><p>{isWhatsApp ? 'Conecte o WhatsApp desta conta para preparar e enviar a campanha.' : 'Conecte o Brevo e ative o acompanhamento para preparar e enviar a campanha.'}</p><Link className="btn btn-secondary" href="/configuracoes?tab=conexoes">Configurar conexão</Link></div>}
          <div className={styles.review}>
            <section aria-label="Prévia da mensagem"><h3>{selected.subject || 'Mensagem de WhatsApp'}</h3><p className={styles.message}>{selected.content}</p><small className="muted">{isWhatsApp ? 'Os campos do modelo serão preenchidos com os dados de cada contato.' : 'O e-mail inclui um link para cancelar a inscrição.'}</small></section>
            <section className="stack" aria-label="Público da campanha"><h3>Público</h3><p>Com {isWhatsApp ? 'telefone' : 'e-mail'} válido · {selected.audience.tag ? `Tag: ${selected.audience.tag}` : 'Todas as tags'} · {selected.audience.source || 'Todas as origens'}</p>
              <Button variant="secondary" disabled={busy} onClick={async () => {
                setBusy(true); setError('');
                try { setAudience(await post<Audience>('/campaigns/audience', { ...selected.audience, channel: selected.channel })); }
                catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
              }}><Eye size={15} />Revisar público</Button>
              {audience && <div role="status"><strong>{plural(audience.total, 'destinatário elegível', 'destinatários elegíveis')}</strong><p className="muted">Excluídos: {audience.excluded.without_email ?? audience.excluded.without_phone} sem {isWhatsApp ? 'telefone' : 'e-mail'}, {audience.excluded.invalid} inválidos, {audience.excluded.suppressed} bloqueados e {audience.excluded.duplicates} duplicados.</p><p className="muted">Até {audience.limit} destinatários por campanha.{!isWhatsApp && ' O Brevo também aplica os descadastros registrados na plataforma.'}</p><ul className={styles.recipients}>{audience.sample.map(item => <li key={item.contact_id}>{item.name}<small>{item.email || item.phone}</small></li>)}</ul>{audience.total > 20 && <small>Prévia dos primeiros 20 contatos.</small>}</div>}
            </section>
          </div>
          <div className={styles.metrics}>{Object.entries(isWhatsApp ? whatsappMetrics : emailMetrics).map(([key, label]) => <div key={key}><strong>{selected.metrics?.[key] || 0}</strong><small>{label}</small></div>)}</div>
          {(error || selected.error) && <p className="form-error" role="alert">{error || selected.error}</p>}
          <div className="row-actions">
            {selected.status === 'draft' && <Button disabled={busy || !audience || !audience.total || audience.total > audience.limit || !(isWhatsApp ? whatsappReady : emailReady)} onClick={() => act('prepare')}>{isWhatsApp ? 'Preparar campanha' : 'Preparar no Brevo'}</Button>}
            {selected.status !== 'draft' && <Button variant="secondary" disabled={busy} onClick={() => act('refresh')}><RefreshCw size={15} />{isWhatsApp ? 'Atualizar resultados' : 'Consultar Brevo'}</Button>}
            {selected.status === 'ready' && <Button disabled={busy} onClick={() => { setConsent(false); setConfirming(true); }}><Send size={15} />Revisar e enviar</Button>}
            {isWhatsApp && selected.metrics.queued > 0 && !busy && <Button onClick={() => act('process')}><Send size={15} />Continuar envio</Button>}
            {isWhatsApp && busy && selected.metrics.queued > 0 && <Button variant="secondary" onClick={() => { paused.current = true; }}><Pause size={15} />Pausar após a mensagem atual</Button>}
            {!isWhatsApp && selected.status === 'unknown' && <a className="btn btn-secondary" href="https://app.brevo.com" target="_blank" rel="noreferrer">Abrir painel do Brevo</a>}
          </div>
          {isWhatsApp && selected.metrics.queued > 0 && <p className="muted" role="status">Mantenha esta página aberta durante o envio. Ao sair, os destinatários pendentes poderão ser retomados em “Continuar envio”.</p>}
          {isWhatsApp && (selected.metrics.unknown > 0 || selected.metrics.sending > 0) && <p className="muted">Mensagens sem confirmação não são reenviadas automaticamente. Confira as conversas antes de criar outro envio.</p>}
          {selected.status === 'importing' && <p className="muted">O público está sendo importado. Use “Consultar Brevo” até a campanha ficar pronta para envio.</p>}
        </div>}
      </Modal>
    </>}
    <Modal open={Boolean(composer)} onClose={() => { if (!saving) setComposer(null); }} title={`${composer?.id ? 'Editar' : 'Nova'} campanha de ${composer?.channel === 'whatsapp' ? 'WhatsApp' : 'e-mail'}`}>
      {composer && <form className="stack" onSubmit={async event => {
        event.preventDefault(); if (saving) return; setSaving(true); setFormError('');
        try {
          const body = { name: composer.name, channel: composer.channel, subject: composer.channel === 'email' ? composer.subject : '', content: composer.content, audience: { tag: composer.tag, source: composer.source } };
          const row = composer.id ? await patch<Campaign>('/campaigns/' + composer.id, body) : await post<Campaign>('/campaigns', body);
          setSelected(row); setAudience(null); setComposer(null); setTab('campaigns'); setError(''); await refreshAll(); notify('Rascunho salvo. Revise a mensagem e o público.');
        } catch (reason) { setFormError((reason as Error).message); } finally { setSaving(false); }
      }}><fieldset disabled={saving} className="form-grid">
        <div className="field field-wide"><label htmlFor="campaign-name">Nome da campanha *</label><input id="campaign-name" required maxLength={150} value={composer.name} onChange={event => setComposer({ ...composer, name: event.target.value })} /></div>
        <div className="field field-wide"><label htmlFor="campaign-template">Usar modelo</label><select id="campaign-template" value={composer.template} onChange={event => { const row = templates.data?.find(item => item.id === event.target.value); setComposer({ ...composer, template: event.target.value, ...(row ? { subject: row.subject || '', content: row.content } : {}) }); }}><option value="">Escrever mensagem</option>{templates.data?.filter(row => row.channel === composer.channel).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select><small className="muted">Você pode editar a mensagem sem alterar o modelo.</small></div>
        {composer.channel === 'email' && <div className="field field-wide"><label htmlFor="campaign-subject">Assunto do e-mail *</label><input id="campaign-subject" required maxLength={180} value={composer.subject} onChange={event => setComposer({ ...composer, subject: event.target.value })} /></div>}
        <div className="field"><label htmlFor="campaign-tag">Tag dos contatos</label><select id="campaign-tag" value={composer.tag} onChange={event => setComposer({ ...composer, tag: event.target.value })}><option value="">Todas as tags</option>{(contacts.data?.tags || []).map(value => <option key={value}>{value}</option>)}</select></div>
        <div className="field"><label htmlFor="campaign-source">Origem dos contatos</label><select id="campaign-source" value={composer.source} onChange={event => setComposer({ ...composer, source: event.target.value })}><option value="">Todas as origens</option>{(contacts.data?.sources || []).map(value => <option key={value}>{value}</option>)}</select></div>
        <div className="field field-wide"><label htmlFor="campaign-content">Mensagem *</label><textarea id="campaign-content" required maxLength={20000} rows={7} value={composer.content} onChange={event => setComposer({ ...composer, content: event.target.value })} /><small className="muted">{composer.channel === 'whatsapp' ? 'Personalize com {{name}}, {{email}} ou {{phone}}.' : 'O link de descadastro será incluído no e-mail.'}</small></div>
      </fieldset>{formError && <p className="form-error" role="alert">{formError}</p>}<div className="row-actions"><Button type="submit" disabled={saving}>{saving ? 'Salvando…' : 'Salvar rascunho'}</Button><Button variant="secondary" disabled={saving} onClick={() => setComposer(null)}>Cancelar</Button></div></form>}
    </Modal>
    <FormDialog key={templateEditor ? `${templateEditor.channel}-${templateEditor.row?.id || 'new'}` : 'closed'} open={Boolean(templateEditor)} onClose={() => setTemplateEditor(null)} title={`${templateEditor?.row ? 'Editar' : 'Novo'} modelo de ${templateEditor?.channel === 'whatsapp' ? 'WhatsApp' : 'e-mail'}`} fields={templateFields} initial={templateEditor?.row || {}} onSubmit={async data => {
      if (!templateEditor) return;
      const body = { ...data, channel: templateEditor.channel, subject: templateEditor.channel === 'email' ? data.subject || '' : '' };
      if (templateEditor.row) await patch('/message-templates/' + templateEditor.row.id, body);
      else await post('/message-templates', body);
      await refreshAll(); setTab('templates'); notify('Modelo salvo.');
    }} />
    <Modal open={confirming} onClose={() => { if (!busy) setConfirming(false); }} title="Enviar campanha agora">
      <div className="stack"><p><strong>{selected?.subject || selected?.name}</strong></p><p>{isWhatsApp ? 'O WhatsApp conectado a esta conta enviará a mensagem' : 'O Brevo receberá a solicitação de envio'} para até {selected?.recipient_count} destinatários.</p>
        <label className="checkbox-label"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} disabled={busy} />Revisei a mensagem e confirmo que este público autoriza receber estas comunicações.</label>
        {error && <p className="form-error" role="alert">{error}</p>}<div className="row-actions"><Button disabled={busy || !consent} onClick={() => act('send')}>{busy ? 'Solicitando envio…' : 'Confirmar envio'}</Button><Button variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>Cancelar</Button></div>
      </div>
    </Modal>
  </div>;
}
