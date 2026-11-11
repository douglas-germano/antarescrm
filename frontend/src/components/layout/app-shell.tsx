import { RecordLink } from '@/components/record-link';
import { Link } from '@tanstack/react-router';
import { usePathname } from '@/lib/navigation';
import { useEffect, useRef, useState } from 'react';
import {
  Fish,
  House,
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
  FileInput,
  Workflow,
  Filter,
  Mail,
  Instagram,
} from 'lucide-react';
import { useSession } from '@/components/providers';
import { useMessageNotifications } from '@/components/inbox/message-notifications';
import { DataState } from '@/components/ui';
const links = [
  { href: '/', label: 'Visão geral', icon: House },
  { href: '/mensagens', label: 'Caixa de entrada', icon: MessageCircle },
  { href: '/crm', label: 'Funil de vendas', icon: KanbanSquare },
  { href: '/automacoes', label: 'Automações', icon: Workflow },
  { href: '/campanhas', label: 'Campanhas', icon: Mail },
  { href: '/instagram', label: 'Instagram', icon: Instagram },
  { href: '/formularios', label: 'Formulários', icon: FileInput },
  { href: '/funis', label: 'Funis de páginas', icon: Filter },
  { href: '/contatos', label: 'Contatos', icon: Users },
  { href: '/empresas', label: 'Empresas', icon: Building2 },
  { href: '/projetos', label: 'Projetos', icon: FolderKanban },
  { href: '/tarefas', label: 'Tarefas', icon: CheckSquare },
  { href: '/agenda', label: 'Atividades', icon: CalendarDays },
  { href: '/pesca', label: 'Pesca', icon: Fish },
  { href: '/relatorios', label: 'Relatórios', icon: BarChart3 },
];
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, error } = useSession();
  const { count: unreadMessages } = useMessageNotifications();
  const inboxLabel = unreadMessages ? `Caixa de entrada: ${unreadMessages} ${unreadMessages === 1 ? 'mensagem não lida' : 'mensagens não lidas'}` : 'Caixa de entrada';
  const visibleLinks = links.filter(link => link.href !== '/campanhas' || ['owner', 'admin'].includes(user?.role || ''));
  const navigation = visibleLinks;
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // One floating label for the whole rail: the nav scrolls, so a per-item tooltip would be clipped.
  const [tip, setTip] = useState<{ label: string; top: number } | null>(null);
  const tipProps = (label: string) => ({
    onMouseEnter: (event: React.MouseEvent<HTMLElement>) => showTip(event.currentTarget, label),
    onFocus: (event: React.FocusEvent<HTMLElement>) => showTip(event.currentTarget, label),
    onMouseLeave: () => setTip(null),
    onBlur: () => setTip(null),
  });
  function showTip(target: HTMLElement, label: string) {
    if (open) return;
    const rect = target.getBoundingClientRect();
    setTip({ label, top: rect.top + rect.height / 2 });
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
    <div className="app">
      <a href="#main-content" className="skip-link">
        Ir para o conteúdo
      </a>
      {open && <div className="sidebar-scrim" onClick={() => { setOpen(false); menuRef.current?.focus(); }} />}
      <aside id="app-sidebar" ref={sidebarRef} className={'sidebar ' + (open ? 'sidebar-open' : '')}>
        <div className="sidebar-header">
          <Link to="/" className="brand" onClick={() => setOpen(false)} aria-label="Antares CRM — visão geral">
            <img src="/mark.svg" width="36" height="36" alt="" />
            <span>antares<strong>crm</strong></span>
          </Link>
          <button className="sidebar-close" aria-label="Fechar navegação" onClick={() => { setOpen(false); menuRef.current?.focus(); }}><X size={18} /></button>
        </div>
        <nav aria-label="Navegação principal">
          {navigation.map((l) => (
            <RecordLink key={l.href} href={l.href}
              aria-label={l.href === '/mensagens' ? inboxLabel : l.label}
              {...tipProps(l.label)}
              className={active?.href === l.href ? 'active' : ''}
              aria-current={active?.href === l.href ? 'page' : undefined}
              onClick={() => setOpen(false)}>
              <l.icon size={20} strokeWidth={1.7} />
              <span>{l.label}</span>
              {l.href === '/mensagens' && unreadMessages > 0 && <strong className="nav-unread-count" aria-hidden="true">{unreadMessages > 99 ? '99+' : unreadMessages}</strong>}
            </RecordLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <Link
            className={'settings-link ' + (pathname === '/configuracoes' ? 'active' : '')}
            aria-label="Configurações"
            {...tipProps('Configurações')}
            aria-current={pathname === '/configuracoes' ? 'page' : undefined}
            to="/configuracoes"
            onClick={() => setOpen(false)}
          >
            <Settings size={20} strokeWidth={1.7} />
            <span>Configurações</span>
          </Link>
        </div>
      </aside>
      {tip && <div className="sidebar-tooltip" role="tooltip" style={{ top: tip.top }}>{tip.label}</div>}
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
