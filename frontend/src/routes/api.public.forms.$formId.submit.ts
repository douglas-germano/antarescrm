import { createFileRoute } from '@tanstack/react-router';
import { handlePublicForm } from '@/lib/bff';
async function POST(request: Request, { params }: { params: { formId: string } }) {
  return handlePublicForm(request, params.formId, true, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}

export const Route = createFileRoute('/api/public/forms/$formId/submit')({
  server: {
    handlers: {
      POST: ({ request, params }) => POST(request, { params }),
    },
  },
});
