import { handlePublicForm } from '@/lib/bff';
export async function POST(request: Request, { params }: { params: Promise<{ formId: string }> }) {
  return handlePublicForm(request, (await params).formId, true, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}
