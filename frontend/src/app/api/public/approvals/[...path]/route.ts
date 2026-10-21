import { handlePublicApproval } from '@/lib/bff';
async function handler(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return handlePublicApproval(request, (await params).path, { FLASK_API_URL: process.env.FLASK_API_URL, APP_URL: process.env.APP_URL });
}
export { handler as GET, handler as POST };
