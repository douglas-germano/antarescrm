import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/public/login/index';

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>): { next?: 'assinatura' } =>
    search.next === 'assinatura' ? { next: 'assinatura' } : {},
  component: function LoginRoute() {
    const { next } = Route.useSearch();
    return <Screen openSubscription={next === 'assinatura'} />;
  },
});
