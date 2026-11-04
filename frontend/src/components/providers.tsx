import { RecordLink } from '@/components/record-link';
import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { CheckCircle2, AlertCircle, MessageCircle, X } from 'lucide-react';
import { useData, setActiveWorkspace } from '@/lib/api';
import { setZone } from '@/lib/format';
import type { User, Workspace } from '@/lib/types';
type Session = {
  user?: User;
  workspace?: Workspace;
  loading: boolean;
  error?: Error;
  reload: () => Promise<unknown>;
};
const SessionContext = createContext<Session>({ loading: true, reload: async () => {} });
type NoticeAction = { href: string; label: string };
const NoticeContext = createContext<{ notify: (message: string, type?: 'success' | 'error' | 'message', action?: NoticeAction) => void; clearMessageNotices: () => void }>({
  notify: () => {}, clearMessageNotices: () => {},
});
export function useSession() {
  return useContext(SessionContext);
}
export function useNotify() {
  return useContext(NoticeContext);
}
/** Mounted only by the authenticated route group. Public pages never request a session. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data, error, isLoading, mutate } = useData<{ user: User; workspace: Workspace }>(
    '/auth/me',
  );
  setActiveWorkspace(data?.workspace?.id);
  setZone(data?.workspace?.timezone);
  useEffect(() => () => { setActiveWorkspace(undefined); }, []);
  return <SessionContext.Provider value={{ user: data?.user, workspace: data?.workspace, loading: isLoading, error, reload: mutate }}>
    {children}
  </SessionContext.Provider>;
}

/** Notifications are also available to public forms, without authentication side effects. */
export function Providers({ children }: { children: React.ReactNode }) {
  const [notices, setNotices] = useState<{ id: number; message: string; type: string; action?: NoticeAction }[]>([]);
  const toasts = useRef<HTMLDivElement>(null);
  // Open dialogs live in the browser's top layer and would cover the toasts (including error messages), so the
  // stack is promoted to the top layer too, each time a notice is added so that it sits above any open dialog.
  useEffect(() => {
    const el = toasts.current;
    if (!el || typeof el.showPopover !== 'function') return;
    if (el.matches(':popover-open')) el.hidePopover();
    if (notices.length) el.showPopover();
  }, [notices]);
  const notify = useCallback((message: string, type: 'success' | 'error' | 'message' = 'success', action?: NoticeAction) => {
    const id = Date.now() + Math.random();
    setNotices((n) => [...n.slice(-2), { id, message, type, action }]);
    setTimeout(() => setNotices((n) => n.filter((x) => x.id !== id)), 6000);
  }, []);
  const clearMessageNotices = useCallback(() => setNotices(current => current.filter(item => item.type !== 'message')), []);
  return (
      <NoticeContext.Provider value={{ notify, clearMessageNotices }}>
        {children}
        <div className="toast-stack" data-message-alerts={notices.some(notice => notice.type === 'message') || undefined} aria-live="polite" popover="manual" ref={toasts}>
          {notices.map((n) => (
            <div className={'toast ' + n.type} key={n.id}>
              {n.type === 'message' ? <MessageCircle size={20} /> : n.type === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
              <span>{n.message}{n.action && <RecordLink className="toast-action" href={n.action.href} onClick={() => setNotices(current => current.filter(item => item.id !== n.id))}>{n.action.label}</RecordLink>}</span>
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
  );
}
