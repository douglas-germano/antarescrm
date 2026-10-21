import Link from 'next/link';
import type { ReactNode } from 'react';
import { legal, legalLinks } from '@/lib/legal';
import './legal.css';
export default function LegalLayout({ children }: { children: ReactNode }) {
  return <div className="legal-shell">
    <a className="legal-skip" href="#legal-content">Ir para o conteúdo</a>
    <header className="legal-header"><Link href="/login" className="legal-brand"><img src="/mark.svg" width="32" height="32" alt="" /><span>Antares CRM</span></Link><Link href="/login" className="btn btn-secondary">Entrar</Link></header>
    <main id="legal-content" className="legal-content">{children}</main>
    <footer className="legal-footer"><nav aria-label="Informações legais">{legalLinks.map(link => <Link href={link.href} key={link.href}>{link.label}</Link>)}</nav><p>{legal.service} · {legal.responsible} · <a href={'mailto:' + legal.email}>{legal.email}</a></p></footer>
  </div>;
}
