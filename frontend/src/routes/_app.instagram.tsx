import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/app/instagram/index';

export const Route = createFileRoute('/_app/instagram')({
  component: Screen,
});
