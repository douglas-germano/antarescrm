import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/p/[funnelId]/[[...slug]]/index';

export const Route = createFileRoute('/p/$funnelId/$')({
  component: Screen,
});
