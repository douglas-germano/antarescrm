import { NextResponse, type NextRequest } from 'next/server';
import { canonicalHosts } from '@/lib/bff';

/**
 * Customer domains reach this same server. Only the public pages may be served there: the CRM, the login and the
 * authenticated gateway stay on the platform's own hostname. The root path shows the funnel chosen for the domain.
 */
const PUBLIC_PATHS = /^\/(p|f|agendar|agendamento|aprovacao)(\/|$)|^\/api\/public\/|^\/_next\/|^\/(favicon\.ico|icon\.svg|mark\.svg)$/;
const HIT_TTL = 60_000;
const MISS_TTL = 10_000;
type Resolved = { funnel_id: string | null } | null;
const cache = new Map<string, { at: number; value: Resolved }>();

const text = (message: string, status: number) =>
  new NextResponse(message, { status, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' } });

async function resolveHost(host: string): Promise<Resolved> {
  const hit = cache.get(host);
  if (hit && Date.now() - hit.at < (hit.value ? HIT_TTL : MISS_TTL)) return hit.value;
  const api = (process.env.FLASK_API_URL || 'http://127.0.0.1:5001/api/v1').replace(/\/$/, '');
  const response = await fetch(`${api}/public/domains/resolve?host=${encodeURIComponent(host)}`, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
  if (response.status !== 404 && !response.ok) throw new Error('resolver');
  const value: Resolved = response.ok ? await response.json() : null;
  if (cache.size > 500) cache.clear();
  cache.set(host, { at: Date.now(), value });
  return value;
}

export async function middleware(request: NextRequest) {
  const host = (request.headers.get('x-forwarded-host') || request.headers.get('host') || '').split(',')[0].trim().toLowerCase().replace(/:\d+$/, '');
  if (!host || canonicalHosts({ APP_URL: process.env.APP_URL }).has(host)) return NextResponse.next();
  const path = request.nextUrl.pathname;
  if (path !== '/' && !PUBLIC_PATHS.test(path)) return text('Página não encontrada.', 404);
  let resolved: Resolved;
  try { resolved = await resolveHost(host); } catch { return text('Serviço indisponível. Tente novamente.', 503); }
  if (!resolved) return text('Domínio não configurado.', 404);
  if (path === '/') {
    if (!resolved.funnel_id) return text('Nenhuma página foi definida para este domínio.', 404);
    return NextResponse.rewrite(new URL('/p/' + resolved.funnel_id, request.url));
  }
  return NextResponse.next();
}

export const config = { runtime: 'nodejs', matcher: ['/((?!_next/static|_next/image).*)'] };
