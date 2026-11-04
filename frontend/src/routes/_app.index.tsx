import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/dashboard';

export const Route = createFileRoute('/_app/')({
  loader: ({ location, context }) => context.publicFunnel ? undefined : prepareRoute(location.pathname),
  component: Home,
});

import PublicFunnel from '@/screens/public/p/[funnelId]/[[...slug]]/index';
function Home() {
  const { publicFunnel } = Route.useRouteContext();
  return publicFunnel ? <PublicFunnel domainFunnelId={publicFunnel} /> : <Screen />;
}
