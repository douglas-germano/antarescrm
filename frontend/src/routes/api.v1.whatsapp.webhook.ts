import { createFileRoute } from '@tanstack/react-router';
import { handleEvolutionWebhook } from '@/lib/bff';
async function POST(request: Request) {
  return handleEvolutionWebhook(request, { FLASK_API_URL: process.env.FLASK_API_URL });
}

export const Route = createFileRoute('/api/v1/whatsapp/webhook')({
  server: {
    handlers: {
      POST: ({ request }) => POST(request),
    },
  },
});
