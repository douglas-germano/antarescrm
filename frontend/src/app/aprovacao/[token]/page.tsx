'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { CheckCircle2, FileText, MessageSquareWarning } from 'lucide-react';
import { DataState } from '@/components/ui';
import type { Row } from '@/lib/types';

async function call(path: string, body?: unknown) {
  const response = await fetch('/api/public/approvals/' + path, { method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error?.message || 'Não foi possível concluir. Tente novamente.');
  return data;
}

/** The page a client opens from the approval link: no login, one decision. */
export default function ApprovalPage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<Row>();
  const [error, setError] = useState<Error>();
  const [name, setName] = useState('');
  const [comment, setComment] = useState('');
  const [mode, setMode] = useState<'approved' | 'changes_requested' | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [done, setDone] = useState<string>();

  useEffect(() => { call('approvals/' + token).then(setData).catch(setError); }, [token]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!mode || busy) return;
    setBusy(true); setFailure('');
    try {
      const result = await call(`approvals/${token}/decide`, { decision: mode, name: name.trim(), ...(comment.trim() ? { comment: comment.trim() } : {}) });
      setDone(result.status);
    } catch (e) { setFailure((e as Error).message); }
    finally { setBusy(false); }
  }

  const fileUrl = `/api/public/approvals/approvals/${token}/file?inline=1`;
  return (
    <main className="capture-page approval-page">
      <section className="capture-card approval-card">
        <DataState loading={!data && !error} error={error}>
          {data && (
            <div className="stack">
              <p className="small-caps">{data.company}</p>
              <h1>{data.title}</h1>
              <p className="muted">Projeto: {data.project}</p>
              {data.message && <p className="approval-note">{data.message}</p>}
              {data.file && (
                <div className="approval-file">
                  {data.file.mimetype === 'video/mp4' ? <video src={fileUrl} controls preload="metadata" />
                    : data.file.mimetype.startsWith('image/') ? <a href={fileUrl} target="_blank" rel="noreferrer"><img src={fileUrl} alt={data.file.name} /></a>
                    : data.file.mimetype === 'application/pdf' ? <iframe src={fileUrl} title={data.file.name} />
                    : <a className="btn btn-secondary" href={fileUrl.replace('?inline=1', '')}><FileText size={16} /> Baixar {data.file.name}</a>}
                  <small className="muted">{data.file.name} · versão {data.file.version}</small>
                </div>
              )}

              {done ? (
                <div className="approval-done" role="status">
                  {done === 'approved' ? <CheckCircle2 size={40} color="#2e7d52" /> : <MessageSquareWarning size={40} color="#c77d00" />}
                  <h2>{done === 'approved' ? 'Aprovação registrada' : 'Pedido de ajustes enviado'}</h2>
                  <p className="muted">Obrigado! A equipe foi avisada da sua resposta. Você pode fechar esta página.</p>
                </div>
              ) : data.status !== 'pending' ? (
                <p className="approval-closed" role="status">
                  {data.status === 'approved' ? 'Esta solicitação já foi aprovada.' : data.status === 'changes_requested' ? 'Os ajustes desta solicitação já foram enviados.'
                    : data.status === 'expired' ? 'Este link expirou. Peça um novo link à equipe.' : 'Esta solicitação não está mais disponível.'}
                </p>
              ) : !mode ? (
                <div className="approval-choices">
                  <button type="button" className="btn btn-primary" onClick={() => setMode('approved')}>Aprovar</button>
                  <button type="button" className="btn btn-secondary" onClick={() => setMode('changes_requested')}>Solicitar ajustes</button>
                </div>
              ) : (
                <form className="stack" onSubmit={submit}>
                  <div className="field"><label htmlFor="ap-name">Seu nome <span className="required">*</span></label><input id="ap-name" required maxLength={150} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></div>
                  <div className="field"><label htmlFor="ap-comment">{mode === 'approved' ? 'Comentário (opcional)' : 'Quais ajustes você deseja?'}{mode === 'changes_requested' && <span className="required"> *</span>}</label>
                    <textarea id="ap-comment" rows={4} maxLength={2000} required={mode === 'changes_requested'} value={comment} onChange={(e) => setComment(e.target.value)} /></div>
                  <p className="muted approval-legal">Ao enviar, sua resposta é registrada com seu nome, data e horário, como comprovação desta decisão.</p>
                  {failure && <p className="form-error" role="alert">{failure}</p>}
                  <div className="approval-choices">
                    <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? 'Enviando…' : mode === 'approved' ? 'Confirmar aprovação' : 'Enviar ajustes'}</button>
                    <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => setMode(null)}>Voltar</button>
                  </div>
                </form>
              )}
            </div>
          )}
        </DataState>
      </section>
    </main>
  );
}
