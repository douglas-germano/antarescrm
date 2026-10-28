'use client';
import { useState } from 'react';
import { Mail, Plug, Power, CheckCheck } from 'lucide-react';
import { post, remove, useData, refreshAll } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, DataState, ConfirmDialog, Badge } from '@/components/ui';
import { Card, CardHeader, CardBody } from '@/components/blocks';

type Connection = { configured: boolean; sender_email: string; sender_name: string; webhook_id: number | null };
export function BrevoSettings() {
  const state = useData<{ connection: Connection | null }>('/brevo/connection');
  const current = state.data?.connection;
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [disconnecting, setDisconnecting] = useState(false);
  const [key, setKey] = useState('');
  return <Card as="section">
    <CardHeader title={<span className="connection-title"><Mail size={18} /> Brevo</span>}
      description="Campanhas de e-mail, convites para a equipe e recuperação de acesso."
      actions={<Badge value={current?.configured ? 'completed' : 'doing'} label={current?.configured ? 'Conectado' : 'Configuração pendente'} />} />
    <DataState loading={state.isLoading} error={state.error}><CardBody>
      <form key={current?.sender_email || 'new'} className="stack" onSubmit={async event => {
        event.preventDefault(); if (busy) return; setBusy(true); setError('');
        const data = new FormData(event.currentTarget);
        try {
          await post('/brevo/connection', { sender_email: data.get('sender_email'), sender_name: data.get('sender_name'), ...(key ? { api_key: key } : {}) });
          setKey(''); await refreshAll(); notify('Brevo conectado.');
        } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
      }}>
        <div className="form-grid">
          <div className="field"><label htmlFor="brevo-name">Nome do remetente</label><input id="brevo-name" name="sender_name" maxLength={150} required defaultValue={current?.sender_name || ''} disabled={busy} /></div>
          <div className="field"><label htmlFor="brevo-email">E-mail do remetente</label><input id="brevo-email" type="email" name="sender_email" maxLength={254} required defaultValue={current?.sender_email || ''} disabled={busy} /><small>Use um remetente ativo e um domínio autenticado no Brevo.</small></div>
          <div className="field"><label htmlFor="brevo-key">Chave de API</label><input id="brevo-key" type="password" autoComplete="new-password" value={key} onChange={event => setKey(event.target.value)} required={!current?.configured} maxLength={500} disabled={busy} placeholder={current?.configured ? 'Deixe vazio para manter a chave atual' : 'Chave criada no Brevo'} /><small>A chave fica protegida e não será exibida novamente. Esta conexão pertence à conta de cliente atual.</small></div>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="row-actions">
          <Button type="submit" disabled={busy}><Plug size={15} />{busy ? 'Validando…' : 'Salvar e validar conexão'}</Button>
          {current?.configured && <Button variant="secondary" disabled={busy} onClick={async () => {
            setBusy(true); setError('');
            try { await post('/brevo/webhooks', {}); await refreshAll(); notify('Acompanhamento de campanhas ativado.'); }
            catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
          }}><CheckCheck size={15} />{current.webhook_id ? 'Atualizar acompanhamento' : 'Ativar acompanhamento'}</Button>}
          {current?.configured && <Button variant="ghost" disabled={busy} onClick={() => setDisconnecting(true)}><Power size={15} />Desconectar</Button>}
        </div>
        {current?.configured && <p className="muted">{current.webhook_id ? 'Acompanhamento ativo: entregas, aberturas, cliques, falhas e descadastros.' : 'Ative o acompanhamento para preparar campanhas e receber os resultados no Antares.'}</p>}
      </form>
    </CardBody></DataState>
    <ConfirmDialog open={disconnecting} onClose={() => setDisconnecting(false)} title="Desconectar o Brevo?" description="Os novos envios desta conta ficarão indisponíveis. O histórico será preservado."
      onConfirm={async () => { await remove('/brevo/connection'); await refreshAll(); setKey(''); notify('Brevo desconectado.'); }} />
  </Card>;
}
