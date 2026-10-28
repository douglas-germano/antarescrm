import type { Page } from './types.ts';

/** Replace pagination parameters, rather than appending duplicate page/per_page keys. */
export function pagePath(path: string, page: number, size: number): string {
  const url = new URL(path, 'http://internal');
  url.searchParams.set('page', String(page));
  url.searchParams.set('per_page', String(size));
  return url.pathname + url.search;
}

/** For small complete option lists only. Bound fan-out even when the account has many pages. */
export async function collectPages<T>(path: string, read: (path: string) => Promise<Page<T>>, concurrency = 3): Promise<T[]> {
  const first = await read(pagePath(path, 1, 100));
  const pages: T[][] = [first.items];
  let next = 2;
  await Promise.all(Array.from({ length: Math.min(concurrency, Math.max(0, first.pages - 1)) }, async () => {
    while (next <= first.pages) {
      const number = next++;
      pages[number - 1] = (await read(pagePath(path, number, 100))).items;
    }
  }));
  return pages.flat();
}
