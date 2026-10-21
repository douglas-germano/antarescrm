'use client';
import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { api } from '@/lib/api';
import type { Row, Page } from '@/lib/types';

export const CONVERSATIONS_PER_PAGE = 30;
const MESSAGES_PER_PAGE = 50;

export function useConnection(allowed: boolean, watching: boolean) {
  const base = useSWR<Row>(allowed ? '/whatsapp/connection' : null, api, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  const live = useSWR<Row>(
    watching && base.data?.configured ? '/whatsapp/connection?refresh=true' : null,
    api,
    { refreshInterval: 5000, revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const refresh = async () => {
    await base.mutate();
    await live.mutate();
  };
  return {
    current: live.data || base.data,
    loading: base.isLoading,
    error: base.error,
    refresh,
  };
}

export function useConversations(allowed: boolean) {
  const [search, setSearch] = useState('');
  const [querySearch, setQuerySearch] = useState('');
  const [status, setStatusValue] = useState('open');
  const [page, setPage] = useState(1);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuerySearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  const path = allowed
    ? `/whatsapp/conversations?per_page=${CONVERSATIONS_PER_PAGE}&page=${page}&search=${encodeURIComponent(querySearch)}${status ? '&status=' + status : ''}`
    : null;
  const swr = useSWR<Page>(path, api, {
    refreshInterval: 5000,
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  return {
    items: swr.data?.items || [],
    pages: swr.data?.pages || 1,
    total: swr.data?.total || 0,
    loading: swr.isLoading,
    error: swr.error,
    mutate: swr.mutate,
    search,
    setSearch,
    status,
    setStatus: (value: string) => {
      setStatusValue(value);
      setPage(1);
    },
    page,
    setPage,
  };
}

/** Newest page polled every 3s, plus older pages loaded on demand and merged by id. */
export function useMessages(conversationId: string) {
  const [older, setOlder] = useState<Row[]>([]);
  const swr = useSWR<Page>(
    `/whatsapp/conversations/${conversationId}/messages?per_page=${MESSAGES_PER_PAGE}&page=1`,
    api,
    { refreshInterval: 3000, revalidateOnFocus: false, shouldRetryOnError: false },
  );
  const combined: Row[] = [...(swr.data?.items || []), ...older];
  const messages: Row[] = [...new Map<string, Row>(combined.map((r) => [r.id, r])).values()].sort((a, b) =>
    a.occurred_at.localeCompare(b.occurred_at),
  );
  async function loadOlder() {
    const next = await api(
      `/whatsapp/conversations/${conversationId}/messages?per_page=${MESSAGES_PER_PAGE}&page=${older.length / MESSAGES_PER_PAGE + 2}`,
    );
    setOlder((rows) => [...rows, ...next.items]);
  }
  return {
    messages,
    latestId: swr.data?.items?.[0]?.id as string | undefined,
    hasOlder: combined.length < (swr.data?.total || 0),
    loading: swr.isLoading,
    error: swr.error,
    mutate: swr.mutate,
    loadOlder,
    clearOlder: () => setOlder([]),
  };
}
