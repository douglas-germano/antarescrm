import { createIsomorphicFn } from '@tanstack/react-start';
import { getRequest } from '@tanstack/react-start/server';
import { readEntrySession } from './entry-session.server';

/** Returns route-access hints only. Flask and the gateway still authorize every private API request. */
export const getEntrySession = createIsomorphicFn()
  .server(() => readEntrySession(getRequest()))
  .client(async (): Promise<{ hasSession: boolean; publicFunnel: string | null }> => {
    // This endpoint also works when returning to a customer-domain homepage via browser history.
    const response = await fetch('/api/public/entry', { cache: 'no-store' });
    if (!response.ok) throw new Error('Não foi possível verificar o acesso à página.');
    return response.json();
  });
