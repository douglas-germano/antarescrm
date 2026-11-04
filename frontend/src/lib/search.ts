/** Keep the browser's string query semantics, including flags such as ?new=true and ?modelo=0. */
export function parseSearch(search: string): Record<string, string | string[]> {
  const result: Record<string, string | string[]> = Object.create(null);
  for (const [key, value] of new URLSearchParams(search)) {
    const previous = result[key];
    result[key] = previous === undefined ? value : Array.isArray(previous) ? [...previous, value] : [previous, value];
  }
  return result;
}

export function stringifySearch(search: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item === undefined || item === null) continue;
      params.append(key, typeof item === 'object' ? JSON.stringify(item) : String(item));
    }
  }
  const query = params.toString();
  return query ? '?' + query : '';
}
