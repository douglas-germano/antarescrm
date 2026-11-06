import { ArrowLeft, Check, ChevronDown, Clock, Handshake, Link2, MessageSquareText, MoreVertical, PanelRight, RefreshCw, RotateCcw, UserPlus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, useData, useList } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Popover } from '@/components/ui';
import { initials } from '@/lib/format';
import type { Row } from '@/lib/types';
import { ChannelIcon, ThreadAvatar, channelName } from '@/components/whatsapp/ThreadList';

/** Fills {{name}}, {{email}}, {{phone}} and {{custom.x}} the way the server renders templates. */
export function renderTemplate(text: string, contact?: Row | null) {
  let out = text;
  for (const key of ['name', 'email', 'phone']) out = out.split('{{' + key + '}}').join(contact?.[key] || '');
  for (const [key, value] of Object.entries(contact?.custom_fields || {})) out = out.split('{{custom.' + key + '}}').join(String(value));
  return out;
}

/** Which saved message templates suit a channel: Instagram has none of its own, so short-text ones are offered. */
const TEMPLATE_CHANNELS: Record<string, string[]> = { whatsapp: ['whatsapp'], instagram: ['whatsapp', 'sms'], email: ['email'], sms: ['sms'] };

export function TemplatePicker({ channel, contact, disabled, onPick }: { channel: string; contact?: Row | null; disabled?: boolean; onPick: (text: string) => void }) {
  const templates = useList('/message-templates');
  const options = (templates.data || []).filter((t) => (TEMPLATE_CHANNELS[channel] || [channel]).includes(t.channel));
  if (disabled) return <button type="button" className="icon-btn" disabled aria-label="Respostas prontas"><MessageSquareText size={19} /></button>;
  return (
    <Popover label="" ariaLabel="Respostas prontas" icon={<MessageSquareText size={19} />} variant="ghost" align="start" panelClassName="menu-panel reply-panel">
      {(close) => <>
        <span className="reply-panel-title">Respostas prontas</span>
        {options.length ? options.map((t) => (
          <button type="button" key={t.id} onClick={() => { onPick(renderTemplate(t.content, contact)); close(); }}>
            <span className="reply-option"><strong>{t.name}</strong><small>{renderTemplate(t.content, contact).slice(0, 90)}</small></span>
          </button>
        )) : <p className="muted reply-empty">Nenhum modelo para {channelName[channel] || channel}. Cadastre modelos de mensagem em Campanhas.</p>}
      </>}
    </Popover>
  );
}

/** Instagram only lets a business reply within 24 hours of the person's last message. */
export function instagramWindow(lastInboundAt?: string | null) {
  if (!lastInboundAt) return { open: false, hoursLeft: 0 };
  const left = new Date(lastInboundAt).getTime() + 24 * 3600_000 - Date.now();
  return { open: left > 0, hoursLeft: Math.max(0, Math.ceil(left / 3600_000)) };
}

