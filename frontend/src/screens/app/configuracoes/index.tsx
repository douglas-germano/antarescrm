import { useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from '@/lib/navigation';
import { KanbanSquare, FolderKanban, Plug, UserCircle, Users, Building2, Activity, Globe, Briefcase, Bell, CalendarClock, RefreshCw, Bot, KeyRound } from 'lucide-react';
import { AtlasSettings } from '@/components/settings/atlas-settings';
import { ConnectionsSettings } from '@/components/settings/connections-settings';
import { DomainsSettings } from '@/components/settings/domains-settings';
import { McpSettings } from '@/components/settings/mcp-settings';
import { ProfileSettings } from '@/components/settings/profile-settings';
import { ProjectStageSettings } from '@/components/settings/project-stage-settings';
import { PipelineSettings } from '@/components/settings/pipeline-settings';
import { OperationsSettings } from '@/components/settings/operations-settings';
import { ClientAccountsSettings } from '@/components/settings/client-accounts-settings';
import { NotificationSettings } from '@/components/settings/notification-settings';
import { BookingSettings } from '@/components/settings/booking-settings';
import { AccountSettings } from '@/components/settings/account-settings';
import { TeamSettings } from '@/components/settings/team-settings';
import { confirmLeave } from '@/components/settings/unsaved';
import { useSession } from '@/components/providers';
import { useData, refreshAll } from '@/lib/api';
import type { Workspace } from '@/lib/types';
import { PageHeader, Button } from '@/components/ui';

type Section = { key: string; label: string; icon: ReactNode; description: string; show?: boolean };

export default function SettingsPage() {
  const { user, workspace } = useSession();
  const canManage = ['owner', 'admin'].includes(user?.role || '');
  const agencyAdmin = workspace && !workspace.parent_workspace_id && user?.workspace_id === workspace.id && canManage;
  const { data: accessibleAccounts } = useData<{ items: Workspace[] }>(user ? '/auth/workspaces' : null);
  const canChooseAccount = !!(agencyAdmin || (workspace && user?.workspace_id !== workspace.id) || (accessibleAccounts?.items.length || 0) > 1);

  // Grouped like Gaio's settings; each section has its own address (?tab=…), so links and "back" land on it.
  const groups: { title: string; items: Section[] }[] = [
    { title: 'Pessoal', items: [
      { key: 'perfil', label: 'Perfil', icon: <UserCircle size={16} />, description: 'Seus dados, e-mail de acesso e senha' },
      { key: 'notificacoes', label: 'Notificações', icon: <Bell size={16} />, description: 'Avisos de novas mensagens' },
    ] },
    { title: 'Conta', items: [
      { key: 'conta', label: 'Conta', icon: <Building2 size={16} />, description: 'Nome, identificador e fuso horário' },
      { key: 'equipe', label: 'Equipe', icon: <Users size={16} />, description: 'Pessoas, níveis de acesso e convites' },
      { key: 'clientes', label: 'Clientes', icon: <Briefcase size={16} />, description: 'Contas de clientes da agência', show: canChooseAccount },
    ] },
    { title: 'Vendas e agenda', items: [
      { key: 'funis', label: 'Funis', icon: <KanbanSquare size={16} />, description: 'Funis de venda e etapas' },
      { key: 'projetos', label: 'Projetos', icon: <FolderKanban size={16} />, description: 'Etapas dos projetos' },
      { key: 'agendamento', label: 'Agendamento', icon: <CalendarClock size={16} />, description: 'Links públicos de agendamento' },
    ] },
    { title: 'IA', items: [
      { key: 'atlas', label: 'Atlas', icon: <Bot size={16} />, description: 'Roteiro de atendimento do Atlas', show: canManage },
    ] },
    { title: 'Integrações', items: [
      { key: 'conexoes', label: 'Conexões', icon: <Plug size={16} />, description: 'WhatsApp, Instagram, e-mail e ChatGPT', show: canManage },
      { key: 'mcp', label: 'Acesso para IAs', icon: <KeyRound size={16} />, description: 'Tokens MCP para Claude, ChatGPT e agentes', show: canManage },
      { key: 'dominios', label: 'Domínios', icon: <Globe size={16} />, description: 'Domínios próprios das páginas', show: canManage },
    ] },
    { title: 'Sistema', items: [
      { key: 'operacao', label: 'Operação', icon: <Activity size={16} />, description: 'Saúde do sistema e backups', show: canManage },
    ] },
  ].map((g) => ({ ...g, items: g.items.filter((i) => i.show !== false) })).filter((g) => g.items.length);
  const sections = groups.flatMap((g) => g.items);

  const [tab, setTab] = useState('perfil');
  const searchParams = useSearchParams();
  const OLD_KEYS: Record<string, string> = { profile: 'perfil', workspace: 'conta', team: 'equipe' };
  useEffect(() => {
    const requested = searchParams.get('tab') || 'perfil';
    const key = OLD_KEYS[requested] || requested;
    if (sections.some((s) => s.key === key)) setTab(key);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, canManage, canChooseAccount]);
  function selectTab(value: string) {
    if (value === tab || !confirmLeave()) return;
    setTab(value);
    const url = new URL(window.location.href);
    if (value === 'perfil') url.searchParams.delete('tab');
    else url.searchParams.set('tab', value);
    window.history.pushState(null, '', url.pathname + url.search + url.hash);
  }
  const current = sections.find((s) => s.key === tab) || sections[0];

  return (
    <div className="page settings-page">
      <PageHeader compact title="Configurações" />
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Seções das configurações">
          {groups.map((group) => (
            <div className="settings-nav-group" key={group.title}>
              <span className="settings-nav-title">{group.title}</span>
              {group.items.map((item) => (
                <button type="button" key={item.key} className={'settings-nav-item' + (item.key === tab ? ' active' : '')}
                  aria-current={item.key === tab ? 'page' : undefined} onClick={() => selectTab(item.key)}>
                  {item.icon}<span>{item.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="settings-content">
          <header className="settings-heading">
            <div><h2>{current.label}</h2><p>{current.description}</p></div>
            {tab === 'operacao' && <Button variant="soft" onClick={() => refreshAll()}><RefreshCw size={15} />Atualizar estado</Button>}
          </header>
          {tab === 'perfil' && <ProfileSettings key={user?.id} />}
          {tab === 'notificacoes' && <NotificationSettings />}
          {tab === 'conta' && <AccountSettings key={workspace?.id} canManage={canManage} />}
          {tab === 'equipe' && <TeamSettings canManage={canManage} />}
          {tab === 'clientes' && canChooseAccount && <ClientAccountsSettings />}
          {tab === 'funis' && <PipelineSettings />}
          {tab === 'projetos' && <ProjectStageSettings />}
          {tab === 'agendamento' && <BookingSettings />}
          {tab === 'atlas' && canManage && <AtlasSettings key={workspace?.id} />}
            {tab === 'conexoes' && canManage && <ConnectionsSettings />}
          {tab === 'mcp' && canManage && <McpSettings />}
          {tab === 'dominios' && canManage && <DomainsSettings />}
          {tab === 'operacao' && canManage && <OperationsSettings />}
        </div>
      </div>
    </div>
  );
}
