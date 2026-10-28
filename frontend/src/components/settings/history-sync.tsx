'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { RefreshCw } from 'lucide-react';
import { api, post } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button } from '@/components/ui';

type Sync = {
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  phase: string;
  scanned: number;
  imported: number;
  duplicates: number;
  skipped: number;
  unresolved: number;
  total: number;
  mapped_records: number;
  error?: string;
  updated_at: string;
};
const labels = { queued: 'Na fila', running: 'Em andamento', completed: 'Concluída', failed: 'Interrompida', cancelled: 'Pausada' };

export function HistorySync({ channel, connected }: { channel: 'whatsapp' | 'instagram'; connected: boolean }) {
  const path = '/history-sync/' + channel;
  const { workspace } = useSession();
  const state = useSWR<{ sync: Sync | null }>(workspace?.id ? ['history', workspace.id, path] : null, () => api<{ sync: Sync | null }>(path), { refreshInterval: 3000 });
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const sync = state.data?.sync;
  const active = sync?.status === 'queued' || sync?.status === 'running';
  async function action(action: 'start' | 'resume' | 'cancel') {
    setBusy(true);
    try { await state.mutate(await post<{ sync: Sync | null }>(path, { action })); }
    catch (e) { notify((e as Error).message, 'error'); }
    finally { setBusy(false); }
  }
  return <section className="stack" aria-label={`Histórico do ${channel === 'whatsapp' ? 'WhatsApp' : 'Instagram'}`}>
    <div>
      <strong>Mensagens antigas</strong>
      <p className="muted">Importe o histórico disponível {channel === 'whatsapp' ? 'na Evolution' : 'no Instagram'}. A sincronização continua em segundo plano e preserva as datas, sem gerar notificações ou automações.</p>
      {channel === 'whatsapp' && <p className="muted">Conversas individuais. Contatos sem telefone identificado ficam pendentes; grupos são ignorados. Anexos antigos dependem da disponibilidade no provedor.</p>}
    </div>
    {state.error && <p role="alert">Não foi possível consultar a sincronização. <Button variant="secondary" onClick={() => state.mutate()}>Tentar novamente</Button></p>}
    {sync && <div role="status" aria-live="polite">
      <strong>{labels[sync.status]}{active && sync.phase === 'mapping' ? ' · Identificando contatos' : ''}</strong>
      <p>{sync.imported.toLocaleString('pt-BR')} importadas · {sync.duplicates.toLocaleString('pt-BR')} já existentes · {sync.skipped.toLocaleString('pt-BR')} ignoradas</p>
      <p className="muted">{(sync.phase === 'mapping' ? sync.mapped_records : sync.scanned).toLocaleString('pt-BR')} mensagens verificadas{channel === 'whatsapp' && sync.total ? ` de aproximadamente ${sync.total.toLocaleString('pt-BR')} registros` : ''}.</p>
      {sync.unresolved > 0 && <p>{sync.unresolved.toLocaleString('pt-BR')} registros sem associação segura ao telefone. Podem ser verificados em uma nova sincronização.</p>}
      {sync.error && <p role="alert">{sync.error}</p>}
      <small className="muted">Última atualização: {new Date(sync.updated_at).toLocaleString('pt-BR')}</small>
    </div>}
    <div className="row-actions">
      {active ? <Button variant="secondary" disabled={busy} onClick={() => action('cancel')}>Pausar sincronização</Button> : <>
        <Button variant="secondary" disabled={busy || state.isLoading || Boolean(state.error) || !connected} onClick={() => action('start')}><RefreshCw size={15} />{sync ? 'Sincronizar novamente' : 'Sincronizar mensagens antigas'}</Button>
        {sync && ['failed', 'cancelled'].includes(sync.status) && <Button disabled={busy || !connected} onClick={() => action('resume')}>Retomar do último ponto</Button>}
      </>}
    </div>
  </section>;
}
