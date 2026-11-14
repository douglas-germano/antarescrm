import { createFileRoute } from '@tanstack/react-router';
import { handleAsaasWebhook } from '@/lib/asaas-webhook';

export const Route = createFileRoute('/api/v1/billing/asaas/webhook')({
  server: {
    handlers: {
      POST: ({ request }) => handleAsaasWebhook(request, { FLASK_API_URL: process.env.FLASK_API_URL }),
    },
  },
});
