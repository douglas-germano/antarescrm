import { useMemo } from 'react';
import { useRouter, useRouterState } from '@tanstack/react-router';

/** Navigation for URLs composed from records or supplied by notification payloads. */
export function useAppRouter() {
  const router = useRouter();
  return useMemo(() => ({
    push: (href: string) => router.navigate({ href }),
    replace: (href: string) => router.navigate({ href, replace: true }),
  }), [router]);
}

export function usePathname() {
  return useRouterState({ select: state => state.location.pathname });
}

export function useSearchParams() {
  const search = useRouterState({ select: state => state.location.searchStr });
  return useMemo(() => new URLSearchParams(search), [search]);
}
