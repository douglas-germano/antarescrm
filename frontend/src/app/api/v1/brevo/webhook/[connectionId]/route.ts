import { handleBrevoWebhook } from '@/lib/bff';
export async function POST(request: Request, { params }: { params: Promise<{ connectionId: string }> }) {
  return handleBrevoWebhook(request, (await params).connectionId, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}
