import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/definir-senha/index';

export const Route = createFileRoute('/definir-senha')({
  component: Screen,
});
