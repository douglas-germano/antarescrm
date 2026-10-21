'use client';
import { useData } from './api';
import type { Row } from './types';

/** Origin to show in shareable links: the account's first active custom domain, else the address in use now. */
export function usePublicOrigin(): string {
  const domains = useData<{ items: Row[] }>('/domains?per_page=100');
  const active = domains.data?.items.find((d) => d.status === 'active');
  if (active) return active.url;
  return typeof window === 'undefined' ? '' : window.location.origin;
}
