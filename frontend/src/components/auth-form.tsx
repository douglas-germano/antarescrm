'use client';
import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Loader2, Eye, EyeOff, AlertCircle } from 'lucide-react';

export function AuthForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [show, setShow] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError('');
    setBusy(true);
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const response = await fetch('/api/session/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message || 'Não foi possível entrar. Revise os dados.');
      window.location.replace('/');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="login-brand">
          <img src="/mark.svg" width="40" height="40" alt="" />
          <span>antares<strong>crm</strong></span>
        </div>
        <header className="login-heading">
          <h1 id="login-title">Entrar</h1>
        </header>
        <form onSubmit={submit} aria-busy={busy}>
          <div className="field">
            <label htmlFor="slug">Conta</label>
            <input id="slug" name="slug" placeholder="Identificador da conta" required autoComplete="organization" autoCapitalize="none" spellCheck={false} disabled={busy} />
          </div>
          <div className="field">
            <label htmlFor="email">E-mail</label>
            <input id="email" name="email" type="email" autoComplete="username" placeholder="voce@empresa.com.br" required autoCapitalize="none" spellCheck={false} disabled={busy} />
          </div>
          <div className="field">
            <label htmlFor="password">Senha</label>
            <div className="password-field">
              <input id="password" name="password" type={show ? 'text' : 'password'} autoComplete="current-password" maxLength={128} required placeholder="Sua senha" disabled={busy} />
              <button type="button" className="icon-btn" aria-label={show ? 'Ocultar senha' : 'Mostrar senha'} aria-pressed={show} onClick={() => setShow(!show)}>
                {show ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          {error && <div className="form-error" role="alert"><AlertCircle size={18} /><span>{error}</span></div>}
          <button className="btn btn-primary login-submit" disabled={busy} type="submit">
            {busy ? <><Loader2 size={18} className="spin" />Entrando…</> : <>Entrar<ArrowRight size={18} /></>}
          </button>
        </form>
        <nav className="login-legal" aria-label="Informações legais"><Link href="/privacidade">Privacidade</Link><Link href="/termos">Termos</Link><Link href="/exclusao-de-dados">Exclusão de dados</Link></nav>
      </section>
    </main>
  );
}
