import { Handshake, Instagram, Mail, MessageCircle, Search, SlidersHorizontal, Smartphone, X } from 'lucide-react';
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

export type InboxView = 'all' | 'unread' | 'mine';
const VIEWS: { value: InboxView; label: string }[] = [
  { value: 'all', label: 'Todas' },
  { value: 'unread', label: 'Não lidas' },
  { value: 'mine', label: 'Minhas' },
];
const STATUSES = [
  { value: 'open', label: 'Abertas' },
  { value: 'closed', label: 'Encerradas' },
  { value: 'all', label: 'Abertas e encerradas' },
];

/** The unified conversation list: views with counts, channel chips, extra filters, then one row per thread. */
export function ThreadList({
  threads, counts, channels, nameOf, ownerOf, selected, onSelect, search, onSearch,
  view, onView, status, onStatus, channel, onChannel, unassigned, onUnassigned, footer,
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
  unassigned: boolean;
  onUnassigned: (value: boolean) => void;
  footer?: ReactNode;
}) {
  const extraFilters = (status !== 'open' ? 1 : 0) + (unassigned ? 1 : 0);
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
            <label className="checkbox-label"><input type="checkbox" checked={unassigned} onChange={(e) => onUnassigned(e.target.checked)} />Somente sem responsável</label>
          </>}</Popover>
        </div>
        <div className="inbox-views" role="tablist" aria-label="Conversas">
          {VIEWS.map((v) => (
            <button key={v.value} type="button" role="tab" aria-selected={view === v.value} className={'inbox-view' + (view === v.value ? ' active' : '')} onClick={() => onView(v.value)}>
              {v.label}{counts[v.value] > 0 && <span>{counts[v.value] > 99 ? '99+' : counts[v.value]}</span>}
            </button>
          ))}
        </div>
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
          const waiting = thread.last_direction === 'in' && thread.status !== 'closed';
          const owner = ownerOf(thread);
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
                  {owner && <span className="owner-avatar" data-tip={'Responsável: ' + owner} aria-label={'Responsável: ' + owner}>{initials(owner)}</span>}
                  {unread > 0 && <span className="wa-unread" aria-label={`${unread} não lidas`}>{unread}</span>}
                </span>
              </span>
            </button>
          );
        })}
        {!threads.length && <EmptyState icon={<MessageCircle />} title="Nenhuma conversa" description={view === 'mine' ? 'Nenhuma conversa atribuída a você com estes filtros.' : 'Inicie um atendimento ou ajuste os filtros.'} />}
      </div>
      {footer}
    </aside>
  );
}
