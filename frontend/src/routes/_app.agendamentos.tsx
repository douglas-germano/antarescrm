import { createFileRoute, redirect } from '@tanstack/react-router';

export const Route = createFileRoute('/_app/agendamentos')({
  beforeLoad: () => { throw redirect({ href: '/configuracoes?tab=agendamento', statusCode: 307 }); },
});
