import { createFileRoute, redirect } from '@tanstack/react-router';

export const Route = createFileRoute('/_app/whatsapp')({
  beforeLoad: ({ location }) => {
    const conversation = new URLSearchParams(location.searchStr).get('conversation');
    throw redirect({ href: '/mensagens' + (conversation ? '?conversation=' + encodeURIComponent(conversation) : ''), statusCode: 307 });
  },
});
