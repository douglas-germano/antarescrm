'use client';
import { useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ArrowRight, Check, ChevronLeft, ChevronRight, Clock, Copy, Filter, GitBranch, Maximize2, Pencil, Plus, Trash2, X, Zap, ZoomIn, ZoomOut } from 'lucide-react';
import { post, patch, refreshAll } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, ConfirmDialog } from '@/components/ui';
import { ConditionsEditor, emptyConditions, type Conditions } from '@/components/automations/conditions-editor';
import {
  ACTIONS, BRANCH_LABEL, DELAY_UNITS, EVENTS, MAX_DEPTH, MAX_PATH_STEPS, MAX_STEPS, countSteps, describeStep, editList, firstProblem,
  formatDelay, listAt, newBranch, newStep, pathKey, splitDelay, stepAt, stepPayload, stepProblem, type Step, type StepPath,
} from '@/components/automations/model';
import { actionIcon, eventIcon, isInstagram } from '@/components/automations/icons';
import type { Row } from '@/lib/types';

/** Everything the editor changes; `id` is present when the rule already exists. */
export type FlowDraft = {
  id?: string; name: string; event: string; source: string; required_tag: string; assignee_id: string;
  active: boolean; stop_on_reply: boolean; conditions: Conditions; steps: Step[];
};
type Selection = 'trigger' | StepPath | null;
const ZOOMS = [0.6, 0.75, 0.9, 1, 1.15, 1.3];

