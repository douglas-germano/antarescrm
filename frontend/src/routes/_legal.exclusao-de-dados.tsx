import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/legal/exclusao-de-dados/index';
import { legal } from '@/lib/legal';

export const Route = createFileRoute('/_legal/exclusao-de-dados')({
  component: Screen,
  head: () => ({ meta: [{ title: "Exclus\u00e3o de Dados \u00b7 Antares CRM" }, { name: 'description', content: "Como solicitar a exclus\u00e3o dos seus dados no Antares CRM e revogar integra\u00e7\u00f5es." }, { name: 'robots', content: 'index, follow' }], links: [{ rel: 'canonical', href: legal.origin + '/exclusao-de-dados' }] }),
});
