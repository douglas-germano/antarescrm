import { createFileRoute } from '@tanstack/react-router';
import { handleAccess } from '@/lib/bff';
async function POST(request: Request, { params }: { params: { action: string } }) {
  return handleAccess(request, params.action, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}

export const Route = createFileRoute('/api/access/$action')({
  server: {
    handlers: {
      POST: ({ request, params }) => POST(request, { params }),
    },
  },
});
