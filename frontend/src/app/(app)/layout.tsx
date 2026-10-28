import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { AppShell } from '@/components/layout/app-shell';
import { MessageNotificationProvider } from '@/components/inbox/message-notifications';
import { SessionProvider } from '@/components/providers';
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const jar = await cookies();
  if (!jar.has('crm_access') && !jar.has('crm_refresh')) redirect('/login');
  return <SessionProvider><MessageNotificationProvider><AppShell>{children}</AppShell></MessageNotificationProvider></SessionProvider>;
}
