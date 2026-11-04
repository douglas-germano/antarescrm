import { createFileRoute, redirect } from '@tanstack/react-router';

export const Route = createFileRoute('/_app/operacao')({
  beforeLoad: () => { throw redirect({ href: '/configuracoes?tab=operacao', statusCode: 307 }); },
});
