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
