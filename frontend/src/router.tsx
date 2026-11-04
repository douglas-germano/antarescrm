import { createRouter } from '@tanstack/react-router';
import { routeTree } from './routeTree.gen';
import { parseSearch, stringifySearch } from './lib/search';

export function getRouter() {
  return createRouter({
    routeTree,
    scrollRestoration: true,
    parseSearch,
    stringifySearch,
    defaultPreload: 'intent',
    defaultPreloadDelay: 80,
    defaultPreloadStaleTime: 30_000,
    // Keep the current screen mounted during normal route preparation instead of flashing a blank fallback.
    defaultPendingMs: 10_000,
    defaultPendingMinMs: 0,
    defaultNotFoundComponent: () => <main className="fp-status"><h1>Página não encontrada</h1><a href="/">Voltar ao início</a></main>,
  });
}

declare module '@tanstack/react-router' {
  interface Register { router: ReturnType<typeof getRouter> }
}
