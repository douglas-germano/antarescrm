/** Same-origin API gateway: keeps JWTs in HttpOnly cookies so the browser never talks to Flask directly. */
export type GatewayEnv = { FLASK_API_URL?: string; COOKIE_SECURE?: string; APP_URL?: string };
const json = (body: unknown, status = 200) =>
  Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
const failure = (message: string, status: number) => json({ error: { message } }, status);
function base(env: GatewayEnv) {
  const value = env.FLASK_API_URL || 'http://127.0.0.1:5001/api/v1';
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
    throw new Error('FLASK_API_URL inválida.');
  return value.replace(/\/$/, '');
}
function sameOrigin(request: Request, env: GatewayEnv) {
  if (['GET', 'HEAD'].includes(request.method)) return true;
  const origin = request.headers.get('origin');
  // A reverse proxy may expose HTTPS while Next receives an internal HTTP URL.
  const expected = env.APP_URL ? new URL(env.APP_URL).origin : new URL(request.url).origin;
  return !origin || origin === expected;
}
/** Hostname the visitor actually used, without port. Behind the tunnel this is the public name, not 127.0.0.1. */
function requestHost(request: Request) {
  const raw = request.headers.get('x-forwarded-host') || request.headers.get('host') || '';
  return raw.split(',')[0].trim().toLowerCase().replace(/:\d+$/, '');
}
export function canonicalHosts(env: GatewayEnv) {
  const hosts = new Set(['localhost', '127.0.0.1', '[::1]']);
  if (env.APP_URL) hosts.add(new URL(env.APP_URL).hostname.toLowerCase());
  return hosts;
}
/** A customer domain, if the page is being served on one. The API trusts this header only because it sits behind this gateway. */
function domainHeader(request: Request, env: GatewayEnv): Record<string, string> {
  const host = requestHost(request);
  return host && !canonicalHosts(env).has(host) ? { 'X-Custom-Domain': host } : {};
}
/** Public pages on a customer domain post from that domain, so accept an Origin that matches the Host actually used. */
function samePublicOrigin(request: Request, env: GatewayEnv) {
  if (sameOrigin(request, env)) return true;
  const origin = request.headers.get('origin');
  try { return !!origin && new URL(origin).hostname.toLowerCase() === requestHost(request) && !canonicalHosts(env).has(requestHost(request)); }
  catch { return false; }
}
function cookies(request: Request) {
  return new Map((request.headers.get('cookie') || '').split(';').map((part) => {
    const i = part.indexOf('=');
    return [part.slice(0, i).trim(), part.slice(i + 1)] as const;
  }));
}
function setCookie(response: Response, name: string, value: string, maxAge: number, env: GatewayEnv) {
  if (!/^[A-Za-z0-9._-]*$/.test(value)) throw new Error('Token de sessão inválido.');
  const secure = env.COOKIE_SECURE !== 'false';
  response.headers.append('Set-Cookie', `${name}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${secure ? '; Secure' : ''}`);
}
function sessionCookies(response: Response, data: { access_token: string; refresh_token?: string }, env: GatewayEnv) {
  setCookie(response, 'crm_access', data.access_token, 1800, env);
  if (data.refresh_token) setCookie(response, 'crm_refresh', data.refresh_token, 604800, env);
}
function clearSession(response: Response, env: GatewayEnv) {
  setCookie(response, 'crm_access', '', 0, env);
  setCookie(response, 'crm_refresh', '', 0, env);
}
export async function handleSession(request: Request, action: string, env: GatewayEnv): Promise<Response> {
  if (request.method !== 'POST') return failure('Método não permitido.', 405);
  if (!sameOrigin(request, env)) return failure('Origem inválida.', 403);
  if (!['login', 'register', 'logout', 'switch'].includes(action)) return failure('Rota não encontrada.', 404);
  if (action === 'switch') return handleBackend(request, ['auth', 'switch'], env, true);
  if (action === 'logout') {
    let revoked = false;
    try {
      const jar = cookies(request);
      let access = jar.get('crm_access');
      const refresh = jar.get('crm_refresh');
      const revoke = (token: string | undefined) => fetch(`${base(env)}/auth/logout`, {
        method: 'POST', headers: { Authorization: `Bearer ${token || ''}` },
        cache: 'no-store', signal: AbortSignal.timeout(15000),
      });
      let result = access ? await revoke(access) : null;
      if ((!result || result.status === 401) && refresh) {
        const renewed = await fetch(`${base(env)}/auth/refresh`, {
          method: 'POST', headers: { Authorization: `Bearer ${refresh}` },
          cache: 'no-store', signal: AbortSignal.timeout(15000),
        });
        if (renewed.ok) {
          access = (await renewed.json() as { access_token: string }).access_token;
          result = await revoke(access);
        }
      }
      revoked = Boolean(result?.ok);
    } catch { /* Local logout must still remove the browser session. */ }
    const response = json({ message: 'Sessão encerrada neste navegador.', remote_revoked: revoked });
    clearSession(response, env);
    return response;
  }
  try {
    const upstream = await fetch(`${base(env)}/auth/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: await request.text(),
      cache: 'no-store', signal: AbortSignal.timeout(15000),
    });
    const data = await upstream.json() as any;
    if (!upstream.ok) return json(data, upstream.status);
    const response = json({ user: data.user, workspace: data.workspace }, upstream.status);
    sessionCookies(response, data, env);
    return response;
  } catch {
    return failure('O servidor está indisponível. Verifique a configuração do backend.', 502);
  }
}
export async function handleBackend(request: Request, path: string[], env: GatewayEnv, sessionSwitch = false): Promise<Response> {
  if (!['GET', 'HEAD', 'POST', 'PATCH', 'DELETE'].includes(request.method)) return failure('Método não permitido.', 405);
  if (!sameOrigin(request, env)) return failure('Origem inválida.', 403);
  if (!path.length || path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part))) return failure('Caminho inválido.', 400);
  if (path[0] === 'auth' && (path.length !== 2 || !['me', 'workspaces', ...(sessionSwitch ? ['switch'] : [])].includes(path[1]))) return failure('Rota inválida.', 404);
  const jar = cookies(request);
  let access = jar.get('crm_access');
  const refresh = jar.get('crm_refresh');
  if (!access && !refresh) return failure('Autenticação necessária.', 401);
  try {
    const body = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer();
    const call = (token: string | undefined) => fetch(`${base(env)}/${path.join('/')}${new URL(request.url).search}`, {
      method: request.method,
      headers: {
        'Content-Type': request.headers.get('content-type') || 'application/json',
        Authorization: `Bearer ${token || ''}`,
        ...(request.headers.get('x-workspace-id') ? { 'X-Workspace-ID': request.headers.get('x-workspace-id')! } : {}),
        ...(request.headers.get('range') ? { Range: request.headers.get('range')! } : {}),
      },
      body, cache: 'no-store',
      signal: AbortSignal.timeout(['whatsapp', 'instagram'].includes(path[0]) || path[0] === 'inbox' ? 60000 : 20000),
    });
    let upstream = await call(access);
    let renewed: any = null;
    if (upstream.status === 401 && refresh) {
      const response = await fetch(`${base(env)}/auth/refresh`, {
        method: 'POST', headers: { Authorization: `Bearer ${refresh}` },
        cache: 'no-store', signal: AbortSignal.timeout(15000),
      });
      if (response.ok) {
        renewed = await response.json();
        access = renewed.access_token;
        upstream = await call(access);
      } else if (![401, 403].includes(response.status)) {
        return failure('Não foi possível renovar a sessão agora. Tente novamente.', response.status === 429 ? 429 : 503);
      }
    }
    if (sessionSwitch && upstream.ok) {
      const data = await upstream.json();
      const response = json({ user: data.user, workspace: data.workspace });
      sessionCookies(response, data, env);
      return response;
    }
    const headers = new Headers({ 'Cache-Control': 'no-store' });
    for (const name of ['content-type', 'content-disposition', 'content-range', 'accept-ranges']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    const response = new Response(request.method === 'HEAD' || [204, 205, 304].includes(upstream.status) ? null : upstream.body,
      { status: upstream.status, headers });
    if (renewed) sessionCookies(response, renewed, env);
    if (upstream.status === 401) clearSession(response, env);
    return response;
  } catch {
    return failure('Não foi possível conectar ao servidor. Tente novamente.', 502);
  }
}


/** Public capture proxy: exact routes only, never forwards cookies or JWTs. */
export async function handlePublicForm(request: Request, formId: string, submit: boolean, env: GatewayEnv): Promise<Response> {
  if (!/^[0-9a-f-]{36}$/i.test(formId)) return failure('Formulário indisponível.', 404);
  if (request.method !== (submit ? 'POST' : 'GET')) return failure('Método não permitido.', 405);
  if (!samePublicOrigin(request, env)) return failure('Origem inválida.', 403);
  try {
    const body = submit ? await request.text() : undefined;
    if (body && new TextEncoder().encode(body).length > 8192) return failure('Solicitação muito grande.', 413);
    const upstream = await fetch(`${base(env)}/public/forms/${formId}${submit ? '/submit' : ''}`, {
      method: request.method, headers: { 'Content-Type': 'application/json', ...domainHeader(request, env) }, body,
      cache: 'no-store', signal: AbortSignal.timeout(20000),
    });
    const data = await upstream.json();
    return json(data, upstream.status);
  } catch { return failure('Não foi possível enviar sua solicitação. Tente novamente.', 502); }
}

/** Public booking proxy: route allowlist; never forwards session credentials. */
export async function handlePublicBooking(request: Request, path: string[], env: GatewayEnv): Promise<Response> {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const calendar = path[0] === 'calendars' && uuid.test(path[1] || '') &&
    ((path.length === 2 && request.method === 'GET') || (path.length === 3 && ((path[2] === 'slots' && request.method === 'GET') || (path[2] === 'book' && request.method === 'POST'))));
  const booking = path[0] === 'bookings' && /^[A-Za-z0-9_.-]{20,700}$/.test(path[1] || '') &&
    ((path.length === 2 && request.method === 'GET') || (path.length === 3 && ['cancel','reschedule'].includes(path[2]) && request.method === 'POST'));
  if (!calendar && !booking) return failure('Rota indisponível.', 404);
  if (!samePublicOrigin(request, env)) return failure('Origem inválida.', 403);
  try {
    const body = request.method === 'POST' ? await request.text() : undefined;
    if (body && new TextEncoder().encode(body).length > 8192) return failure('Solicitação muito grande.', 413);
    const response = await fetch(`${base(env)}/public/${path.join('/')}${new URL(request.url).search}`, {
      method: request.method, headers: { 'Content-Type': 'application/json', ...domainHeader(request, env) }, body,
      cache: 'no-store', signal: AbortSignal.timeout(20000),
    });
    return json(await response.json(), response.status);
  } catch { return failure('Não foi possível acessar a agenda. Tente novamente.', 502); }
}

/** Public funnel pages: page JSON and view tracking only; never forwards session credentials. */
export async function handlePublicFunnel(request: Request, path: string[], env: GatewayEnv): Promise<Response> {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const slug = /^[a-z0-9]+(-[a-z0-9]+)*$/;
  const page = uuid.test(path[0] || '') && request.method === 'GET' && (path.length === 1 || (path.length === 2 && slug.test(path[1]) && path[1].length <= 60));
  const view = uuid.test(path[0] || '') && request.method === 'POST' && path.length === 4 && path[1] === 'steps' && uuid.test(path[2]) && path[3] === 'view';
  if (!page && !view) return failure('Rota indisponível.', 404);
  if (!samePublicOrigin(request, env)) return failure('Origem inválida.', 403);
  try {
    const body = view ? await request.text() : undefined;
    if (body && new TextEncoder().encode(body).length > 1024) return failure('Solicitação muito grande.', 413);
    const upstream = await fetch(`${base(env)}/public/funnels/${path.join('/')}`, {
      method: request.method, headers: { 'Content-Type': 'application/json', ...domainHeader(request, env) }, body, cache: 'no-store', signal: AbortSignal.timeout(20000),
    });
    if (upstream.status === 204) return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
    return json(await upstream.json(), upstream.status);
  } catch { return failure('Não foi possível carregar a página. Tente novamente.', 502); }
}

/** Client approval links: exact routes, no credentials forwarded. The file route streams the layout back to the browser. */
export async function handlePublicApproval(request: Request, path: string[], env: GatewayEnv): Promise<Response> {
  const token = /^[A-Za-z0-9_-]{30,100}$/.test(path[1] || '');
  const ok = path[0] === 'approvals' && token && ((path.length === 2 && request.method === 'GET') ||
    (path.length === 3 && ((path[2] === 'file' && request.method === 'GET') || (path[2] === 'decide' && request.method === 'POST'))));
  if (!ok) return failure('Rota indisponível.', 404);
  if (!samePublicOrigin(request, env)) return failure('Origem inválida.', 403);
  try {
    const body = request.method === 'POST' ? await request.text() : undefined;
    if (body && new TextEncoder().encode(body).length > 8192) return failure('Solicitação muito grande.', 413);
    const ip = request.headers.get('cf-connecting-ip') || (request.headers.get('x-forwarded-for') || '').split(',')[0].trim();
    const upstream = await fetch(`${base(env)}/public/${path.join('/')}${new URL(request.url).search}`, {
      method: request.method, headers: { 'Content-Type': 'application/json', ...domainHeader(request, env), ...(ip ? { 'X-Client-IP': ip } : {}) },
      body, cache: 'no-store', signal: AbortSignal.timeout(30000),
    });
    const headers = new Headers({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer' });
    for (const name of ['content-type', 'content-disposition', 'content-security-policy']) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch { return failure('Não foi possível acessar a aprovação. Tente novamente.', 502); }
}

/** Evolution callbacks authenticate in Flask with the per-instance secret, without a user session. */
export async function handleEvolutionWebhook(request: Request, env: GatewayEnv): Promise<Response> {
  if (request.method !== 'POST') return failure('Método não permitido.', 405);
  const secret = request.headers.get('x-webhook-secret');
  const signature = request.headers.get('x-webhook-signature');
  if (!secret && !signature) return failure('Autenticação de webhook inválida.', 401);
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json'))
    return failure('Payload inválido.', 415);
  const maxBytes = 15 * 1024 * 1024;
  if (Number(request.headers.get('content-length')) > maxBytes) return failure('Payload muito grande.', 413);
  const chunks: Uint8Array[] = [];
  let size = 0;
  const reader = request.body?.getReader();
  try {
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > maxBytes) { await reader.cancel(); return failure('Payload muito grande.', 413); }
        chunks.push(value);
      }
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (secret) headers['X-Webhook-Secret'] = secret;
    if (signature) headers['X-Webhook-Signature'] = signature;
    const response = await fetch(base(env) + '/whatsapp/webhook', {
      method: 'POST', headers, body, cache: 'no-store', signal: AbortSignal.timeout(30000),
    });
    return new Response(await response.arrayBuffer(), {
      status: response.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  } catch { return failure('Não foi possível receber a atualização do WhatsApp.', 502); }
  finally { reader?.releaseLock(); }
}
