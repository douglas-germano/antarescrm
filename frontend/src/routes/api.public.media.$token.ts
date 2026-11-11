import { createFileRoute } from '@tanstack/react-router';
import { handlePublicMedia } from '@/lib/bff';

const env = () => ({ FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });

export const Route = createFileRoute('/api/public/media/$token')({
  server: {
    handlers: {
      GET: ({ request, params }) => handlePublicMedia(request, params.token, env()),
      HEAD: ({ request, params }) => handlePublicMedia(request, params.token, env()),
    },
  },
});
