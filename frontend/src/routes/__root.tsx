import { createRootRoute, HeadContent, Outlet, Scripts } from '@tanstack/react-router';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/inter/800.css';
import '@/styles/globals.css';
import '@/styles/modules.css';
import '@/styles/inbox.css';
import '@/styles/automations.css';
import '@/styles/reports.css';
import '@/styles/instagram.css';
import '@/styles/projects.css';
import '@/styles/forms.css';
import '@/styles/builder.css';
import '@/styles/funnels.css';
import '@/styles/native-navigation.css';
import '@/styles/dark-glass.css';
import { Providers } from '@/components/providers';
import { ActionTooltip } from '@/components/layout/action-tooltip';
import { NavigationProgress } from '@/components/layout/navigation-progress';

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Antares CRM' },
      { name: 'description', content: 'Contatos, empresas, funil, tarefas e WhatsApp no mesmo lugar.' },
    ],
    links: [{ rel: 'icon', type: 'image/svg+xml', href: '/icon.svg' }],
  }),
  shellComponent: ({ children }) => (
    <html lang="pt-BR">
      <head><HeadContent /></head>
      <body><Providers><NavigationProgress />{children}</Providers><ActionTooltip /><Scripts /></body>
    </html>
  ),
  component: Outlet,
});
