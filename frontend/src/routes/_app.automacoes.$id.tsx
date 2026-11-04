import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/automacoes/[id]/index';

export const Route = createFileRoute('/_app/automacoes/$id')({
  component: Screen,
});
