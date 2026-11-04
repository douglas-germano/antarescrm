import { prepareRoute } from '@/lib/route-data';
import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/formularios/index';

export const Route = createFileRoute('/_app/formularios/')({
  loader: ({ location }) => prepareRoute(location.pathname),
  component: Screen,
});
