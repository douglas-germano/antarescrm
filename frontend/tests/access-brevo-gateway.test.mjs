import test from 'node:test';
import assert from 'node:assert/strict';
import { handleAccess, handleBrevoWebhook } from '../src/lib/bff.ts';
const env = { FLASK_API_URL: 'http://backend.test/api/v1', APP_URL: 'https://crm.test' };

test('access recovery and acceptance forward only JSON without session credentials', async () => {
  const original = globalThis.fetch;
  try {
    for (const action of ['forgot-password', 'accept-access']) {
      globalThis.fetch = async (url, init) => {
        assert.equal(url, 'http://backend.test/api/v1/auth/' + action);
        assert.deepEqual(init.headers, { 'Content-Type': 'application/json' });
        assert.equal(init.body, '{"email":"test@example.com"}');
        return Response.json({ message: 'ok' });
      };
      const response = await handleAccess(new Request('https://crm.test/api/access/' + action, { method: 'POST',
        body: '{"email":"test@example.com"}', headers: { origin: 'https://crm.test', cookie: 'crm_access=secret', authorization: 'Bearer secret' } }), action, env);
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('set-cookie'), null);
      assert.equal(response.headers.get('cache-control'), 'no-store');
    }
  } finally { globalThis.fetch = original; }
});

test('public access endpoints reject unknown actions, foreign origins, GET and oversized requests', async () => {
  assert.equal((await handleAccess(new Request('https://crm.test', { method: 'POST' }), 'login', env)).status, 404);
  assert.equal((await handleAccess(new Request('https://crm.test'), 'forgot-password', env)).status, 405);
  assert.equal((await handleAccess(new Request('https://crm.test', { method: 'POST', headers: { origin: 'https://evil.test' } }), 'forgot-password', env)).status, 403);
  assert.equal((await handleAccess(new Request('https://crm.test', { method: 'POST', body: 'x'.repeat(4097) }), 'accept-access', env)).status, 413);
});

test('provider webhook forwards its dedicated secret and original body, never browser credentials', async () => {
  const original = globalThis.fetch;
  const id = '11111111-1111-4111-8111-111111111111';
  const body = '{ "event": "delivered" }';
  try {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, 'http://backend.test/api/v1/brevo/webhook/' + id);
      assert.equal(new TextDecoder().decode(init.body), body);
      assert.deepEqual(init.headers, { 'Content-Type': 'application/json', 'X-Brevo-Secret': 'webhook-private-key' });
      return Response.json({ received: true });
    };
    const response = await handleBrevoWebhook(new Request('https://crm.test/hook', { method: 'POST', body,
      headers: { cookie: 'crm_access=secret', authorization: 'Bearer secret', 'X-Brevo-Secret': 'webhook-private-key' } }), id, env);
    assert.equal(response.status, 200);
    assert.equal((await handleBrevoWebhook(new Request('https://crm.test/hook'), id, env)).status, 405);
    assert.equal((await handleBrevoWebhook(new Request('https://crm.test/hook', { method: 'POST' }), '../auth', env)).status, 400);
    assert.equal((await handleBrevoWebhook(new Request('https://crm.test/hook', { method: 'POST', body: 'x'.repeat(262145) }), id, env)).status, 413);
  } finally { globalThis.fetch = original; }
});

test('provider and access gateway failures return a bounded message', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('private-transport-error'); };
  try {
    const response = await handleAccess(new Request('https://crm.test', { method: 'POST' }), 'forgot-password', env);
    assert.equal(response.status, 502); assert.ok(!(await response.text()).includes('private-transport-error'));
    const hook = await handleBrevoWebhook(new Request('https://crm.test', { method: 'POST' }), '11111111-1111-4111-8111-111111111111', env);
    assert.equal(hook.status, 502);
  } finally { globalThis.fetch = original; }
});
