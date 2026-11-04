import { createFileRoute } from '@tanstack/react-router';
import { finishInstagramLogin } from '@/lib/instagram-webhook';

async function GET(request: Request) {
  return finishInstagramLogin(request, { FLASK_API_URL: process.env.FLASK_API_URL,
    APP_URL: process.env.APP_URL, COOKIE_SECURE: process.env.COOKIE_SECURE });
}

export const Route = createFileRoute('/api/v1/instagram/callback')({
  server: {
    handlers: {
      GET: ({ request }) => GET(request),
    },
  },
});
