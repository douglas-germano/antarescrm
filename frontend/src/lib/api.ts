'use client';
import useSWR, { preload } from 'swr';
import { fetchWithRetry } from './retry.ts';
import { useState, useEffect } from 'react';
import { collectPages, pagePath } from './pagination.ts';
import type { Page, Row } from './types';

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
export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
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
      buttons: 'Botões',
      quick_replies: 'Respostas rápidas',
      offset: 'Posição do card',
    };
    // Nested errors (e.g. one field of an automation step) arrive as objects; list each leaf with its field name.
    const leaves: string[] = [];
    const walk = (value: unknown, keys: string[]) => {
      if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
        const field = [...keys].reverse().find((k) => !/^\d+$/.test(k)) || '';
        const text = value.map((item) => (item === 'Unknown field.' ? 'campo não reconhecido pelo servidor' : item)).join(' ');
        leaves.push(`${labels[field] || field}: ${text}`);
      } else if (value && typeof value === 'object') {
        Object.entries(value).forEach(([k, v]) => walk(v, [...keys, k]));
      } else if (value) {
        leaves.push(`${labels[keys[keys.length - 1]] || keys[keys.length - 1]}: ${value}`);
      }
    };
    if (detail && typeof detail === 'object') walk(detail, []);
    const messages = leaves.join(' · ');
    throw new RequestError(
      messages || body?.error?.message || 'Não foi possível conectar ao sistema. Tente novamente.',
      response.status,
    );
  }
  return body;
}
export const post = <T = unknown>(path: string, data: unknown) =>
  api<T>(path, { method: 'POST', body: JSON.stringify(data) });
export const patch = <T = unknown>(path: string, data: unknown) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(data) });
export const put = <T = unknown>(path: string, data: unknown) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(data) });
export const remove = (path: string) => api(path, { method: 'DELETE' });
/** Multipart upload: the browser sets the boundary, so no JSON content type is sent. */
export async function upload<T = unknown>(path: string, body: FormData): Promise<T> {
  const response = await fetch('/api/backend' + path, {
    method: 'POST', body, cache: 'no-store',
    headers: activeWorkspaceId ? { 'X-Workspace-ID': activeWorkspaceId } : {},
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new RequestError(data?.error?.message || 'Não foi possível enviar o arquivo.', response.status);
  return data as T;
}
export function useData<T = unknown>(path: string | null) {
  return useSWR<T>(path, (url: string) => api<T>(url), {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
}
export async function listAll<T = Row>(path: string): Promise<T[]> {
  return collectPages<T>(path, (url) => api<Page<T>>(url));
}
/** Warm the same cache keys used by the screens before the router commits a navigation. */
export async function prepareData({ data = [], lists = [] }: { data?: string[]; lists?: string[] }) {
  await Promise.all([
    ...data.map(path => preload(path, () => api(path))),
    ...lists.map(path => preload(['list', activeWorkspaceId, path], () => listAll(path))),
  ]);
}
/** Complete lists for options/small resources. Main tables should use usePage. */
export function useList<T = Row>(path: string | null) {
  return useSWR<T[]>(path ? ['list', activeWorkspaceId, path] : null, () => listAll<T>(path!), {
    revalidateOnFocus: false, shouldRetryOnError: false,
  });
}
export function usePage<T, Result extends Page<T> = Page<T>>(path: string, size = 25) {
  const [position, setPosition] = useState({ path, page: 1 });
  const page = position.path === path ? position.page : 1;
  const response = useData<Result>(pagePath(path, page, size));
  useEffect(() => {
    if (response.data && page > Math.max(1, response.data.pages)) {
      setPosition({ path, page: Math.max(1, response.data.pages) });
    }
  }, [path, page, response.data]);
  return { ...response, page, size, setPage: (next: number) => setPosition({ path, page: next }) };
}
export async function refreshAll() {
  const { mutate } = await import('swr');
  await mutate(() => true);
}
