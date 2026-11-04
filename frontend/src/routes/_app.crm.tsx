import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/crm/index';

export const Route = createFileRoute('/_app/crm')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
