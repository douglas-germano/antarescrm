'use client';
import { useEffect, useState } from 'react';
import { Instagram } from 'lucide-react';
import { initials } from '@/lib/format';
import { post, useData } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, ConfirmDialog, DataState } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';
import type { Row } from '@/lib/types';

export function InstagramSettings() {
  const state = useData<{ configured: boolean; connected: boolean; connection: Row | null }>('/instagram/connection');
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const [disconnect, setDisconnect] = useState(false);
  const [delivery, setDelivery] = useState<Row | null>(null);
  const [pictureFailed, setPictureFailed] = useState(false);
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
    try { const result = await post('/instagram/connect', {}); window.location.assign(result.url); }
    catch (e) { notify((e as Error).message, 'error'); setBusy(false); }
  }
  const current = state.data?.connection;
  return <Card as="section">
    <CardHeader title={<span className="connection-title"><Instagram size={18} /> Instagram</span>}
      actions={<span className="deal-chip">{state.data?.connected ? 'Conectado' : 'Desconectado'}</span>} />
    <DataState loading={state.isLoading} error={state.error}>
      <CardBody>
        {state.data?.configured ? <div className="stack">
          {current && (
            <div className="ig-profile">
              {current.profile_picture_url && !pictureFailed
                ? <img src={current.profile_picture_url} alt={'Foto de perfil de @' + current.username} width={56} height={56} referrerPolicy="no-referrer" onError={() => setPictureFailed(true)} />
                : <span className="ig-avatar" aria-hidden>{initials(current.name || current.username)}</span>}
              <div>
                <strong>{current.name || '@' + current.username}</strong>
                <span>@{current.username}</span>
                {current.expires_at && <small>Autorização até {new Date(current.expires_at).toLocaleDateString('pt-BR')}</small>}
              </div>
            </div>
          )}
          <p className="muted">Receba mensagens na Caixa de entrada e responda dentro da janela de 24 horas. Sem disparos em massa.</p>
          <div className="row-actions">
            <Button disabled={busy} onClick={connect}>{state.data.connected ? 'Renovar conexão' : 'Conectar Instagram'}</Button>
            {state.data.connected && <Button variant="secondary" disabled={busy} onClick={async () => {
              setBusy(true);
              try { await post('/instagram/refresh', {}); notify('Autorização renovada.'); await state.mutate(); }
              catch (e) { notify((e as Error).message, 'error'); }
              finally { setBusy(false); }
            }}>Renovar token</Button>}
            {state.data.connected && <Button variant="secondary" disabled={busy} onClick={async () => {
              setBusy(true);
              try {
                const result = await post('/instagram/verify', {});
                setDelivery(result);
                notify(result.subscribed ? (result.activated ? 'Recebimento de mensagens ativado.' : 'Recebimento de mensagens ativo.') : 'O Instagram não confirmou o recebimento.', result.subscribed ? 'success' : 'error');
              } catch (e) { setDelivery(null); notify((e as Error).message, 'error'); }
              finally { setBusy(false); }
            }}>Verificar recebimento</Button>}
            {current?.active && <Button variant="danger" onClick={() => setDisconnect(true)}>Desvincular</Button>}
          </div>
          {delivery && (
            <ul className="connection-list" aria-label="Resultado da verificação">
              <li><span className="connection-info"><strong>Mensagens</strong><small>{delivery.subscribed ? 'A conta está assinada para receber mensagens.' : 'A conta não está assinada. Confira se o app está em modo de desenvolvimento e se a conta é testadora.'}</small></span>
                <span className={'deal-chip' + (delivery.subscribed ? '' : ' warn')}>{delivery.subscribed ? 'Ativo' : 'Inativo'}</span></li>
              <li><span className="connection-info"><strong>Eventos recebidos</strong><small>{delivery.events ? `Último em ${new Date(delivery.last_event_at).toLocaleString('pt-BR')}` : 'Nenhum evento chegou ainda. Envie uma mensagem de teste de uma conta testadora.'}</small></span>
                <span className="deal-chip">{delivery.events}</span></li>
            </ul>
          )}
        </div> : <p>Configuração do aplicativo pendente no servidor.</p>}
      </CardBody>
    </DataState>
    <ConfirmDialog open={disconnect} onClose={() => setDisconnect(false)} title="Desvincular o Instagram?"
      description="O Antares deixará de receber e responder por este perfil. O histórico será preservado. Para revogar o acesso na Meta, remova o aplicativo nas configurações do Instagram."
      onConfirm={async () => { await post('/instagram/disconnect', {}); await state.mutate(); notify('Perfil desvinculado do Antares.'); }} />
  </Card>;
}
