'use client';
import { useState } from 'react';
import { Eye, EyeOff, KeyRound, LogOut, Save } from 'lucide-react';
import { patch } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { Button } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import { useUnsavedGuard } from '@/components/settings/unsaved';
import { initials, roles } from '@/lib/format';

const MIN_PASSWORD = 10;

/** The signed-in person's own data, login e-mail, password and sign-out, each block saved on its own. */
export function ProfileSettings() {
  const { user, reload } = useSession();
  const { notify } = useNotify();
  const saved = { name: user?.name || '', title: user?.title || '', email: user?.email || '' };
  const [form, setForm] = useState(saved);
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const emailChanged = form.email.trim().toLowerCase() !== saved.email.toLowerCase();
  const dirty = form.name !== saved.name || form.title !== saved.title || emailChanged;
  useUnsavedGuard('profile', dirty);

  const [secret, setSecret] = useState({ current: '', next: '', repeat: '' });
  const [show, setShow] = useState(false);
  const [secretBusy, setSecretBusy] = useState(false);
  const [secretError, setSecretError] = useState('');
  const mismatch = !!secret.repeat && secret.next !== secret.repeat;
  const short = !!secret.next && secret.next.length < MIN_PASSWORD;
  const ready = !!secret.current && secret.next.length >= MIN_PASSWORD && secret.next === secret.repeat;
  useUnsavedGuard('password', !!(secret.current || secret.next || secret.repeat));

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      await patch('/auth/me', {
        name: form.name.trim(), title: form.title.trim() || null,
        ...(emailChanged ? { email: form.email.trim(), current_password: confirmPassword } : {}),
      });
      await reload();
      setConfirmPassword('');
      notify(emailChanged ? 'Perfil atualizado. Use o novo e-mail no próximo acesso.' : 'Perfil atualizado.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function savePassword(e: React.FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setSecretBusy(true); setSecretError('');
    try {
      await patch('/auth/me', { current_password: secret.current, password: secret.next });
      window.location.replace('/login');
    } catch (err) {
      setSecretError((err as Error).message);
      setSecretBusy(false);
    }
  }
  async function logout() {
    try {
      const response = await fetch('/api/session/logout', { method: 'POST' });
      if (!response.ok) throw new Error('Não foi possível sair.');
      window.location.replace('/login');
    } catch (e) {
      notify((e as Error).message, 'error');
    }
  }
  const type = show ? 'text' : 'password';
  return (
    <div className="settings-stack">
      <Card as="section" className="profile-hero">
        <span className="avatar profile-avatar">{initials(user?.name)}</span>
        <div>
          <strong>{user?.name}</strong>
          <small>{user?.email}</small>
        </div>
        <span className={'role-badge role-' + (user?.role || 'member')}>{roles[user?.role || ''] || 'Equipe'}</span>
      </Card>

      <Card as="section">
        <CardHeader title="Dados pessoais" description="Como você aparece para a equipe e o e-mail que usa para entrar." />
        <CardBody>
          <form className="settings-form" onSubmit={saveProfile}>
            <div className="field"><label htmlFor="profile-name">Nome</label>
              <input id="profile-name" value={form.name} required maxLength={150} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div className="field"><label htmlFor="profile-title">Cargo</label>
              <input id="profile-title" value={form.title} maxLength={80} placeholder="Vendedor, SDR, Gerente…" onChange={(e) => setForm({ ...form, title: e.target.value })} />
              <small>Texto livre que aparece na equipe. O nível de acesso ({roles[user?.role || ''] || 'Equipe'}) é definido por um administrador.</small></div>
            <div className="field"><label htmlFor="profile-email">E-mail de acesso</label>
              <input id="profile-email" type="email" value={form.email} required maxLength={254} autoComplete="email" onChange={(e) => setForm({ ...form, email: e.target.value })} />
              <small>É o e-mail usado para entrar no Antares e receber links de acesso.</small></div>
            {emailChanged && (
              <div className="field settings-confirm"><label htmlFor="profile-confirm">Senha atual, para confirmar a troca de e-mail</label>
                <input id="profile-confirm" type="password" value={confirmPassword} required autoComplete="current-password" maxLength={128} onChange={(e) => setConfirmPassword(e.target.value)} /></div>
            )}
            {error && <p className="form-error" role="alert">{error}</p>}
            <div className="settings-actions">
              <Button type="submit" disabled={busy || !dirty || !form.name.trim()}><Save size={16} />{busy ? 'Salvando…' : 'Salvar dados'}</Button>
              {dirty && <Button variant="ghost" onClick={() => { setForm(saved); setConfirmPassword(''); setError(''); }}>Descartar</Button>}
            </div>
          </form>
        </CardBody>
      </Card>

      <Card as="section">
        <CardHeader title="Segurança" description="Troque a senha ou encerre esta sessão." />
        <CardBody>
          <form className="settings-form" onSubmit={savePassword}>
            <div className="field"><label htmlFor="profile-current">Senha atual</label>
              <input id="profile-current" type={type} value={secret.current} autoComplete="current-password" maxLength={128} onChange={(e) => setSecret({ ...secret, current: e.target.value })} /></div>
            <div className="field"><label htmlFor="profile-new">Nova senha</label>
              <div className="password-input">
                <input id="profile-new" type={type} value={secret.next} autoComplete="new-password" maxLength={128} onChange={(e) => setSecret({ ...secret, next: e.target.value })} />
                <button type="button" className="icon-btn" aria-label={show ? 'Ocultar senhas' : 'Mostrar senhas'} data-tip={show ? 'Ocultar' : 'Mostrar'} onClick={() => setShow(!show)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
              <small className={short ? 'text-danger' : ''}>No mínimo {MIN_PASSWORD} caracteres{secret.next ? ` · ${secret.next.length} digitados` : ''}.</small></div>
            <div className="field"><label htmlFor="profile-repeat">Confirme a nova senha</label>
              <input id="profile-repeat" type={type} value={secret.repeat} autoComplete="new-password" maxLength={128} onChange={(e) => setSecret({ ...secret, repeat: e.target.value })} />
              {mismatch && <small className="text-danger">As senhas não conferem.</small>}</div>
            {secretError && <p className="form-error" role="alert">{secretError}</p>}
            <p className="muted settings-note">Ao trocar a senha, você será desconectado de todos os dispositivos e entrará de novo com a senha nova.</p>
            <div className="settings-actions">
              <Button type="submit" disabled={secretBusy || !ready}><KeyRound size={16} />{secretBusy ? 'Trocando…' : 'Trocar senha'}</Button>
              <span className="spacer" />
              <Button variant="secondary" onClick={logout}><LogOut size={16} />Sair do sistema</Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
