import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/agendar/[calendarId]/index';

export const Route = createFileRoute('/agendar/$calendarId')({
  component: Screen,
});
