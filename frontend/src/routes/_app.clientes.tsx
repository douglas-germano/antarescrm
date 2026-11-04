import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/clientes/index';

export const Route = createFileRoute('/_app/clientes')({
  component: Screen,
});
