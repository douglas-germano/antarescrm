import { AlertTriangle, Clock, Handshake, Instagram, Mail, MessageCircle, Search, SlidersHorizontal, Smartphone, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { EmptyState, Popover } from '@/components/ui';
import { initials } from '@/lib/format';
import type { Row } from '@/lib/types';
import { listTime } from '@/components/whatsapp/helpers';

export const channelName: Record<string, string> = { email: 'E-mail', sms: 'SMS', whatsapp: 'WhatsApp', instagram: 'Instagram' };

export function ChannelIcon({ channel, size = 11 }: { channel: string; size?: number }) {
  if (channel === 'instagram') return <Instagram size={size} />;
  if (channel === 'email') return <Mail size={size} />;
  if (channel === 'sms') return <Smartphone size={size} />;
  return <MessageCircle size={size} />;
}

export function ThreadAvatar({ name, channel }: { name: string; channel: string }) {
  return (
    <span className="wa-avatar">
      <span className="avatar">{initials(name)}</span>
      <span className={'wa-channel-badge ' + channel} title={channelName[channel]}><ChannelIcon channel={channel} /></span>
    </span>
  );
}

export type InboxView = 'all' | 'unread' | 'mine' | 'unassigned' | 'waiting' | 'failed';
const VIEWS: { value: InboxView; label: string }[] = [
  { value: 'all', label: 'Todas' },
  { value: 'unread', label: 'Não lidas' },
  { value: 'mine', label: 'Minhas' },
  { value: 'unassigned', label: 'Sem responsável' },
  { value: 'waiting', label: 'Aguardando equipe' },
  { value: 'failed', label: 'Falhas' },
];

/** Whether a conversation belongs to a quick filter; `me` is the signed-in user's id. */
export function inInboxView(thread: Row, view: InboxView, me?: string) {
  if (view === 'unread') return Number(thread.unread_count || 0) > 0;
  if (view === 'mine') return Boolean(me) && thread.assigned_to_id === me;
  if (view === 'unassigned') return !thread.assigned_to_id;
  if (view === 'waiting') return thread.waiting_on === 'team';
  if (view === 'failed') return Boolean(thread.delivery_failed);
  return true;
}

/** Minutes the contact has waited for the team, or null when nobody waits on us. */
export function waitingMinutes(thread: Row, at = Date.now()) {
  if (thread.waiting_on !== 'team' || !thread.waiting_since) return null;
  return Math.max(0, Math.floor((at - new Date(thread.waiting_since).getTime()) / 60000));
}

/** Short wait label: "4 min", "2 h", "3 d". */
export function waitLabel(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} h`;
  return `${Math.floor(minutes / 1440)} d`;
}

/** Up to 15 min is fine, up to an hour is a warning, beyond that is late. */
export const slaLevel = (minutes: number) => (minutes > 60 ? 'late' : minutes > 15 ? 'warn' : 'ok');

/** "Mediana 12 min" style text for the first-response line. */
export function durationLabel(seconds: number) {
  if (seconds < 60) return `${seconds} s`;
  return waitLabel(Math.round(seconds / 60));
}
const STATUSES = [
  { value: 'open', label: 'Abertas' },
  { value: 'closed', label: 'Encerradas' },
  { value: 'all', label: 'Abertas e encerradas' },
];

/** The unified conversation list: views with counts, channel chips, extra filters, then one row per thread. */
export function ThreadList({
  threads, counts, channels, nameOf, ownerOf, selected, onSelect, search, onSearch,
  view, onView, status, onStatus, channel, onChannel, firstResponse, footer,
}: {
  threads: Row[];
  counts: Record<InboxView, number>;
  /** Unread conversations per channel, for the chip badges; only channels with conversations get a chip. */
  channels: { channel: string; unread: number }[];
  nameOf: (thread: Row) => string;
  ownerOf: (thread: Row) => string | undefined;
  selected: Row | null;
  onSelect: (thread: Row) => void;
  search: string;
  onSearch: (value: string) => void;
  view: InboxView;
  onView: (value: InboxView) => void;
  status: string;
  onStatus: (value: string) => void;
  channel: string;
  onChannel: (value: string) => void;
  /** Median first response of the last days, from the inbox summary. */
  firstResponse?: { median: number | null; sample: number; days: number };
  footer?: ReactNode;
}) {
  const extraFilters = status !== 'open' ? 1 : 0;
  return (
    <aside className="wa-list">
      <div className="wa-list-head tips-below">
        <div className="wa-list-search">
          <div className="search">
            <Search size={16} />
            <input aria-label="Buscar conversa" placeholder="Buscar conversa…" value={search} onChange={(e) => onSearch(e.target.value)} />
            {search && <button type="button" aria-label="Limpar busca" onClick={() => onSearch('')}><X size={14} /></button>}
          </div>
          <Popover label="" ariaLabel="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" align="end" panelClassName="filter-panel"
            badge={extraFilters ? <span className="popover-badge">{extraFilters}</span> : undefined}>{() => <>
            <label className="field"><span>Situação</span>
              <select value={status} onChange={(e) => onStatus(e.target.value)}>{STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
          </>}</Popover>
        </div>
        <div className="inbox-views" role="tablist" aria-label="Conversas">
          {VIEWS.map((v) => (
            <button key={v.value} type="button" role="tab" aria-selected={view === v.value} className={'inbox-view' + (view === v.value ? ' active' : '')} onClick={() => onView(v.value)}>
              {v.label}{counts[v.value] > 0 && <span>{counts[v.value] > 99 ? '99+' : counts[v.value]}</span>}
            </button>
          ))}
        </div>
        {firstResponse && (
          <p className="inbox-sla" data-tip={`Tempo entre a mensagem do contato e a primeira resposta da equipe, em ${firstResponse.sample} atendimento(s).`}>
            <Clock size={12} /> 1ª resposta ({firstResponse.days} dias): {firstResponse.median == null ? 'sem dados' : 'mediana ' + durationLabel(firstResponse.median)}
          </p>
        )}
        {channels.length > 1 && (
          <div className="inbox-channels" role="group" aria-label="Canal">
            <button type="button" className={'inbox-channel' + (channel === 'all' ? ' active' : '')} onClick={() => onChannel('all')}>Todos</button>
            {channels.map((c) => (
              <button key={c.channel} type="button" className={'inbox-channel ' + c.channel + (channel === c.channel ? ' active' : '')} aria-pressed={channel === c.channel}
                data-tip={channelName[c.channel]} aria-label={channelName[c.channel]} onClick={() => onChannel(channel === c.channel ? 'all' : c.channel)}>
                <ChannelIcon channel={c.channel} size={14} />{channelName[c.channel]}{c.unread > 0 && <span>{c.unread}</span>}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="wa-items">
        {threads.map((thread) => {
          const name = nameOf(thread);
          const active = selected?.id === thread.id && selected?.source === thread.source;
          const unread = Number(thread.unread_count || 0);
          const waiting = thread.waiting_on === 'team';
          const owner = ownerOf(thread);
          const minutes = waitingMinutes(thread);
          const failed = Boolean(thread.delivery_failed);
          const isOpen = thread.status !== 'closed';
          return (
            <button type="button" key={thread.source + thread.id} className={'wa-item' + (active ? ' selected' : '') + (unread ? ' unread' : '') + (waiting ? ' waiting' : '')} aria-current={active || undefined} onClick={() => onSelect(thread)}>
              <ThreadAvatar name={name} channel={thread.channel} />
              <span className="wa-item-body">
                <span className="wa-item-top">
                  <strong>{name}</strong>
                  <time>{listTime(thread.last_message_at || thread.updated_at)}</time>
                </span>
                {thread.channel === 'instagram' && thread.display_address && thread.display_address !== 'Instagram' && thread.display_address !== name && <small className="wa-item-handle">{thread.display_address}</small>}
                {thread.instagram_account && <small className="wa-item-handle">via @{thread.instagram_account}</small>}
                <span className="wa-item-bottom">
                  <span className="wa-item-preview">{thread.preview || 'Conversa iniciada'}</span>
                  {thread.has_open_deal && <span className="wa-item-deal" data-tip="Tem negócio em aberto" aria-label="Tem negócio em aberto"><Handshake size={12} /></span>}
                  {unread > 0 && <span className="wa-unread" aria-label={`${unread} não lidas`}>{unread}</span>}
                </span>
                {(isOpen || failed) && (
                  <span className="wa-item-meta">
                    {owner
                      ? <span className="wa-owner-chip" title={'Responsável: ' + owner}><span className="owner-avatar">{initials(owner)}</span>{owner.split(' ')[0]}</span>
                      : isOpen && <span className="wa-owner-chip none">Sem responsável</span>}
                    {minutes != null && <span className={'wa-wait ' + slaLevel(minutes)} title="Tempo esperando resposta da equipe"><Clock size={11} />{waitLabel(minutes)}</span>}
                    {failed && <span className="wa-failed" title={thread.delivery_error || 'Falha no envio'}><AlertTriangle size={11} />Falha no envio</span>}
                  </span>
                )}
              </span>
            </button>
          );
        })}
        {!threads.length && <EmptyState icon={<MessageCircle />} title="Nenhuma conversa" description={view === 'failed' ? 'Nenhuma conversa com falha de envio.' : view === 'mine' ? 'Nenhuma conversa atribuída a você com estes filtros.' : 'Inicie um atendimento ou ajuste os filtros.'} />}
      </div>
      {footer}
    </aside>
  );
}
