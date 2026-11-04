import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/campanhas/index';

export const Route = createFileRoute('/_app/campanhas')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
