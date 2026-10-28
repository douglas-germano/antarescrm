import type { Opportunity } from '@/lib/types';
const DAY = 86400000;
/** Days since the last sign of life on a deal: its latest completed activity or stage move. */
export const staleDays = (row: Opportunity) => {
  const times = [row.last_contact_at, row.stage_changed_at].filter((v): v is string => typeof v === 'string').map((v) => Date.parse(v));
  return times.length ? Math.max(0, Math.floor((Date.now() - Math.max(...times)) / DAY)) : null;
};
export const inStageDays = (row: Opportunity) => (row.stage_changed_at ? Math.max(0, Math.floor((Date.now() - Date.parse(row.stage_changed_at)) / DAY)) : null);
export type SortKey = 'title' | 'stage' | 'amount' | 'close' | 'owner' | 'stale';

