import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/projetos/index';

export const Route = createFileRoute('/_app/projetos/')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
