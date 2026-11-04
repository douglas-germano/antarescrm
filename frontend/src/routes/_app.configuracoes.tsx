import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/configuracoes/index';

export const Route = createFileRoute('/_app/configuracoes')({
  component: Screen,
});
