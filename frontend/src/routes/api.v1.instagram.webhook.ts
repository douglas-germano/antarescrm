import { createFileRoute } from '@tanstack/react-router';
import { verifyInstagramWebhook, receiveInstagramWebhook } from '@/lib/instagram-webhook';


async function GET(request: Request) {
  return verifyInstagramWebhook(request, process.env.INSTAGRAM_WEBHOOK_VERIFY_TOKEN);
}

async function POST(request: Request) {
  return receiveInstagramWebhook(request, { FLASK_API_URL: process.env.FLASK_API_URL });
}

export const Route = createFileRoute('/api/v1/instagram/webhook')({
  server: {
    handlers: {
      GET: ({ request }) => GET(request),
      POST: ({ request }) => POST(request),
    },
  },
});
