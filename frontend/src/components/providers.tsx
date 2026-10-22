'use client';
import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { usePathname } from 'next/navigation';
import { CheckCircle2, AlertCircle, X } from 'lucide-react';
import { useData, setActiveWorkspace } from '@/lib/api';
import { setZone } from '@/lib/format';
import type { User, Workspace } from '@/lib/types';
type Session = {
  user?: User;
  workspace?: Workspace;
  loading: boolean;
  error?: Error;
  reload: () => Promise<any>;
};
const SessionContext = createContext<Session>({ loading: true, reload: async () => {} });
const NoticeContext = createContext<{ notify: (message: string, type?: 'success' | 'error') => void }>({
  notify: () => {},
});
export function useSession() {
  return useContext(SessionContext);
}
export function useNotify() {
  return useContext(NoticeContext);
}
export function Providers({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const publicPage = ['/login', '/cadastro', '/privacidade', '/termos', '/exclusao-de-dados'].includes(pathname) || pathname.startsWith('/f/') || pathname.startsWith('/agendar/') || pathname.startsWith('/agendamento/') || pathname.startsWith('/aprovacao/');
  const { data, error, isLoading, mutate } = useData<{ user: User; workspace: Workspace }>(
    publicPage ? null : '/auth/me',
  );
  setActiveWorkspace(data?.workspace?.id);
  setZone(data?.workspace?.timezone);
  const [notices, setNotices] = useState<{ id: number; message: string; type: string }[]>([]);
  const toasts = useRef<HTMLDivElement>(null);
  // Open dialogs live in the browser's top layer and would cover the toasts (including error messages), so the
  // stack is promoted to the top layer too, each time a notice is added so that it sits above any open dialog.
  useEffect(() => {
    const el = toasts.current;
    if (!el || typeof el.showPopover !== 'function') return;
    if (el.matches(':popover-open')) el.hidePopover();
    if (notices.length) el.showPopover();
  }, [notices]);
  const notify = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    const id = Date.now() + Math.random();
    setNotices((n) => [...n.slice(-2), { id, message, type }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), 6000);
  }, []);
  return (
    <SessionContext.Provider
      value={{ user: data?.user, workspace: data?.workspace, loading: isLoading, error, reload: mutate }}
    >
      <NoticeContext.Provider value={{ notify }}>
        {children}
        <div className="toast-stack" aria-live="polite" popover="manual" ref={toasts}>
          {notices.map((n) => (
            <div className={'toast ' + n.type} key={n.id}>
              {n.type === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
              <span>{n.message}</span>
              <button
                aria-label="Fechar aviso"
                onClick={() => setNotices((a) => a.filter((x) => x.id !== n.id))}
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      </NoticeContext.Provider>
    </SessionContext.Provider>
  );
}
