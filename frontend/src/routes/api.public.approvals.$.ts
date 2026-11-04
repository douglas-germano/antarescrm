import { createFileRoute } from '@tanstack/react-router';
import { handlePublicApproval } from '@/lib/bff';
async function handler(request: Request, { params }: { params: { path: string[] } }) {
  return handlePublicApproval(request, params.path, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}

export const Route = createFileRoute('/api/public/approvals/$')({
  server: {
    handlers: {
      GET: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
      POST: ({ request, params }) => handler(request, { params: { path: (params._splat || '').split('/').filter(Boolean) } }),
    },
  },
});
