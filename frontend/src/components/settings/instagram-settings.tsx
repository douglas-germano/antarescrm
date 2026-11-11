import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { Instagram, Plus } from 'lucide-react';
import { initials } from '@/lib/format';
import { post, useData } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, ConfirmDialog, DataState } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import { HistorySync } from '@/components/settings/history-sync';
import type { Row } from '@/lib/types';

type Listing = { configured: boolean; connected: boolean; connection: Row | null; connections: Row[] };

function Avatar({ account }: { account: Row }) {
  const [failed, setFailed] = useState(false);
  return account.profile_picture_url && !failed
    ? <img src={account.profile_picture_url} alt={'Foto de perfil de @' + account.username} width={56} height={56} referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    : <span className="ig-avatar" aria-hidden>{initials(account.name || account.username)}</span>;
}

function AccountCard({ account, onChanged, onConnect, busy }: { account: Row; onChanged: () => Promise<unknown>; onConnect: () => void; busy: boolean }) {
  const { notify } = useNotify();
  const [working, setWorking] = useState(false);
  const [delivery, setDelivery] = useState<Row | null>(null);
  const [disconnect, setDisconnect] = useState(false);
  const body = { connection_id: account.id };
  const run = async (fn: () => Promise<void>) => {
    setWorking(true);
    try { await fn(); } catch (e) { notify((e as Error).message, 'error'); } finally { setWorking(false); }
  };
  const missing = account.connected && (!account.can_publish || !account.can_read_insights);
  return <li className="ig-account">
    <div className="ig-profile">
      <Avatar account={account} />
      <div>
        <strong>{account.name || '@' + account.username}</strong>
        <span>@{account.username}</span>
        {account.expires_at && <small>Autorização até {new Date(account.expires_at).toLocaleDateString('pt-BR')}</small>}
      </div>
      <span className={'deal-chip' + (account.connected ? '' : ' warn')}>{account.connected ? 'Conectado' : account.active ? 'Expirado' : 'Desvinculado'}</span>
    </div>
    {missing && <p className="ig-warning" role="note">
      Esta conta foi autorizada antes da publicação e das métricas. Use <strong>Reautorizar</strong> e entre com @{account.username} para liberar os novos recursos.
    </p>}
    <div className="row-actions">
      <Button variant={missing || !account.connected ? 'primary' : 'secondary'} disabled={busy || working} onClick={onConnect}>Reautorizar</Button>
      {account.connected && <Button variant="secondary" disabled={working} onClick={() => run(async () => {
        await post('/instagram/refresh', body); notify('Autorização renovada.'); await onChanged();
      })}>Renovar token</Button>}
      {account.connected && <Button variant="secondary" disabled={working} onClick={() => run(async () => {
        try {
          const result = await post<Row>('/instagram/verify', body);
          setDelivery(result);
          notify(result.subscribed ? (result.activated ? 'Recebimento de mensagens ativado.' : 'Recebimento de mensagens ativo.') : 'O Instagram não confirmou o recebimento.', result.subscribed ? 'success' : 'error');
        } catch (e) { setDelivery(null); throw e; }
      })}>Verificar recebimento</Button>}
      {account.active && <Button variant="danger" onClick={() => setDisconnect(true)}>Desvincular</Button>}
    </div>
    {delivery && (
      <ul className="connection-list" aria-label={'Resultado da verificação de @' + account.username}>
        <li><span className="connection-info"><strong>Mensagens</strong><small>{delivery.subscribed ? 'A conta está assinada para receber mensagens.' : 'A conta não está assinada. Confira se o app está em modo de desenvolvimento e se a conta é testadora.'}</small></span>
          <span className={'deal-chip' + (delivery.subscribed ? '' : ' warn')}>{delivery.subscribed ? 'Ativo' : 'Inativo'}</span></li>
        <li><span className="connection-info"><strong>Eventos recebidos</strong><small>{delivery.events ? `Último em ${new Date(delivery.last_event_at).toLocaleString('pt-BR')}` : 'Nenhum evento chegou ainda. Envie uma mensagem de teste de uma conta testadora.'}</small></span>
          <span className="deal-chip">{delivery.events}</span></li>
      </ul>
    )}
    <ConfirmDialog open={disconnect} onClose={() => setDisconnect(false)} title={'Desvincular @' + account.username + '?'}
      description="O Antares deixará de receber, responder e publicar por este perfil. O histórico será preservado e publicações agendadas não serão enviadas. Para revogar o acesso na Meta, remova o aplicativo nas configurações do Instagram."
      onConfirm={async () => { await post('/instagram/disconnect', body); await onChanged(); notify('Perfil desvinculado do Antares.'); }} />
  </li>;
}

export function InstagramSettings() {
  const state = useData<Listing>('/instagram/connection');
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const url = new URL(window.location.href);
    const result = url.searchParams.get('instagram');
    if (!result) return;
    notify(result === 'connected' ? 'Instagram conectado.' : 'Não foi possível conectar. Tente novamente com a mesma conta do Antares.', result === 'connected' ? 'success' : 'error');
    url.searchParams.delete('instagram');
    window.history.replaceState(null, '', url.pathname + url.search);
  }, [notify]);
  async function connect() {
    setBusy(true);
    try { const result = await post<{ url: string }>('/instagram/connect', {}); window.location.assign(result.url); }
    catch (e) { notify((e as Error).message, 'error'); setBusy(false); }
  }
  const accounts = state.data?.connections || [];
  const usable = accounts.filter(a => a.connected);
  return <Card as="section">
    <CardHeader title={<span className="connection-title"><Instagram size={18} /> Instagram</span>}
      actions={<span className="deal-chip">{usable.length ? `${usable.length} ${usable.length === 1 ? 'perfil conectado' : 'perfis conectados'}` : 'Desconectado'}</span>} />
    <DataState loading={state.isLoading} error={state.error}>
      <CardBody>
        {state.data?.configured ? <div className="stack">
          <p className="muted">Conecte um ou mais perfis profissionais. Cada perfil recebe mensagens na Caixa de entrada, publica posts agendados e mostra métricas em <Link to="/instagram">Instagram</Link>. Um perfil pertence a uma única conta de cliente do Antares.</p>
          {accounts.length > 0 && <ul className="ig-accounts" aria-label="Perfis do Instagram">
            {accounts.map(account => <AccountCard key={account.id} account={account} busy={busy} onConnect={connect} onChanged={() => state.mutate()} />)}
          </ul>}
          <div className="row-actions">
            <Button disabled={busy} onClick={connect}><Plus size={16} />{accounts.length ? 'Conectar outro perfil' : 'Conectar Instagram'}</Button>
          </div>
          <p className="muted ig-hint">Para conectar o perfil de um cliente, saia do Instagram no navegador ou use uma janela anônima: a Meta autoriza a conta que estiver logada. Enquanto o aplicativo não passar pela análise da Meta, o perfil do cliente precisa ser adicionado como testador do app.</p>
          <HistorySync channel="instagram" connected={usable.length > 0}
            accounts={usable.map(a => ({ id: String(a.id), label: '@' + a.username }))} />
        </div> : <p>Configuração do aplicativo pendente no servidor.</p>}
      </CardBody>
    </DataState>
  </Card>;
}
