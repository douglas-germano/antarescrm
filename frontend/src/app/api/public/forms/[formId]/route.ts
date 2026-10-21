import { handlePublicForm } from '@/lib/bff';
export async function GET(request: Request, { params }: { params: Promise<{ formId: string }> }) {
  return handlePublicForm(request, (await params).formId, false, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}
