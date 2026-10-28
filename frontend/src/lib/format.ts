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
/** First letter of the first two words that have letters: "Bianca - Rio Turbo" → "BR", "Agro 2 Irmãos" → "AI". */
export const initials = (name = '') =>
  name
    .split(/\s+/)
    .map((word) => word.match(/\p{L}/u)?.[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
/** CNPJ as 12.345.678/0001-90; anything that is not 14 digits is returned unchanged. */
export const formatCnpj = (value?: string | null) => {
  const digits = (value || '').replace(/\D/g, '');
  return digits.length === 14 ? digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : value || '';
};
/** Imported contacts often carry the phone number as their name; those have no letters at all. */
export const hasRealName = (name = '') => /\p{L}/u.test(name);
/** Brazilian numbers as +55 11 97074-7755; anything else is returned unchanged. */
export const formatPhone = (value?: string | null) => {
  if (!value) return '';
  const digits = value.replace(/\D/g, '');
  const match = digits.match(/^55(\d{2})(\d{4,5})(\d{4})$/);
  return match ? `+55 ${match[1]} ${match[2]}-${match[3]}` : value;
};
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
