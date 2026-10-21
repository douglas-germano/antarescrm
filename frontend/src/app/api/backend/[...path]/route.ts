import { handleBackend } from '@/lib/bff';
async function handler(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return handleBackend(request, (await params).path, {
    FLASK_API_URL: process.env.FLASK_API_URL,
    APP_URL: process.env.APP_URL,
    COOKIE_SECURE: process.env.COOKIE_SECURE || (process.env.NODE_ENV === 'production' ? 'true' : 'false'),
  });
}
export { handler as GET, handler as HEAD, handler as POST, handler as PATCH, handler as DELETE };
