import { handleSession } from '@/lib/bff';
export async function POST(request: Request, { params }: { params: Promise<{ action: string }> }) {
  return handleSession(request, (await params).action, {
    FLASK_API_URL: process.env.FLASK_API_URL,
    APP_URL: process.env.APP_URL,
    COOKIE_SECURE: process.env.COOKIE_SECURE || (process.env.NODE_ENV === 'production' ? 'true' : 'false'),
  });
}
