import { createFileRoute } from '@tanstack/react-router';
import { handleBackend } from '@/lib/bff';
async function handler(request: Request, { params }: { params: { path: string[] } }) {
  return handleBackend(request, params.path, {
    FLASK_API_URL: process.env.FLASK_API_URL,
    APP_URL: process.env.APP_URL,
    COOKIE_SECURE: process.env.COOKIE_SECURE || (process.env.NODE_ENV === 'production' ? 'true' : 'false'),
  });
}

export const Route = createFileRoute('/api/backend/$')({
  server: {
    handlers: {
      GET: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
      HEAD: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
      POST: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
      PATCH: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
      DELETE: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
    },
  },
});
