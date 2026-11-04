import { createFileRoute } from '@tanstack/react-router';
import Screen from '@/screens/legal/privacidade/index';
import { legal } from '@/lib/legal';

export const Route = createFileRoute('/_legal/privacidade')({
  component: Screen,
  head: () => ({ meta: [{ title: "Pol\u00edtica de Privacidade \u00b7 Antares CRM" }, { name: 'description', content: "Como o Antares CRM trata dados pessoais e como exercer seus direitos." }, { name: 'robots', content: 'index, follow' }], links: [{ rel: 'canonical', href: legal.origin + '/privacidade' }] }),
});
