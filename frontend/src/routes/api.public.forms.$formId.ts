import { createFileRoute } from '@tanstack/react-router';
import { handlePublicForm } from '@/lib/bff';
async function GET(request: Request, { params }: { params: { formId: string } }) {
  return handlePublicForm(request, params.formId, false, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}

export const Route = createFileRoute('/api/public/forms/$formId')({
  server: {
    handlers: {
      GET: ({ request, params }) => GET(request, { params }),
    },
  },
});
