import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/cadastro/index';

export const Route = createFileRoute('/cadastro')({
  component: Screen,
});
