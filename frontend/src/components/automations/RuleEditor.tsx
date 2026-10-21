'use client';
import { useState } from 'react';
import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from 'lucide-react';
import { post, patch, refreshAll } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, Modal } from '@/components/ui';
import { ConditionsEditor, emptyConditions, type Conditions } from '@/components/automations/conditions-editor';
import type { Row } from '@/lib/types';
import { ACTIONS, DELAY_UNITS, EVENTS, newStep, splitDelay, stepsOf, type Step } from '@/components/automations/model';

/** Draft of a rule; `id` is present when editing an existing one. */
export type RuleDraft = Partial<Row> & { name?: string; event?: string; steps?: Step[] };

function DelayField({ minutes, onChange }: { minutes: number; onChange: (minutes: number) => void }) {
  const initial = splitDelay(minutes);
  const [unit, setUnit] = useState(initial.unit);
  const amount = Math.round(minutes / unit);
  return (
    <div className="field">
      <label>Esperar antes desta etapa</label>
      <div className="delay-input">
        <input type="number" min={0} max={Math.floor(525600 / unit)} required aria-label="Tempo de espera" value={amount} onChange={(e) => onChange(Number(e.target.value) * unit)} />
        <select aria-label="Unidade" value={unit} onChange={(e) => { const next = Number(e.target.value); setUnit(next); onChange(amount * next); }}>
          {DELAY_UNITS.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
        </select>
      </div>
    </div>
  );
}

export function RuleEditor({ draft, onClose, staff, templates, stages }: {
  draft: RuleDraft | null; onClose: () => void; staff: Row[]; templates: Row[]; stages: Row[];
}) {
  const { notify } = useNotify();
  return (
    <Modal open={draft !== null} onClose={onClose} title={draft?.id ? 'Editar automação' : 'Nova automação'} wide>
      {draft && <EditorForm key={draft.id || draft.name || 'new'} draft={draft} onClose={onClose} staff={staff} templates={templates} stages={stages} notify={notify} />}
    </Modal>
  );
}

function EditorForm({ draft, onClose, staff, templates, stages, notify }: {
  draft: RuleDraft; onClose: () => void; staff: Row[]; templates: Row[]; stages: Row[]; notify: (message: string, kind?: 'error') => void;
}) {
  const [conditions, setConditions] = useState<Conditions>({ ...emptyConditions(), ...draft.conditions });
  const [steps, setSteps] = useState<Step[]>(draft.steps?.length ? draft.steps : stepsOf({ actions: draft.actions, task_title: draft.task_title, due_days: draft.due_days }));
  const [event, setEvent] = useState(draft.event || 'contact.created');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const change = (index: number, update: Partial<Step>) => setSteps((previous) => previous.map((step, i) => (i === index ? { ...step, ...update } : step)));
  const move = (index: number, direction: -1 | 1) => setSteps((previous) => {
    const target = index + direction;
    if (target < 0 || target >= previous.length) return previous;
    const next = [...previous];
    [next[index], next[target]] = [next[target], next[index]];
    return next;
  });

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setFailure('');
    const form = new FormData(event.currentTarget);
    const data = {
      conditions,
      name: String(form.get('name')),
      event: String(form.get('event')),
      source: String(form.get('source') || '') || null,
      required_tag: String(form.get('required_tag') || '') || null,
      assignee_id: String(form.get('assignee_id') || '') || null,
      active: form.get('active') === 'on',
      stop_on_reply: form.get('stop_on_reply') === 'on',
      task_title: steps.find((step) => step.title)?.title || String(form.get('name')),
      due_days: 0,
      actions: steps.map((step) => ({
        conditions: step.conditions || emptyConditions(), kind: step.kind, delay_minutes: step.delay_minutes, due_days: step.due_days,
        ...(step.kind === 'send_message' ? { template_id: step.template_id } : step.kind === 'reply_comment' || step.kind === 'private_reply' ? { content: step.content } : step.kind === 'add_tag' ? { tag: step.tag } : step.kind === 'move_stage' ? { stage_id: step.stage_id } : { title: step.title }),
      })),
    };
    try {
      if (draft.id) await patch('/automations/' + draft.id, data);
      else await post('/automations', data);
      await refreshAll();
      notify('Automação salva.');
      onClose();
    } catch (error) {
      setFailure((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="auto-form stack" onSubmit={submit}>
      <section className="auto-section">
        <header><span className="auto-step-no">1</span><div><h3>Identificação</h3><p>Dê um nome claro e escolha se a automação já começa ativa.</p></div></header>
        <div className="form-grid">
          <div className="field"><label htmlFor="auto-name">Nome da automação</label><input id="auto-name" name="name" required maxLength={150} defaultValue={draft.name || ''} placeholder="Ex.: Primeiro contato com novos leads" /></div>
          <div className="field"><label htmlFor="auto-assignee">Responsável pelas tarefas</label>
            <select id="auto-assignee" name="assignee_id" defaultValue={draft.assignee_id || ''}><option value="">Sem responsável</option>{staff.filter((u) => u.active).map((u) => <option value={u.id} key={u.id}>{u.name}</option>)}</select></div>
        </div>
        <label className="checkbox-label"><input name="active" type="checkbox" defaultChecked={draft.id ? draft.active : true} />Automação ativa</label>
      </section>

      <section className="auto-section">
        <header><span className="auto-step-no">2</span><div><h3>Quando acontecer</h3><p>{EVENTS[event]?.hint}</p></div></header>
        <div className="field"><label htmlFor="auto-event">Gatilho</label>
          <select id="auto-event" name="event" value={event} onChange={(e) => setEvent(e.target.value)}>{Object.entries(EVENTS).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}</select></div>
        <div className="form-grid">
          <div className="field"><label htmlFor="auto-source">Somente desta origem</label><input id="auto-source" name="source" maxLength={100} defaultValue={draft.source || ''} placeholder="Opcional" /></div>
          <div className="field"><label htmlFor="auto-tag">Somente contatos com a tag</label><input id="auto-tag" name="required_tag" maxLength={80} defaultValue={draft.required_tag || ''} placeholder="Opcional" /></div>
        </div>
        <ConditionsEditor value={conditions} onChange={setConditions} />
        <label className="checkbox-label"><input name="stop_on_reply" type="checkbox" defaultChecked={draft.stop_on_reply || false} />Interromper as ações futuras quando o contato responder</label>
      </section>

      <section className="auto-section">
        <header><span className="auto-step-no">3</span><div><h3>Fazer isto</h3><p>As etapas rodam em ordem; a espera de cada uma conta a partir da anterior. Se uma falhar, as seguintes param.</p></div></header>
        <ol className="auto-steps">
          {steps.map((step, index) => (
            <li key={index} className="auto-step">
              <div className="auto-step-head">
                <strong>Etapa {index + 1}</strong>
                <div className="auto-step-tools">
                  <button type="button" className="icon-btn" aria-label="Subir etapa" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={15} /></button>
                  <button type="button" className="icon-btn" aria-label="Descer etapa" disabled={index === steps.length - 1} onClick={() => move(index, 1)}><ArrowDown size={15} /></button>
                  <button type="button" className="icon-btn" aria-label="Duplicar etapa" disabled={steps.length >= 10} onClick={() => setSteps((p) => [...p.slice(0, index + 1), { ...step }, ...p.slice(index + 1)])}><Copy size={15} /></button>
                  {steps.length > 1 && <button type="button" className="icon-btn" aria-label="Remover etapa" onClick={() => setSteps((p) => p.filter((_, i) => i !== index))}><Trash2 size={15} /></button>}
                </div>
              </div>
              <div className="form-grid">
                <div className="field"><label>Ação</label>
                  <select aria-label="Ação" value={step.kind} onChange={(e) => change(index, { kind: e.target.value })}>{Object.entries(ACTIONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
                <DelayField minutes={step.delay_minutes} onChange={(minutes) => change(index, { delay_minutes: minutes })} />
              </div>
              {step.kind === 'send_message' && (
                <div className="field"><label>Modelo de mensagem</label>
                  <select required aria-label="Modelo de mensagem" value={step.template_id || ''} onChange={(e) => change(index, { template_id: e.target.value })}><option value="">Selecione um modelo</option>{templates.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.channel}</option>)}</select></div>
              )}
              {(step.kind === 'reply_comment' || step.kind === 'private_reply') && (
                <div className="field"><label>{step.kind === 'reply_comment' ? 'Resposta pública ao comentário' : 'Mensagem privada (direct)'}</label>
                  <textarea required rows={3} maxLength={1000} aria-label="Texto da resposta" value={step.content || ''} onChange={(e) => change(index, { content: e.target.value })} placeholder="Ex.: Oi, {{name}}! Obrigado pelo comentário." />
                  <small>Use {'{{name}}'} para o nome da pessoa e {'{{username}}'} para o @. Cada comentário recebe no máximo uma resposta de cada tipo, com limite de 60 por hora. A mensagem privada só pode ser enviada até 7 dias após o comentário.</small></div>
              )}
              {step.kind === 'add_tag' && (
                <div className="field"><label>Tag</label><input required maxLength={80} aria-label="Tag" value={step.tag || ''} onChange={(e) => change(index, { tag: e.target.value })} placeholder="Ex.: cliente" /></div>
              )}
              {step.kind === 'move_stage' && (
                <div className="field"><label>Etapa de destino</label>
                  <select required aria-label="Etapa de destino" value={step.stage_id || ''} onChange={(e) => change(index, { stage_id: e.target.value })}><option value="">Selecione…</option>{stages.map((s) => <option key={s.id} value={s.id}>{s.pipeline_name} · {s.name}</option>)}</select>
                  <small>Só atua em negócios em aberto vinculados ao evento.</small></div>
              )}
              {(step.kind === 'create_task' || step.kind === 'follow_up') && (
                <div className="form-grid">
                  <div className="field"><label>Título</label><input required maxLength={180} aria-label="Título" value={step.title || ''} onChange={(e) => change(index, { title: e.target.value })} /></div>
                  <div className="field"><label>{step.kind === 'follow_up' ? 'Retorno em (dias)' : 'Prazo da tarefa (dias)'}</label><input type="number" required min={0} max={365} aria-label="Dias" value={step.due_days} onChange={(e) => change(index, { due_days: Number(e.target.value) })} /></div>
                </div>
              )}
              <details className="auto-step-conditions" open={!!step.conditions?.items?.length}>
                <summary>Executar somente se…{step.conditions?.items?.length ? ` (${step.conditions.items.length})` : ''}</summary>
                <ConditionsEditor label="Condições da etapa" value={{ ...emptyConditions(), ...step.conditions }} onChange={(value) => change(index, { conditions: value })} />
              </details>
            </li>
          ))}
        </ol>
        <div><Button variant="secondary" disabled={steps.length >= 10} onClick={() => setSteps((p) => [...p, newStep()])}><Plus size={16} /> Adicionar etapa</Button></div>
      </section>

      {failure && <p role="alert" className="form-error">{failure}</p>}
      <div className="modal-footer"><Button variant="secondary" onClick={onClose}>Cancelar</Button><Button type="submit" disabled={busy}>{busy ? 'Salvando…' : 'Salvar automação'}</Button></div>
    </form>
  );
}
