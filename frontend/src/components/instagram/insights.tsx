import { useState } from 'react';
import useSWR from 'swr';
import { BarChart3, ExternalLink, RefreshCw } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button, DataState, StatCard } from '@/components/ui';
import { Card, CardBody, CardHeader, Tabs, Toolbar, ToolbarEnd } from '@/components/blocks';
import { Bars } from '@/components/reports/report-parts';
import type { Row } from '@/lib/types';

const number = (value: unknown) => typeof value === 'number' ? value.toLocaleString('pt-BR') : '—';
const PERIODS = [{ value: '7', label: '7 dias' }, { value: '30', label: '30 dias' }] as const;
const INTERACTIONS = [
  ['likes', 'Curtidas'], ['comments', 'Comentários'], ['shares', 'Compartilhamentos'], ['saves', 'Salvamentos'], ['replies', 'Respostas a stories'],
] as const;
const AUDIENCE: Record<string, string> = { age: 'Idade', gender: 'Gênero', city: 'Cidades' };
const GENDER: Record<string, string> = { F: 'Feminino', M: 'Masculino', U: 'Não informado' };

function Series({ points, name }: { points: { date: string; value: number }[]; name: string }) {
  if (!points?.length) return <div className="rep-empty"><BarChart3 size={22} /><p>Sem dados diários neste período.</p></div>;
  const data = points.map(p => ({ ...p, label: p.date.slice(5).split('-').reverse().join('/') }));
  return <div className="rep-chart ig-chart">
    <ResponsiveContainer>
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ebebeb" />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#8a8d90' }} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis tick={{ fontSize: 11, fill: '#8a8d90' }} tickLine={false} axisLine={false} width={44} allowDecimals={false} />
        <Tooltip formatter={(value) => [Number(value).toLocaleString('pt-BR'), name]} labelStyle={{ fontSize: 12 }} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
        <Area dataKey="value" name={name} stroke="#ef2f70" fill="#fde8ef" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  </div>;
}

function explain(errors: Row[]) {
  const parts = new Set(errors.map(e => String(e.part).split(':')[0]));
  const notes: string[] = [];
  if (errors.some(e => e.reason === 'rate_limited')) notes.push('O Instagram limitou as consultas desta conta por agora; os números voltam na próxima atualização.');
  if (parts.has('audience')) notes.push('Dados de público aparecem para contas com pelo menos 100 seguidores.');
  if (errors.some(e => e.reason === 'permission' && !String(e.part).startsWith('audience'))) notes.push('Algumas métricas exigem reautorizar o perfil em Configurações → Conexões.');
  if (parts.has('metric') || parts.has('series')) notes.push('Algumas métricas não estão disponíveis para esta conta ou período.');
  return notes;
}