/** Shared header for every channel: who, where, status and owner up front; the rest in a ⋮ menu. */
export function ConversationHeader({ thread, name, address, staff, panelOpen, onTogglePanel, onBack, onUpdate, onCreateOpportunity, onDetails, onSync, syncing, canSync, extra }: {
  thread: Row; name: string; address: string; staff: Row[]; panelOpen: boolean; onTogglePanel: () => void; onBack: () => void;
  onUpdate: (data: Record<string, unknown>) => void; onCreateOpportunity?: () => void; onDetails?: () => void; onSync?: () => void;
  syncing?: boolean; canSync?: boolean; extra?: React.ReactNode;
}) {
  const { user } = useSession();
  const { notify } = useNotify();
  const [assigning, setAssigning] = useState(false);
  const canAssignAtlas = user?.role === 'owner' || user?.role === 'admin';
  const assignmentPath = ['whatsapp', 'instagram'].includes(thread.channel) ? `/atlas/conversations/${thread.channel}/${thread.id}` : null;
  const { data: atlas, mutate: updateAtlas } = useData<{
    active: boolean;
    memory?: string;
    insight?: { handoff?: string; suggestion?: { kind: 'deal' | 'task'; title: string; reason: string } };
  }>(assignmentPath);
  useEffect(() => {
    if (!atlas?.active) return;
    const timer = window.setInterval(() => { void updateAtlas(); }, 5000);
    return () => window.clearInterval(timer);
  }, [atlas?.active, updateAtlas]);
  async function toggleAtlas() {
    if (!canAssignAtlas || !assignmentPath || !atlas || assigning) return;
    setAssigning(true);
    try {
      const result = await api<{ active: boolean }>(assignmentPath, { method: atlas.active ? 'DELETE' : 'POST' });
      await updateAtlas(result, { revalidate: false });
      notify(result.active ? 'Conversa atribuída ao Atlas.' : 'Atendimento do Atlas pausado.');
    } catch (error) {
      notify((error as Error).message, 'error');
    } finally {
      setAssigning(false);
    }
  }
  const closed = thread.status === 'closed';
  return (
    <header className="wa-chat-head tips-below">
      <div className="wa-identity">
        <button type="button" className="icon-btn wa-back" aria-label="Voltar às conversas" onClick={onBack}><ArrowLeft size={19} /></button>
        <ThreadAvatar name={name} channel={thread.channel} />
        <div className="wa-identity-text">
          <h2>{name}</h2>
          <p><ChannelIcon channel={thread.channel} size={12} /><span className="wa-address" title={address}>{channelName[thread.channel]} · {address}</span>
            <span className={'wa-state ' + (closed ? 'closed' : 'open')}>{closed ? 'Encerrada' : 'Aberta'}</span>{extra}</p>
        </div>
      </div>
      <div className="wa-chat-actions">
        {(atlas?.memory || atlas?.insight) && <Popover label={atlas.insight?.handoff && !atlas.active ? 'Resumo do repasse' : 'Contexto Atlas'}
          icon={<MessageSquareText size={15} />} variant="ghost" align="end">
          {(close) => <div className="field" style={{ width: 'min(22rem, 70vw)', padding: 12, overflowWrap: 'anywhere' }}>
            {atlas.insight?.handoff && <><strong>Resumo para a equipe</strong><p>{atlas.insight.handoff}</p></>}
            {atlas.memory && <><strong>Contexto guardado</strong><p>{atlas.memory}</p></>}
            {atlas.insight?.suggestion && <>
              <strong>{atlas.insight.suggestion.kind === 'deal' ? 'Negócio sugerido' : 'Tarefa sugerida'}</strong>
              <p>{atlas.insight.suggestion.title}</p><p className="muted">{atlas.insight.suggestion.reason}</p>
              {atlas.insight.suggestion.kind === 'deal' && onCreateOpportunity &&
                <button type="button" className="btn btn-soft" onClick={() => { close(); onCreateOpportunity(); }}>Criar negócio</button>}
            </>}
          </div>}
        </Popover>}

        {canAssignAtlas && atlas && <button type="button" className="btn btn-soft" disabled={assigning || (closed && !atlas.active)} onClick={toggleAtlas}>
          {atlas.active ? 'Pausar Atlas' : 'Atribuir ao Atlas'}
        </button>}
        {atlas?.active ? <span className="wa-state open">Responsável: Atlas</span> : <label className="owner-select" data-tip={thread.assigned_to_id ? 'Responsável: ' + (staff.find((u) => u.id === thread.assigned_to_id)?.name || '') : 'Sem responsável · clique para atribuir'}>
          <span className="owner-avatar">{thread.assigned_to_id ? initials(staff.find((u) => u.id === thread.assigned_to_id)?.name) : <UserPlus size={13} />}</span>
          <ChevronDown size={13} />
          <select aria-label="Responsável pela conversa" value={thread.assigned_to_id || ''} onChange={(e) => onUpdate({ assigned_to_id: e.target.value || null })}>
            <option value="">Sem responsável</option>
            {staff.filter((u) => u.active || u.id === thread.assigned_to_id).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </label>}
        <button type="button" className="btn btn-soft" onClick={() => onUpdate({ status: closed ? 'open' : 'closed' })}>
          {closed ? <><RotateCcw size={15} />Reabrir</> : <><Check size={15} />Encerrar</>}
        </button>
        <button type="button" className={'icon-btn' + (panelOpen ? ' active' : '')} aria-pressed={panelOpen} aria-label="Painel do contato" data-tip={panelOpen ? 'Ocultar contato' : 'Mostrar contato'} data-tip-align="end" onClick={onTogglePanel}><PanelRight size={17} /></button>
        <Popover label="" ariaLabel="Mais ações" icon={<MoreVertical size={17} />} variant="ghost" align="end" panelClassName="menu-panel">
          {(close) => <>
            {onCreateOpportunity && <button type="button" onClick={() => { close(); onCreateOpportunity(); }}><Handshake size={15} />Criar negócio</button>}
            {onDetails && <button type="button" onClick={() => { close(); onDetails(); }}><Link2 size={15} />Detalhes e vínculo do contato</button>}
            {onSync && <button type="button" disabled={syncing || !canSync} onClick={() => { close(); onSync(); }}><RefreshCw size={15} className={syncing ? 'spin' : ''} />Importar histórico do WhatsApp</button>}
          </>}
        </Popover>
      </div>
    </header>
  );
}

/** "Janela aberta · 5 h restantes" next to an Instagram conversation's status. */
export function WindowChip({ lastInboundAt }: { lastInboundAt?: string | null }) {
  const w = instagramWindow(lastInboundAt);
  return <span className={'ig-window' + (w.open ? '' : ' closed')} data-tip="O Instagram só permite responder até 24 horas depois da última mensagem do contato."><Clock size={11} />{w.open ? `${w.hoursLeft} h para responder` : 'Janela de 24 h encerrada'}</span>;
}
