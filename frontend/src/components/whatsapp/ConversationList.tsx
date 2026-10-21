import { MessageCircle } from 'lucide-react';
import { DataState, EmptyState, SearchInput } from '@/components/ui';
import { Tabs } from '@/components/blocks';
import { Pager } from '@/components/fit';
import type { Row } from '@/lib/types';
import { CONVERSATIONS_PER_PAGE } from '@/components/whatsapp/hooks';
import { ConversationItem } from '@/components/whatsapp/ConversationItem';

const STATUS_TABS = [
  { value: 'open', label: 'Abertas' },
  { value: 'closed', label: 'Encerradas' },
  { value: '', label: 'Todas' },
];

export function ConversationList({
  items,
  loading,
  error,
  selectedId,
  onSelect,
  search,
  onSearch,
  status,
  onStatus,
  page,
  pages,
  total,
  onPage,
}: {
  items: Row[];
  loading: boolean;
  error?: Error;
  selectedId: string | null;
  onSelect: (conversation: Row) => void;
  search: string;
  onSearch: (value: string) => void;
  status: string;
  onStatus: (value: string) => void;
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const from = (page - 1) * CONVERSATIONS_PER_PAGE + 1;
  return (
    <aside className="wa-list">
      <div className="wa-list-filters">
        <SearchInput value={search} onChange={onSearch} placeholder="Buscar nome ou telefone" />
        <div className="wa-filter-row">
          <Tabs items={STATUS_TABS} value={status} onChange={onStatus} label="Filtrar conversas" />
        </div>
      </div>
      <div className="wa-items">
        <DataState loading={loading} error={error}>
          {items.length ? (
            items.map((row) => (
              <ConversationItem
                key={row.id}
                conversation={row}
                selected={selectedId === row.id}
                onSelect={onSelect}
              />
            ))
          ) : (
            <EmptyState
              icon={<MessageCircle size={24} />}
              title="Nenhuma conversa"
            />
          )}
        </DataState>
      </div>
      {total > 0 && (
        <Pager
          page={page - 1}
          pages={pages}
          onChange={(p) => onPage(p + 1)}
          from={from}
          to={from + items.length - 1}
          total={total}
        />
      )}
    </aside>
  );
}
