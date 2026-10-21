import test from 'node:test';
import assert from 'node:assert/strict';
import { handleBackend, handleSession, handlePublicForm } from '../src/lib/bff.ts';

const env = { FLASK_API_URL: 'http://backend.test/api/v1', APP_URL: 'http://crm.test', COOKIE_SECURE: 'false' };
const request = (path, body, extra = {}) => new Request('http://crm.test' + path, {
  method: body ? 'POST' : 'GET', headers: { cookie: 'crm_access=old-access; crm_refresh=old-refresh', origin: 'http://crm.test', 'Content-Type': 'application/json', ...extra },
  ...(body ? { body: JSON.stringify(body) } : {}),
});
async function mockFetch(fn, run) {
  const saved = globalThis.fetch; globalThis.fetch = fn;
  try { await run(); } finally { globalThis.fetch = saved; }
}

test('account switch keeps tokens in HttpOnly cookies and forwards expected account', async () => {
  await mockFetch(async (url, init) => {
    assert.equal(url, 'http://backend.test/api/v1/auth/switch');
    assert.equal(init.headers.Authorization, 'Bearer old-access');
    assert.equal(init.headers['X-Workspace-ID'], 'agency');
    return Response.json({ user: { name: 'Staff' }, workspace: { id: 'client' }, access_token: 'new-access', refresh_token: 'new-refresh' });
  }, async () => {
    const response = await handleSession(request('/api/session/switch', { workspace_id: 'client' }, { 'X-Workspace-ID': 'agency' }), 'switch', env);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.workspace.id, 'client');
    assert.ok(!('access_token' in body) && !('refresh_token' in body));
    const cookies = response.headers.getSetCookie();
    assert.equal(cookies.length, 2);
    assert.ok(cookies.every(c => c.includes('HttpOnly') && c.includes('SameSite=Lax')));
  });
});

test('switch refreshes expired session then rotates both account tokens', async () => {
  const calls = [];
  await mockFetch(async (url, init) => {
    calls.push([url, init.headers.Authorization]);
    if (url.endsWith('/auth/refresh')) return Response.json({ access_token: 'renewed-access' });
    if (init.headers.Authorization === 'Bearer old-access') return Response.json({ error: { message: 'Expired' } }, { status: 401 });
    return Response.json({ workspace: { id: 'client' }, access_token: 'client-access', refresh_token: 'client-refresh' });
  }, async () => {
    const response = await handleSession(request('/api/session/switch', { workspace_id: 'client' }), 'switch', env);
    assert.equal(response.status, 200);
    assert.equal(calls.length, 3);
    assert.ok(response.headers.get('set-cookie').includes('client-refresh'));
  });
});

test('cross-origin switch rejected before any upstream call', async () => {
  await mockFetch(() => { throw new Error('must not call'); }, async () => {
    const r = await handleSession(request('/api/session/switch', { workspace_id: 'client' }, { origin: 'https://other.test' }), 'switch', env);
    assert.equal(r.status, 403);
  });
});

test('anonymous session cannot switch', async () => {
  await mockFetch(() => { throw new Error('must not call'); }, async () => {
    const req = new Request('http://crm.test/api/session/switch', { method: 'POST', headers: { origin: 'http://crm.test' }, body: '{}' });
    assert.equal((await handleSession(req, 'switch', env)).status, 401);
  });
});

test('backend gateway blocks direct auth switching and arbitrary auth paths', async () => {
  for (const path of [['auth', 'switch'], ['auth', 'refresh'], ['auth', 'register'], ['auth', 'login']]) {
    assert.equal((await handleBackend(request('/api/backend/' + path.join('/'), {}), path, env)).status, 404);
  }
});

test('account-changed failure reaches browser with no session mutation', async () => {
  await mockFetch(async () => Response.json({ error: { code: 'account_changed' } }, { status: 409 }), async () => {
    const r = await handleBackend(request('/api/backend/contacts', { name: 'test' }), ['contacts'], env);
    assert.equal(r.status, 409); assert.equal((await r.json()).error.code, 'account_changed');
    assert.equal(r.headers.get('set-cookie'), null);
  });
});

