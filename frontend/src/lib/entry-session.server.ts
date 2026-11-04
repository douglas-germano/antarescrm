import { customHost, resolveHost } from './domains.server';

/** Route-access hints only. Flask and the gateway authorize every private API request. */
export async function readEntrySession(request: Request) {
  const host = customHost(request);
  const cookie = request.headers.get('cookie') || '';
  return {
    hasSession: !host && /(?:^|;\s*)crm_(?:access|refresh)=[^;]+/.test(cookie),
    publicFunnel: host ? (await resolveHost(host))?.funnel_id || null : null,
  };
}
