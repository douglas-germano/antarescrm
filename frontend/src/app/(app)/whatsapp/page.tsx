import { redirect } from 'next/navigation';
export default async function WhatsAppPage({ searchParams }: { searchParams: Promise<{ conversation?: string }> }) {
  const { conversation } = await searchParams;
  redirect('/mensagens' + (conversation ? '?conversation=' + encodeURIComponent(conversation) : ''));
}
