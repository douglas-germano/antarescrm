import { useState } from 'react';
import { Copy, KeyRound, Plus } from 'lucide-react';
import { post, remove, useData } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, ConfirmDialog, DataState, EmptyState, Modal } from '@/components/ui';
import { Card, CardBody, CardHeader } from '@/components/blocks';
import type { Row } from '@/lib/types';

type Listing = { items: Row[]; scopes: Record<string, string>; durations: number[]; endpoint: string };
const RISKY = new Set(['messages:send', 'instagram:publish', 'instagram:comments']);
const date = (value?: string) => (value ? new Date(value).toLocaleDateString('pt-BR') : '—');

async function copy(text: string, notify: (m: string, t?: 'success' | 'error') => void) {
  try { await navigator.clipboard.writeText(text); notify('Copiado.'); }
  catch { notify('Não foi possível copiar. Selecione e copie manualmente.', 'error'); }
}

export function McpSettings() {
  const state = useData<Listing>('/api-tokens');
  const { notify } = useNotify();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<{ name: string; scopes: string[]; days: number }>({ name: '', scopes: ['messages:read', 'instagram:read'], days: 90 });
  const [secret, setSecret] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const endpoint = state.data?.endpoint || '';
  const config = secret ? JSON.stringify({ mcpServers: { antares: { type: 'http', url: endpoint, headers: { Authorization: 'Bearer ' + secret } } } }, null, 2) : '';
  const cli = secret ? `claude mcp add --transport http antares ${endpoint} --header "Authorization: Bearer ${secret}"` : '';

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const row = await post<Row>('/api-tokens', form);
      setSecret(row.token); setCreating(false);
      setForm({ name: '', scopes: ['messages:read', 'instagram:read'], days: 90 });
      await state.mutate();
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return <Card as="section">
    <CardHeader title={<span className="connection-title"><KeyRound size={18} /> Acesso para IAs (MCP)</span>}
      description="Permite que Claude, ChatGPT, Cursor e outros agentes leiam e respondam mensagens, publiquem e acompanhem o Instagram desta conta."
      actions={<Button onClick={() => { setError(''); setCreating(true); }}><Plus size={16} />Novo token</Button>} />
    <DataState loading={state.isLoading} error={state.error}>
      <CardBody>
        <div className="stack">
          <div className="field"><label htmlFor="mcp-endpoint">Endereço do servidor MCP</label>
            <div className="mcp-copy"><input id="mcp-endpoint" readOnly value={endpoint} /><Button variant="secondary" onClick={() => copy(endpoint, notify)}><Copy size={15} />Copiar</Button></div>
            <small>Transporte HTTP. Envie o token no cabeçalho <code>Authorization: Bearer …</code>.</small></div>
          {state.data?.items.length ? <div className="table-wrap"><table className="data-table">
            <thead><tr><th>Nome</th><th>Permissões</th><th>Criado</th><th>Último uso</th><th>Validade</th><th /></tr></thead>
            <tbody>{state.data.items.map(row => <tr key={row.id}>
              <td><strong>{row.name}</strong><small><code>{row.prefix}…</code></small></td>
              <td><div className="deal-chips">{(row.scopes as string[]).map(s => <span key={s} className={'deal-chip' + (RISKY.has(s) ? ' warn' : '')} title={state.data!.scopes[s]}>{s}</span>)}</div></td>
              <td>{date(row.created_at)}</td>
              <td>{row.last_used_at ? new Date(row.last_used_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : 'Nunca'}</td>
              <td>{row.revoked_at ? <span className="deal-chip">Revogado</span> : row.active ? date(row.expires_at) : <span className="deal-chip warn">Expirado</span>}</td>
              <td>{row.active && <Button variant="danger" onClick={() => setRevoking(row)}>Revogar</Button>}</td>
            </tr>)}</tbody>
          </table></div> : <EmptyState icon={<KeyRound />} title="Nenhum token ainda" description="Crie um token com as permissões que a IA precisa." />}
          <p className="muted">Cada token age em nome de quem o criou, somente nesta conta. Envios, publicações e respostas exigem confirmação na chamada, ficam no registro de auditoria e têm limite de 60 por hora por token.</p>
        </div>
      </CardBody>
    </DataState>

    <Modal open={creating} onClose={() => { if (!busy) setCreating(false); }} title="Novo token para IA" description="Dê só as permissões necessárias.">
      <form className="stack" onSubmit={create}>
        <div className="field"><label htmlFor="mcp-name">Nome</label>
          <input id="mcp-name" required maxLength={120} value={form.name} placeholder="Ex.: Claude do Douglas" onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <fieldset className="field mcp-scopes"><legend className="field-label">Permissões</legend>
          {Object.entries(state.data?.scopes || {}).map(([key, label]) => <label key={key} className="checkbox-label">
            <input type="checkbox" checked={form.scopes.includes(key)} onChange={(e) => setForm({ ...form, scopes: e.target.checked ? [...form.scopes, key] : form.scopes.filter(s => s !== key) })} />
            <span><strong>{label}</strong> <code>{key}</code>{RISKY.has(key) && <em> · ação irreversível</em>}</span>
          </label>)}
        </fieldset>
        <div className="field"><label htmlFor="mcp-days">Validade</label>
          <select id="mcp-days" value={form.days} onChange={(e) => setForm({ ...form, days: Number(e.target.value) })}>
            {(state.data?.durations || [90]).map(d => <option key={d} value={d}>{d} dias</option>)}
          </select></div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="row-actions"><Button type="submit" disabled={busy || !form.scopes.length}>Criar token</Button></div>
      </form>
    </Modal>

    <Modal open={!!secret} onClose={() => setSecret(null)} wide title="Copie o token agora" description="Ele não será exibido novamente. Guarde-o como uma senha.">
      <div className="stack">
        <div className="field"><label htmlFor="mcp-secret">Token</label>
          <div className="mcp-copy"><input id="mcp-secret" readOnly value={secret || ''} onFocus={(e) => e.target.select()} /><Button onClick={() => copy(secret!, notify)}><Copy size={15} />Copiar</Button></div></div>
        <div className="field"><span className="field-label">Claude Code</span>
          <pre className="mcp-snippet">{cli}</pre><Button variant="secondary" onClick={() => copy(cli, notify)}><Copy size={15} />Copiar comando</Button></div>
        <div className="field"><span className="field-label">Claude Desktop, Cursor e outros clientes (JSON)</span>
          <pre className="mcp-snippet">{config}</pre><Button variant="secondary" onClick={() => copy(config, notify)}><Copy size={15} />Copiar configuração</Button></div>
        <Button onClick={() => setSecret(null)}>Já copiei</Button>
      </div>
    </Modal>

    <ConfirmDialog open={!!revoking} onClose={() => setRevoking(null)} title={'Revogar “' + (revoking?.name || '') + '”?'}
      description="A IA que usa este token perde o acesso imediatamente. Não é possível desfazer."
      onConfirm={async () => { await remove('/api-tokens/' + revoking!.id); await state.mutate(); notify('Token revogado.'); }} />
  </Card>;
}
