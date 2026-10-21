import { handleEvolutionWebhook } from '@/lib/bff';
export const runtime = 'nodejs';
export async function POST(request: Request) {
  return handleEvolutionWebhook(request, { FLASK_API_URL: process.env.FLASK_API_URL });
}
