import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/tarefas/index';

export const Route = createFileRoute('/_app/tarefas')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
