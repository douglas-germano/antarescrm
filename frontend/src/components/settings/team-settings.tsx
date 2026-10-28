'use client';
import { useState } from 'react';
import { KeyRound, Mail, Pencil, Plus, Users } from 'lucide-react';
import { useSession, useNotify } from '@/components/providers';
import { useList, post, patch, refreshAll } from '@/lib/api';
import type { Field, Row } from '@/lib/types';
import { DataState, Button, FormDialog, EmptyState, SearchInput } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { Card, CardHeader } from '@/components/blocks';
import { roles, opts, initials, searchMatch } from '@/lib/format';

/** People with access to the account: roles, invitations and password resets. */
export function TeamSettings({ canManage }: { canManage: boolean }) {
  const { user, workspace } = useSession();
  const { notify } = useNotify();
  const { data: users, isLoading, error } = useList('/users');
  const [search, setSearch] = useState('');
  const [editUser, setEditUser] = useState<Row | null | false>(false);
  const [passwordUser, setPasswordUser] = useState<Row | null>(null);
  const [inviting, setInviting] = useState(false);
  const rows = (users || []).filter((u) => searchMatch(search, [u.name, u.email, u.title, roles[u.role]]));
  const userFields: Field[] = [
    { name: 'name', label: 'Nome', required: true },
    ...(!editUser ? [{ name: 'email', label: 'E-mail', type: 'email' as const, required: true }] : []),
    ...(!editUser ? [{ name: 'password', label: 'Senha inicial', type: 'password' as const, required: true, help: 'No mínimo 10 caracteres.' }] : []),
    { name: 'title', label: 'Cargo', placeholder: 'Vendedor, SDR, Gerente…' },
    ...(!editUser || editUser.role !== 'owner'
      ? [
          { name: 'role', label: 'Nível de acesso', type: 'select' as const, options: opts(Object.fromEntries(Object.entries(roles).filter(([key]) => key !== 'owner'))), defaultValue: 'member' },
          { name: 'active', label: 'Acesso ativo', type: 'checkbox' as const, defaultValue: true },
        ]
      : []),
  ];
  const status = (u: Row) => (u.invite_pending ? ['pending', 'Convite pendente'] : u.active ? ['active', 'Ativo'] : ['inactive', 'Inativo']);
  return (
    <Card as="section" fill>
      <CardHeader
        title="Equipe"
        description={`${(users || []).length} ${(users || []).length === 1 ? 'pessoa' : 'pessoas'} com acesso a esta conta`}
        actions={<div className="row-actions">
          {(users || []).length > 5 && <SearchInput value={search} onChange={setSearch} placeholder="Buscar pessoa" />}
          {canManage && <>
            <Button variant="soft" onClick={() => setInviting(true)}><Mail size={16} />Convidar por e-mail</Button>
            <Button onClick={() => setEditUser(null)}><Plus size={16} />Novo perfil</Button>
          </>}
        </div>}
      />
      <DataState loading={isLoading} error={error}>
        {rows.length ? (
          <PagedTable
            rows={rows}
            header={<tr><th>Pessoa</th><th>Cargo</th><th>Nível</th><th>Situação</th><th /></tr>}
            renderRow={(u) => {
              const [tone, label] = status(u);
              return (
                <tr key={u.id} className="team-row">
                  <td>
                    <div className="client-identity">
                      <span className="avatar">{initials(u.name)}</span>
                      <span className="team-person"><strong>{u.name}{u.id === user?.id && <em> · você</em>}</strong><small className="muted">{u.email}</small></span>
                    </div>
                  </td>
                  <td>{u.title || <span className="muted">—</span>}</td>
                  <td><span className={'role-badge role-' + u.role}>{roles[u.role] || u.role}</span></td>
                  <td><span className={'team-status ' + tone}><i />{label}</span></td>
                  <td>
                    {canManage && u.workspace_id === workspace?.id && <div className="row-actions team-actions">
                      <button type="button" className="icon-btn" aria-label={'Editar ' + u.name} data-tip="Editar" onClick={() => setEditUser(u)}><Pencil size={15} /></button>
                      <button type="button" className="icon-btn" aria-label={'Definir nova senha de ' + u.name} data-tip="Definir nova senha" data-tip-align="end" onClick={() => setPasswordUser(u)}><KeyRound size={15} /></button>
                    </div>}
                  </td>
                </tr>
              );
            }}
          />
        ) : <EmptyState icon={<Users />} title="Ninguém encontrado" description={search ? 'Tente outro nome ou e-mail.' : undefined} />}
      </DataState>
      <FormDialog
        open={inviting} onClose={() => setInviting(false)} title="Convidar para a equipe"
        description="A pessoa receberá um link válido por 24 horas para definir sua própria senha. Para reenviar, informe o mesmo e-mail."
        fields={[{ name: 'name', label: 'Nome', required: true }, { name: 'email', label: 'E-mail', type: 'email', required: true },
          { name: 'role', label: 'Nível de acesso', type: 'select', required: true, defaultValue: 'member', options: opts({ member: 'Membro', admin: 'Administrador' }) }]}
        onSubmit={async (data) => {
          const result = await post<{ delivery_status: string }>('/users/invitations', data);
          await refreshAll(); setInviting(false);
          notify(result.delivery_status === 'sent' ? 'Convite enviado por e-mail.' : 'Convite criado, mas o envio está sem confirmação. Confira no Brevo antes de solicitar outro.', result.delivery_status === 'sent' ? undefined : 'error');
        }}
      />
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
    </Card>
  );
}
