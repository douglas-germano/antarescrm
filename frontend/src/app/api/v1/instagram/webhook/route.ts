import { verifyInstagramWebhook, receiveInstagramWebhook } from '@/lib/instagram-webhook';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  return verifyInstagramWebhook(request, process.env.INSTAGRAM_WEBHOOK_VERIFY_TOKEN);
}

export async function POST(request: Request) {
  return receiveInstagramWebhook(request, { FLASK_API_URL: process.env.FLASK_API_URL });
}
