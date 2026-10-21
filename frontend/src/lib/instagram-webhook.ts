import { timingSafeEqual } from 'node:crypto';
import { handleBackend, type GatewayEnv } from './bff.ts';

/** Meta's subscription handshake. Event delivery is enabled separately. */
export function verifyInstagramWebhook(request: Request, expectedToken?: string): Response {
  const respond = (body: string, status: number) => new Response(body, {
    status, headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' },
  });
  if (!expectedToken) { console.warn('instagram webhook verify: token not configured'); return respond('Instagram webhook not configured.', 503); }
  const query = new URL(request.url).searchParams;
  const token = query.get('hub.verify_token') || '';
  const expected = Buffer.from(expectedToken);
  const provided = Buffer.from(token);
  if (provided.length !== expected.length || !timingSafeEqual(provided, expected))
    { console.warn('instagram webhook verify: wrong token'); return respond('Verification denied.', 403); }
  const challenge = query.get('hub.challenge');
  if (query.get('hub.mode') !== 'subscribe' || !challenge || challenge.length > 1024)
    return respond('Invalid verification request.', 400);
  console.warn('instagram webhook verify: handshake ok');
  return respond(challenge, 200);
}

/** Preserve signed bytes; the backend validates Meta's HMAC before parsing/persisting. */
export async function receiveInstagramWebhook(request: Request, env: GatewayEnv): Promise<Response> {
  const fail = (status: number) => (console.warn('instagram webhook gateway: rejected with', status), Response.json({ error: { message: 'Não foi possível receber o evento do Instagram.' } }, { status }));
  const signature = request.headers.get('x-hub-signature-256') || '';
  if (!/^sha256=[a-f0-9]{64}$/.test(signature)) return fail(401);
  if (!request.headers.get('content-type')?.startsWith('application/json')) return fail(415);
  const max = 2 * 1024 * 1024;
  if (Number(request.headers.get('content-length')) > max) return fail(413);
  const reader = request.body?.getReader();
  try {
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > max) { await reader.cancel(); return fail(413); }
      chunks.push(value);
    }
    const url = new URL(env.FLASK_API_URL || 'http://127.0.0.1:5001/api/v1');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return fail(503);
    const body = new Uint8Array(size);
    let offset = 0;
    for (const part of chunks) { body.set(part, offset); offset += part.byteLength; }
    const upstream = await fetch(url.toString().replace(/\/$/, '') + '/instagram/webhook', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': signature },
      body, cache: 'no-store', signal: AbortSignal.timeout(30000),
    });
    return new Response(await upstream.arrayBuffer(), { status: upstream.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
  } catch { return fail(503); }
  finally { reader?.releaseLock(); }
}

export async function finishInstagramLogin(request: Request, env: GatewayEnv): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get('code'), state = url.searchParams.get('state');
  const destination = new URL('/configuracoes?tab=conexoes', env.APP_URL || url.origin);
  let result: Response | undefined;
  if (code && state && !url.searchParams.has('error')) {
    const headers = new Headers({ 'Content-Type': 'application/json', cookie: request.headers.get('cookie') || '' });
    result = await handleBackend(new Request(new URL('/api/backend/instagram/complete', request.url), { method: 'POST', headers, body: JSON.stringify({ code, state }) }),
      ['instagram', 'complete'], env);
  }
  destination.searchParams.set('instagram', result?.ok ? 'connected' : 'error');
  const response = new Response(null, { status: 303, headers: { Location: destination.toString(), 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' } });
  for (const value of result?.headers.getSetCookie() || []) response.headers.append('Set-Cookie', value);
  return response;
}
