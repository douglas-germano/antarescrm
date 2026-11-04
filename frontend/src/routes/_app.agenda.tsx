import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/agenda/index';

export const Route = createFileRoute('/_app/agenda')({
  component: Screen,
});
