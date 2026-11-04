import { createFileRoute } from '@tanstack/react-router';
import { handleSession } from '@/lib/bff';
async function POST(request: Request, { params }: { params: { action: string } }) {
  return handleSession(request, params.action, {
    FLASK_API_URL: process.env.FLASK_API_URL,
    APP_URL: process.env.APP_URL,
    COOKIE_SECURE: process.env.COOKIE_SECURE || (process.env.NODE_ENV === 'production' ? 'true' : 'false'),
  });
}

export const Route = createFileRoute('/api/session/$action')({
  server: {
    handlers: {
      POST: ({ request, params }) => POST(request, { params }),
    },
  },
});
