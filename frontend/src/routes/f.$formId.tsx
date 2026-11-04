import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/f/[formId]/index';

export const Route = createFileRoute('/f/$formId')({
  component: Screen,
});
