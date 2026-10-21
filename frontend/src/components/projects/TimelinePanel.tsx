'use client';
import { useState } from 'react';
import { CheckCircle2, FileText, MessageSquare, Repeat, ShieldCheck, Sparkles } from 'lucide-react';
import { post, refreshAll } from '@/lib/api';
import { day, hour } from '@/lib/format';
import { useNotify } from '../providers';
import { Button } from '../ui';
import type { Row } from '@/lib/types';

const ICON: Record<string, React.ReactNode> = {
  created: <Sparkles size={14} />, stage: <Repeat size={14} />, status: <CheckCircle2 size={14} />, file: <FileText size={14} />, approval: <ShieldCheck size={14} />, note: <MessageSquare size={14} />,
};

export function TimelinePanel({ project }: { project: Row }) {
  const { notify } = useNotify();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    try { await post(`/projects/${project.id}/notes`, { text: text.trim() }); setText(''); await refreshAll(); }
    catch (err) { notify((err as Error).message, 'error'); }
    finally { setBusy(false); }
  }
  return (
    <section className="proj-timeline">
      <form className="note-form" onSubmit={add}>
        <textarea aria-label="Nova anotação" rows={2} maxLength={500} placeholder="Registre uma decisão, ligação ou combinado com o cliente…" value={text} onChange={(e) => setText(e.target.value)} />
        <Button type="submit" disabled={busy || !text.trim()}>Registrar</Button>
      </form>
      <ol className="timeline">
        {project.events.map((e: Row) => (
          <li key={e.id} className={'tl-' + e.kind}>
            <span className="tl-icon">{ICON[e.kind] || ICON.note}</span>
            <div><p>{e.text}</p><small>{day(e.created_at)} às {hour(e.created_at)}{e.user_name ? ' · ' + e.user_name : ''}</small></div>
          </li>
        ))}
      </ol>
    </section>
  );
}
