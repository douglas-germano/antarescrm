import type { Metadata } from 'next';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/inter/800.css';
import './globals.css';
import './modules.css';
import './inbox.css';
import './automations.css';
import './reports.css';
import './projects.css';
import './forms.css';
import './builder.css';
import './funnels.css';
import { Providers } from '@/components/providers';
export const metadata: Metadata = {
  title: { default: 'Antares CRM', template: '%s · Antares CRM' },
  description: 'Contatos, empresas, funil, tarefas e WhatsApp no mesmo lugar.',
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" data-scroll-behavior="smooth">
      <body suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