test('public capture proxy never forwards authenticated cookies or JWTs', async () => {
  await mockFetch(async (url, init) => {
    assert.ok(url.endsWith('/public/forms/11111111-1111-4111-8111-111111111111/submit'));
    assert.equal(init.headers.Authorization, undefined); assert.equal(init.headers.cookie, undefined);
    return Response.json({ message: 'Received' });
  }, async () => {
    const r = await handlePublicForm(request('/api/public/forms/id/submit', { name: 'Test' }), '11111111-1111-4111-8111-111111111111', true, env);
    assert.equal(r.status, 200); assert.equal(r.headers.get('set-cookie'), null);
  });
});

test('public proxy rejects invalid route, body size and cross-origin writes', async () => {
  await mockFetch(() => { throw new Error('must not call'); }, async () => {
    const id = '11111111-1111-4111-8111-111111111111';
    assert.equal((await handlePublicForm(request('/test'), '../../auth/login', false, env)).status, 404);
    assert.equal((await handlePublicForm(request('/test', { text: 'x'.repeat(9000) }), id, true, env)).status, 413);
    assert.equal((await handlePublicForm(request('/test', {}, { origin: 'https://other.test' }), id, true, env)).status, 403);
  });
});

test('public booking proxy restricts paths and does not forward account credentials', async () => {
  const { handlePublicBooking } = await import('../src/lib/bff.ts');
  const id = '11111111-1111-4111-8111-111111111111';
  await mockFetch(async (url, init) => {
    assert.equal(init.headers.Authorization, undefined);
    assert.equal(init.headers.cookie, undefined);
    assert.equal(url, 'http://backend.test/api/v1/public/calendars/' + id + '/slots?date=2030-01-08');
    return Response.json({ items:[] });
  }, async () => {
    assert.equal((await handlePublicBooking(request('/test?date=2030-01-08'), ['calendars',id,'slots'],env)).status,200);
  });
  await mockFetch(() => { throw new Error('unexpected upstream call'); }, async () => {
    assert.equal((await handlePublicBooking(request('/test'),['auth','me'],env)).status,404);
    assert.equal((await handlePublicBooking(request('/test',{}, { origin:'https://other.test' }),['calendars',id,'book'],env)).status,403);
    assert.equal((await handlePublicBooking(request('/test',{ text:'x'.repeat(9000) }),['calendars',id,'book'],env)).status,413);
  });
});

test('Evolution webhook preserves signed bytes and does not forward user credentials', async () => {
  const { handleEvolutionWebhook } = await import('../src/lib/bff.ts');
  const body = '{ "instance": "crm-test", "event": "CONNECTION_UPDATE", "data": {"state":"open"} }\n';
  await mockFetch(async (url, init) => {
    assert.equal(url, 'http://backend.test/api/v1/whatsapp/webhook');
    assert.equal(Buffer.from(init.body).toString(), body);
    assert.equal(init.headers['X-Webhook-Secret'], 'instance-only-secret');
    assert.equal(init.headers['X-Webhook-Signature'], 'sha256=signed-by-provider');
    assert.equal(init.headers.Authorization, undefined);
    assert.equal(init.headers.cookie, undefined);
    return Response.json({ ok: true });
  }, async () => {
    const req = new Request('http://crm.test/api/v1/whatsapp/webhook', { method:'POST', body,
      headers: { 'Content-Type':'application/json', 'X-Webhook-Secret':'instance-only-secret',
        'X-Webhook-Signature':'sha256=signed-by-provider', cookie:'crm_access=private', Authorization:'Bearer private' } });
    const result = await handleEvolutionWebhook(req, env);
    assert.equal(result.status, 200); assert.equal(result.headers.get('set-cookie'), null);
  });
});

test('Evolution webhook rejects absent credentials and oversized callbacks; backend remains authoritative', async () => {
  const { handleEvolutionWebhook } = await import('../src/lib/bff.ts');
  await mockFetch(() => { throw new Error('must not forward'); }, async () => {
    assert.equal((await handleEvolutionWebhook(request('/test', {}),env)).status,401);
    const req = request('/test', {}, { 'X-Webhook-Secret':'instance-secret', 'Content-Length':String(16*1024*1024) });
    assert.equal((await handleEvolutionWebhook(req,env)).status,413);
  });
  await mockFetch(async () => Response.json({ error:{ message:'invalid' } },{status:401}),async () => {
    const req = request('/test', {}, {'X-Webhook-Signature':'sha256=invalid'});
    assert.equal((await handleEvolutionWebhook(req,env)).status,401);
  });
});
