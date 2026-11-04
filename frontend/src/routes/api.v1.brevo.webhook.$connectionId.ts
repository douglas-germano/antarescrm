import { createFileRoute } from '@tanstack/react-router';
import { handleBrevoWebhook } from '@/lib/bff';
async function POST(request: Request, { params }: { params: { connectionId: string } }) {
  return handleBrevoWebhook(request, params.connectionId, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}

export const Route = createFileRoute('/api/v1/brevo/webhook/$connectionId')({
  server: {
    handlers: {
      POST: ({ request, params }) => POST(request, { params }),
    },
  },
});
