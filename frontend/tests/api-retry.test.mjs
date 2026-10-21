import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchWithRetry } from '../src/lib/retry.ts';

async function withFetch(sequence, run) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(init?.method || 'GET');
    const next = sequence[Math.min(calls.length - 1, sequence.length - 1)];
    if (next instanceof Error) throw next;
    return new Response('{}', { status: next });
  };
  try { return await run(calls); } finally { globalThis.fetch = original; }
}

test('reads are retried after a gateway 502 and then succeed', async () => {
  await withFetch([502, 502, 200], async (calls) => {
    assert.equal((await fetchWithRetry('/x', {})).status, 200);
    assert.equal(calls.length, 3);
  });
});

test('reads recover from a dropped connection', async () => {
  await withFetch([new TypeError('fetch failed'), 200], async (calls) => {
    assert.equal((await fetchWithRetry('/x', { method: 'GET' })).status, 200);
    assert.equal(calls.length, 2);
  });
});

test('a persistent 502 is returned after the retries are used up', async () => {
  await withFetch([502], async (calls) => {
    assert.equal((await fetchWithRetry('/x', {})).status, 502);
    assert.equal(calls.length, 3);
  });
});

test('writes and real errors are never repeated', async () => {
  await withFetch([502], async (calls) => {
    assert.equal((await fetchWithRetry('/x', { method: 'POST' })).status, 502);
    assert.equal(calls.length, 1);
  });
  await withFetch([404], async (calls) => {
    assert.equal((await fetchWithRetry('/x', {})).status, 404);
    assert.equal(calls.length, 1);
  });
  await withFetch([Object.assign(new Error('aborted'), { name: 'AbortError' })], async (calls) => {
    await assert.rejects(fetchWithRetry('/x', {}), { name: 'AbortError' });
    assert.equal(calls.length, 1);
  });
});
