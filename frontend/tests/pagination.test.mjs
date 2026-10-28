import test from 'node:test';
import assert from 'node:assert/strict';
import { collectPages, pagePath } from '../src/lib/pagination.ts';

test('pagination replaces existing keys and preserves filters', () => {
  const url = new URL(pagePath('/contacts?source=Site&page=9&per_page=20', 2, 25), 'http://fixture');
  assert.deepEqual(url.searchParams.getAll('page'), ['2']);
  assert.deepEqual(url.searchParams.getAll('per_page'), ['25']);
  assert.equal(url.searchParams.get('source'), 'Site');
});
test('complete option lists bound concurrency and preserve page order', async () => {
  let active = 0, peak = 0;
  const rows = await collectPages('/users', async path => {
    const page = Number(new URL(path, 'http://fixture').searchParams.get('page'));
    active++; peak = Math.max(peak, active);
    await new Promise(resolve => setTimeout(resolve, (10 - page) * 2)); active--;
    return { items: [{ id: page }], page, pages: 9, per_page: 100, total: 9 };
  });
  assert.ok(peak <= 3);
  assert.deepEqual(rows.map(row => row.id), [1,2,3,4,5,6,7,8,9]);
});
test('a failed page rejects the list instead of returning incomplete data', async () => {
  await assert.rejects(collectPages('/users', async path => {
    const page = Number(new URL(path, 'http://fixture').searchParams.get('page'));
    if (page === 2) throw new Error('offline');
    return { items: [], page, pages: 2, total: 1, per_page: 100 };
  }), /offline/);
});
