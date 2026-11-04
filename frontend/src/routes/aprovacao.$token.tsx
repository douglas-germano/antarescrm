import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/aprovacao/[token]/index';

export const Route = createFileRoute('/aprovacao/$token')({
  component: Screen,
});
