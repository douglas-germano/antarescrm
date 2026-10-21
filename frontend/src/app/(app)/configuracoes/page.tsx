'use client';
import { useEffect, useState } from 'react';
import { Plus, Pencil, KeyRound, KanbanSquare, FolderKanban, Plug, UserCircle, Users, Building2, Save, Activity } from 'lucide-react';
import { ConnectionsSettings } from '@/components/connections-settings';
import { ProfileSettings } from '@/components/profile-settings';
import { ProjectStageSettings } from '@/components/project-stage-settings';
import { PipelineSettings } from '@/components/pipeline-settings';
import { OperationsSettings } from '@/components/operations-settings';
import { useSession, useNotify } from '@/components/providers';
import { useList, post, patch, refreshAll } from '@/lib/api';
import { PageHeader, DataState, Button, FormDialog, Badge } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { Card, CardHeader, CardBody, Tabs, Toolbar } from '@/components/blocks';
import { roles, opts, initials } from '@/lib/format';
import type { Row, Field } from '@/lib/types';

export default function SettingsPage() {
  const { user, workspace, reload } = useSession();
  const { notify } = useNotify();
  const canManage = ['owner', 'admin'].includes(user?.role || '');
  const { data: users, isLoading, error } = useList('/users');
  const [tab, setTab] = useState('profile');
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get('tab');
    if (canManage && requested === 'operacao') setTab('operations');
    if (requested === 'funis') setTab('pipelines');
    if (requested === 'projetos') setTab('projects');
    if (canManage && requested === 'conexoes') setTab('connections');
  }, [canManage]);
  function selectTab(value: string) {
    setTab(value);
    const url = new URL(window.location.href);
    if (value === 'operations') url.searchParams.set('tab', 'operacao');
    else if (value === 'pipelines') url.searchParams.set('tab', 'funis');
    else if (value === 'projects') url.searchParams.set('tab', 'projetos');
    else if (value === 'connections') url.searchParams.set('tab', 'conexoes');
    else url.searchParams.delete('tab');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
  }
  const [editUser, setEditUser] = useState<Row | null | false>(false);
  const [passwordUser, setPasswordUser] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const userFields: Field[] = [
    { name: 'name', label: 'Nome', required: true },
    ...(!editUser ? [{ name: 'email', label: 'E-mail', type: 'email' as const, required: true }] : []),
    ...(!editUser
      ? [{ name: 'password', label: 'Senha inicial', type: 'password' as const, required: true, help: 'No mínimo 10 caracteres.' }]
      : []),
    { name: 'title', label: 'Perfil / cargo', placeholder: 'Vendedor, SDR, Gerente…' },
    ...(!editUser || editUser.role !== 'owner'
      ? [
          {
            name: 'role',
            label: 'Nível',
            type: 'select' as const,
            options: opts(Object.fromEntries(Object.entries(roles).filter(([key]) => key !== 'owner'))),
            defaultValue: 'member',
          },
          { name: 'active', label: 'Acesso ativo', type: 'checkbox' as const, defaultValue: true },
        ]
      : []),
  ];
  async function saveWorkspace(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setFormError('');
    const raw = new FormData(e.currentTarget);
    try {
      await patch('/workspace', { name: raw.get('name'), timezone: raw.get('timezone') });
      await reload();
      notify('Dados da conta atualizados.');
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <PageHeader compact title="Configurações" />
      <Toolbar>
        <Tabs
          label="Seções"
          value={tab}
          onChange={selectTab}
          items={[
            { value: 'profile', label: 'Perfil', icon: <UserCircle size={14} /> },
            { value: 'workspace', label: 'Conta', icon: <Building2 size={14} /> },
            { value: 'team', label: 'Equipe', icon: <Users size={14} /> },
            { value: 'pipelines', label: 'Funis', icon: <KanbanSquare size={14} /> },
            { value: 'projects', label: 'Projetos', icon: <FolderKanban size={14} /> },
            ...(canManage ? [{ value: 'connections', label: 'Conexões', icon: <Plug size={14} /> }] : []),
            ...(canManage ? [{ value: 'operations', label: 'Operação', icon: <Activity size={14} /> }] : []),
          ]}
        />
        {tab === 'operations' && canManage && <Button variant="secondary" onClick={() => refreshAll()}>Atualizar estado</Button>}
      </Toolbar>
      {tab === 'operations' && canManage && <OperationsSettings />}
      {tab === 'profile' && <ProfileSettings />}
      {tab === 'pipelines' && <PipelineSettings />}
      {tab === 'projects' && <ProjectStageSettings />}
      {tab === 'connections' && canManage && <ConnectionsSettings />}
      {tab === 'workspace' && (
        <Card as="section">
          <CardHeader title="Conta" description={`Identificador de acesso: ${workspace?.slug || ''}`} />
          <CardBody>
            <form className="stack" onSubmit={saveWorkspace}>
              <fieldset disabled={!canManage} className="stack">
              <div className="field">
                <label htmlFor="name">Nome da conta</label>
                <input id="name" name="name" defaultValue={workspace?.name} required maxLength={150} />
              </div>
              <div className="field">
                <label htmlFor="timezone">Fuso horário</label>
                <input id="timezone" name="timezone" defaultValue={workspace?.timezone} required placeholder="America/Sao_Paulo" />
              </div>
              </fieldset>
              {!canManage && <p className="muted">Somente administradores podem alterar esta conta e gerenciar acessos.</p>}
              {formError && <p className="form-error" role="alert">{formError}</p>}
              {canManage && <div>
                <Button type="submit" disabled={busy}>
                  <Save size={16} /> {busy ? 'Salvando…' : 'Salvar'}
                </Button>
              </div>}
            </form>
          </CardBody>
        </Card>
      )}
      {tab === 'team' && (
        <Card as="section" fill>
          <CardHeader
            title="Perfis da equipe"
            actions={
              canManage ? <Button onClick={() => setEditUser(null)}>
                <Plus size={16} /> Novo perfil
              </Button> : undefined
            }
          />
          <DataState loading={isLoading} error={error}>
            <PagedTable
              rows={users || []}
              header={
                <tr>
                  <th>Pessoa</th>
                  <th>Cargo</th>
                  <th>Nível</th>
                  <th>Situação</th>
                  <th className="text-right">Ações</th>
                </tr>
              }
              renderRow={(u) => (
                <tr key={u.id}>
                  <td>
                    <div className="client-identity">
                      <span className="avatar">{initials(u.name)}</span>
                      <span>
                        {u.name}
                        <small className="muted"> {u.email}</small>
                      </span>
                    </div>
                  </td>
                  <td>{u.title || '—'}</td>
                  <td>{roles[u.role] || u.role}</td>
                  <td>
                    <Badge value={u.active ? 'completed' : 'cancelled'} label={u.active ? 'Ativo' : 'Inativo'} />
                  </td>
                  <td>
                    {canManage && u.workspace_id === workspace?.id && <div className="row-actions">
                      <Button variant="ghost" aria-label={'Editar ' + u.name} onClick={() => setEditUser(u)}>
                        <Pencil size={16} />
                      </Button>
                      <Button variant="ghost" aria-label={'Nova senha de ' + u.name} onClick={() => setPasswordUser(u)}>
                        <KeyRound size={16} />
                      </Button>
                    </div>}
                  </td>
                </tr>
              )}
            />
          </DataState>
        </Card>
      )}
      <FormDialog
        open={editUser !== false}
        onClose={() => setEditUser(false)}
        title={editUser ? 'Editar perfil' : 'Novo perfil'}
        fields={userFields}
        initial={editUser || { role: 'member', active: true }}
        onSubmit={async (data) => {
          const body = { ...data, title: data.title || null };
          if (editUser) await patch('/users/' + editUser.id, body);
          else await post('/users', body);
          await refreshAll();
          notify('Perfil salvo.');
          setEditUser(false);
        }}
      />
      <FormDialog
        open={!!passwordUser}
        onClose={() => setPasswordUser(null)}
        title={'Nova senha — ' + (passwordUser?.name || '')}
        description={passwordUser?.id === user?.id ? 'Você será desconectado dos outros dispositivos.' : 'Os acessos desta pessoa serão encerrados.'}
        fields={[{ name: 'password', label: 'Nova senha', type: 'password', required: true, help: 'No mínimo 10 caracteres.' }]}
        onSubmit={async (data) => {
          await patch('/users/' + passwordUser!.id, { password: data.password });
          notify('Senha atualizada.');
          setPasswordUser(null);
        }}
      />
    </div>
  );
}
