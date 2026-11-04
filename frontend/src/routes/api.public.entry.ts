import { createFileRoute } from '@tanstack/react-router';
import { readEntrySession } from '@/lib/entry-session.server';

export const Route = createFileRoute('/api/public/entry')({
  server: {
    handlers: {
      GET: async ({ request }) => Response.json(await readEntrySession(request), {
        headers: { 'Cache-Control': 'no-store' },
      }),
    },
  },
});
