import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/formularios/[id]/index';

export const Route = createFileRoute('/_app/formularios/$id')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
