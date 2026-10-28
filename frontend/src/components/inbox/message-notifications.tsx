'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { Bell, CheckCheck, MessageCircle } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useNotify, useSession } from '@/components/providers';
import { Button, DataState, EmptyState, Modal } from '@/components/ui';
import { api, post } from '@/lib/api';
import { getZone } from '@/lib/format';
import type { Row } from '@/lib/types';
import styles from './message-notifications.module.css';

type Cursor = { id: string; created_at: string };
type Notice = Cursor & { source: string; thread_id: string; message_id: string; channel: string; sender_name: string; preview: string; unread_count: number };
type Feed = { items: Notice[]; total_unread: number; unread_threads: number; cursor: Cursor | null };
type ActiveThread = { source: string; id: string };
type BrowserPermission = NotificationPermission | 'unsupported';
const names: Record<string, string> = { whatsapp: 'WhatsApp', instagram: 'Instagram', email: 'E-mail', sms: 'SMS' };
const conversationUrl = (row: Notice) => '/mensagens?' + new URLSearchParams({ source: row.source, conversation: row.thread_id });
const after = (row: Cursor, baseline: Cursor) => row.created_at > baseline.created_at || (row.created_at === baseline.created_at && row.id > baseline.id);
const NotificationContext = createContext({ count: 0, items: [] as Notice[], open: () => {}, setActive: (_thread: ActiveThread | null) => {}, read: async (_source: string, _thread: string, _message: string) => {}, browser: { enabled: false, permission: 'default' as BrowserPermission, busy: false, error: '', toggle: async () => {} } });
export const useMessageNotifications = () => useContext(NotificationContext);

/** Claim the alert across tabs; nothing personal is stored in the shared ledger. */
async function claimAlert(scope: string, row: Notice) {
  const claim = () => {
    try {
      const viewing = JSON.parse(localStorage.getItem('antares.active-message-thread.' + scope) || 'null');
      if (viewing?.source === row.source && viewing.id === row.thread_id && Date.now() - viewing.at < 15000) return false;
      const identifier = row.id;
      const key = 'antares.message-alerts.' + scope;
      const seen: string[] = JSON.parse(localStorage.getItem(key) || '[]');
      if (seen.includes(identifier)) return false;
      localStorage.setItem(key, JSON.stringify([...seen.slice(-199), identifier]));
    } catch { /* In-app notifications remain usable without browser storage. */ }
    return true;
  };
  if (navigator.locks) return navigator.locks.request('antares.message-alerts.' + scope, claim);
  return claim();
}

export function MessageNotificationProvider({ children }: { children: React.ReactNode }) {
  const { user, workspace } = useSession();
  return <ScopedMessageNotificationProvider key={`${workspace?.id || ''}.${user?.id || ''}`}>{children}</ScopedMessageNotificationProvider>;
}

