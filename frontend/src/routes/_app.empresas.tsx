import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/empresas/index';

export const Route = createFileRoute('/_app/empresas')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
