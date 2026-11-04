import type { ReactNode } from 'react';
import { Link } from '@tanstack/react-router';
import { CalendarCheck, KanbanSquare, MessageCircle } from 'lucide-react';

/** Split layout shared by the access screens: brand panel on the left (hidden on phones), form on the right. */
export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <main className="auth-page">
      <aside className="auth-brand" aria-hidden="true">
        <div className="auth-logo"><img src="/mark.svg" width="44" height="44" alt="" /><span>antares<strong>crm</strong></span></div>
        <div className="auth-pitch">
          <h2>Vendas, atendimento e projetos no mesmo lugar.</h2>
          <ul>
            <li><MessageCircle size={18} />WhatsApp e Instagram numa só caixa de entrada</li>
            <li><KanbanSquare size={18} />Funil de vendas com o próximo passo de cada negócio</li>
            <li><CalendarCheck size={18} />Tarefas, agenda e automações da equipe</li>
          </ul>
        </div>
        <small>© Antares CRM</small>
      </aside>
      <section className="auth-panel">
        <div className="auth-box">
          <div className="auth-logo auth-logo-mobile"><img src="/mark.svg" width="36" height="36" alt="" /><span>antares<strong>crm</strong></span></div>
          <header className="auth-heading">
            <h1>{title}</h1>
            {subtitle && <p>{subtitle}</p>}
          </header>
          {children}
          {footer && <div className="auth-footer">{footer}</div>}
          <nav className="auth-legal" aria-label="Informações legais"><Link to="/privacidade">Privacidade</Link><Link to="/termos">Termos</Link><Link to="/exclusao-de-dados">Exclusão de dados</Link></nav>
        </div>
      </section>
    </main>
  );
}

/** What the forgot-password screen pre-fills from the login form. */
export const PREFILL_KEY = 'antares.access.prefill';
export const ACCOUNT_KEY = 'antares.login.account';

export function readStorage(storage: 'local' | 'session', key: string) {
  try { return (storage === 'local' ? localStorage : sessionStorage).getItem(key) || ''; } catch { return ''; }
}
export function writeStorage(storage: 'local' | 'session', key: string, value: string | null) {
  try {
    const store = storage === 'local' ? localStorage : sessionStorage;
    if (value === null) store.removeItem(key); else store.setItem(key, value);
  } catch { /* optional convenience */ }
}
