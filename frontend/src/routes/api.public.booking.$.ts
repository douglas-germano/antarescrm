import { createFileRoute } from '@tanstack/react-router';
import { handlePublicBooking } from '@/lib/bff';
async function handler(request: Request, { params }: { params: { path: string[] } }) {
  return handlePublicBooking(request, params.path, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}

export const Route = createFileRoute('/api/public/booking/$')({
  server: {
    handlers: {
      GET: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
      POST: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
    },
  },
});
