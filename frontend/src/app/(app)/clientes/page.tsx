'use client';
import { useState } from 'react';
import { Plus, ArrowUpRight, Users, Pencil, Building2 } from 'lucide-react';
import { useSession, useNotify } from '@/components/providers';
import { useList, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { switchWorkspace, WorkspaceSwitcher } from '@/components/workspace-switcher';
import { PageHeader, Button, DataState, FormDialog, Modal, ConfirmDialog, EmptyState, Badge } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import type { Row, Field } from '@/lib/types';

export default function ClientAccounts() {
  const { user, workspace } = useSession();
  const allowed = workspace && !workspace.parent_workspace_id && user?.workspace_id === workspace.id && ['owner', 'admin'].includes(user?.role || '');
  const { data: accounts, isLoading, error } = useList(allowed ? '/agency/accounts' : null);
  const { data: staff } = useList(allowed ? '/users' : null);
  const { notify } = useNotify();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Row | null>(null);
  const [access, setAccess] = useState<Row | null>(null);
  const [revoking, setRevoking] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: grants, error: grantError, isLoading: grantsLoading } = useData<{ items: Row[] }>(access ? `/agency/accounts/${access.id}/access` : null);
  const creation: Field[] = [
    { name: 'workspace_name', label: 'Nome do cliente / conta', required: true, wide: true },
    { name: 'slug', label: 'Identificador de login', required: true, placeholder: 'cliente-exemplo', help: 'De 3 a 80 letras minúsculas, números e hífens.' },
    { name: 'timezone', label: 'Fuso horário', required: true, defaultValue: workspace?.timezone || 'America/Cuiaba' },
    { name: 'name', label: 'Nome do responsável do cliente', required: true, wide: true },
    { name: 'email', label: 'E-mail de acesso do cliente', type: 'email', required: true },
    { name: 'password', label: 'Senha inicial do cliente', type: 'password', required: true, help: 'No mínimo 10 caracteres. Nenhum e-mail será enviado automaticamente.' },
  ];
  if (!allowed) return <div className="page client-accounts-page"><PageHeader title="Contas de clientes" /><WorkspaceSwitcher /><EmptyState title="Contas de clientes" description="Acesse a conta da agência com um perfil de administrador para gerenciar os clientes." /></div>;
  return <div className="page client-accounts-page">
    <PageHeader title="Contas de clientes">
      <Button onClick={() => setCreating(true)}><Plus size={17} /> Nova conta</Button>
    </PageHeader>
    <WorkspaceSwitcher />
    
    <DataState loading={isLoading} error={error}>
      {!accounts?.length ? <EmptyState icon={<Building2 />} title="Nenhuma conta de cliente" action={<Button onClick={() => setCreating(true)}>Criar conta de cliente</Button>} /> :
      <div className="account-grid">{accounts.map((account) => <Card as="section" key={account.id}>
        <CardHeader title={account.name} description={`Login: ${account.slug}`} actions={<Badge value={account.active ? 'completed' : 'cancelled'} label={account.active ? 'Ativa' : 'Suspensa'} />} />
        <CardBody><p className="muted">{account.timezone}</p><div className="account-actions">
          <Button disabled={!account.active || busy} onClick={async () => { setBusy(true); try { await switchWorkspace(account.id, workspace.id); } catch (e) { notify((e as Error).message, 'error'); setBusy(false); } }}><ArrowUpRight size={16} /> Entrar na conta</Button>
          <Button variant="secondary" onClick={() => setAccess(account)}><Users size={16} /> Equipe</Button>
          <Button variant="ghost" aria-label={'Editar ' + account.name} onClick={() => setEditing(account)}><Pencil size={16} /></Button>
        </div></CardBody>
      </Card>)}</div>}
    </DataState>
    <FormDialog open={creating} onClose={() => setCreating(false)} title="Nova conta de cliente" fields={creation} submitLabel="Criar conta"
      description="O cliente entra no mesmo endereço do CRM, usando o identificador, e-mail e senha definidos aqui."
      onSubmit={async (data) => { await post('/agency/accounts', data); await refreshAll(); notify('Conta criada com acesso separado para o cliente.'); }} />
    <FormDialog open={!!editing} onClose={() => setEditing(null)} title="Configurar conta" initial={editing || {}} fields={[
      { name: 'name', label: 'Nome da conta', required: true }, { name: 'timezone', label: 'Fuso horário', required: true },
      { name: 'active', label: 'Conta ativa', type: 'checkbox', help: 'Desativar bloqueia o acesso da agência e do cliente aos dados desta conta.' },
    ]} onSubmit={async (data) => { await patch('/agency/accounts/' + editing!.id, data); await refreshAll(); notify('Conta atualizada.'); }} />
    <Modal open={!!access} onClose={() => setAccess(null)} title={'Equipe da agência — ' + (access?.name || '')} description="Administradores da agência já têm acesso. O cliente administra a própria equipe dentro da conta dele.">
      <DataState loading={grantsLoading} error={grantError}>
        <div className="stack">{grants?.items.map((grant) => <div className="account-grant" key={grant.id}><span><strong>{grant.user_name}</strong><small>{grant.role === 'admin' ? 'Administrador nesta conta' : 'Membro nesta conta'}</small></span><Button variant="ghost" onClick={() => setRevoking(grant)}>Revogar</Button></div>)}
          {!grants?.items.length && <p className="muted">Nenhum membro da agência recebeu acesso adicional.</p>}
        </div>
      </DataState>
      <form className="stack account-access-form" onSubmit={async (event) => {
        event.preventDefault(); const form = new globalThis.FormData(event.currentTarget); setBusy(true);
        try { await post(`/agency/accounts/${access!.id}/access`, { user_id: form.get('user_id'), role: form.get('role') }); await refreshAll(); notify('Acesso atualizado.'); }
        catch (e) { notify((e as Error).message, 'error'); } finally { setBusy(false); }
      }}><div className="field"><label htmlFor="agency-staff">Membro da agência</label><select id="agency-staff" name="user_id" required><option value="">Selecione…</option>{staff?.filter((u) => u.active && u.role === 'member').map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></div>
        <div className="field"><label htmlFor="client-role">Permissão nesta conta</label><select id="client-role" name="role" defaultValue="member"><option value="member">Membro — operação do CRM</option><option value="admin">Administrador — inclui equipe e configurações</option></select></div>
        <Button type="submit" disabled={busy}>{busy ? 'Salvando…' : 'Conceder / atualizar acesso'}</Button>
      </form>
    </Modal>
    <ConfirmDialog open={!!revoking} onClose={() => setRevoking(null)} title="Revogar acesso à conta?" description="A pessoa perde o acesso a esta conta imediatamente, inclusive nas sessões já abertas."
      onConfirm={async () => { await remove(`/agency/accounts/${access!.id}/access/${revoking!.user_id}`); await refreshAll(); notify('Acesso revogado.'); }} />
  </div>;
}
