import { useState } from 'react';
import { Download, FileText } from 'lucide-react';
import type { Row } from '@/lib/types';

export function MessageMedia({ message }: { message: Row }) {
  const [failed, setFailed] = useState(false);
  const url = '/api/backend' + message.media_path;
  if (failed)
    return (
      <div className="wa-media-error">
        Não foi possível recuperar a mídia.{' '}
        <a href={url} target="_blank" rel="noreferrer">
          Tentar baixar
        </a>
      </div>
    );
  if (['image', 'sticker'].includes(message.kind))
    return (
      <a href={url} target="_blank" rel="noreferrer">
        <img
          src={url}
          alt={message.kind === 'sticker' ? 'Figurinha recebida' : 'Imagem da conversa'}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      </a>
    );
  if (message.kind === 'audio') return <audio controls preload="none" src={url} onError={() => setFailed(true)} />;
  if (message.kind === 'video')
    return <video controls preload="metadata" src={url} onError={() => setFailed(true)} />;
  return (
    <a className="wa-file" href={url} target="_blank" rel="noreferrer">
      <FileText size={22} />
      <span>{message.filename || 'Baixar documento'}</span>
      <Download size={16} />
    </a>
  );
}
