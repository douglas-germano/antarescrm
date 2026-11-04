import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/mensagens/index';

export const Route = createFileRoute('/_app/mensagens')({
  component: Screen,
});
