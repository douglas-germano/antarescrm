import { Instagram, Mail, MessageCircle, Search, Smartphone, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { EmptyState } from '@/components/ui';
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

const statusTabs = [
  { value: 'open', label: 'Abertas' },
  { value: 'closed', label: 'Encerradas' },
  { value: 'all', label: 'Todas' },
];

/** The unified conversation list: search, status and channel filters, then one row per thread. */
export function ThreadList({
  threads,
  nameOf,
  selected,
  onSelect,
  search,
  onSearch,
  status,
  onStatus,
  channel,
  onChannel,
  footer,
}: {
  threads: Row[];
  nameOf: (thread: Row) => string;
  selected: Row | null;
  onSelect: (thread: Row) => void;
  search: string;
  onSearch: (value: string) => void;
  status: string;
  onStatus: (value: string) => void;
  channel: string;
  onChannel: (value: string) => void;
  footer?: ReactNode;
}) {
  return (
    <aside className="wa-list">
      <div className="wa-list-head">
        <div className="search">
          <Search size={16} />
          <input aria-label="Buscar conversa" placeholder="Buscar conversa…" value={search} onChange={(e) => onSearch(e.target.value)} />
          {search && <button type="button" aria-label="Limpar busca" onClick={() => onSearch('')}><X size={14} /></button>}
        </div>
        <div className="wa-list-filters-row">
          <div className="wa-chips" role="tablist" aria-label="Situação">
            {statusTabs.map((tab) => (
              <button key={tab.value} type="button" role="tab" aria-selected={status === tab.value} className={'wa-chip-btn' + (status === tab.value ? ' active' : '')} onClick={() => onStatus(tab.value)}>
                {tab.label}
              </button>
            ))}
          </div>
          <select aria-label="Canal" value={channel} onChange={(e) => onChannel(e.target.value)}>
            <option value="all">Todos canais</option>
            {Object.entries(channelName).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
      </div>
      <div className="wa-items">
        {threads.map((thread) => {
          const name = nameOf(thread);
          const active = selected?.id === thread.id && selected?.source === thread.source;
          const unread = Number(thread.unread_count || 0);
          return (
            <button type="button" key={thread.source + thread.id} className={'wa-item' + (active ? ' selected' : '') + (unread ? ' unread' : '')} aria-current={active || undefined} onClick={() => onSelect(thread)}>
              <ThreadAvatar name={name} channel={thread.channel} />
              <span className="wa-item-body">
                <span className="wa-item-top">
                  <strong>{name}</strong>
                  <time>{listTime(thread.last_message_at || thread.updated_at)}</time>
                </span>
                <span className="wa-item-bottom">
                  <span className="wa-item-preview">{thread.preview || 'Conversa iniciada'}</span>
                  {unread > 0 && <span className="wa-unread" aria-label={`${unread} não lidas`}>{unread}</span>}
                </span>
              </span>
            </button>
          );
        })}
        {!threads.length && <EmptyState icon={<MessageCircle />} title="Nenhuma conversa" description="Inicie um atendimento ou ajuste os filtros." />}
      </div>
      {footer}
    </aside>
  );
}
