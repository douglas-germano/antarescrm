import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Film, ImagePlus, Link2, Trash2 } from 'lucide-react';
import { patch, post, upload } from '@/lib/api';
import { useNotify, useSession } from '@/components/providers';
import { Button, Modal } from '@/components/ui';
import { Tabs } from '@/components/blocks';
import type { Row } from '@/lib/types';

export type MediaType = 'IMAGE' | 'CAROUSEL' | 'REELS';
type Item = { media_id?: string; url?: string; kind: 'image' | 'video'; filename?: string; preview?: string };

export const TYPES: { value: MediaType; label: string }[] = [
  { value: 'IMAGE', label: 'Imagem' },
  { value: 'CAROUSEL', label: 'Carrossel' },
  { value: 'REELS', label: 'Reel' },
];
const CAPTION_MAX = 2200;
const MAX_ITEMS: Record<MediaType, number> = { IMAGE: 1, CAROUSEL: 10, REELS: 1 };

export const mediaSrc = (item: Item) => item.preview || (item.media_id ? `/api/backend/instagram/media/${item.media_id}/file` : item.url || '');

/** Instagram only takes JPEG photos: other images are redrawn as JPEG in the browser before upload. */
async function asJpeg(file: File): Promise<File> {
  if (file.type === 'image/jpeg') return file;
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1440 / bitmap.width);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext('2d')!;
  context.fillStyle = '#fff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
  if (!blob) throw new Error('Não foi possível converter a imagem para JPEG.');
  return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' });
}

function toLocalInput(value?: string | null) {
  const date = value ? new Date(value) : new Date(Date.now() + 3600_000);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 16);
}