function ScopedMessageNotificationProvider({ children }: { children: React.ReactNode }) {
  const { user, workspace } = useSession();
  const { notify, clearMessageNotices } = useNotify();
  const router = useRouter();
  const scope = `${workspace?.id || ''}.${user?.id || ''}`;
  const feed = useSWR<Feed>(user && workspace ? ['message-notifications', workspace.id, user.id] : null, () => api('/inbox/notifications'), { refreshInterval: 5000, refreshWhenHidden: true, revalidateOnFocus: true, shouldRetryOnError: false });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [desktop, setDesktop] = useState(false);
  const [permission, setPermission] = useState<BrowserPermission>('default');
  const [desktopBusy, setDesktopBusy] = useState(false);
  const [desktopError, setDesktopError] = useState('');
  const active = useRef<ActiveThread | null>(null);
  const tabId = useRef('');
  const baseline = useRef<Cursor | null | undefined>(undefined);
  const seen = useRef(new Set<string>());
  const denied = [401, 403, 409].includes(feed.error?.status);
  const count = denied ? 0 : feed.data?.total_unread || 0;
  const notifications = denied ? [] : feed.data?.items || [];
  const native = useRef(new Set<Notification>());
  const publishActive = useCallback(() => {
    if (!tabId.current) tabId.current = crypto.randomUUID();
    try {
      const key = 'antares.active-message-thread.' + scope;
      if (active.current && document.visibilityState === 'visible' && document.hasFocus()) localStorage.setItem(key, JSON.stringify({ ...active.current, owner: tabId.current, at: Date.now() }));
      else if (JSON.parse(localStorage.getItem(key) || 'null')?.owner === tabId.current) localStorage.removeItem(key);
    } catch { /* optional cross-tab coordination */ }
  }, [scope]);
  const setActive = useCallback((thread: ActiveThread | null) => { active.current = thread; publishActive(); }, [publishActive]);
  useEffect(() => {
    const timer = setInterval(publishActive, 5000);
    document.addEventListener('visibilitychange', publishActive); window.addEventListener('focus', publishActive); window.addEventListener('blur', publishActive);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', publishActive); window.removeEventListener('focus', publishActive); window.removeEventListener('blur', publishActive); active.current = null; publishActive(); };
  }, [publishActive]);
  useEffect(() => {
    setPermission('Notification' in window ? Notification.permission : 'unsupported');
    try { setDesktop(localStorage.getItem('antares.desktop-alerts.' + scope) === 'true'); } catch { /* optional preference */ }
    const syncPreference = (event: StorageEvent) => {
      if (event.key !== 'antares.desktop-alerts.' + scope) return;
      setDesktop(event.newValue === 'true');
      setPermission('Notification' in window ? Notification.permission : 'unsupported');
    };
    window.addEventListener('storage', syncPreference);
    return () => { window.removeEventListener('storage', syncPreference); clearMessageNotices(); for (const item of native.current) item.close(); native.current.clear(); };
  }, [scope, clearMessageNotices]);
  useEffect(() => {
    if (!feed.error || denied) return;
    const timer = setTimeout(() => { void feed.mutate().catch(() => {}); }, 15000);
    return () => clearTimeout(timer);
  }, [feed.error, feed.mutate, denied]);
  useEffect(() => { if (denied) { clearMessageNotices(); for (const item of native.current) item.close(); } }, [denied, clearMessageNotices]);
  useEffect(() => {
    document.title = `${count ? `(${count}) ` : ''}Antares CRM`;
    return () => { document.title = 'Antares CRM'; };
  }, [count]);
  useEffect(() => {
    if (!feed.data || denied) return;
    if (baseline.current === undefined) {
      baseline.current = feed.data.cursor;
      feed.data.items.forEach(row => seen.current.add(row.id));
      return;
    }
    const fresh = feed.data.items.filter(row => !seen.current.has(row.id) && (!baseline.current || after(row, baseline.current)));
    feed.data.items.forEach(row => seen.current.add(row.id));
    if (seen.current.size > 5000) { baseline.current = feed.data.cursor; seen.current = new Set(feed.data.items.map(row => row.id)); }
    let alive = true;
    for (const row of fresh) {
      if (document.visibilityState === 'visible' && document.hasFocus() && active.current?.source === row.source && active.current.id === row.thread_id) continue;
      void claimAlert(scope, row).then(claimed => {
        if (!claimed || !alive) return;
        notify(`${row.sender_name} · ${names[row.channel] || row.channel}: ${row.preview || 'Nova mensagem'}`, 'message', { label: 'Abrir conversa', href: conversationUrl(row) });
        if (desktop && 'Notification' in window && Notification.permission === 'granted' && (document.visibilityState !== 'visible' || !document.hasFocus())) {
          try {
            const item = new Notification('Nova mensagem · ' + row.sender_name, { body: names[row.channel] || 'Antares CRM', icon: '/mark.svg', tag: scope + '.' + row.id });
            native.current.add(item);
            item.onclose = () => native.current.delete(item);
            item.onclick = () => { window.focus(); router.push(conversationUrl(row)); item.close(); };
          } catch { setDesktop(false); setPermission('unsupported'); }
        }
      });
    }
    return () => { alive = false; };
  }, [feed.data, scope, notify, desktop, router, denied]);
  const read = useCallback(async (source: string, thread: string, message: string) => {
    await post('/inbox/notifications/read', { source, thread_id: thread, message_id: message });
    await feed.mutate();
  }, [feed.mutate]);
  async function toggleDesktop() {
    if (!('Notification' in window) || desktopBusy) return;
    setDesktopBusy(true); setDesktopError('');
    try {
      const result = desktop ? Notification.permission : await Notification.requestPermission();
      setPermission(result);
      const enabled = !desktop && result === 'granted';
      setDesktop(enabled);
      try { localStorage.setItem('antares.desktop-alerts.' + scope, String(enabled)); } catch { /* optional preference */ }
    } catch { setDesktopError('Este navegador não permitiu ativar os avisos. Os avisos dentro do sistema continuam disponíveis.'); }
    finally { setDesktopBusy(false); }
  }
  return <NotificationContext.Provider value={{ count, items: notifications, open: () => setOpen(true), setActive, read, browser: { enabled: desktop, permission, busy: desktopBusy, error: desktopError, toggle: toggleDesktop } }}>
    {children}
    <Modal open={open} onClose={() => setOpen(false)} title="Notificações de mensagens">
      <div className="stack">
        <div className={styles.controls}>
          <p>{feed.error && (!feed.data || denied) ? 'Atualização de notificações indisponível.' : count ? `${count} ${count === 1 ? 'mensagem não lida' : 'mensagens não lidas'} em ${feed.data?.unread_threads || 0} ${(feed.data?.unread_threads || 0) === 1 ? 'conversa' : 'conversas'}.` : 'Nenhuma mensagem não lida.'}</p>
          <Button variant="secondary" disabled={busy || !count} onClick={async () => {
            setBusy(true); setError('');
            try { await post('/inbox/notifications/read-all', {}); await feed.mutate(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
          }}><CheckCheck size={16} />Marcar todas como lidas</Button>
        </div>
        {(error || (feed.error && feed.data && !denied)) && <p className="form-error" role="alert">{error || 'Não foi possível atualizar as notificações. A próxima consulta tentará novamente.'}</p>}
        <DataState loading={feed.isLoading} error={feed.error && (!feed.data || denied) ? { message: 'Não foi possível atualizar as notificações. Tente novamente em instantes.' } : undefined}>
          {notifications.length ? <ul className={styles.list}>{notifications.map(row => <li key={row.id}>
            <Link href={conversationUrl(row)} onClick={() => setOpen(false)}><MessageCircle size={20} /><div><strong>{row.sender_name}<span>{row.unread_count}</span></strong><small>{names[row.channel]} · {new Date(row.created_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short', timeZone: getZone() })}</small><p>{row.preview || 'Nova mensagem recebida'}</p></div></Link>
            <button type="button" className="icon-btn" aria-label={'Marcar mensagens de ' + row.sender_name + ' como lidas'} onClick={() => { void read(row.source, row.thread_id, row.message_id).catch(reason => setError((reason as Error).message)); }}><CheckCheck size={17} /></button>
          </li>)}</ul> : <EmptyState icon={<Bell />} title="Tudo em dia" description="Novas mensagens recebidas aparecerão aqui." />}
        </DataState>
        {(feed.data?.unread_threads || 0) > 20 && <small className="muted">Exibindo as 20 conversas mais recentes.</small>}
        <Link href="/configuracoes?tab=notificacoes" onClick={() => setOpen(false)}>Preferências de notificações</Link>
      </div>
    </Modal>
  </NotificationContext.Provider>;
}

export function MessageNotificationButton() {
  const { count, open } = useMessageNotifications();
  return <button type="button" className={'icon-btn ' + styles.trigger} onClick={open} aria-label={`Notificações de mensagens${count ? `: ${count} não lidas` : ''}`} data-tip="Mensagens não lidas"><Bell size={18} />{count > 0 && <span className={styles.badge}>{count > 99 ? '99+' : count}</span>}</button>;
}

/** Only acknowledge the most recent received message that has actually loaded on a visible chat. */
export function useReadIncomingMessages(source: string, threadId: string, messages: Row[]) {
  const { read, setActive, items } = useMessageNotifications();
  const last = messages.filter(row => row.direction === 'in').reduce<Row | null>((latest, row) => !latest || row.created_at > latest.created_at || (row.created_at === latest.created_at && row.id > latest.id) ? row : latest, null);
  const pending = items.find(row => row.source === source && row.thread_id === threadId && messages.some(message => message.id === row.message_id));
  const lastId = pending?.message_id || last?.id;
  const acknowledged = useRef('');
  useEffect(() => {
    setActive({ source, id: threadId });
    return () => setActive(null);
  }, [source, threadId, setActive]);
  useEffect(() => {
    let alive = true;
    const attempt = () => {
      if (!lastId || document.visibilityState !== 'visible' || !document.hasFocus() || acknowledged.current === lastId) return;
      acknowledged.current = lastId;
      void read(source, threadId, lastId).catch(() => { if (alive) acknowledged.current = ''; });
    };
    attempt(); document.addEventListener('visibilitychange', attempt); window.addEventListener('focus', attempt);
    return () => { alive = false; document.removeEventListener('visibilitychange', attempt); window.removeEventListener('focus', attempt); };
  }, [source, threadId, lastId, read]);
}
