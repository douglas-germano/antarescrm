import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/funis/index';

export const Route = createFileRoute('/_app/funis/')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
