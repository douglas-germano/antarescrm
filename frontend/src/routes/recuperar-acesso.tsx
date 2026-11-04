import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/recuperar-acesso/index';

export const Route = createFileRoute('/recuperar-acesso')({
  component: Screen,
});
