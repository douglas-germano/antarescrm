import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyInstagramWebhook, receiveInstagramWebhook, finishInstagramLogin } from '../src/lib/instagram-webhook.ts';

const token = 'test-verification-token';
const request = (values = {}) => new Request('https://crm.test/api/v1/instagram/webhook?' + new URLSearchParams({
  'hub.mode': 'subscribe', 'hub.verify_token': token, 'hub.challenge': '123456789', ...values,
}));

test('Meta handshake echoes challenge as plain text without session cookies', async () => {
  const response = verifyInstagramWebhook(request(), token);
  assert.equal(response.status, 200);
  assert.equal(await response.text(), '123456789');
  assert.equal(response.headers.get('content-type'), 'text/plain; charset=utf-8');
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(response.headers.get('set-cookie'), null);
});

test('unconfigured endpoint and incorrect tokens cannot verify a subscription', () => {
  assert.equal(verifyInstagramWebhook(request()).status, 503);
  for (const value of ['', 'wrong', 'x'.repeat(token.length)])
    assert.equal(verifyInstagramWebhook(request({ 'hub.verify_token': value }), token).status, 403);
});

test('requires subscribe mode and a bounded nonempty challenge', () => {
  for (const values of [{ 'hub.mode': 'invalid' }, { 'hub.challenge': '' }, { 'hub.challenge': 'a'.repeat(1025) }])
    assert.equal(verifyInstagramWebhook(request(values), token).status, 400);
});

test('signed delivery preserves bytes and never forwards cookies or bearer credentials', async () => {
  const original = globalThis.fetch;
  const body = '{ "object": "instagram", "entry": [] }';
  globalThis.fetch = async (url, init) => {
    assert.equal(url, 'http://backend.test/api/v1/instagram/webhook');
    assert.equal(new TextDecoder().decode(init.body), body);
    assert.deepEqual(Object.keys(init.headers).sort(), ['Content-Type', 'X-Hub-Signature-256']);
    return Response.json({ received: true });
  };
  try {
    const r = await receiveInstagramWebhook(new Request('https://crm.test/hook', { method: 'POST', body,
      headers: { 'Content-Type': 'application/json', 'X-Hub-Signature-256': 'sha256=' + 'a'.repeat(64), cookie: 'crm_access=private' } }), { FLASK_API_URL: 'http://backend.test/api/v1' });
    assert.equal(r.status, 200);
    const invalid = await receiveInstagramWebhook(new Request('https://crm.test/hook', { method: 'POST', body }), {});
    assert.equal(invalid.status, 401);
  } finally { globalThis.fetch = original; }
});

test('OAuth callback requires code/state and redirects only to the configured app', async () => {
  const r = await finishInstagramLogin(new Request('https://spoof.test/callback?error=denied&next=https://evil.test'), { APP_URL: 'https://crm.test' });
  assert.equal(r.status, 303);
  assert.equal(r.headers.get('location'), 'https://crm.test/configuracoes?tab=conexoes&instagram=error');
});
