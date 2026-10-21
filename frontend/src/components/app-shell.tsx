'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import {
  LayoutDashboard,
  MessageCircle,
  Users,
  Building2,
  KanbanSquare,
  FolderKanban,
  CheckSquare,
  CalendarDays,
  BarChart3,
  Settings,
  Menu,
  X,
  ChevronRight,
  PanelLeftClose,
  FileInput,
  Workflow,
} from 'lucide-react';
import { useSession } from './providers';
import { useData } from '@/lib/api';
import type { Workspace } from '@/lib/types';
import { DataState } from './ui';
const links = [
  { href: '/', label: 'Visão geral', icon: LayoutDashboard },
  { href: '/contatos', label: 'Contatos', icon: Users },
  { href: '/empresas', label: 'Empresas', icon: Building2 },
  { href: '/crm', label: 'Funil de vendas', icon: KanbanSquare },
  { href: '/projetos', label: 'Projetos', icon: FolderKanban },
  { href: '/mensagens', label: 'Caixa de entrada', icon: MessageCircle },
  { href: '/tarefas', label: 'Tarefas', icon: CheckSquare },
  { href: '/agenda', label: 'Atividades', icon: CalendarDays },
  { href: '/formularios', label: 'Formulários', icon: FileInput },
  { href: '/automacoes', label: 'Automações', icon: Workflow },
  { href: '/relatorios', label: 'Relatórios', icon: BarChart3 },
];
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, workspace, loading, error } = useSession();
  const agencyAdmin = workspace && !workspace.parent_workspace_id && user?.workspace_id === workspace.id && ['owner', 'admin'].includes(user?.role || '');
  const { data: accessibleAccounts } = useData<{ items: Workspace[] }>(user ? '/auth/workspaces' : null);
  const canChooseAccount = agencyAdmin || (workspace && user?.workspace_id !== workspace.id) || (accessibleAccounts?.items.length || 0) > 1;
  const navigation = canChooseAccount ? [...links, { href: '/clientes', label: 'Contas de clientes', icon: Building2 }] : links;
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    try { setCollapsed(localStorage.getItem('antares.sidebar.collapsed') === 'true'); } catch { /* Storage may be unavailable. */ }
  }, []);
  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem('antares.sidebar.collapsed', String(next)); } catch { /* Keep the current session usable. */ }
  }
  const menuRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    sidebarRef.current?.querySelector<HTMLAnchorElement>('a')?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        menuRef.current?.focus();
      }
      if (event.key !== 'Tab') return;
      const targets = Array.from(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])') || []);
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);
  const active = navigation.find((l) => (l.href === '/' ? pathname === '/' : pathname === l.href || pathname.startsWith(l.href + '/')));
  return (
    <div className={'app' + (collapsed ? ' sidebar-collapsed' : '')}>
      <a href="#main-content" className="skip-link">
        Ir para o conteúdo
      </a>
      {open && <div className="sidebar-scrim" onClick={() => setOpen(false)} />}
      <aside id="app-sidebar" ref={sidebarRef} className={'sidebar ' + (open ? 'sidebar-open' : '')}>
        <button className="sidebar-toggle" type="button" onClick={toggleSidebar}
          aria-label={collapsed ? 'Expandir sidebar' : 'Recolher sidebar'}
          title={collapsed ? 'Expandir sidebar' : 'Recolher sidebar'}
          aria-expanded={!collapsed} aria-controls="app-sidebar">
          <PanelLeftClose size={16} strokeWidth={1.8} />
        </button>
        <div className="sidebar-header">
          <Link href="/" className="brand" onClick={() => setOpen(false)} aria-label="Antares CRM — visão geral">
            <img src="/mark.svg" width="40" height="40" alt="" />
            <span>antares<strong>crm</strong></span>
          </Link>
          <button className="sidebar-close" aria-label="Fechar navegação" onClick={() => { setOpen(false); menuRef.current?.focus(); }}><X size={18} /></button>
        </div>
        <nav aria-label="Navegação principal">
          {navigation.map((l) => (
            <Link key={l.href} href={l.href} aria-label={l.label} title={l.label}
              className={active?.href === l.href ? 'active' : ''}
              aria-current={active?.href === l.href ? 'page' : undefined}
              onClick={() => setOpen(false)}>
              <l.icon size={20} strokeWidth={1.7} />
              <span>{l.label}</span>
              {active?.href === l.href && <ChevronRight className="nav-active-arrow" size={14} />}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link
            className={'settings-link ' + (pathname === '/configuracoes' ? 'active' : '')}
            aria-label="Configurações"
            title="Configurações"
            aria-current={pathname === '/configuracoes' ? 'page' : undefined}
            href="/configuracoes"
            onClick={() => setOpen(false)}
          >
            <Settings size={20} />
            <span>Configurações</span>
          </Link>
        </div>
      </aside>
      <button
        ref={menuRef}
        aria-controls="app-sidebar"
        className="mobile-menu"
        aria-label={open ? 'Fechar menu' : 'Abrir menu'}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      <div className="app-content">
        <main id="main-content" className="main-content">
          <DataState loading={loading} error={error}>
            {user ? children : null}
          </DataState>
        </main>
      </div>
    </div>
  );
}