export function Composer({ open, onClose, accounts, account, editing, onSaved }: {
  open: boolean; onClose: () => void; accounts: Row[]; account: string; editing: Row | null; onSaved: () => void;
}) {
  const { notify } = useNotify();
  const { user } = useSession();
  const manager = ['owner', 'admin'].includes(user?.role || '');
  const [type, setType] = useState<MediaType>('IMAGE');
  const [connection, setConnection] = useState(account);
  const [caption, setCaption] = useState('');
  const [items, setItems] = useState<Item[]>([]);
  const [link, setLink] = useState('');
  const [when, setWhen] = useState(toLocalInput());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setType((editing?.media_type as MediaType) || 'IMAGE');
    setConnection(editing?.connection_id || account);
    setCaption(editing?.caption || '');
    setItems((editing?.items as Item[]) || []);
    setWhen(toLocalInput(editing?.status === 'scheduled' ? editing.scheduled_at : null));
    setLink(''); setError('');
  }, [open, editing, account]);

  const profile = accounts.find(a => a.id === connection);
  const hashtags = (caption.match(/(^|\s)#\w/g) || []).length;
  const accept = type === 'REELS' ? 'video/mp4,video/quicktime' : type === 'IMAGE' ? 'image/*' : 'image/*,video/mp4,video/quicktime';
  const full = items.length >= MAX_ITEMS[type];
  const problems = useMemo(() => {
    const list: string[] = [];
    if (!items.length) list.push(type === 'REELS' ? 'Adicione o vídeo do Reel.' : 'Adicione a mídia da publicação.');
    if (type === 'CAROUSEL' && items.length === 1) list.push('Um carrossel precisa de pelo menos 2 itens.');
    if (type === 'IMAGE' && items.some(i => i.kind !== 'image')) list.push('Use uma imagem, ou escolha Reel para vídeos.');
    if (type === 'REELS' && items.some(i => i.kind !== 'video')) list.push('Um Reel usa um vídeo.');
    if (caption.length > CAPTION_MAX) list.push(`A legenda passou de ${CAPTION_MAX} caracteres.`);
    if (hashtags > 30) list.push('O Instagram aceita até 30 hashtags.');
    return list;
  }, [items, type, caption, hashtags]);

  async function addFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true); setError('');
    try {
      const room = MAX_ITEMS[type] - items.length;
      const added: Item[] = [];
      for (const original of Array.from(files).slice(0, Math.max(0, room))) {
        const video = original.type.startsWith('video/');
        const file = video ? original : await asJpeg(original);
        const body = new FormData();
        body.set('file', file);
        const row = await upload<Row>('/instagram/media', body);
        added.push({ media_id: row.id, kind: row.kind, filename: row.filename, preview: URL.createObjectURL(file) });
      }
      setItems(current => [...current, ...added]);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  function addLink() {
    const url = link.trim();
    if (!/^https:\/\/\S+$/.test(url)) { setError('Informe um link público que comece com https://'); return; }
    const kind = /\.(mp4|mov)(\?|$)/i.test(url) || type === 'REELS' ? 'video' : 'image';
    setItems(current => [...current, { url, kind }]);
    setLink(''); setError('');
  }

  const move = (index: number, delta: number) => setItems(current => {
    const next = [...current];
    const [item] = next.splice(index, 1);
    next.splice(index + delta, 0, item);
    return next;
  });

  async function save(action: 'draft' | 'schedule' | 'publish') {
    if (action !== 'draft' && problems.length) { setError(problems[0]); return; }
    setBusy(true); setError('');
    const payload = {
      connection_id: connection, media_type: type, caption,
      items: items.map(({ media_id, url, kind }) => (media_id ? { media_id } : { url, kind })),
    };
    const scheduled_at = action === 'schedule' ? new Date(when).toISOString() : null;
    try {
      if (editing) {
        await patch<Row>(`/instagram/posts/${editing.id}`, payload);
        if (action === 'draft' && editing.status === 'scheduled') await post(`/instagram/posts/${editing.id}/cancel`, {});
        if (action !== 'draft') await post(`/instagram/posts/${editing.id}/schedule`, scheduled_at ? { scheduled_at } : {});
      } else {
        await post('/instagram/posts', { ...payload, scheduled_at, action });
      }
      notify(action === 'publish' ? 'Publicação enviada. O Instagram leva alguns instantes para concluir.' : action === 'schedule' ? 'Publicação agendada.' : 'Rascunho salvo.');
      onSaved(); onClose();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  return <Modal open={open} onClose={() => { if (!busy) onClose(); }} wide
    title={editing ? 'Editar publicação' : 'Nova publicação'} description="Imagem, carrossel ou Reel, publicado agora ou no horário que você escolher.">
    <div className="ig-composer">
      <form className="stack" onSubmit={(e) => { e.preventDefault(); void save('publish'); }}>
        <div className="form-grid">
          <div className="field"><label htmlFor="ig-account">Perfil</label>
            <select id="ig-account" value={connection} onChange={(e) => setConnection(e.target.value)} disabled={busy}>
              {accounts.map(a => <option key={a.id} value={a.id} disabled={!a.can_publish}>@{a.username}{a.can_publish ? '' : ' · reautorize para publicar'}</option>)}
            </select></div>
          <div className="field"><span className="field-label">Formato</span>
            <Tabs label="Formato da publicação" items={TYPES} value={type} onChange={(value) => { setType(value); setItems(current => current.slice(0, MAX_ITEMS[value])); }} /></div>
        </div>
        <div className="field">
          <span className="field-label">Mídia {type === 'CAROUSEL' && <small>({items.length}/10)</small>}</span>
          {items.length > 0 && <ol className="ig-media-list">
            {items.map((item, index) => <li key={(item.media_id || item.url) + ':' + index}>
              <span className="ig-thumb">{item.kind === 'video' ? <video src={mediaSrc(item)} muted preload="metadata" /> : <img src={mediaSrc(item)} alt="" />}</span>
              <span className="ig-media-name">{item.kind === 'video' && <Film size={14} />}{item.filename || item.url}</span>
              {type === 'CAROUSEL' && <>
                <button type="button" className="icon-btn" aria-label="Mover para cima" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={14} /></button>
                <button type="button" className="icon-btn" aria-label="Mover para baixo" disabled={index === items.length - 1} onClick={() => move(index, 1)}><ArrowDown size={14} /></button>
              </>}
              <button type="button" className="icon-btn danger" aria-label="Remover mídia" onClick={() => setItems(items.filter((_, i) => i !== index))}><Trash2 size={14} /></button>
            </li>)}
          </ol>}
          {!full && <div className="ig-media-actions">
            <input ref={input} type="file" hidden multiple={type === 'CAROUSEL'} accept={accept} aria-label="Arquivo da publicação"
              onChange={(e) => { void addFiles(e.target.files); e.target.value = ''; }} />
            <Button variant="secondary" disabled={busy} onClick={() => input.current?.click()}><ImagePlus size={16} />Enviar {type === 'REELS' ? 'vídeo' : 'arquivo'}</Button>
            <div className="ig-link">
              <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="ou cole um link público https://" aria-label="Link público da mídia" disabled={busy}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addLink(); } }} />
              <Button variant="ghost" disabled={busy || !link.trim()} onClick={addLink}><Link2 size={16} />Adicionar</Button>
            </div>
          </div>}
          <small className="muted">JPEG (outras imagens são convertidas automaticamente) ou vídeo MP4/MOV, até 14 MB por arquivo. Proporção entre 4:5 e 1,91:1; Reels em 9:16.</small>
        </div>
        <div className="field">
          <label htmlFor="ig-caption">Legenda</label>
          <textarea id="ig-caption" rows={6} value={caption} onChange={(e) => setCaption(e.target.value)} disabled={busy} placeholder="Escreva a legenda, com hashtags e menções." />
          <small className={caption.length > CAPTION_MAX || hashtags > 30 ? 'text-danger' : ''}>{caption.length}/{CAPTION_MAX} caracteres · {hashtags}/30 hashtags</small>
        </div>
        {manager && <div className="field ig-when">
          <label htmlFor="ig-when">Agendar para</label>
          <input id="ig-when" type="datetime-local" value={when} min={toLocalInput(new Date().toISOString())} onChange={(e) => setWhen(e.target.value)} disabled={busy} />
          <small>Horário do seu navegador. O Antares publica no momento marcado; o computador do servidor precisa estar ligado.</small>
        </div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="row-actions ig-composer-actions">
          <Button variant="ghost" disabled={busy} onClick={() => save('draft')}>Salvar rascunho</Button>
          {manager && <Button variant="secondary" disabled={busy || !when} onClick={() => save('schedule')}>Agendar</Button>}
          {manager && <Button type="submit" disabled={busy || !profile?.can_publish}>Publicar agora</Button>}
        </div>
        {!manager && <p className="muted">Proprietários e administradores aprovam e publicam os rascunhos.</p>}
      </form>
      <aside className="ig-preview" aria-label="Pré-visualização">
        <header><span className="ig-avatar small" aria-hidden>{(profile?.username || '?').slice(0, 1).toUpperCase()}</span><strong>{profile?.username || 'perfil'}</strong></header>
        <div className={'ig-preview-media' + (type === 'REELS' ? ' reel' : '')}>
          {items[0] ? (items[0].kind === 'video' ? <video src={mediaSrc(items[0])} muted controls preload="metadata" /> : <img src={mediaSrc(items[0])} alt="" />) : <span className="muted">Pré-visualização</span>}
          {type === 'CAROUSEL' && items.length > 1 && <span className="ig-count">1/{items.length}</span>}
        </div>
        <p><strong>{profile?.username}</strong> {caption.slice(0, 280)}{caption.length > 280 ? '… mais' : ''}</p>
      </aside>
    </div>
  </Modal>;
}
