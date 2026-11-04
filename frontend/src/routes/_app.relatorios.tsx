import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/relatorios/index';

export const Route = createFileRoute('/_app/relatorios')({
  component: Screen,
});
