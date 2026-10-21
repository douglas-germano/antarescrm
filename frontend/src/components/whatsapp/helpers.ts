import { getZone, today } from '@/lib/format';
import type { Row } from '@/lib/types';

export const contactName = (conversation: Row): string => conversation.contact_name || conversation.phone;

export const clockTime = (value: string) =>
  new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: getZone() }).format(
    new Date(value),
  );

const dayKey = (value: string | Date) =>
  new Intl.DateTimeFormat('en-CA', { timeZone: getZone() }).format(new Date(value));

/** Groups messages by calendar day in the workspace zone. */
export const messageDay = (value: string) => dayKey(value);

export function dayLabel(value: string) {
  const key = dayKey(value);
  if (key === today()) return 'Hoje';
  if (key === dayKey(new Date(Date.now() - 86_400_000))) return 'Ontem';
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    timeZone: getZone(),
  }).format(new Date(value));
}

/** Time for today's items, short date for older ones; used in conversation lists. */
export function listTime(value?: string | null) {
  if (!value) return '';
  if (dayKey(value) === today()) return clockTime(value);
  if (dayKey(value) === dayKey(new Date(Date.now() - 86_400_000))) return 'Ontem';
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', timeZone: getZone() }).format(new Date(value));
}
