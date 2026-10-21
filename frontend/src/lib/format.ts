import type { Option, Row } from './types';
export const brl = (value: unknown) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value || 0));
let zone = 'America/Sao_Paulo';
/** The workspace time zone, applied once the session loads so dates match what the API calls "today". */
export const setZone = (value?: string) => {
  if (value) zone = value;
};
export const getZone = () => zone;
export const day = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat('pt-BR', { timeZone: zone }).format(
        new Date(value.length === 10 ? value + 'T12:00:00Z' : value),
      )
    : 'Sem prazo';
export const hour = (value: string) =>
  new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: zone }).format(new Date(value));
export const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: zone }).format(new Date());
/** ISO instant → value for <input type="datetime-local"> in the browser's local time. */
export const toLocalInput = (value: string) => {
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
export const initials = (name = '') =>
  name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0])
    .join('')
    .toUpperCase();
export const roles: Record<string, string> = {
  owner: 'Proprietário',
  admin: 'Administrador',
  member: 'Membro',
};
export const statuses: Record<string, string> = {
  todo: 'A fazer',
  doing: 'Em andamento',
  done: 'Concluída',
  cancelled: 'Cancelada',
  open: 'Em aberto',
  won: 'Ganho',
  lost: 'Perdido',
  pending: 'Pendente',
  completed: 'Concluída',
};
export const priorities: Record<string, string> = {
  low: 'Baixa',
  medium: 'Normal',
  high: 'Alta',
  urgent: 'Urgente',
};
export const kinds: Record<string, string> = {
  follow_up: 'Retorno',
  call: 'Ligação',
  meeting: 'Reunião',
  email: 'E-mail',
  note: 'Anotação',
};
export const opts = (map: Record<string, string>): Option[] =>
  Object.entries(map).map(([value, label]) => ({ value, label }));
export const rowOptions = (rows: Row[], key = 'name'): Option[] =>
  rows.map((r) => ({ value: r.id, label: r[key] }));
export const taskStatuses = opts({ todo: 'A fazer', doing: 'Em andamento', done: 'Concluída', cancelled: 'Cancelada' });

const fold = (value: unknown) => String(value ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
/**
 * Page search: every word must appear in some value, ignoring accents and case
 * ("joao silva" finds "João da Silva"), and typed digits match phone numbers in any format.
 */
export function searchMatch(term: string, values: unknown[]) {
  const words = fold(term).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const haystack = values.map(fold);
  const digits = haystack.map((v) => v.replace(/\D/g, ''));
  return words.every((word) => haystack.some((v) => v.includes(word)) || (/^\d{3,}$/.test(word) && digits.some((d) => d.includes(word))));
}
