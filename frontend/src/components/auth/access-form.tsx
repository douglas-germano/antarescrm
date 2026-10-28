'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

export function AccessForm({ mode }: { mode: 'request' | 'accept' }) {
  const [token, setToken] = useState('');
  const [ready, setReady] = useState(mode === 'request');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const readLink = useRef(false);
  useEffect(() => {
    if (mode === 'accept' && !readLink.current) {
      readLink.current = true;
      setToken(new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
      window.history.replaceState(null, '', window.location.pathname);
      setReady(true);
    }
  }, [mode]);
  return <main className="login-page"><section className="login-card" aria-labelledby="access-title">
    <div className="login-brand"><img src="/mark.svg" width="40" height="40" alt="" /><span>antares<strong>crm</strong></span></div>
    <header className="login-heading"><h1 id="access-title">{mode === 'request' ? 'Recuperar acesso' : 'Definir senha'}</h1><p>{mode === 'request' ? 'Informe a conta e o e-mail do seu usuário.' : 'Escolha uma senha com pelo menos 10 caracteres.'}</p></header>
    {done ? <p role="status">{done}</p> : !ready ? <p>Carregando…</p> : mode === 'accept' && !token ? <p role="alert">O link está incompleto. Solicite um novo acesso ou peça outro convite ao administrador.</p> : <form aria-busy={busy} onSubmit={async event => {
      event.preventDefault(); if (busy) return;
      const data = new FormData(event.currentTarget);
      if (mode === 'accept' && data.get('password') !== data.get('confirmation')) { setError('As senhas não conferem.'); return; }
      setBusy(true); setError('');
      try {
        const response = await fetch('/api/access/' + (mode === 'request' ? 'forgot-password' : 'accept-access'), {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(mode === 'request' ? { slug: data.get('slug'), email: data.get('email') } : { token, password: data.get('password') }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error?.message || 'Não foi possível concluir. Tente novamente.');
        setToken(''); setDone(result.message);
      } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
    }}>
      {mode === 'request' ? <>
        <div className="field"><label htmlFor="access-account">Conta</label><input id="access-account" name="slug" autoComplete="organization" autoCapitalize="none" maxLength={80} required disabled={busy} /></div>
        <div className="field"><label htmlFor="access-email">E-mail</label><input id="access-email" name="email" type="email" autoComplete="username" maxLength={254} required disabled={busy} /></div>
      </> : <>
        <div className="field"><label htmlFor="access-password">Nova senha</label><input id="access-password" name="password" type="password" autoComplete="new-password" minLength={10} maxLength={128} required disabled={busy} /></div>
        <div className="field"><label htmlFor="access-confirmation">Confirmar senha</label><input id="access-confirmation" name="confirmation" type="password" autoComplete="new-password" minLength={10} maxLength={128} required disabled={busy} /></div>
      </>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="btn btn-primary login-submit" type="submit" disabled={busy}>{busy ? 'Aguarde…' : mode === 'request' ? 'Solicitar link de acesso' : 'Salvar nova senha'}</button>
    </form>}
    <nav className="login-legal"><Link href="/login">Voltar para entrar</Link>{mode === 'accept' && <Link href="/recuperar-acesso">Solicitar novo link</Link>}</nav>
  </section></main>;
}
