import { createFileRoute, Outlet, redirect } from '@tanstack/react-router';
import { getEntrySession } from '@/lib/session';
import { AppShell } from '@/components/layout/app-shell';
import { MessageNotificationProvider } from '@/components/inbox/message-notifications';
import { SessionProvider } from '@/components/providers';

export const Route = createFileRoute('/_app')({
  validateSearch: (search: Record<string, unknown>) => search,
  beforeLoad: async ({ location }) => {
    const session = await getEntrySession();
    if (location.pathname === '/' && session.publicFunnel) return session;
    if (!session.hasSession) throw redirect({ to: '/login' });
    return session;
  },
  component: AuthenticatedLayout,
});

function AuthenticatedLayout() {
  const { publicFunnel } = Route.useRouteContext();
  if (publicFunnel) return <Outlet />;
  return <SessionProvider><MessageNotificationProvider><AppShell><Outlet /></AppShell></MessageNotificationProvider></SessionProvider>;
}
