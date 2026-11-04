import handler, { createServerEntry } from '@tanstack/react-start/server-entry';
import { guardDomain } from './lib/domains.server';

export default createServerEntry({
  async fetch(request, options) {
    const blocked = await guardDomain(request);
    if (blocked) return blocked;
    const response = await handler.fetch(request, options);
    // HTML varies by session and customer hostname. Static assets are served separately by Nitro.
    response.headers.set('Cache-Control', 'no-store');
    return response;
  },
});
