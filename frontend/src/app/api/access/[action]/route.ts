import { handleAccess } from '@/lib/bff';
export async function POST(request: Request, { params }: { params: Promise<{ action: string }> }) {
  return handleAccess(request, (await params).action, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}
