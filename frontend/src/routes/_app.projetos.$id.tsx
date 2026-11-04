import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/projetos/[id]/index';

export const Route = createFileRoute('/_app/projetos/$id')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
