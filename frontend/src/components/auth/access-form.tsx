'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, ArrowRight, Check, CircleCheck, Eye, EyeOff, Link2Off, Loader2, MailCheck } from 'lucide-react';
import { ACCOUNT_KEY, AuthShell, PREFILL_KEY, readStorage, writeStorage } from '@/components/auth/auth-shell';

const MIN_PASSWORD = 10;
const RESEND_SECONDS = 60;

/** Rough strength, only to guide the person: length matters most, variety helps. */
function strength(password: string) {
  if (!password) return { level: 0, label: '' };
  let score = password.length >= MIN_PASSWORD ? 1 : 0;
  if (password.length >= 14) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  if (password.length < MIN_PASSWORD) return { level: 1, label: 'Curta demais' };
  return score >= 4 ? { level: 3, label: 'Forte' } : score >= 2 ? { level: 2, label: 'Boa' } : { level: 1, label: 'Fraca' };
}

async function call(action: string, body: object) {
  const response = await fetch('/api/access/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || 'Não foi possível concluir. Tente novamente.');
  return result as { message: string };
}

/** "Esqueci minha senha": asks for a link, then confirms and lets the person resend after a minute. */
function RequestAccess() {
  const [form, setForm] = useState({ slug: '', email: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sent, setSent] = useState(false);
  const [wait, setWait] = useState(0);
  useEffect(() => {
    const prefill = readStorage('session', PREFILL_KEY);
    let from: { slug?: string; email?: string } = {};
    try { from = prefill ? JSON.parse(prefill) : {}; } catch { /* ignore a malformed value */ }
    setForm({ slug: from.slug || readStorage('local', ACCOUNT_KEY), email: from.email || '' });
  }, []);
  useEffect(() => {
    if (!wait) return;
    const timer = setTimeout(() => setWait((w) => w - 1), 1000);
    return () => clearTimeout(timer);
  }, [wait]);
  async function send(event?: React.FormEvent) {
    event?.preventDefault();
    if (busy) return;
    setBusy(true); setError('');
    try {
      await call('forgot-password', form);
      setSent(true); setWait(RESEND_SECONDS);
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  if (sent) {
    return (
      <AuthShell title="Verifique seu e-mail" footer={<Link href="/login">Voltar para entrar</Link>}>
        <div className="auth-result">
          <span className="auth-result-icon"><MailCheck size={26} /></span>
          <p>Se <strong>{form.email}</strong> tiver acesso à conta <strong>{form.slug}</strong>, enviamos um link para definir uma nova senha. Ele vale por 24 horas.</p>
          <p className="muted">Não chegou? Confira a caixa de spam ou o endereço digitado.</p>
          <button type="button" className="btn btn-secondary auth-submit" disabled={busy || wait > 0} onClick={() => send()}>
            {busy ? <><Loader2 size={18} className="spin" />Enviando…</> : wait > 0 ? `Reenviar em ${wait} s` : 'Reenviar link'}
          </button>
          <button type="button" className="auth-link" onClick={() => setSent(false)}>Usar outro e-mail</button>
          {error && <div className="form-error" role="alert"><AlertCircle size={18} /><span>{error}</span></div>}
        </div>
      </AuthShell>
    );
  }
  return (
    <AuthShell title="Recuperar acesso" subtitle="Enviaremos um link para você definir uma nova senha." footer={<Link href="/login">Voltar para entrar</Link>}>
      <form className="auth-form" aria-busy={busy} onSubmit={send}>
        <div className="field"><label htmlFor="access-account">Conta</label>
          <input id="access-account" autoComplete="organization" autoCapitalize="none" spellCheck={false} maxLength={80} required disabled={busy} placeholder="Ex.: minhaempresa"
            value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} /></div>
        <div className="field"><label htmlFor="access-email">E-mail</label>
          <input id="access-email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={254} required disabled={busy} placeholder="voce@empresa.com.br"
            autoFocus={!!form.slug && !form.email} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        {error && <div className="form-error" role="alert"><AlertCircle size={18} /><span>{error}</span></div>}
        <button className="btn btn-primary auth-submit" type="submit" disabled={busy}>{busy ? <><Loader2 size={18} className="spin" />Enviando…</> : 'Enviar link de acesso'}</button>
      </form>
    </AuthShell>
  );
}

/** "Definir senha" from an invitation or reset link: requirements shown live, then a way straight to login. */
function AcceptAccess() {
  const [token, setToken] = useState('');
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [show, setShow] = useState(false);
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const readLink = useRef(false);
  useEffect(() => {
    if (readLink.current) return;
    readLink.current = true;
    setToken(new URLSearchParams(window.location.hash.slice(1)).get('token') || '');
    window.history.replaceState(null, '', window.location.pathname); // Keep the token out of history.
    setReady(true);
  }, []);
  const long = password.length >= MIN_PASSWORD;
  const same = !!repeat && password === repeat;
  const s = strength(password);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !long || !same) return;
    setBusy(true); setError('');
    try {
      await call('accept-access', { token, password });
      setToken(''); setDone(true);
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  if (done) {
    return (
      <AuthShell title="Senha definida">
        <div className="auth-result">
          <span className="auth-result-icon ok"><CircleCheck size={26} /></span>
          <p>Pronto! Sua senha foi salva. Use-a com a conta e o e-mail do convite para entrar.</p>
          <Link href="/login" className="btn btn-primary auth-submit">Entrar agora<ArrowRight size={18} /></Link>
        </div>
      </AuthShell>
    );
  }
  if (ready && !token) {
    return (
      <AuthShell title="Link incompleto" footer={<Link href="/login">Voltar para entrar</Link>}>
        <div className="auth-result">
          <span className="auth-result-icon warn"><Link2Off size={26} /></span>
          <p>Este link não está completo ou já foi usado. Peça um novo link, ou um novo convite ao administrador da sua empresa.</p>
          <Link href="/recuperar-acesso" className="btn btn-primary auth-submit">Solicitar novo link</Link>
        </div>
      </AuthShell>
    );
  }
  const type = show ? 'text' : 'password';
  return (
    <AuthShell title="Definir senha" subtitle="Escolha a senha que você vai usar para entrar no Antares." footer={<Link href="/login">Voltar para entrar</Link>}>
      {!ready ? <p className="muted">Carregando…</p> : (
        <form className="auth-form" aria-busy={busy} onSubmit={submit}>
          <div className="field"><label htmlFor="access-password">Nova senha</label>
            <div className="password-field">
              <input id="access-password" type={type} autoComplete="new-password" maxLength={128} required disabled={busy} autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="icon-btn" aria-label={show ? 'Ocultar senhas' : 'Mostrar senhas'} aria-pressed={show} onClick={() => setShow(!show)}>{show ? <EyeOff size={18} /> : <Eye size={18} />}</button>
            </div>
            {password && <div className={'auth-strength level-' + s.level} aria-live="polite"><span><i /><i /><i /></span>{s.label}</div>}
          </div>
          <div className="field"><label htmlFor="access-confirmation">Confirme a nova senha</label>
            <input id="access-confirmation" type={type} autoComplete="new-password" maxLength={128} required disabled={busy} value={repeat} onChange={(e) => setRepeat(e.target.value)} /></div>
          <ul className="auth-rules" aria-label="Requisitos da senha">
            <li className={long ? 'ok' : ''}><Check size={14} />{MIN_PASSWORD} caracteres ou mais</li>
            <li className={same ? 'ok' : ''}><Check size={14} />As duas senhas conferem</li>
          </ul>
          {error && (
            <div className="form-error" role="alert"><AlertCircle size={18} /><span>{error} <Link href="/recuperar-acesso">Solicitar novo link</Link></span></div>
          )}
          <button className="btn btn-primary auth-submit" type="submit" disabled={busy || !long || !same}>{busy ? <><Loader2 size={18} className="spin" />Salvando…</> : 'Salvar senha'}</button>
        </form>
      )}
    </AuthShell>
  );
}

export function AccessForm({ mode }: { mode: 'request' | 'accept' }) {
  return mode === 'request' ? <RequestAccess /> : <AcceptAccess />;
}
