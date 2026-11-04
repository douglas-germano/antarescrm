import test from 'node:test';
import assert from 'node:assert/strict';
import { parseSearch, stringifySearch } from '../src/lib/search.ts';

test('navigation keeps boolean and numeric query flags as ordinary browser strings', () => {
  const query = stringifySearch({ new: 'true', attention: true, modelo: '0', page: 2 });
  const params = new URLSearchParams(query);
  assert.equal(params.get('new'), 'true');
  assert.equal(params.get('attention'), 'true');
  assert.equal(params.get('modelo'), '0');
  assert.equal(params.get('page'), '2');
  assert.equal(parseSearch(query).new, 'true');
});

test('query navigation preserves accents, phone numbers and repeated parameters', () => {
  const original = '?search=Jo%C3%A3o+Silva&phone=%2B5565999999999&tag=a&tag=b';
  assert.deepEqual([...new URLSearchParams(stringifySearch(parseSearch(original)))], [...new URLSearchParams(original)]);
  assert.equal(stringifySearch({ missing: undefined }), '');
});