function DelayField({ minutes, onChange }: { minutes: number; onChange: (minutes: number) => void }) {
  const initial = splitDelay(minutes);
  const [unit, setUnit] = useState(initial.unit);
  const amount = Math.round(minutes / unit);
  return (
    <div className="field">
      <label>Esperar antes deste passo</label>
      <div className="delay-input">
        <input type="number" min={0} max={Math.floor(525600 / unit)} aria-label="Tempo de espera" value={amount} onChange={(e) => onChange(Math.max(0, Number(e.target.value)) * unit)} />
        <select aria-label="Unidade" value={unit} onChange={(e) => { const next = Number(e.target.value); setUnit(next); onChange(amount * next); }}>
          {DELAY_UNITS.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
        </select>
      </div>
      <small>A espera conta a partir do passo anterior.</small>
    </div>
  );
}

/** Line between two cards; shows the wait before the next step, like Gaio's connectors. */
function Connector({ delay, onInsert, disabled }: { delay?: number; onInsert: () => void; disabled: boolean }) {
  return (
    <div className="flow-connector">
      <span className="flow-line" />
      {delay ? <span className="flow-delay"><Clock size={12} />Esperar {formatDelay(delay)}</span> : null}
      <button type="button" className="flow-insert" aria-label="Inserir passo aqui" data-tip="Inserir passo" disabled={disabled} onClick={onInsert}><Plus size={13} /></button>
    </div>
  );
}

/** "Próximo passo" adds an action after the card; "Ramificar" splits everything after it into Sim / Não. */
function NodeFooter({ onAdd, onBranch, disabled, branchDisabled }: { onAdd: () => void; onBranch: () => void; disabled: boolean; branchDisabled: boolean }) {
  return (
    <div className="flow-node-footer">
      <button type="button" className="flow-next" disabled={branchDisabled} data-tip="Dividir o fluxo em dois caminhos por condição" onClick={(e) => { e.stopPropagation(); onBranch(); }}>
        Ramificar <GitBranch size={12} />
      </button>
      <button type="button" className="flow-next" disabled={disabled} onClick={(e) => { e.stopPropagation(); onAdd(); }}>
        Próximo passo <Plus size={12} />
      </button>
    </div>
  );
}

export function FlowEditor({ initial, staff, templates, stages }: { initial: FlowDraft; staff: Row[]; templates: Row[]; stages: Row[] }) {
  const router = useRouter();
  const { notify } = useNotify();
  const [draft, setDraft] = useState<FlowDraft>(initial);
  const [selected, setSelected] = useState<Selection>(initial.id ? null : 'trigger');
  const [zoom, setZoom] = useState(3);
  const [dirty, setDirty] = useState(!initial.id);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [editingName, setEditingName] = useState(!initial.id && !initial.name);
  const [removingBranch, setRemovingBranch] = useState<StepPath | null>(null);
  const lookups = {
    template: (id?: string) => templates.find((t) => t.id === id)?.name,
    stage: (id?: string) => stages.find((s) => s.id === id)?.name,
  };
  const update = (patchDraft: Partial<FlowDraft>) => { setDraft((d) => ({ ...d, ...patchDraft })); setDirty(true); setFailure(''); };
  const total = countSteps(draft.steps);
  const setSteps = (listPath: StepPath, edit: (list: Step[]) => Step[]) => update({ steps: editList(draft.steps, listPath, edit) });
  const updateStep = (path: StepPath, patchStep: Partial<Step>) => {
    const index = path[path.length - 1] as number;
    setSteps(path.slice(0, -1), (list) => list.map((s, i) => (i === index ? { ...s, ...patchStep } : s)));
  };
  /** A path is full at 10 steps, the flow at 30 in all; a branch also needs room for its depth. */
  const canInsert = (listPath: StepPath) => total < MAX_STEPS && listAt(draft.steps, listPath).length < MAX_PATH_STEPS;
  const canBranch = (listPath: StepPath) => total < MAX_STEPS && listPath.length / 2 < MAX_DEPTH;
  const insertStep = (listPath: StepPath, at: number) => {
    if (!canInsert(listPath)) return;
    setSteps(listPath, (list) => [...list.slice(0, at), newStep(), ...list.slice(at)]);
    setSelected([...listPath, at]);
  };
  // The steps after the split point move into the "Sim" path, so nothing the user built is lost.
  const insertBranch = (listPath: StepPath, at: number) => {
    if (!canBranch(listPath)) return;
    setSteps(listPath, (list) => [...list.slice(0, at), newBranch(list.slice(at))]);
    setSelected([...listPath, at]);
  };
  const moveStep = (path: StepPath, direction: -1 | 1) => {
    const index = path[path.length - 1] as number;
    const listPath = path.slice(0, -1);
    const list = listAt(draft.steps, listPath);
    const target = index + direction;
    if (target < 0 || target >= list.length || list[target].kind === 'branch') return;
    setSteps(listPath, (items) => { const next = [...items]; [next[index], next[target]] = [next[target], next[index]]; return next; });
    setSelected([...listPath, target]);
  };
  const removeStep = (path: StepPath) => {
    const index = path[path.length - 1] as number;
    setSteps(path.slice(0, -1), (list) => list.filter((_, i) => i !== index));
    setSelected(null);
  };
  const duplicateStep = (path: StepPath) => {
    const index = path[path.length - 1] as number;
    const listPath = path.slice(0, -1);
    if (!canInsert(listPath)) return;
    setSteps(listPath, (list) => [...list.slice(0, index + 1), { ...list[index] }, ...list.slice(index + 1)]);
    setSelected([...listPath, index + 1]);
  };

  async function save() {
    if (busy) return;
    if (!draft.name.trim()) { setEditingName(true); setFailure('Dê um nome à automação.'); return; }
    if (!draft.steps.length) { setFailure('Adicione ao menos um passo depois do gatilho.'); return; }
    const broken = firstProblem(draft.steps);
    if (broken) { setSelected(broken.path); setFailure(broken.problem); return; }
    setBusy(true);
    setFailure('');
    const body = {
      conditions: draft.conditions,
      name: draft.name.trim(),
      event: draft.event,
      source: draft.source.trim() || null,
      required_tag: draft.required_tag.trim() || null,
      assignee_id: draft.assignee_id || null,
      active: draft.active,
      stop_on_reply: draft.stop_on_reply,
      task_title: draft.steps.find((step) => step.title)?.title || draft.name.trim(),
      due_days: 0,
      actions: draft.steps.map(stepPayload),
    };
    try {
      if (draft.id) await patch('/automations/' + draft.id, body);
      const created = draft.id ? null : await post<{ id: string }>('/automations', body);
      await refreshAll();
      setDirty(false);
      notify('Automação salva.');
      // A new rule continues in its own address, so reloading or sharing the page keeps it.
      if (created) router.replace('/automacoes/' + created.id);
    } catch (error) {
      setFailure((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const filters = [
    draft.conditions.items.length && `${draft.conditions.items.length} ${draft.conditions.items.length === 1 ? 'condição' : 'condições'}`,
    draft.source && `Origem: ${draft.source}`,
    draft.required_tag && `Tag: ${draft.required_tag}`,
  ].filter(Boolean).join(' · ');
  const stepPath = Array.isArray(selected) ? selected : null;
  const step = stepPath ? stepAt(draft.steps, stepPath) : null;

  let panel: ReactNode = null;
  if (selected === 'trigger') {
    panel = <>
      <div className="field"><label htmlFor="flow-event">Quando acontecer</label>
        <select id="flow-event" value={draft.event} onChange={(e) => update({ event: e.target.value })}>
          {Object.entries(EVENTS).map(([value, meta]) => <option key={value} value={value}>{meta.label}</option>)}
        </select>
        <small>{EVENTS[draft.event]?.hint}</small></div>
      <div className="field"><label htmlFor="flow-source">Somente desta origem</label><input id="flow-source" maxLength={100} value={draft.source} placeholder="Opcional" onChange={(e) => update({ source: e.target.value })} /></div>
      <div className="field"><label htmlFor="flow-tag">Somente contatos com a tag</label><input id="flow-tag" maxLength={80} value={draft.required_tag} placeholder="Opcional" onChange={(e) => update({ required_tag: e.target.value })} /></div>
      <ConditionsEditor value={draft.conditions} onChange={(conditions) => update({ conditions })} />
      <label className="checkbox-label"><input type="checkbox" checked={draft.stop_on_reply} onChange={(e) => update({ stop_on_reply: e.target.checked })} />Interromper os próximos passos quando o contato responder</label>
      <div className="field"><label htmlFor="flow-assignee">Responsável pelas tarefas criadas</label>
        <select id="flow-assignee" value={draft.assignee_id} onChange={(e) => update({ assignee_id: e.target.value })}>
          <option value="">Sem responsável</option>{staff.filter((u) => u.active).map((u) => <option value={u.id} key={u.id}>{u.name}</option>)}
        </select></div>
    </>;
  } else if (step && stepPath && step.kind === 'branch') {
    const path = stepPath;
    panel = <>
      <p className="muted">Quando o fluxo chegar aqui, o contato é avaliado. Se atender às condições, segue pelo caminho <b>Sim</b>; senão, pelo <b>Não</b>.</p>
      <DelayField key={pathKey(path)} minutes={step.delay_minutes} onChange={(minutes) => updateStep(path, { delay_minutes: minutes })} />
      <ConditionsEditor label="Condições do caminho Sim" value={{ ...emptyConditions(), ...step.conditions }} onChange={(value) => updateStep(path, { conditions: value })} />
      <div className="flow-panel-tools">
        <span className="spacer" />
        <Button variant="ghost" onClick={() => (countSteps([step]) > 1 ? setRemovingBranch(path) : removeStep(path))}><Trash2 size={15} />Excluir ramificação</Button>
      </div>
    </>;
  } else if (step && stepPath) {
    const path = stepPath;
    const index = path[path.length - 1] as number;
    const siblings = listAt(draft.steps, path.slice(0, -1));
    panel = <>
      <div className="field"><label htmlFor="flow-action">Ação</label>
        <select id="flow-action" value={step.kind} onChange={(e) => updateStep(path, { kind: e.target.value })}>
          {Object.entries(ACTIONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></div>
      <DelayField key={pathKey(path)} minutes={step.delay_minutes} onChange={(minutes) => updateStep(path, { delay_minutes: minutes })} />
      {step.kind === 'send_message' && (
        <div className="field"><label>Modelo de mensagem</label>
          <select aria-label="Modelo de mensagem" value={step.template_id || ''} onChange={(e) => updateStep(path, { template_id: e.target.value })}>
            <option value="">Selecione um modelo</option>{templates.map((t) => <option key={t.id} value={t.id}>{t.name} · {t.channel}</option>)}
          </select></div>
      )}
      {(step.kind === 'reply_comment' || step.kind === 'private_reply') && (
        <div className="field"><label>{step.kind === 'reply_comment' ? 'Resposta pública ao comentário' : 'Mensagem privada (direct)'}</label>
          <textarea rows={4} maxLength={1000} aria-label="Texto da resposta" value={step.content || ''} onChange={(e) => updateStep(path, { content: e.target.value })} placeholder="Ex.: Oi, {{name}}! Obrigado pelo comentário." />
          <small>Use {'{{name}}'} para o nome e {'{{username}}'} para o @. Cada comentário recebe no máximo uma resposta de cada tipo, com limite de 60 por hora. A mensagem privada só pode ser enviada até 7 dias após o comentário.</small></div>
      )}
      {step.kind === 'add_tag' && (
        <div className="field"><label>Tag</label><input maxLength={80} aria-label="Tag" value={step.tag || ''} onChange={(e) => updateStep(path, { tag: e.target.value })} placeholder="Ex.: cliente" /></div>
      )}
      {step.kind === 'move_stage' && (
        <div className="field"><label>Etapa de destino</label>
          <select aria-label="Etapa de destino" value={step.stage_id || ''} onChange={(e) => updateStep(path, { stage_id: e.target.value })}>
            <option value="">Selecione…</option>{stages.map((s) => <option key={s.id} value={s.id}>{s.pipeline_name} · {s.name}</option>)}
          </select>
          <small>Só atua em negócios em aberto ligados ao evento.</small></div>
      )}
      {(step.kind === 'create_task' || step.kind === 'follow_up') && <>
        <div className="field"><label>Título</label><input maxLength={180} aria-label="Título" value={step.title || ''} onChange={(e) => updateStep(path, { title: e.target.value })} /></div>
        <div className="field"><label>{step.kind === 'follow_up' ? 'Retorno em (dias)' : 'Prazo da tarefa (dias)'}</label><input type="number" min={0} max={365} aria-label="Dias" value={step.due_days} onChange={(e) => updateStep(path, { due_days: Number(e.target.value) })} /></div>
      </>}
      <details className="auto-step-conditions" open={!!step.conditions?.items?.length}>
        <summary>Executar somente se…{step.conditions?.items?.length ? ` (${step.conditions.items.length})` : ''}</summary>
        <ConditionsEditor label="Condições deste passo" value={{ ...emptyConditions(), ...step.conditions }} onChange={(value) => updateStep(path, { conditions: value })} />
      </details>
      <div className="flow-panel-tools">
        <button type="button" className="icon-btn" aria-label="Mover para antes" data-tip="Mover para antes" data-tip-align="start" disabled={index === 0} onClick={() => moveStep(path, -1)}><ArrowLeft size={15} /></button>
        <button type="button" className="icon-btn" aria-label="Mover para depois" data-tip="Mover para depois" disabled={index === siblings.length - 1 || siblings[index + 1]?.kind === 'branch'} onClick={() => moveStep(path, 1)}><ArrowRight size={15} /></button>
        <button type="button" className="icon-btn" aria-label="Duplicar passo" data-tip="Duplicar" disabled={!canInsert(path.slice(0, -1))} onClick={() => duplicateStep(path)}><Copy size={15} /></button>
        <span className="spacer" />
        <Button variant="ghost" onClick={() => removeStep(path)}><Trash2 size={15} />Excluir passo</Button>
      </div>
    </>;
  }

  const isSelected = (path: StepPath) => Array.isArray(selected) && pathKey(selected) === pathKey(path);
  const select = (path: StepPath) => (e: { stopPropagation: () => void }) => { e.stopPropagation(); setSelected(path); };

  /** Draws one path of the flow; a branch at its end splits into a "Sim" row above a "Não" row. */
  function renderPath(list: Step[], listPath: StepPath): ReactNode {
    return list.map((s, index) => {
      const path = [...listPath, index];
      const problem = stepProblem(s);
      const last = index === list.length - 1;
      if (s.kind === 'branch') {
        return (
          <div className="flow-step-wrap" key={pathKey(path)}>
            <Connector delay={s.delay_minutes} disabled={!canInsert(listPath)} onInsert={() => insertStep(listPath, index)} />
            <article className={'flow-node flow-step flow-branch-node' + (isSelected(path) ? ' selected' : '') + (problem ? ' incomplete' : '')} onClick={select(path)}>
              <span className="flow-port in" />
              <header>
                <span className="flow-row-icon branch"><GitBranch size={15} /></span>
                <strong>Ramificação</strong>
              </header>
              <div className="flow-node-body">
                {problem ? <span className="flow-missing">{problem}</span> : <p>{describeStep(s, lookups)}</p>}
              </div>
              <span className="flow-port out" />
            </article>
            <div className="flow-branches">
              {(['yes', 'no'] as const).map((side) => {
                const sub = s[side] || [];
                const subPath = [...path, side];
                return (
                  <div className={'flow-branch-row ' + side} key={side}>
                    <div className="flow-branch-lead">
                      <span className="flow-line" />
                      <span className={'flow-branch-label ' + side}>{side === 'yes' ? <><Check size={11} />Sim</> : <><X size={11} />Não</>}</span>
                    </div>
                    {sub.length ? renderPath(sub, subPath) : (
                      <button type="button" className="flow-node flow-add flow-add-small" disabled={!canInsert(subPath)} onClick={(e) => { e.stopPropagation(); insertStep(subPath, 0); }}>
                        <Plus size={15} />{side === 'yes' ? 'Passo se atender' : 'Passo se não atender'}
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      }
      return (
        <div className="flow-step-wrap" key={pathKey(path)}>
          <Connector delay={s.delay_minutes} disabled={!canInsert(listPath)} onInsert={() => insertStep(listPath, index)} />
          <article className={'flow-node flow-step' + (isSelected(path) ? ' selected' : '') + (problem ? ' incomplete' : '')} onClick={select(path)}>
            <span className="flow-port in" />
            <header>
              <span className={'flow-row-icon' + (isInstagram(s.kind) ? ' ig' : '')}>{actionIcon(s.kind)}</span>
              <strong>{ACTIONS[s.kind] || s.kind}</strong>
              <small className="flow-index">{index + 1}</small>
            </header>
            <div className="flow-node-body">
              {problem ? <span className="flow-missing">{problem}</span> : <p>{describeStep(s, lookups)}</p>}
              {!!s.conditions?.items?.length && <span className="deal-chip"><Filter size={10} />Se {s.conditions.items.length} {s.conditions.items.length === 1 ? 'condição' : 'condições'}</span>}
            </div>
            <NodeFooter disabled={!canInsert(listPath)} branchDisabled={!canBranch(listPath)}
              onAdd={() => insertStep(listPath, index + 1)} onBranch={() => insertBranch(listPath, index + 1)} />
            {!last && <span className="flow-port out" />}
          </article>
        </div>
      );
    });
  }

  return (
    <div className="flow-editor">
      <header className="flow-topbar">
        <Link href="/automacoes" className="flow-back" aria-label="Voltar para automações" data-tip="Voltar" data-tip-align="start"><ChevronLeft size={18} /></Link>
        {editingName ? (
          <input className="flow-name-input" autoFocus aria-label="Nome da automação" maxLength={150} value={draft.name} placeholder="Nome da automação"
            onChange={(e) => update({ name: e.target.value })} onBlur={() => draft.name.trim() && setEditingName(false)}
            onKeyDown={(e) => { if (e.key === 'Enter' && draft.name.trim()) setEditingName(false); }} />
        ) : (
          <button type="button" className="flow-name" onClick={() => setEditingName(true)} aria-label="Renomear automação">
            <span>{draft.name}</span><Pencil size={15} />
          </button>
        )}
        <span className="flow-status muted">{busy ? 'Salvando…' : dirty ? 'Alterações não salvas' : 'Tudo salvo'}</span>
        <div className="flow-topbar-actions">
          <label className="flow-active">
            <button type="button" role="switch" aria-checked={draft.active} aria-label={draft.active ? 'Desativar automação' : 'Ativar automação'}
              className={'switch' + (draft.active ? ' on' : '')} onClick={() => update({ active: !draft.active })}><span /></button>
            {draft.active ? 'Ativa' : 'Inativa'}
          </label>
          <Button disabled={busy} onClick={save}>{busy ? 'Salvando…' : 'Salvar'}</Button>
        </div>
      </header>
      {failure && <p className="flow-error" role="alert">{failure}<button type="button" aria-label="Fechar aviso" onClick={() => setFailure('')}><X size={14} /></button></p>}

      <div className="flow-body">
        {panel && (
          <aside className="flow-panel" aria-label={selected === 'trigger' ? 'Gatilho' : step?.kind === 'branch' ? 'Ramificação' : 'Passo'}>
            <header>
              <h2>{selected === 'trigger' ? 'Gatilho' : step?.kind === 'branch' ? BRANCH_LABEL : 'Passo'}</h2>
              <button type="button" className="icon-btn" aria-label="Fechar painel" onClick={() => setSelected(null)}><X size={16} /></button>
            </header>
            <div className="flow-panel-body stack">{panel}</div>
          </aside>
        )}

        <div className="flow-canvas" onClick={() => setSelected(null)}>
          <div className="flow-stage" style={{ transform: `scale(${ZOOMS[zoom]})` }}>
            <div className="flow-trigger-wrap">
              <span className="flow-tag"><Zap size={11} />Gatilho</span>
              <article className={'flow-node flow-trigger' + (selected === 'trigger' ? ' selected' : '')} onClick={(e) => { e.stopPropagation(); setSelected('trigger'); }}>
                <small className="flow-kicker">{isInstagram(draft.event) ? 'Instagram' : 'Antares'}</small>
                <strong className="flow-title">O que inicia a automação</strong>
                <div className="flow-row">
                  <span className={'flow-row-icon' + (isInstagram(draft.event) ? ' ig' : '')}>{eventIcon(draft.event)}</span>
                  <span><b>Evento</b><small>{EVENTS[draft.event]?.label || draft.event}</small></span>
                  <ChevronRight size={14} />
                </div>
                <div className="flow-row">
                  <span className="flow-row-icon"><Filter size={14} /></span>
                  <span><b>Condições</b><small>{filters || 'Qualquer contato'}</small></span>
                  <ChevronRight size={14} />
                </div>
                <NodeFooter disabled={!canInsert([])} branchDisabled={!canBranch([])} onAdd={() => insertStep([], 0)} onBranch={() => insertBranch([], 0)} />
                <span className="flow-port out" />
              </article>
            </div>

            {renderPath(draft.steps, [])}

            {!draft.steps.length && (
              <div className="flow-step-wrap">
                <div className="flow-connector"><span className="flow-line dashed" /></div>
                <button type="button" className="flow-node flow-add" onClick={(e) => { e.stopPropagation(); insertStep([], 0); }}>
                  <Plus size={18} />Adicionar o primeiro passo
                </button>
              </div>
            )}
          </div>
        </div>

        <ConfirmDialog open={removingBranch !== null} onClose={() => setRemovingBranch(null)} title="Excluir ramificação?"
          description="Os passos dos caminhos Sim e Não também serão excluídos."
          onConfirm={async () => { if (removingBranch) removeStep(removingBranch); setRemovingBranch(null); }} />
        <div className="flow-tools" aria-label="Zoom">
          <button type="button" className="icon-btn" aria-label="Aproximar" data-tip="Aproximar" data-tip-align="end" disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom((z) => z + 1)}><ZoomIn size={17} /></button>
          <button type="button" className="icon-btn" aria-label="Afastar" data-tip="Afastar" data-tip-align="end" disabled={zoom === 0} onClick={() => setZoom((z) => z - 1)}><ZoomOut size={17} /></button>
          <button type="button" className="icon-btn" aria-label="Tamanho original" data-tip="Tamanho original" data-tip-align="end" onClick={() => setZoom(3)}><Maximize2 size={16} /></button>
          <span className="flow-zoom">{Math.round(ZOOMS[zoom] * 100)}%</span>
        </div>
      </div>
    </div>
  );
}