export function InsightsPanel({ account }: { account: Row }) {
  const { workspace } = useSession();
  const { notify } = useNotify();
  const [days, setDays] = useState<'7' | '30'>('30');
  const [refreshing, setRefreshing] = useState(false);
  const path = `/instagram/accounts/${account.id}/insights?days=${days}`;
  const state = useSWR<Row>(workspace?.id && account.can_read_insights ? ['ig-insights', workspace.id, path] : null, () => api<Row>(path), { revalidateOnFocus: false, shouldRetryOnError: false });
  const data = state.data;
  if (!account.can_read_insights) return <Card as="section"><CardBody>
    <p className="ig-warning" role="note">@{account.username} ainda não autorizou as métricas. Reautorize o perfil em Configurações → Conexões.</p>
  </CardBody></Card>;
  const totals = data?.totals || {};
  const followers = (data?.history || []).map((p: Row) => ({ date: p.date, value: p.followers }));
  const notes = explain(data?.errors || []);
  async function refresh() {
    setRefreshing(true);
    try { await state.mutate(await api<Row>(path + '&refresh=1'), { revalidate: false }); }
    catch (e) { notify((e as Error).message, 'error'); }
    finally { setRefreshing(false); }
  }
  return <div className="stack ig-insights">
    <Toolbar>
      <Tabs label="Período" items={PERIODS.map(p => ({ ...p }))} value={days} onChange={setDays} />
      <ToolbarEnd>
        {data?.fetched_at && <small className="muted">Atualizado {new Date(data.fetched_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}</small>}
        <Button variant="soft" disabled={refreshing || state.isLoading} onClick={refresh}><RefreshCw size={15} />Atualizar</Button>
      </ToolbarEnd>
    </Toolbar>
    <DataState loading={state.isLoading} error={state.error}>
      {data && <>
        {notes.length > 0 && <ul className="ig-notes">{notes.map(n => <li key={n}>{n}</li>)}</ul>}
        <div className="stat-grid ig-stats">
          <StatCard label="Seguidores" value={number(data.account?.followers_count)} detail={`${number(data.account?.media_count)} publicações`} />
          <StatCard label="Alcance" value={number(totals.reach)} detail="Contas únicas que viram seu conteúdo" />
          <StatCard label="Visualizações" value={number(totals.views)} detail="Vezes que o conteúdo foi exibido" />
          <StatCard label="Contas com engajamento" value={number(totals.accounts_engaged)} />
          <StatCard label="Interações" value={number(totals.total_interactions)} />
          <StatCard label="Toques no link do perfil" value={number(totals.profile_links_taps)} />
        </div>
        <div className="ig-grid">
          <Card as="section"><CardHeader title="Alcance por dia" /><CardBody><Series points={data.series?.reach || []} name="Alcance" /></CardBody></Card>
          <Card as="section"><CardHeader title="Seguidores" description="Histórico guardado pelo Antares, um registro por dia." />
            <CardBody><Series points={followers.length > 1 ? followers : data.series?.follower_count || []} name="Seguidores" /></CardBody></Card>
          <Card as="section"><CardHeader title="Interações" /><CardBody>
            <Bars rows={INTERACTIONS.map(([key, label]) => ({ id: key, label, value: Number(totals[key] || 0) }))} label="label" value="value" format={v => v.toLocaleString('pt-BR')} />
          </CardBody></Card>
          {Object.keys(data.audience || {}).length > 0 && <Card as="section"><CardHeader title="Público" description="Seguidores, últimos 30 dias." /><CardBody className="ig-audience">
            {Object.entries(data.audience as Record<string, Row[]>).map(([key, rows]) => <div key={key}>
              <h4>{AUDIENCE[key] || key}</h4>
              <Bars rows={rows.map(r => ({ id: r.key, label: key === 'gender' ? GENDER[r.key] || r.key : r.key, value: r.value }))} label="label" value="value" format={v => v.toLocaleString('pt-BR')} />
            </div>)}
          </CardBody></Card>}
        </div>
        <Card as="section"><CardHeader title="Publicações recentes" description="As 12 últimas, com as métricas de cada uma." /><CardBody>
          {data.media?.length ? <div className="table-wrap"><table className="data-table ig-media-table">
            <thead><tr><th>Publicação</th><th>Data</th><th className="text-right">Alcance</th><th className="text-right">Visualizações</th><th className="text-right">Curtidas</th><th className="text-right">Comentários</th><th className="text-right">Salvos</th><th className="text-right">Compart.</th><th /></tr></thead>
            <tbody>{data.media.map((m: Row) => <tr key={m.id}>
              <td><span className="ig-media-cell">
                {m.media_type === 'VIDEO' ? (m.thumbnail_url ? <img src={m.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="ig-thumb" />)
                  : m.media_url || m.thumbnail_url ? <img src={m.thumbnail_url || m.media_url} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="ig-thumb" />}
                <span>{(m.caption || 'Sem legenda').slice(0, 80)}</span></span></td>
              <td>{m.timestamp ? new Date(m.timestamp).toLocaleDateString('pt-BR') : ''}</td>
              <td className="text-right">{number(m.insights?.reach)}</td>
              <td className="text-right">{number(m.insights?.views)}</td>
              <td className="text-right">{number(m.insights?.likes ?? m.like_count)}</td>
              <td className="text-right">{number(m.insights?.comments ?? m.comments_count)}</td>
              <td className="text-right">{number(m.insights?.saved)}</td>
              <td className="text-right">{number(m.insights?.shares)}</td>
              <td>{m.permalink && <a className="icon-btn" href={m.permalink} target="_blank" rel="noreferrer" aria-label="Abrir no Instagram"><ExternalLink size={14} /></a>}</td>
            </tr>)}</tbody>
          </table></div> : <p className="muted">Nenhuma publicação encontrada.</p>}
        </CardBody></Card>
      </>}
    </DataState>
  </div>;
}
