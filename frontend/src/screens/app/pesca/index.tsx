import { useEffect, useState } from 'react';
import { ArrowUpRight, Fish, Plus, Settings2 } from 'lucide-react';
import { useData, usePage, post } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button, DataState, PageHeader } from '@/components/ui';
import { RecordLink } from '@/components/record-link';
import { PostCard } from '@/components/fishing/post-card';
import { statusLabels, type FishingMetrics, type FishingPost, type FishingSettings } from '@/components/fishing/types';
import '@/components/fishing/fishing.css';

export default function FishingPage() {
  const [tab, setTab] = useState('fila');
  const [status, setStatus] = useState('na_fila');
  const config = useData<FishingSettings>('/fishing/settings');
  const metrics = useData<FishingMetrics>('/fishing/metrics');
  const posts = usePage<FishingPost>('/fishing/posts?status=' + status, 12);
  const { user, workspace } = useSession();
  const canManage = ['owner', 'admin'].includes(user?.role || '');
  const { notify } = useNotify();
  const [busy, setBusy] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [url, setUrl] = useState('');
  const [caption, setCaption] = useState('');
  const [author, setAuthor] = useState('');
  const enabled = config.data?.enabled && config.data.provider_ready;
  async function refresh() { await Promise.all([posts.mutate(), metrics.mutate()]); }
  useEffect(() => {
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh(); }, 8000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, posts.page, workspace?.id]);
  async function add(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      await post('/fishing/posts', { url, caption, author, image_data: image });
      setUrl(''); setCaption(''); setAuthor(''); setImage(null);
      setTab('fila'); setStatus('novo'); await refresh();
      notify('Post adicionado. O Copiloto vai avaliar e preparar as sugestões.');
    } catch (err) { notify((err as Error).message, 'error'); }
    finally { setBusy(false); }
  }
  async function loadImage(file?: File) {
    setImage(null);
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 4 * 1024 * 1024) {
      notify('Use PNG, JPEG ou WebP de até 4 MB.', 'error'); return;
    }
    setImageLoading(true);
    try {
      const result = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error('Não foi possível ler a imagem.')); reader.readAsDataURL(file);
      });
      setImage(result);
    } catch (err) { notify((err as Error).message, 'error'); }
    finally { setImageLoading(false); }
  }
  return <div className="page fishing-page" key={workspace?.id}>
    <PageHeader title="Pesca" eyebrow="Copiloto de prospecção" description="Encontre um bom assunto. Comece uma conversa.">
      {canManage && <RecordLink href="/configuracoes?tab=pesca" className="btn btn-secondary"><Settings2 size={16} />Configurar marca</RecordLink>}
      <Button onClick={() => setTab('fontes')}><Plus size={16} />Adicionar post</Button>
    </PageHeader>
    <div className="fishing-intro"><div><Fish size={25} /><div><strong>A IA rascunha. Você dá o tom.</strong><p>Cole um post, revise as sugestões e publique pelo Instagram.</p></div></div><span><b>{metrics.data?.published_today || 0}</b> / {config.data?.daily_limit || 40} hoje</span></div>
    <nav className="fishing-tabs" aria-label="Seções da Pesca">{[['fila', 'Fila de revisão'], ['fontes', 'Fontes'], ['resultados', 'Resultados']].map(([key, label]) => <button key={key} aria-current={tab === key ? 'page' : undefined} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</nav>
    <DataState loading={config.isLoading} error={config.error}>
      {!enabled && <div className="fishing-note"><strong>Prepare a Pesca para começar</strong><p>{!config.data?.provider_ready ? 'A conexão de IA precisa ser configurada no servidor. ' : ''}Defina o perfil da marca e habilite a Pesca nas configurações.{!canManage && ' Peça a um administrador da conta.'}</p></div>}
      {tab === 'fila' && <>
        <div className="fishing-toolbar"><label>Mostrar<select value={status} onChange={e => setStatus(e.target.value)}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><span className="muted">{posts.data?.total || 0} posts · Cards expiram em 48 horas</span></div>
        <DataState loading={posts.isLoading} error={posts.error}>
          {posts.data?.items.length ? <div className="fishing-grid">{posts.data.items.map(row => <PostCard key={row.id} row={row} refresh={refresh} />)}</div> : <div className="fishing-empty"><Fish size={36} /><h2>{status === 'na_fila' ? 'Uma boa conversa começa com um post.' : 'Nenhum post por aqui.'}</h2><p>{status === 'na_fila' ? 'Adicione o link e a legenda de um post relevante. O Copiloto avalia se vale comentar e prepara até três sugestões para você revisar.' : 'Use o filtro para acompanhar os posts ou adicione uma nova fonte.'}</p><Button variant="secondary" onClick={() => setTab('fontes')}>Adicionar primeiro post <ArrowUpRight size={15} /></Button></div>}
          {(posts.data?.pages || 0) > 1 && <div className="fishing-actions"><Button variant="secondary" disabled={posts.page === 1} onClick={() => posts.setPage(posts.page - 1)}>Anterior</Button><span>Página {posts.page} de {posts.data?.pages}</span><Button variant="secondary" disabled={posts.page >= (posts.data?.pages || 0)} onClick={() => posts.setPage(posts.page + 1)}>Próxima</Button></div>}
        </DataState>
        <p className="fishing-shortcuts muted">Com o card em foco: 1–3 escolher · E editar · Enter copiar e abrir · P pular</p>
      </>}
      {tab === 'fontes' && <div className="fishing-sources"><form onSubmit={add} className="fishing-card fishing-add"><h2>Traga um post para a conversa</h2><p className="muted">Escolha um post recente. Cole a legenda para a IA entender o contexto.</p>
        <label>Link do post<input type="url" required maxLength={500} placeholder="https://www.instagram.com/p/…" value={url} onChange={e => setUrl(e.target.value)} /></label>
        <label>Autor (opcional)<input maxLength={31} pattern="@?[a-zA-Z0-9_.]{0,30}" placeholder="@perfil" value={author} onChange={e => setAuthor(e.target.value)} /></label>
        <p className="muted">Informar o autor permite respeitar o intervalo de 7 dias entre comentários no mesmo perfil.</p>
        <label>Legenda do post<textarea required rows={7} maxLength={5000} value={caption} onChange={e => setCaption(e.target.value)} /></label>
        <label>Imagem ou capa (opcional, até 4 MB)<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => { const file = e.currentTarget.files?.[0]; e.currentTarget.value = ''; void loadImage(file); }} /></label>
        {image && <><img className="fishing-upload-preview" src={image} alt="Imagem selecionada" /><Button variant="ghost" onClick={() => setImage(null)}>Remover imagem</Button></>}
        <Button type="submit" disabled={!enabled || busy || imageLoading}>{busy ? 'Adicionando…' : 'Avaliar e gerar sugestões'}</Button>
      </form><aside className="fishing-source-notes"><span className="eyebrow">Fontes disponíveis</span><h2>Um post por vez.<br />Uma conversa com contexto.</h2><p>Links colados já entram na fila de análise. A IA não acessa o perfil nem coleta publicações pelo link.</p><p>A imagem é opcional. Sem ela, a avaliação usa somente a legenda informada.</p><hr /><h3>Próximas etapas</h3><p>Perfis, hashtags e menções ainda não estão disponíveis nesta versão. A coleta automática depende das permissões e da integração com a Meta.</p></aside></div>}
      {tab === 'resultados' && <DataState loading={metrics.isLoading} error={metrics.error}>{metrics.data && <>
        <p className="fishing-note">Dados acumulados da Pesca nesta conta. “Publicado” significa confirmação de uma pessoa; o Antares não verifica a publicação no Instagram. Visitas, seguidores e DMs ainda não são atribuídos à Pesca.</p>
        <div className="fishing-stats">{[['Posts adicionados', metrics.data.total], ['Publicados', metrics.data.counts.publicado || 0], ['Aproveitamento', metrics.data.approval_rate + '%'], ['Comentários editados', metrics.data.edit_rate + '%'], ['Tokens de IA', metrics.data.tokens.toLocaleString('pt-BR')], ['Custo informado pela IA', metrics.data.cost_usd === null ? 'Não informado' : 'US$ ' + Number(metrics.data.cost_usd).toFixed(4)]].map(([label, value]) => <div key={String(label)}><span>{label}</span><strong>{value}</strong></div>)}</div>
        <div className="fishing-card"><h2>O caminho dos posts</h2><div className="fishing-status-list">{Object.entries(statusLabels).filter(([key]) => key !== 'todos').map(([key, label]) => <div key={key}><span>{label}</span><strong>{metrics.data?.counts[key] || 0}</strong></div>)}</div><p className="muted">{metrics.data.ai_calls_today} chamadas de IA hoje, de {config.data?.daily_ai_limit || 100} permitidas.{metrics.data.unknown_cost_calls > 0 && ` Há ${metrics.data.unknown_cost_calls} chamada(s) com custo desconhecido; o total pode estar incompleto.`}</p></div>
      </>}</DataState>}
    </DataState>
  </div>;
}
