import { useEffect, useRef, useState } from 'react';
import { ExternalLink, RefreshCw, SkipForward } from 'lucide-react';
import { post, useData } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button } from '@/components/ui';
import { statusLabels, type FishingPost } from './types';

const kinds: Record<string, string> = { acrescenta: 'Acrescentar uma ideia', pergunta: 'Fazer uma pergunta', reacao: 'Reagir ao post' };
export function PostCard({ row, refresh }: { row: FishingPost; refresh: () => Promise<unknown> }) {
  const [selected, setSelected] = useState(row.drafts[0]?.id || '');
  const [text, setText] = useState(row.drafts[0]?.text || '');
  const [busy, setBusy] = useState(false);
  const { user } = useSession();
  const { notify } = useNotify();
  const editor = useRef<HTMLTextAreaElement>(null);
  const { data: image } = useData<{ image_data: string | null }>(row.has_image ? `/fishing/posts/${row.id}/image` : null);
  const draftKey = row.drafts.map(d => d.id).join(',');
  useEffect(() => {
    setSelected(row.drafts[0]?.id || ''); setText(row.drafts[0]?.text || '');
    // Draft selection resets only after a new generation arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey]);
  async function action(path: string, body: unknown) {
    setBusy(true);
    try { await post(`/fishing/posts/${row.id}/${path}`, body); await refresh(); }
    catch (err) { notify((err as Error).message, 'error'); }
    finally { setBusy(false); }
  }
  async function open() {
    if (busy || !text.trim() || !selected) return;
    setBusy(true);
    let popup: Window | null = null;
    try {
      // Create the tab during the user gesture, before awaiting clipboard/API operations.
      popup = window.open('about:blank', '_blank');
      if (popup) popup.opener = null;
      await navigator.clipboard.writeText(text.trim());
      const result = await post<{ warning: string | null }>(`/fishing/posts/${row.id}/open`, { draft_id: selected, text });
      if (popup) popup.location.href = row.url;
      notify(result.warning || 'Texto copiado. Cole no Instagram e depois confirme se publicou.', result.warning ? 'message' : 'success');
      await refresh();
    } catch (err) {
      popup?.close();
      notify((err as Error).message || 'Não foi possível copiar o texto. Verifique a permissão da área de transferência.', 'error');
    } finally { setBusy(false); }
  }
  function choose(id: string) { setSelected(id); setText(row.drafts.find(d => d.id === id)?.text || ''); }
  const pending = row.status === 'na_fila' && !!row.opened_at;
  const canReview = row.status === 'na_fila' && !pending;
  return <article className="fishing-card" tabIndex={0} aria-label={`Post de ${row.author || 'autor não informado'}`} onKeyDown={event => {
    if (!canReview || busy || /^(INPUT|TEXTAREA|BUTTON|SELECT|A)$/.test((event.target as HTMLElement).tagName) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (['1', '2', '3'].includes(event.key)) { event.preventDefault(); const draft = row.drafts[Number(event.key) - 1]; if (draft) choose(draft.id); }
    if (event.key.toLowerCase() === 'e') { event.preventDefault(); editor.current?.focus(); }
    if (event.key === 'Enter') { event.preventDefault(); void open(); }
    if (event.key.toLowerCase() === 'p') { event.preventDefault(); void action('decide', { action: 'pulado' }); }
  }}>
    <header className="fishing-card-head"><div><strong>{row.author ? '@' + row.author : 'Link adicionado'}</strong><span className="muted">{statusLabels[row.status]} · Adicionado {new Date(row.created_at).toLocaleDateString('pt-BR')}</span></div>
      {row.score !== null && <span className="fishing-score">{row.score}<small>/100</small></span>}
    </header>
    {image?.image_data && <img className="fishing-post-image" src={image.image_data} alt="Imagem do post adicionada para análise" />}
    <p className="fishing-caption">{row.caption}</p>
    {row.reason && <p className="fishing-reason">{row.reason}</p>}
    {row.summary && <p>{row.summary}</p>}
    {row.error && <p role="alert" className="fishing-error">{row.error}</p>}
    {canReview && <>
      <fieldset className="fishing-options"><legend>Escolha um caminho para a conversa</legend>{row.drafts.map((draft, index) => <label key={draft.id} className={selected === draft.id ? 'selected' : ''}>
        <input type="radio" name={'draft-' + row.id} checked={selected === draft.id} onChange={() => choose(draft.id)} />
        <span><small>{index + 1} · {kinds[draft.kind]}</small>{draft.text}</span>
      </label>)}</fieldset>
      <label className="fishing-editor">Seu comentário<textarea ref={editor} maxLength={220} rows={3} value={text} onChange={e => setText(e.target.value)} /><small>{text.length}/220 · Revise antes de comentar</small></label>
      <div className="fishing-actions"><Button disabled={busy || !text.trim()} onClick={open}><ExternalLink size={15} />Copiar e abrir post</Button><Button variant="secondary" disabled={busy} onClick={() => action('regenerate', {})}><RefreshCw size={15} />Gerar outras</Button><Button variant="ghost" disabled={busy} onClick={() => action('decide', { action: 'pulado' })}><SkipForward size={15} />Pular</Button></div>
    </>}
    {pending && <div className="fishing-confirm"><strong>Publicou no Instagram?</strong><p>O texto foi copiado. A publicação é feita por você no post.</p><blockquote>{row.published_text}</blockquote>
      <a href={row.url} target="_blank" rel="noopener noreferrer">Abrir o post no Instagram <ExternalLink size={13} /></a>
      {row.user_id === user?.id ? <div className="fishing-actions"><Button disabled={busy} onClick={() => action('decide', { action: 'publicado' })}>Sim, publiquei</Button><Button variant="secondary" disabled={busy} onClick={() => action('decide', { action: 'pulado' })}>Não publiquei · pular</Button></div> : <p className="muted">Aguardando confirmação de quem abriu este post.</p>}
    </div>}
    {['descartado', 'erro'].includes(row.status) && <Button variant="secondary" disabled={busy} onClick={() => action('regenerate', {})}>Avaliar novamente</Button>}
    {row.status === 'publicado' && <><blockquote>{row.published_text}</blockquote>{row.user_id === user?.id && <Button variant="ghost" disabled={busy} onClick={() => action('decide', { action: 'desfazer' })}>Desfazer confirmação</Button>}<small className="muted">Desfazer altera só o registro no Antares.</small></>}
    {!canReview && !pending && <a href={row.url} target="_blank" rel="noopener noreferrer">Ver post no Instagram <ExternalLink size={13} /></a>}
  </article>;
}
