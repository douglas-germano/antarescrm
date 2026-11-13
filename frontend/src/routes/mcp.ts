import { createFileRoute } from '@tanstack/react-router';
import { handleMcp } from '@/lib/bff';

const env = () => ({ FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });

export const Route = createFileRoute('/mcp')({
  server: {
    handlers: {
      POST: ({ request }) => handleMcp(request, env()),
      GET: ({ request }) => handleMcp(request, env()),
      DELETE: ({ request }) => handleMcp(request, env()),
    },
  },
});
