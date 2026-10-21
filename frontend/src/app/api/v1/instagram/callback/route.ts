import { finishInstagramLogin } from '@/lib/instagram-webhook';

export const runtime = 'nodejs';
export async function GET(request: Request) {
  return finishInstagramLogin(request, { FLASK_API_URL: process.env.FLASK_API_URL,
    APP_URL: process.env.APP_URL, COOKIE_SECURE: process.env.COOKIE_SECURE });
}
