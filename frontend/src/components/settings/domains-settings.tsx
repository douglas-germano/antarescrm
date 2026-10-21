'use client';
import { useState } from 'react';
import { Copy, Globe, RefreshCw, Trash2 } from 'lucide-react';
import { Badge, Button, ConfirmDialog, DataState, EmptyState } from '@/components/ui';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import { useNotify } from '@/components/providers';
import { patch, post, refreshAll, remove, useData, useList } from '@/lib/api';
import type { Row } from '@/lib/types';

type DnsRecord = { purpose: 'ownership' | 'routing' | 'routing_apex'; type: string; name: string; value: string };
type Setup = { cname_target: string; ips: string[]; tls_managed: boolean; limit: number };
const STATUS: Record<string, { badge: string; label: string }> = {
  pending: { badge: 'pending', label: 'Aguardando DNS' },
  verified: { badge: 'doing', label: 'Verificado' },
  active: { badge: 'completed', label: 'Ativo' },
};

export function DomainsSettings() {
  const { notify } = useNotify();
  const setup = useData<Setup>('/domains/setup');
  const domains = useList('/domains');
  const funnels = useList('/funnels');
  const [hostname, setHostname] = useState('');
  const [funnelId, setFunnelId] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [removing, setRemoving] = useState<Row | null>(null);

  async function run(key: string, action: () => Promise<void>) {
    if (busy) return;
    setBusy(key); setError('');
    try { await action(); } catch (e) { setError((e as Error).message); } finally { setBusy(''); }
  }
  const copy = async (value: string) => {
    try { await navigator.clipboard.writeText(value); notify('Copiado.'); } catch { notify('Não foi possível copiar.', 'error'); }
  };
  const info = setup.data;

  return <div className="stack">
    <Card as="section">
      <CardHeader title="Domínios personalizados" description="Publique funis, formulários e agendas no endereço da sua marca." />
      <CardBody>
        <form className="domain-form" onSubmit={(e) => {
          e.preventDefault();
          run('add', async () => {
            await post('/domains', { hostname, funnel_id: funnelId || null });
            setHostname(''); setFunnelId(''); await refreshAll(); notify('Domínio adicionado. Siga as instruções de DNS abaixo.');
          });
        }}>
          <label>Domínio<input required value={hostname} maxLength={253} placeholder="paginas.suaempresa.com.br" onChange={(e) => setHostname(e.target.value)} disabled={!!busy} /></label>
          <label>Página inicial do domínio<select value={funnelId} onChange={(e) => setFunnelId(e.target.value)} disabled={!!busy}>
            <option value="">Nenhuma (somente links diretos)</option>
            {(funnels.data || []).map((f) => <option key={f.id} value={f.id}>{f.name}{f.status !== 'published' ? ' (rascunho)' : ''}</option>)}
          </select></label>
          <Button type="submit" disabled={!!busy || !hostname.trim() || (!!info && (domains.data?.length || 0) >= info.limit)}>{busy === 'add' ? 'Adicionando…' : 'Adicionar domínio'}</Button>
        </form>
        {info && <p className="muted">Você pode cadastrar até {info.limit} domínios. Use um subdomínio (como <code>paginas.suaempresa.com.br</code>) para não afetar o site principal.</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
      </CardBody>
    </Card>

    <DataState loading={domains.isLoading} error={domains.error}>
      {!domains.data?.length
        ? <EmptyState icon={<Globe />} title="Nenhum domínio" description="Adicione um domínio para publicar suas páginas com a sua marca." />
        : domains.data.map((d) => {
          const status = STATUS[d.status] || STATUS.pending;
          const records: DnsRecord[] = d.dns || [];
          return <Card key={d.id} as="section">
            <CardHeader title={d.hostname} description={d.url} actions={<Badge value={status.badge} label={status.label} />} />
            <CardBody>
              <div className="domain-row">
                <label>Página inicial<select value={d.funnel_id || ''} disabled={!!busy} onChange={(e) => run('funnel' + d.id, async () => { await patch('/domains/' + d.id, { funnel_id: e.target.value || null }); await refreshAll(); notify('Página inicial atualizada.'); })}>
                  <option value="">Nenhuma</option>
                  {(funnels.data || []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select></label>
                <div className="domain-actions">
                  <Button variant="secondary" disabled={!!busy} onClick={() => run('verify' + d.id, async () => {
                    const result = await post<Row>(`/domains/${d.id}/verify`, {}); await refreshAll();
                    notify(result.status === 'active' ? 'Domínio ativo.' : result.last_error || 'Verificação concluída.', result.status === 'pending' ? 'error' : 'success');
                  })}><RefreshCw size={14} /> {busy === 'verify' + d.id ? 'Verificando…' : 'Verificar agora'}</Button>
                  <Button variant="ghost" aria-label={'Remover ' + d.hostname} disabled={!!busy} onClick={() => setRemoving(d)}><Trash2 size={16} /></Button>
                </div>
              </div>
              {d.status === 'active' && <p className="muted">Tudo certo: <a href={d.url} target="_blank" rel="noreferrer">{d.url}</a> está respondendo.</p>}
              {d.last_error && d.status !== 'active' && <p className="form-error" role="status">{d.last_error}</p>}
              {d.status !== 'active' && <>
                <h3 className="domain-step">1. Comprove que o domínio é seu</h3>
                <DnsTable rows={records.filter((r) => r.purpose === 'ownership')} done={!!d.verified_at} onCopy={copy} />
                <h3 className="domain-step">2. Aponte o domínio para o Antares</h3>
                <DnsTable rows={records.filter((r) => r.purpose !== 'ownership')} done={!!d.routing_ok} onCopy={copy} />
                <p className="muted">Subdomínios usam o registro CNAME. Para um domínio raiz (sem subdomínio), use o registro A{info?.ips.length ? '' : ' ou ALIAS/ANAME, se o seu provedor aceitar CNAME na raiz'} indicado. A propagação pode levar de alguns minutos a algumas horas.</p>
                {info?.tls_managed && <p className="muted">O certificado HTTPS é emitido automaticamente depois que o domínio passa a apontar para o Antares{d.tls_status === 'pending' ? ' (em andamento)' : ''}.</p>}
              </>}
            </CardBody>
          </Card>;
        })}
    </DataState>
    <ConfirmDialog open={!!removing} onClose={() => setRemoving(null)} title="Remover domínio" description={`As páginas deixam de responder em ${removing?.hostname}. Os links no endereço padrão do Antares continuam funcionando.`}
      onConfirm={async () => { if (removing) { await remove('/domains/' + removing.id); await refreshAll(); notify('Domínio removido.'); } }} />
  </div>;
}

function DnsTable({ rows, done, onCopy }: { rows: DnsRecord[]; done: boolean; onCopy: (v: string) => void }) {
  return <div className="table-wrap"><table className="data-table dns-table">
    <thead><tr><th>Tipo</th><th>Nome / host</th><th>Valor</th><th>{done ? 'Estado' : ''}</th></tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}>
      <td><strong>{r.type}</strong>{r.purpose === 'routing_apex' && <small> (domínio raiz)</small>}</td>
      <td><code>{r.name}</code></td>
      <td><code>{r.value}</code></td>
      <td className="dns-actions"><Button variant="ghost" aria-label={'Copiar valor de ' + r.type} onClick={() => onCopy(r.value)}><Copy size={14} /></Button>{done && i === 0 && <Badge value="completed" label="OK" />}</td>
    </tr>)}</tbody>
  </table></div>;
}
