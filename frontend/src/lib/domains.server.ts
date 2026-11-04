import { canonicalHosts } from './bff';

const PUBLIC_PATHS = /^\/(p|f|agendar|agendamento|aprovacao)(\/|$)|^\/api\/public\/|^\/assets\/|^\/(favicon\.ico|icon\.svg|mark\.svg)$/;
const cache = new Map<string, { at: number; value: { funnel_id: string | null } | null }>();

export function customHost(request: Request) {
  const host = (request.headers.get('x-forwarded-host') || request.headers.get('host') || '').split(',')[0].trim().toLowerCase().replace(/:\d+$/, '');
  return host && !canonicalHosts({ APP_URL: process.env.APP_URL }).has(host) ? host : null;
}

export async function resolveHost(host: string) {
  const hit = cache.get(host);
  if (hit && Date.now() - hit.at < (hit.value ? 60_000 : 10_000)) return hit.value;
  const api = (process.env.FLASK_API_URL || 'http://127.0.0.1:5003/api/v1').replace(/\/$/, '');
  const response = await fetch(`${api}/public/domains/resolve?host=${encodeURIComponent(host)}`, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
  if (response.status !== 404 && !response.ok) throw new Error('resolver');
  const value: { funnel_id: string | null } | null = response.ok ? await response.json() : null;
  if (cache.size > 500) cache.clear();
  cache.set(host, { at: Date.now(), value });
  return value;
}

const text = (message: string, status: number) => new Response(message, {
  status, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' },
});

/** Customer domains expose public content only, including when accessed with platform cookies. */
export async function guardDomain(request: Request): Promise<Response | undefined> {
  const host = customHost(request);
  if (!host) return;
  const path = new URL(request.url).pathname;
  if (path !== '/' && !PUBLIC_PATHS.test(path)) return text('Página não encontrada.', 404);
  let resolved;
  try { resolved = await resolveHost(host); }
  catch { return text('Serviço indisponível. Tente novamente.', 503); }
  if (!resolved) return text('Domínio não configurado.', 404);
  if (path === '/' && !resolved.funnel_id) return text('Nenhuma página foi definida para este domínio.', 404);
}
