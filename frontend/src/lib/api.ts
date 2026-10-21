'use client';
import useSWR from 'swr';
import { fetchWithRetry } from './retry.ts';
import type { Row } from './types';

let activeWorkspaceId: string | undefined;
export function setActiveWorkspace(id?: string) { activeWorkspaceId = id; }

export class RequestError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetchWithRetry('/api/backend' + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(activeWorkspaceId ? { 'X-Workspace-ID': activeWorkspaceId } : {}), ...init.headers },
    cache: 'no-store',
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (body?.error?.code === 'account_changed' && typeof window !== 'undefined') window.location.reload();
    if (response.status === 401 && typeof window !== 'undefined') {
      window.location.assign('/login');
    }
    const detail = body?.error?.details;
    const labels: Record<string, string> = {
      name: 'Nome',
      email: 'E-mail',
      phone: 'Telefone',
      amount: 'Valor',
      due_date: 'Prazo',
      scheduled_at: 'Data e hora',
      password: 'Senha',
      slug: 'Identificador',
      url: 'Link',
      title: 'Título',
    };
    const messages =
      detail && typeof detail === 'object'
        ? Object.entries(detail)
            .map(([k, v]) => `${labels[k] || k}: ${Array.isArray(v) ? v.join(' ') : v}`)
            .join(' · ')
        : '';
    throw new RequestError(
      messages || body?.error?.message || 'Não foi possível conectar ao sistema. Tente novamente.',
      response.status,
    );
  }
  return body;
}
export const post = <T = any>(path: string, data: unknown) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(data) });
export const patch = <T = any>(path: string, data: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(data) });
export const remove = (path: string) => api(path, { method: 'DELETE' });
export function useData<T = any>(path: string | null) {
  return useSWR<T>(path, (url: string) => api<T>(url), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
}
export async function listAll(path: string): Promise<Row[]> {
  const separator = path.includes('?') ? '&' : '?';
  const first = await api(path + separator + 'per_page=100&page=1');
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, (first.pages || 1) - 1) }, (_, i) =>
      api(path + separator + 'per_page=100&page=' + (i + 2)),
    ),
  );
  return [...first.items, ...rest.flatMap((p) => p.items)];
}
export function useList(path: string | null) {
  return useSWR<Row[]>(path ? ['list', path] : null, () => listAll(path!), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
}
export async function refreshAll() {
  const { mutate } = await import('swr');
  await mutate(() => true);
}
