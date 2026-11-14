import { AuthForm } from '@/components/auth/auth-form';
export default function Login({ openSubscription }: { openSubscription: boolean }) {
  return <AuthForm openSubscription={openSubscription} />;
}
