'use client';
import { useState } from 'react';
import { Check, Copy, Link2, Plus, X } from 'lucide-react';
import { api, post, refreshAll } from '@/lib/api';
import { day, hour } from '@/lib/format';
import { useNotify } from '@/components/providers';
import { Badge, Button, ConfirmDialog, EmptyState, FormDialog, Modal } from '@/components/ui';
import type { Field, Row } from '@/lib/types';
import { APPROVAL } from '@/components/projects/model';

const linkOf = (token: string) => `${window.location.origin}/aprovacao/${token}`;

/** Approval requests for a project: public link for the client, or a decision registered by the team. */
export function ApprovalsPanel({ project, request, onNew, onClose }: { project: Row; request: Row | 'new' | null; onNew: () => void; onClose: () => void }) {
  const { notify } = useNotify();
  const [link, setLink] = useState<string | null>(null);
  const [deciding, setDeciding] = useState<Row | null>(null);
  const [cancelling, setCancelling] = useState<Row | null>(null);
  const files: Row[] = project.files.map((g: Row) => g.latest);
  const target = request && request !== 'new' ? request : null;

  const fields: Field[] = [
    { name: 'title', label: 'O que será aprovado', required: true, placeholder: 'Aprovação da arte do carrossel', wide: true },
    { name: 'file_id', label: 'Arquivo', type: 'select', options: files.map((f) => ({ value: f.id, label: `${f.title} (v${f.version})` })), help: 'A versão escolhida é a que o cliente vai ver.' },
    { name: 'channel', label: 'Como o cliente responde', type: 'select', required: true, options: [{ value: 'public', label: 'Pelo link público (sem login)' }, { value: 'internal', label: 'Registro manual pela equipe' }], defaultValue: 'public' },
    { name: 'expires_days', label: 'Validade do link (dias)', type: 'number', min: 1, max: 180, defaultValue: 30 },
    { name: 'message', label: 'Mensagem ao cliente', type: 'textarea', wide: true },
  ];

  return (
    <section className="proj-approvals">
      <div className="proj-toolbar">
        <p className="muted">Envie um criativo (arte, vídeo ou documento) para o cliente aprovar. O link público registra quem respondeu, quando e o comentário.</p>
        <Button onClick={onNew}><Plus size={16} /> Nova solicitação</Button>
      </div>
      {project.approvals.length ? (
        <ul className="approval-list">
          {project.approvals.map((a: Row) => {
            const state = a.expired ? 'expired' : a.status;
            return (
              <li key={a.id} className="approval-item">
                <div className="approval-main">
                  <div className="approval-head"><strong>{a.title}</strong><Badge value={APPROVAL[state]?.badge || 'skipped'} label={APPROVAL[state]?.label || state} /></div>
                  <small>{a.file_title ? `${a.file_title} (v${a.file_version}) · ` : ''}Solicitada em {day(a.created_at)} · {a.channel === 'public' ? 'link público' : 'registro manual'}</small>
                  {a.message && <p className="approval-message">{a.message}</p>}
                  {a.decided_at && (
                    <p className={'approval-decision ' + a.status}>
                      <strong>{a.decided_by}</strong> {a.status === 'approved' ? 'aprovou' : 'pediu ajustes'} em {day(a.decided_at)} às {hour(a.decided_at)}
                      {a.decided_ip && <small> · IP {a.decided_ip}</small>}
                      {a.decision_comment && <span>“{a.decision_comment}”</span>}
                    </p>
                  )}
                </div>
                {a.status === 'pending' && (
                  <div className="approval-actions">
                    {a.channel === 'public' && <Button variant="secondary" onClick={async () => { const r = await post(`/projects/${project.id}/approvals/${a.id}/regenerate`, {}); setLink(linkOf(r.token)); await refreshAll(); }}><Link2 size={15} /> Novo link</Button>}
                    <Button variant="secondary" onClick={() => setDeciding(a)}><Check size={15} /> Registrar resposta</Button>
                    <Button variant="ghost" onClick={() => setCancelling(a)}><X size={15} /> Cancelar</Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : <EmptyState icon={<Link2 />} title="Nenhuma aprovação solicitada" description="Use “Solicitar aprovação” em um arquivo, ou crie uma solicitação aqui." />}

      <FormDialog open={request !== null} onClose={onClose} title="Solicitar aprovação" fields={fields} submitLabel="Criar solicitação"
        initial={{ title: target ? `Aprovação: ${target.title}` : '', file_id: target?.id || '', channel: 'public', expires_days: 30 }}
        onSubmit={async (data) => {
          const body: Record<string, any> = { title: data.title, channel: data.channel || 'public', expires_days: Number(data.expires_days) || 30 };
          if (data.file_id) body.file_id = data.file_id;
          if (data.message) body.message = data.message;
          const created = await post(`/projects/${project.id}/approvals`, body);
          await refreshAll();
          if (created.token) setLink(linkOf(created.token));
          notify('Solicitação criada.');
        }} />

      <Modal open={!!link} onClose={() => setLink(null)} title="Link de aprovação" description="Envie este link ao cliente. Ele só aparece agora: se perder, gere um novo link.">
        <div className="stack">
          <div className="copy-row"><input readOnly value={link || ''} aria-label="Link de aprovação" onFocus={(e) => e.currentTarget.select()} />
            <Button onClick={async () => { await navigator.clipboard.writeText(link || ''); notify('Link copiado.'); }}><Copy size={15} /> Copiar</Button></div>
          <p className="muted">O cliente abre sem precisar de login, vê o arquivo e escolhe entre aprovar ou pedir ajustes. A resposta é registrada com nome, data e comentário, e o link só funciona uma vez.</p>
          <div className="modal-footer"><Button onClick={() => setLink(null)}>Concluir</Button></div>
        </div>
      </Modal>

      <FormDialog open={!!deciding} onClose={() => setDeciding(null)} title="Registrar resposta do cliente" description={deciding?.title} submitLabel="Registrar"
        fields={[
          { name: 'decision', label: 'Resposta', type: 'select', required: true, options: [{ value: 'approved', label: 'Aprovado' }, { value: 'changes_requested', label: 'Ajustes solicitados' }] },
          { name: 'name', label: 'Quem respondeu', required: true, placeholder: 'Nome do cliente (e canal, ex.: WhatsApp)' },
          { name: 'comment', label: 'Comentário', type: 'textarea', wide: true, help: 'Obrigatório quando houver ajustes.' },
        ]}
        onSubmit={async (data) => { await post(`/projects/${project.id}/approvals/${deciding!.id}/decide`, { decision: data.decision, name: data.name, ...(data.comment ? { comment: data.comment } : {}) }); await refreshAll(); notify('Resposta registrada.'); }} />
      <ConfirmDialog open={!!cancelling} onClose={() => setCancelling(null)} title="Cancelar solicitação?" description="O link deixa de funcionar. O histórico é mantido."
        onConfirm={async () => { await post(`/projects/${project.id}/approvals/${cancelling!.id}/cancel`, {}); await refreshAll(); setCancelling(null); notify('Solicitação cancelada.'); }} />
    </section>
  );
}
