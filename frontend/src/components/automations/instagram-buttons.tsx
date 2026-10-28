'use client';
import { Link2, MessageSquareReply, Plus, X } from 'lucide-react';
import { MAX_BUTTONS, MAX_QUICK_REPLIES, type LinkButton } from '@/components/automations/model';

/** Link buttons and quick replies for an Instagram direct message, as the official API allows them. */
export function InstagramButtons({ buttons, quickReplies, onChange }: {
  buttons: LinkButton[];
  quickReplies: string[];
  onChange: (patch: { buttons?: LinkButton[]; quick_replies?: string[] }) => void;
}) {
  const setButton = (index: number, patch: Partial<LinkButton>) => onChange({ buttons: buttons.map((b, i) => (i === index ? { ...b, ...patch } : b)) });
  const setReply = (index: number, value: string) => onChange({ quick_replies: quickReplies.map((q, i) => (i === index ? value : q)) });
  return (
    <div className="ig-buttons stack">
      <div className="field">
        <label><Link2 size={13} /> Botões de link</label>
        {buttons.map((button, index) => (
          <div className="ig-button-row" key={index}>
            <input maxLength={20} aria-label={`Nome do botão ${index + 1}`} placeholder="Ex.: Ver proposta" value={button.title} onChange={(e) => setButton(index, { title: e.target.value })} />
            <input type="url" maxLength={1000} aria-label={`Link do botão ${index + 1}`} placeholder="https://" value={button.url} onChange={(e) => setButton(index, { url: e.target.value })} />
            <button type="button" className="icon-btn" aria-label={`Remover botão ${index + 1}`} onClick={() => onChange({ buttons: buttons.filter((_, i) => i !== index) })}><X size={14} /></button>
          </div>
        ))}
        {buttons.length < MAX_BUTTONS && (
          <button type="button" className="btn btn-soft ig-add" onClick={() => onChange({ buttons: [...buttons, { title: '', url: '' }] })}><Plus size={14} />Adicionar botão</button>
        )}
        <small>Até {MAX_BUTTONS} botões, com nome de até 20 letras. O link abre dentro do Instagram. Com botões, o texto pode ter até 640 caracteres.</small>
      </div>
      <div className="field">
        <label><MessageSquareReply size={13} /> Respostas rápidas</label>
        <div className="ig-replies">
          {quickReplies.map((reply, index) => (
            <span className="ig-reply" key={index}>
              <input maxLength={20} aria-label={`Resposta rápida ${index + 1}`} placeholder="Ex.: Sim, quero" value={reply} onChange={(e) => setReply(index, e.target.value)} />
              <button type="button" aria-label={`Remover resposta ${index + 1}`} onClick={() => onChange({ quick_replies: quickReplies.filter((_, i) => i !== index) })}><X size={12} /></button>
            </span>
          ))}
          {quickReplies.length < MAX_QUICK_REPLIES && (
            <button type="button" className="btn btn-soft ig-add" onClick={() => onChange({ quick_replies: [...quickReplies, ''] })}><Plus size={14} />Adicionar resposta</button>
          )}
        </div>
        <small>Opções que o contato toca para responder (até {MAX_QUICK_REPLIES}, com até 20 letras). A opção tocada chega como mensagem do contato: use “Resposta do contato” numa ramificação para seguir caminhos diferentes. Só aparecem no aplicativo do celular.</small>
      </div>
    </div>
  );
}
