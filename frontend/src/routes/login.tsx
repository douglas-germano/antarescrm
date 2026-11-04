import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/login/index';

export const Route = createFileRoute('/login')({
  component: Screen,
});
