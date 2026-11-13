import test from 'node:test';
import assert from 'node:assert/strict';
import { handlePublicMedia } from '../src/lib/bff.ts';

const env = { FLASK_API_URL: 'http://backend.test/api/v1', APP_URL: 'http://crm.test' };
const token = 'a'.repeat(43);
async function mockFetch(fn, run) {
  const saved = globalThis.fetch; globalThis.fetch = fn;
  try { await run(); } finally { globalThis.fetch = saved; }
}

test('post media is served for Instagram without forwarding cookies or sessions', async () => {
  await mockFetch(async (url, init) => {
    assert.equal(url, 'http://backend.test/api/v1/public/instagram-media/' + token);
    assert.ok(!init.headers.Authorization && !init.headers.cookie && !init.headers.Cookie);
    return new Response(new Uint8Array([0xff, 0xd8, 0xff]), { headers: { 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=600', 'Set-Cookie': 'x=1' } });
  }, async () => {
    const response = await handlePublicMedia(new Request('http://crm.test/api/public/media/' + token, { headers: { cookie: 'crm_access=secret' } }), token, env);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'image/jpeg');
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(response.headers.get('set-cookie'), null);
    assert.deepEqual([...new Uint8Array(await response.arrayBuffer())], [0xff, 0xd8, 0xff]);
  });
});

test('invalid tokens and methods never reach the backend', async () => {
  await mockFetch(async () => { throw new Error('must not be called'); }, async () => {
    assert.equal((await handlePublicMedia(new Request('http://crm.test/x'), '../etc', env)).status, 404);
    assert.equal((await handlePublicMedia(new Request('http://crm.test/x', { method: 'POST', body: 'x' }), token, env)).status, 404);
  });
});

test('unavailable files are not cached', async () => {
  await mockFetch(async () => Response.json({ error: { message: 'Arquivo indisponível.' } }, { status: 404 }), async () => {
    const response = await handlePublicMedia(new Request('http://crm.test/api/public/media/' + token), token, env);
    assert.equal(response.status, 404);
    assert.equal(response.headers.get('cache-control'), 'no-store');
  });
});

test('MCP forwards only the token and protocol headers, never cookies', async () => {
  const { handleMcp } = await import('../src/lib/bff.ts');
  await mockFetch(async (url, init) => {
    assert.equal(url, 'http://backend.test/api/v1/mcp');
    assert.equal(init.headers.authorization, 'Bearer antares_x');
    assert.equal(init.headers['mcp-protocol-version'], '2025-06-18');
    assert.ok(!init.headers.cookie);
    return Response.json({ jsonrpc: '2.0', id: 1, result: {} });
  }, async () => {
    const response = await handleMcp(new Request('http://crm.test/mcp', { method: 'POST', body: '{"jsonrpc":"2.0","id":1,"method":"ping"}',
      headers: { 'Content-Type': 'application/json', authorization: 'Bearer antares_x', cookie: 'crm_access=secret', 'mcp-protocol-version': '2025-06-18' } }), env);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { jsonrpc: '2.0', id: 1, result: {} });
  });
  assert.equal((await handleMcp(new Request('http://crm.test/mcp'), env)).status, 405);
});
