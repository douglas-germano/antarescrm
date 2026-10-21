'use client';
import { useState } from 'react';
import { LogOut, Save } from 'lucide-react';
import { patch } from '@/lib/api';
import { useSession, useNotify } from '@/components/providers';
import { Button } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import { initials, roles } from '@/lib/format';

/** The signed-in person's own data, password and sign-out. */
export function ProfileSettings() {
  const { user, reload } = useSession();
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function saveProfile(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const raw = new FormData(form);
    const body: Record<string, unknown> = { name: raw.get('name'), title: (raw.get('title') as string) || null };
    const password = String(raw.get('password') || '');
    if (password) { body.password = password; body.current_password = raw.get('current_password'); }
    setBusy(true); setError('');
    try {
      await patch('/auth/me', body);
      if (password) { window.location.replace('/login'); return; }
      await reload();
      notify('Perfil atualizado.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
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
  return (
    <Card as="section">
      <CardHeader title="Meu perfil" description={`${user?.email || ''} · ${roles[user?.role || ''] || 'Equipe'}`}
        actions={<Button variant="secondary" onClick={logout}><LogOut size={16} /> Sair do sistema</Button>} />
      <CardBody>
        <form className="stack profile-form" onSubmit={saveProfile}>
          <div className="profile-identity"><span className="avatar">{initials(user?.name)}</span><strong>{user?.name}</strong></div>
          <div className="profile-row">
          <div className="field"><label htmlFor="profile-name">Nome</label>
            <input id="profile-name" name="name" defaultValue={user?.name} required maxLength={150} /></div>
          <div className="field"><label htmlFor="profile-title">Cargo / perfil</label>
            <input id="profile-title" name="title" defaultValue={user?.title || ''} maxLength={80} placeholder="Vendedor, SDR, Gerente…" /></div>
          </div>
          <fieldset className="stack">
            <legend className="small-caps">Alterar senha</legend>
            <div className="profile-row">
            <div className="field"><label htmlFor="profile-current">Senha atual</label>
              <input id="profile-current" name="current_password" type="password" autoComplete="current-password" maxLength={128} /></div>
            <div className="field"><label htmlFor="profile-new">Nova senha</label>
              <input id="profile-new" name="password" type="password" autoComplete="new-password" minLength={10} maxLength={128} /></div>
            </div>
            <small className="muted">A nova senha precisa de no mínimo 10 caracteres. Ao trocá-la, você será desconectado de todos os dispositivos.</small>
          </fieldset>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div><Button type="submit" disabled={busy}><Save size={16} /> {busy ? 'Salvando…' : 'Salvar'}</Button></div>
        </form>
      </CardBody>
    </Card>
  );
}
