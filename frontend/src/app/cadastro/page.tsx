import Link from 'next/link';
import { ArrowRight, MailPlus, UserRoundPlus } from 'lucide-react';
import { AuthShell } from '@/components/auth/auth-shell';

// Read at request time, so the "Pedir acesso" destination can be set on the server without a new build.
export const dynamic = 'force-dynamic';

/** Accounts are created by invitation; this page explains that instead of silently sending people to login. */
export default function Register() {
  const requestUrl = process.env.ACCESS_REQUEST_URL || '';
  return (
    <AuthShell title="Acesso por convite" subtitle="O Antares não tem cadastro aberto.">
      <div className="auth-result">
        <span className="auth-result-icon"><UserRoundPlus size={26} /></span>
        <p>Quem entra é convidado pelo administrador da empresa: ele envia um e-mail com o link para definir a senha.</p>
        <p className="muted">Já recebeu o convite? Use o link do e-mail ou entre com a conta, o e-mail e a senha.</p>
        <Link href="/login" className="btn btn-primary auth-submit">Já tenho acesso: entrar<ArrowRight size={18} /></Link>
        {requestUrl
          ? <a href={requestUrl} className="btn btn-secondary auth-submit" target={requestUrl.startsWith('http') ? '_blank' : undefined} rel="noreferrer"><MailPlus size={18} />Pedir acesso</a>
          : <p className="muted auth-small">Para pedir acesso, fale com o administrador do Antares na sua empresa.</p>}
      </div>
    </AuthShell>
  );
}
