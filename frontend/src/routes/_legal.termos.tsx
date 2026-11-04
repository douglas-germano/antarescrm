import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/legal/termos/index';
import { legal } from '@/lib/legal';

export const Route = createFileRoute('/_legal/termos')({
  component: Screen,
  head: () => ({ meta: [{ title: "Termos de Servi\u00e7o \u00b7 Antares CRM" }, { name: 'description', content: "Condi\u00e7\u00f5es de uso do Antares CRM, responsabilidades e contato." }, { name: 'robots', content: 'index, follow' }], links: [{ rel: 'canonical', href: legal.origin + '/termos' }] }),
});
