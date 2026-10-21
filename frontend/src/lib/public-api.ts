export async function publicApi(path: string, body?: unknown, signal?: AbortSignal) {
  const response = await fetch('/api/public/booking/' + path, { method: body === undefined ? 'GET':'POST', headers: { 'Content-Type':'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), cache:'no-store', signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message || 'Não foi possível concluir. Tente novamente.');
  return data;
}
