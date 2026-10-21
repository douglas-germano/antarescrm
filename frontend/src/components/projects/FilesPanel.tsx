'use client';
import { useRef, useState } from 'react';
import { Download, FileText, History, ImageIcon, Plus, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { api, refreshAll } from '@/lib/api';
import { day } from '@/lib/format';
import { useNotify } from '../providers';
import { Button, ConfirmDialog, EmptyState, Modal } from '../ui';
import type { Row } from '@/lib/types';
import { FILE_KINDS, fileSize, fileUrl } from './model';

/** Layouts and documents of a project, grouped so each re-upload becomes a new version. */
export function FilesPanel({ project, onRequestApproval }: { project: Row; onRequestApproval: (file: Row) => void }) {
  const { notify } = useNotify();
  const input = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState<Row | null>(null);
  const [dialog, setDialog] = useState<{ file: File; group?: Row } | null>(null);
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ title: '', kind: 'layout', note: '' });

  function choose(file?: File, group?: Row) {
    if (!file) return;
    if (file.size > 14 * 1024 * 1024) { notify('O arquivo deve ter até 14 MB.', 'error'); return; }
    setForm({ title: group?.title || file.name.replace(/\.[^.]+$/, ''), kind: group?.kind || 'layout', note: '' });
    setDialog({ file, group });
  }
  async function send() {
    if (!dialog) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.set('file', dialog.file);
      body.set('title', form.title.trim() || dialog.file.name);
      body.set('kind', form.kind);
      if (form.note.trim()) body.set('note', form.note.trim());
      if (dialog.group) body.set('replaces_group_id', dialog.group.group_id);
      const response = await fetch(`/api/backend/projects/${project.id}/files`, { method: 'POST', body });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.error?.message || 'Não foi possível enviar o arquivo.');
      await refreshAll();
      notify(dialog.group ? 'Nova versão enviada.' : 'Arquivo enviado.');
      setDialog(null);
    } catch (e) { notify((e as Error).message, 'error'); }
    finally { setBusy(false); }
  }

  return (
    <section className="proj-files">
      <input ref={input} type="file" hidden aria-label="Arquivo do projeto" onChange={(e) => { choose(e.target.files?.[0], replacing || undefined); setReplacing(null); e.target.value = ''; }} />
      <div className="proj-toolbar">
        <p className="muted">Artes, vídeos MP4, PDF, documentos do Office, ZIP e arquivos PSD/AI, até 14 MB. Cada novo envio do mesmo criativo vira uma versão.</p>
        <Button onClick={() => { setReplacing(null); input.current?.click(); }}><Upload size={16} /> Enviar arquivo</Button>
      </div>
      {project.files.length ? (
        <div className="file-grid">
          {project.files.map((group: Row) => {
            const file = group.latest;
            return (
              <article key={group.group_id} className="file-card">
                <a className="file-preview" href={fileUrl(project.id, file.id, true)} target="_blank" rel="noreferrer" aria-label={'Abrir ' + group.title}>
                  {file.mimetype === 'video/mp4' ? <video src={fileUrl(project.id, file.id, true)} muted preload="metadata" /> : file.mimetype.startsWith('image/') ? <img src={fileUrl(project.id, file.id, true)} alt={group.title} loading="lazy" /> : file.mimetype === 'application/pdf' ? <FileText size={40} /> : <ImageIcon size={40} />}
                </a>
                <div className="file-info">
                  <div className="file-title"><strong title={group.title}>{group.title}</strong><span className="deal-chip">v{file.version}</span></div>
                  <small>{FILE_KINDS[group.kind] || group.kind} · {fileSize(file.size)} · {day(file.created_at)}</small>
                  {file.note && <small className="file-note">{file.note}</small>}
                </div>
                <div className="file-actions">
                  <a className="icon-btn" href={fileUrl(project.id, file.id)} title="Baixar" aria-label={'Baixar ' + group.title}><Download size={15} /></a>
                  <button type="button" className="icon-btn" title="Enviar nova versão" aria-label={'Nova versão de ' + group.title} onClick={() => { setReplacing(group); input.current?.click(); }}><Plus size={15} /></button>
                  <button type="button" className="icon-btn" title="Solicitar aprovação" aria-label={'Solicitar aprovação de ' + group.title} onClick={() => onRequestApproval(file)}><ShieldCheck size={15} /></button>
                  {group.versions.length > 1 && <button type="button" className="icon-btn" title="Versões" aria-label={'Versões de ' + group.title} onClick={() => setHistory(history === group.group_id ? null : group.group_id)}><History size={15} /></button>}
                  <button type="button" className="icon-btn danger" title="Excluir versão atual" aria-label={'Excluir ' + group.title} onClick={() => setDeleting(file)}><Trash2 size={15} /></button>
                </div>
                {history === group.group_id && (
                  <ul className="version-list">
                    {group.versions.map((v: Row) => (
                      <li key={v.id}><span className="deal-chip">v{v.version}</span><span>{day(v.created_at)} · {fileSize(v.size)}</span>
                        <a href={fileUrl(project.id, v.id, true)} target="_blank" rel="noreferrer">Abrir</a><a href={fileUrl(project.id, v.id)}>Baixar</a></li>
                    ))}
                  </ul>
                )}
              </article>
            );
          })}
        </div>
      ) : <EmptyState icon={<ImageIcon />} title="Nenhum arquivo ainda" description="Envie o primeiro criativo ou documento deste projeto." />}

      <Modal open={!!dialog} onClose={() => { if (!busy) setDialog(null); }} title={dialog?.group ? 'Nova versão' : 'Enviar arquivo'} description={dialog?.file.name}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); void send(); }}>
          <div className="field"><label htmlFor="pf-title">Nome</label><input id="pf-title" required maxLength={180} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
          <div className="field"><label htmlFor="pf-kind">Tipo</label>
            <select id="pf-kind" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{Object.entries(FILE_KINDS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div className="field"><label htmlFor="pf-note">Observação</label><textarea id="pf-note" rows={3} maxLength={2000} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="O que mudou nesta versão?" /></div>
          <div className="modal-footer"><Button variant="secondary" disabled={busy} onClick={() => setDialog(null)}>Cancelar</Button><Button type="submit" disabled={busy}>{busy ? 'Enviando…' : 'Enviar'}</Button></div>
        </form>
      </Modal>
      <ConfirmDialog open={!!deleting} onClose={() => setDeleting(null)} title="Excluir esta versão?" description="Se houver aprovações ligadas a ela, o arquivo fica oculto, mas o histórico é mantido."
        onConfirm={async () => { await api(`/projects/${project.id}/files/${deleting!.id}`, { method: 'DELETE' }); await refreshAll(); setDeleting(null); notify('Arquivo excluído.'); }} />
    </section>
  );
}
