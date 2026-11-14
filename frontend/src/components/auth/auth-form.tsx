import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { ArrowRight, Loader2, Eye, EyeOff, AlertCircle, ArrowUpFromLine } from 'lucide-react';
import { ACCOUNT_KEY, AuthShell, PREFILL_KEY, readStorage, writeStorage } from '@/components/auth/auth-shell';

export function AuthForm({ openSubscription = false }: { openSubscription?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [show, setShow] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const [slug, setSlug] = useState('');
  const [remembered, setRemembered] = useState(false);
  const [email, setEmail] = useState('');
  // The account rarely changes, so the last one used on this browser comes pre-filled.
  useEffect(() => {
    const saved = readStorage('local', ACCOUNT_KEY);
    if (saved) { setSlug(saved); setRemembered(true); }
  }, []);

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
      writeStorage('local', ACCOUNT_KEY, String(data.slug).trim());
      window.location.replace(openSubscription ? '/assinatura' : '/');
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  const caps = (e: React.KeyboardEvent<HTMLInputElement>) => setCapsLock(e.getModifierState('CapsLock'));

  return (
    <AuthShell title="Entrar" subtitle="Acesse sua conta do Antares.">
      <form onSubmit={submit} aria-busy={busy} className="auth-form">
        <div className="field">
          <div className="auth-label-row">
            <label htmlFor="slug">Conta</label>
            {remembered && <button type="button" className="auth-link" onClick={() => { setSlug(''); setRemembered(false); writeStorage('local', ACCOUNT_KEY, null); document.getElementById('slug')?.focus(); }}>Usar outra conta</button>}
          </div>
          <input id="slug" name="slug" placeholder="Ex.: minhaempresa" required autoComplete="organization" autoCapitalize="none" spellCheck={false} disabled={busy}
            value={slug} onChange={(e) => setSlug(e.target.value)} />
          <small className="auth-hint">O identificador da sua empresa. Está no e-mail de convite e em Configurações › Conta.</small>
        </div>
        <div className="field">
          <label htmlFor="email">E-mail</label>
          <input id="email" name="email" type="email" autoComplete="username" placeholder="voce@empresa.com.br" required autoCapitalize="none" spellCheck={false} disabled={busy}
            autoFocus={remembered} value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <div className="auth-label-row">
            <label htmlFor="password">Senha</label>
            <Link to="/recuperar-acesso" className="auth-link" onClick={() => writeStorage('session', PREFILL_KEY, JSON.stringify({ slug, email }))}>Esqueci minha senha</Link>
          </div>
          <div className="password-field">
            <input id="password" name="password" type={show ? 'text' : 'password'} autoComplete="current-password" maxLength={128} required placeholder="Sua senha" disabled={busy}
              onKeyDown={caps} onKeyUp={caps} onBlur={() => setCapsLock(false)} />
            <button type="button" className="icon-btn" aria-label={show ? 'Ocultar senha' : 'Mostrar senha'} aria-pressed={show} onClick={() => setShow(!show)}>
              {show ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {capsLock && <small className="auth-warning" role="status"><ArrowUpFromLine size={13} />Caps Lock está ligado.</small>}
        </div>
        {error && <div className="form-error" role="alert"><AlertCircle size={18} /><span>{error}</span></div>}
        <button className="btn btn-primary auth-submit" disabled={busy} type="submit">
          {busy ? <><Loader2 size={18} className="spin" />Entrando…</> : <>Entrar<ArrowRight size={18} /></>}
        </button>
      </form>
    </AuthShell>
  );
}
