type Env = { FLASK_API_URL?: string };

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });

/** Asaas callbacks carry no session; Flask validates the `asaas-access-token` header. */
export async function handleAsaasWebhook(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') return json(405, { error: { code: 'method', message: 'Método não permitido.' } });
  const token = request.headers.get('asaas-access-token');
  if (!token) return json(401, { error: { code: 'auth', message: 'Autenticação de webhook inválida.' } });
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json'))
    return json(415, { error: { code: 'type', message: 'Payload inválido.' } });
  if (Number(request.headers.get('content-length')) > 1024 * 1024)
    return json(413, { error: { code: 'size', message: 'Payload muito grande.' } });
  const base = (env.FLASK_API_URL || 'http://127.0.0.1:5002/api/v1').replace(/\/$/, '');
  try {
    const upstream = await fetch(`${base}/billing/asaas/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'asaas-access-token': token },
      body: await request.arrayBuffer(),
      cache: 'no-store',
      signal: AbortSignal.timeout(30000),
    });
    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  } catch {
    return json(502, { error: { code: 'upstream', message: 'Não foi possível receber a atualização.' } });
  }
}
