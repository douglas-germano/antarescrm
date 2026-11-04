import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/agendamento/[token]/index';

export const Route = createFileRoute('/agendamento/$token')({
  component: Screen,
});
