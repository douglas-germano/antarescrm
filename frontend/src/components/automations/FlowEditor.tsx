import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Link } from '@tanstack/react-router';
import { useAppRouter } from '@/lib/navigation';
import { ArrowLeft, ArrowRight, Check, ChevronLeft, ChevronRight, Clock, Copy, Filter, GitBranch, LayoutGrid, Maximize2, Pencil, Plus, Trash2, X, Zap, ZoomIn, ZoomOut } from 'lucide-react';
import { post, patch, put, refreshAll, remove, useList } from '@/lib/api';
import { useNotify } from '@/components/providers';
import { Button, ConfirmDialog } from '@/components/ui';
import { ConditionsEditor, emptyConditions, type Conditions } from '@/components/automations/conditions-editor';
import {
  ACTIONS, ATLAS_EVENTS, BRANCH_LABEL, DELAY_UNITS, EVENTS, INSTAGRAM_DMS, MAX_DEPTH, MAX_PATH_STEPS, MAX_STEPS, countSteps, describeStep, editList, firstProblem,
  formatDelay, listAt, newBranch, newStep, pathKey, splitDelay, stepAt, stepPayload, stepProblem, type Step, type StepPath,
} from '@/components/automations/model';
import { actionIcon, eventIcon, isInstagram } from '@/components/automations/icons';
import { InstagramButtons } from '@/components/automations/instagram-buttons';
import { NODE_W, edgeCurve, layoutFlow, type FlowEdge, type FlowNode } from '@/components/automations/layout';
import { PreviewReport, VersionHistory, type PreviewResult } from '@/components/automations/flow-test';
import type { Row } from '@/lib/types';

/** Everything the editor changes; `id` is present when the rule already exists. */
export type FlowDraft = {
  id?: string; name: string; event: string; source: string; required_tag: string; assignee_id: string;
  active: boolean; stop_on_reply: boolean; conditions: Conditions; steps: Step[];
  stageDays?: number; bookingBefore?: number;
  /** Published state of an existing rule: active rules are edited as a draft until published. */
  live?: boolean; hasDraft?: boolean; draftSavedAt?: string;
};
type Selection = 'trigger' | StepPath | null;
type View = { x: number; y: number; z: number };
const MIN_ZOOM = 0.3;
const MAX_ZOOM = 2;
const START_VIEW: View = { x: 120, y: 120, z: 1 };
const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
/** A drag shorter than this is a click: it selects the card instead of moving it. */
const DRAG_THRESHOLD = 4;

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

/** Wait time and "+" sitting halfway along a connector; the line itself is drawn in the SVG layer. */
function EdgeControls({ edge, onInsert, disabled }: { edge: FlowEdge; onInsert?: () => void; disabled: boolean }) {
  const { mid } = edgeCurve(edge.from, edge.to);
  return <>
    {edge.side && (
      <span className={'flow-branch-label ' + edge.side} style={{ left: edge.from.x + 18, top: edge.from.y + (edge.side === 'yes' ? -26 : 6) }}>
        {edge.side === 'yes' ? <><Check size={11} />{edge.waitReply ? 'Respondeu' : 'Sim'}</> : <><X size={11} />{edge.waitReply ? 'Prazo venceu' : 'Não'}</>}
      </span>
    )}
    {!!edge.delay && <span className="flow-delay" style={{ left: mid.x, top: mid.y - 32 }}><Clock size={12} />Esperar {formatDelay(edge.delay)}</span>}
    {onInsert && (
      <button type="button" className="flow-insert" style={{ left: mid.x, top: mid.y }} aria-label="Inserir passo aqui" data-tip="Inserir passo" disabled={disabled} onClick={onInsert}><Plus size={13} /></button>
    )}
  </>;
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

export function FlowEditor({ initial, staff, templates, stages, onRestored }: { initial: FlowDraft; staff: Row[]; templates: Row[]; stages: Row[]; onRestored?: () => void }) {
  const router = useAppRouter();
  const { notify } = useNotify();
  const [draft, setDraft] = useState<FlowDraft>(initial);
  const [selected, setSelected] = useState<Selection>(initial.id ? null : 'trigger');
  const [view, setView] = useState<View>(START_VIEW);
  const [dragging, setDragging] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  // Set while a press turns into a drag, so the click that follows it does not select or deselect.
  const dragged = useRef(false);
  const [dirty, setDirty] = useState(!initial.id);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewDeal, setPreviewDeal] = useState('');
  const [previewSearch, setPreviewSearch] = useState('');
  const [previewReply, setPreviewReply] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  // Edits of an active rule wait in a draft, so the running flow only changes when someone publishes.
  const [live, setLive] = useState(Boolean(initial.live));
  const [pending, setPending] = useState(Boolean(initial.hasDraft));
  const [draftSavedAt, setDraftSavedAt] = useState(initial.draftSavedAt);
  const [discarding, setDiscarding] = useState(false);
  const deals = useList(previewOpen ? '/opportunities?search=' + encodeURIComponent(previewSearch) : null);
  const bookingTrigger = ['booking.created', 'booking.rescheduled'].includes(draft.event);
  const [editingName, setEditingName] = useState(!initial.id && !initial.name);
  const [removingBranch, setRemovingBranch] = useState<StepPath | null>(null);
  const lookups = {
    template: (id?: string) => templates.find((t) => t.id === id)?.name,
    stage: (id?: string) => stages.find((s) => s.id === id)?.name,
  };
  const update = (patchDraft: Partial<FlowDraft>) => { setDraft((d) => ({ ...d, ...patchDraft })); setDirty(true); setFailure(''); setPreview(null); };
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

  async function save(simulate = false, publishing = false): Promise<boolean | 'unchanged'> {
    if (busy) return false;
    if (!simulate && !draft.name.trim()) { setEditingName(true); setFailure('Dê um nome à automação.'); return false; }
    if (!draft.steps.length) { setFailure('Adicione ao menos um passo depois do gatilho.'); return false; }
    if (draft.event === 'opportunity.stage_idle' && !draft.stageDays) { setSelected('trigger'); setFailure('Informe o prazo de permanência na etapa.'); return false; }
    const broken = firstProblem(draft.steps, draft.event);
    if (broken) { setSelected(broken.path); setFailure(broken.problem); return false; }
    setBusy(true);
    setFailure('');
    const body = {
      conditions: draft.conditions,
      name: draft.name.trim() || 'Simulação',
      event: draft.event,
      source: draft.source.trim() || null,
      required_tag: draft.required_tag.trim() || null,
      assignee_id: draft.assignee_id || null,
      active: draft.active,
      stop_on_reply: draft.stop_on_reply,
      task_title: draft.steps.find((step) => step.title)?.title || draft.name.trim() || 'Simulação',
      due_days: 0,
      actions: draft.steps.map((step, index) => ({
        ...stepPayload(step),
        ...(index === 0 && draft.event === 'opportunity.stage_idle' ? { stage_days: draft.stageDays } : {}),
        ...(index === 0 && bookingTrigger && draft.bookingBefore !== undefined ? { booking_before_minutes: draft.bookingBefore } : {}),
      })),
    };
    try {
      if (simulate) {
        setPreview(await post<NonNullable<typeof preview>>('/automations/preview', {
          rule: body, opportunity_id: previewDeal, reply_received: previewReply,
        }));
        return true;
      }
      if (draft.id && live) {
        const { active, ...config } = body;
        const saved = await put<Row>('/automations/' + draft.id + '/draft', config);
        if (!active) { await patch('/automations/' + draft.id, { active: false }); setLive(false); }
        await refreshAll();
        setPending(Boolean(saved.draft));
        setDraftSavedAt(saved.draft_saved_at || undefined);
        setDirty(false);
        if (!publishing) notify(saved.draft ? 'Rascunho salvo. A automação continua rodando com a versão publicada.' : 'Igual à versão publicada: não há nada para publicar.');
        return saved.draft ? true : 'unchanged';
      }
      if (draft.id) await patch('/automations/' + draft.id, body);
      const created = draft.id ? null : await post<{ id: string }>('/automations', body);
      await refreshAll();
      setDirty(false);
      setPending(false);
      setLive(draft.active);
      notify('Automação salva.');
      // A new rule continues in its own address, so reloading or sharing the page keeps it.
      if (created) router.replace('/automacoes/' + created.id);
      return true;
    } catch (error) {
      setFailure((error as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  /** Saves what is on screen as the draft (if changed) and makes it the running version. */
  async function publish() {
    if (!draft.id || busy) return;
    if (dirty) {
      const saved = await save(false, true);
      if (!saved) return;
      if (saved === 'unchanged') { notify('Igual à versão publicada: não há nada para publicar.'); return; }
    }
    setBusy(true);
    try {
      await post('/automations/' + draft.id + '/draft/publish', {});
      await refreshAll();
      setPending(false);
      notify('Rascunho publicado. As próximas execuções já usam esta versão.');
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
      {draft.event === 'opportunity.stage_idle' && <label className="field">Dias na mesma etapa
        <input type="number" min={1} max={365} value={draft.stageDays || ''} onChange={(e) => update({ stageDays: Number(e.target.value) })} />
      </label>}
      {bookingTrigger && <label className="field">Minutos antes da reunião
        <input type="number" min={0} max={43200} value={draft.bookingBefore ?? ''} placeholder="Opcional" onChange={(e) => update({ bookingBefore: e.target.value === '' ? undefined : Number(e.target.value) })} />
        <small>Se preencher, o fluxo começa em relação ao horário da reunião. Em branco, começa no evento.</small>
      </label>}
      <div className="field"><label htmlFor="flow-source">Somente desta origem</label><input id="flow-source" maxLength={100} value={draft.source} placeholder="Opcional" onChange={(e) => update({ source: e.target.value })} /></div>
      <div className="field"><label htmlFor="flow-tag">Somente contatos com a tag</label><input id="flow-tag" maxLength={80} value={draft.required_tag} placeholder="Opcional" onChange={(e) => update({ required_tag: e.target.value })} /></div>
      <ConditionsEditor value={draft.conditions} onChange={(conditions) => update({ conditions })} />
      <label className="checkbox-label"><input type="checkbox" checked={draft.stop_on_reply} onChange={(e) => update({ stop_on_reply: e.target.checked })} />Interromper os próximos passos quando o contato responder</label>
      {draft.stop_on_reply && <small className="muted">Deixe desmarcado se o fluxo espera uma resposta rápida para decidir o caminho: a resposta interromperia o fluxo.</small>}
      <div className="field"><label htmlFor="flow-assignee">Responsável pelas tarefas criadas</label>
        <select id="flow-assignee" value={draft.assignee_id} onChange={(e) => update({ assignee_id: e.target.value })}>
          <option value="">Sem responsável</option>{staff.filter((u) => u.active).map((u) => <option value={u.id} key={u.id}>{u.name}</option>)}
        </select></div>
    </>;
  } else if (step && stepPath && step.kind === 'branch') {
    const path = stepPath;
    panel = <>
      <label className="field">Como decidir o caminho
        <select value={step.wait_reply_minutes ? 'reply' : 'condition'} onChange={(e) => updateStep(path, {
          wait_reply_minutes: e.target.value === 'reply' ? 2880 : undefined,
          reply_channel: e.target.value === 'reply' ? 'whatsapp' : undefined,
        })}>
          <option value="condition">Avaliar condição</option><option value="reply">Aguardar resposta com prazo</option>
        </select>
      </label>
      {!!step.wait_reply_minutes && <>
        <label className="field">Canal da resposta
          <select value={step.reply_channel || ''} onChange={(e) => updateStep(path, { reply_channel: e.target.value })}>
            <option value="whatsapp">WhatsApp</option><option value="instagram">Instagram</option><option value="email">E-mail</option>
          </select>
        </label>
        <label className="field">Prazo máximo em minutos
          <input type="number" min={1} max={10080} value={step.wait_reply_minutes} onChange={(e) => updateStep(path, { wait_reply_minutes: Math.max(1, Number(e.target.value)) })} />
          <small>O fluxo procura uma conversa única no canal escolhido. Desative a opção de interromper ao responder.</small>
        </label>
      </>}
      <DelayField key={pathKey(path)} minutes={step.delay_minutes} onChange={(minutes) => updateStep(path, { delay_minutes: minutes })} />
      {!step.wait_reply_minutes && <ConditionsEditor label="Condições do caminho Sim" value={{ ...emptyConditions(), ...step.conditions }} onChange={(value) => updateStep(path, { conditions: value })} />}
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
          {Object.entries(ACTIONS).map(([value, label]) => <option key={value} value={value} disabled={value === 'atlas_assign' && !ATLAS_EVENTS.includes(draft.event)}>{label}</option>)}
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
      {step.kind === 'instagram_message' && (
        <div className="field"><label>Mensagem no direct</label>
          <textarea rows={4} maxLength={1000} aria-label="Texto da mensagem" value={step.content || ''} onChange={(e) => updateStep(path, { content: e.target.value })} placeholder="Ex.: Oi, {{name}}! Quer receber os detalhes?" />
          <small>Vai para a conversa do contato no Instagram. Pelas regras do Instagram, só é enviada se o contato escreveu nas últimas 24 horas; fora disso, o passo é dispensado.</small></div>
      )}
      {step.kind === 'atlas_assign' && <>
        {draft.event !== 'message.received' && <div className="field">
          <label htmlFor="flow-atlas-channel">Canal</label>
          <select id="flow-atlas-channel" value={step.atlas_channel || ''} onChange={(e) => updateStep(path, { atlas_channel: e.target.value })}>
            <option value="">Selecione…</option><option value="whatsapp">WhatsApp</option><option value="instagram">Instagram</option>
          </select>
        </div>}
        <div className="field">
          <label htmlFor="flow-atlas-goal">Objetivo do Atlas{draft.event === 'message.received' ? ' (opcional)' : ''}</label>
          <textarea id="flow-atlas-goal" rows={4} maxLength={1000} value={step.content || ''} onChange={(e) => updateStep(path, { content: e.target.value })} placeholder="Ex.: pergunte se o contato tem alguma dúvida sobre a proposta." />
          <small>{draft.event === 'message.received'
            ? 'O Atlas assume a conversa do WhatsApp ou Instagram que recebeu a mensagem.'
            : 'O Atlas usa os dados do formulário ou da etapa para escrever. O envio exige uma conversa vinculada com mensagem recebida nas últimas 24 horas.'}</small>
        </div>
      </>}
      {INSTAGRAM_DMS.includes(step.kind) && (
        <InstagramButtons buttons={step.buttons || []} quickReplies={step.quick_replies || []} onChange={(patchStep) => updateStep(path, patchStep)} />
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
        <label className="checkbox-label"><input type="checkbox" checked={!!step.assign_deal_owner} onChange={(e) => updateStep(path, { assign_deal_owner: e.target.checked })} />Atribuir ao dono do negócio</label>
        {step.assign_deal_owner && <small>Se o negócio estiver sem dono ativo, usa o responsável configurado no gatilho.</small>}
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
  const { nodes, edges } = layoutFlow(draft.steps);

  /** Zoom keeping the canvas point under (px, py) still, like map apps and Figma. */
  const zoomAt = (px: number, py: number, factor: number) => setView((v) => {
    const z = clampZoom(v.z * factor);
    return { z, x: px - ((px - v.x) * z) / v.z, y: py - ((py - v.y) * z) / v.z };
  });
  const zoomCenter = (factor: number) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) zoomAt(rect.width / 2, rect.height / 2, factor);
  };
  /** Frames every card in the visible area, never enlarging past 100%. */
  const fitView = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const minX = Math.min(...xs), minY = Math.min(...ys);
    const width = Math.max(...xs) + NODE_W - minX, height = Math.max(...ys) + 260 - minY;
    const z = clampZoom(Math.min(1, (rect.width - 160) / width, (rect.height - 160) / height));
    setView({ z, x: (rect.width - width * z) / 2 - minX * z, y: (rect.height - height * z) / 2 - minY * z });
  };
  const resetLayout = () => {
    const clear = (list: Step[]): Step[] => list.map(({ offset: _offset, ...s }) => ({ ...s, ...(s.yes ? { yes: clear(s.yes) } : {}), ...(s.no ? { no: clear(s.no) } : {}) }));
    update({ steps: clear(draft.steps) });
  };

  // Wheel and trackpad: pinch (ctrl + wheel) or a mouse wheel zooms at the cursor; two-finger scroll pans.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseWheel = e.deltaMode === 1 || (e.deltaX === 0 && Number.isInteger(e.deltaY) && Math.abs(e.deltaY) >= 50);
      if (e.ctrlKey || e.metaKey) zoomAt(e.clientX - rect.left, e.clientY - rect.top, Math.exp(-e.deltaY * 0.01));
      else if (mouseWheel) zoomAt(e.clientX - rect.left, e.clientY - rect.top, Math.exp(-(e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY) * 0.002));
      else setView((v) => ({ ...v, x: v.x - e.deltaX, y: v.y - e.deltaY }));
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, []);

  /** Pressing a step card drags that card; pressing the background or the trigger pans the whole canvas. */
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest('button, input, select, textarea, a')) return;
    const card = (e.target as HTMLElement).closest<HTMLElement>('[data-path]');
    const path = card ? (JSON.parse(card.dataset.path!) as StepPath) : null;
    const origin = path ? { ...(stepAt(draft.steps, path)?.offset || { x: 0, y: 0 }) } : { x: viewRef.current.x, y: viewRef.current.y };
    const start = { x: e.clientX, y: e.clientY };
    const target = e.currentTarget;
    const pointerId = e.pointerId;
    dragged.current = false;
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - start.x, dy = ev.clientY - start.y;
      if (!dragged.current && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
      // Capture only once it is a drag: capturing on press would send a plain click to the canvas, not the card.
      if (!dragged.current) { dragged.current = true; setDragging(true); target.setPointerCapture(pointerId); }
      if (path) {
        const z = viewRef.current.z;
        updateStep(path, { offset: { x: Math.round(origin.x + dx / z), y: Math.round(origin.y + dy / z) } });
      } else {
        setView((v) => ({ ...v, x: origin.x + dx, y: origin.y + dy }));
      }
    };
    const up = () => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
      target.removeEventListener('pointercancel', up);
      setDragging(false);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
    target.addEventListener('pointercancel', up);
  };

  function renderNode(node: FlowNode): ReactNode {
    const style = { left: node.x, top: node.y };
    if (node.kind === 'trigger') {
      return (
        <div className="flow-place flow-trigger-wrap" style={style} key={node.key}>
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
      );
    }
    if (node.kind === 'add') {
      const label = node.side === 'yes' ? 'Passo se atender' : node.side === 'no' ? 'Passo se não atender' : 'Adicionar o primeiro passo';
      return (
        <div className="flow-place" style={style} key={node.key}>
          <button type="button" className={'flow-node flow-add' + (node.side ? ' flow-add-small' : '')} disabled={!canInsert(node.listPath)}
            onClick={(e) => { e.stopPropagation(); insertStep(node.listPath, 0); }}>
            <Plus size={node.side ? 15 : 18} />{label}
          </button>
        </div>
      );
    }
    const { step: s, path, listPath, index } = node;
    const problem = stepProblem(s);
    const branch = s.kind === 'branch';
    return (
      <div className="flow-place" style={style} key={node.key} data-path={JSON.stringify(path)}>
        <article className={'flow-node flow-step' + (branch ? ' flow-branch-node' : '') + (isSelected(path) ? ' selected' : '') + (problem ? ' incomplete' : '')} onClick={select(path)}>
          <span className="flow-port in" />
          <header>
            {branch ? <span className="flow-row-icon branch"><GitBranch size={15} /></span>
              : <span className={'flow-row-icon' + (isInstagram(s.kind) ? ' ig' : '')}>{actionIcon(s.kind)}</span>}
            <strong>{branch ? (s.wait_reply_minutes ? 'Aguardar resposta' : 'Ramificação') : ACTIONS[s.kind] || s.kind}</strong>
            {!branch && <small className="flow-index">{index + 1}</small>}
          </header>
          <div className="flow-node-body">
            {problem ? <span className="flow-missing">{problem}</span> : <p>{describeStep(s, lookups)}</p>}
            {!branch && !!s.conditions?.items?.length && <span className="deal-chip"><Filter size={10} />Se {s.conditions.items.length} {s.conditions.items.length === 1 ? 'condição' : 'condições'}</span>}
            {!branch && (!!s.buttons?.length || !!s.quick_replies?.length) && (
              <span className="flow-dm-options">
                {s.buttons?.map((b, i) => <span key={'b' + i} className="flow-dm-button">{b.title || 'Botão'}</span>)}
                {s.quick_replies?.map((q, i) => <span key={'q' + i} className="flow-dm-reply">{q || '…'}</span>)}
              </span>
            )}
          </div>
          {!branch && <NodeFooter disabled={!canInsert(listPath)} branchDisabled={!canBranch(listPath)}
            onAdd={() => insertStep(listPath, index + 1)} onBranch={() => insertBranch(listPath, index + 1)} />}
          {(branch || !node.last) && <span className="flow-port out" />}
        </article>
      </div>
    );
  }

  return (
    <div className="flow-editor">
      <header className="flow-topbar">
        <Link to="/automacoes" className="flow-back" aria-label="Voltar para automações" data-tip="Voltar" data-tip-align="start"><ChevronLeft size={18} /></Link>
        {editingName ? (
          <input className="flow-name-input" autoFocus aria-label="Nome da automação" maxLength={150} value={draft.name} placeholder="Nome da automação"
            onChange={(e) => update({ name: e.target.value })} onBlur={() => draft.name.trim() && setEditingName(false)}
            onKeyDown={(e) => { if (e.key === 'Enter' && draft.name.trim()) setEditingName(false); }} />
        ) : (
          <button type="button" className="flow-name" onClick={() => setEditingName(true)} aria-label="Renomear automação">
            <span>{draft.name}</span><Pencil size={15} />
          </button>
        )}
        <span className="flow-status muted">{busy ? 'Salvando…' : dirty ? 'Alterações não salvas' : pending ? 'Rascunho não publicado' : 'Tudo salvo'}</span>
        <div className="flow-topbar-actions">
          <label className="flow-active">
            <button type="button" role="switch" aria-checked={draft.active} aria-label={draft.active ? 'Desativar automação' : 'Ativar automação'}
              className={'switch' + (draft.active ? ' on' : '')} onClick={() => update({ active: !draft.active })}><span /></button>
            {draft.active ? 'Ativa' : 'Inativa'}
          </label>
          {draft.id && <Button variant="secondary" onClick={() => { setVersionsOpen(!versionsOpen); setPreviewOpen(false); }}>Versões</Button>}
          <Button variant="secondary" onClick={() => { setPreviewOpen(!previewOpen); setVersionsOpen(false); }}>Testar fluxo</Button>
          {live && pending && !dirty && <Button variant="ghost" disabled={busy} onClick={() => setDiscarding(true)}>Descartar rascunho</Button>}
          <Button variant={live ? 'secondary' : undefined} disabled={busy} onClick={() => save()}>{busy ? 'Salvando…' : live ? 'Salvar rascunho' : 'Salvar'}</Button>
          {live && <Button disabled={busy || (!pending && !dirty)} onClick={publish}>Publicar</Button>}
        </div>
      </header>
      {live && (pending || dirty) && <p className="flow-draft-note" role="status">
        {pending && !dirty ? 'Rascunho salvo' + (draftSavedAt ? ' em ' + new Date(draftSavedAt).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '') + '. ' : 'Você está editando uma automação ativa. '}
        Ela continua rodando com a versão publicada até você clicar em Publicar. Use “Testar fluxo” para conferir antes.
      </p>}
      <ConfirmDialog open={discarding} onClose={() => setDiscarding(false)} title="Descartar o rascunho?"
        description="As alterações não publicadas serão apagadas e o editor volta para a versão em uso."
        onConfirm={async () => {
          if (!draft.id) return;
          await remove('/automations/' + draft.id + '/draft');
          await refreshAll();
          notify('Rascunho descartado.');
          onRestored?.();
        }} />
      {failure && <p className="flow-error" role="alert">{failure}<button type="button" aria-label="Fechar aviso" onClick={() => setFailure('')}><X size={14} /></button></p>}

      {previewOpen && <section className="flow-preview" aria-label="Testar fluxo">
        <label className="field">Buscar negócio
          <input value={previewSearch} onChange={(e) => { setPreviewSearch(e.target.value); setPreviewDeal(''); setPreview(null); }} />
        </label>
        <label className="field">Negócio para simulação
          <select value={previewDeal} onChange={(e) => { setPreviewDeal(e.target.value); setPreview(null); }}>
            <option value="">{deals.isLoading ? 'Carregando…' : 'Selecione um negócio'}</option>
            {(deals.data || []).filter((deal) => deal.contact_id).map((deal) => <option key={deal.id} value={deal.id}>{deal.title}</option>)}
          </select>
        </label>
        <label className="checkbox-label"><input type="checkbox" checked={previewReply} onChange={(e) => { setPreviewReply(e.target.checked); setPreview(null); }} />Simular resposta dentro do prazo</label>
        <Button variant="secondary" disabled={!previewDeal || busy} onClick={() => save(true)}>Simular</Button>
        <small>Usa os dados atuais do negócio e do contato. Nenhuma ação é executada e nenhuma mensagem é enviada.</small>
        {preview && <PreviewReport preview={preview} />}
      </section>}
      {versionsOpen && draft.id && <VersionHistory ruleId={draft.id} dirty={dirty} hasDraft={pending} onRestored={async () => {
        await refreshAll();
        notify('Versão restaurada.');
        onRestored?.();
      }} />}

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

        <div ref={canvasRef} className={'flow-canvas' + (dragging ? ' dragging' : '')} onPointerDown={onPointerDown}
          onClickCapture={(e) => { if (dragged.current) { e.stopPropagation(); dragged.current = false; } }}
          onClick={() => setSelected(null)}
          style={{ backgroundPosition: `${view.x}px ${view.y}px`, backgroundSize: `${18 * view.z}px ${18 * view.z}px` }}>
          <div className="flow-stage" style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})` }}>
            <svg className="flow-edges" aria-hidden="true">
              {edges.map((edge) => <path key={edge.key} d={edgeCurve(edge.from, edge.to).d} className={edge.dashed ? 'dashed' : undefined} />)}
            </svg>
            {edges.map((edge) => (
              <EdgeControls key={edge.key} edge={edge} disabled={!edge.insert || !canInsert(edge.insert.listPath)}
                onInsert={edge.insert ? () => insertStep(edge.insert!.listPath, edge.insert!.index) : undefined} />
            ))}
            {nodes.map(renderNode)}
          </div>
        </div>

        <ConfirmDialog open={removingBranch !== null} onClose={() => setRemovingBranch(null)} title="Excluir ramificação?"
          description="Os passos dos caminhos Sim e Não também serão excluídos."
          onConfirm={async () => { if (removingBranch) removeStep(removingBranch); setRemovingBranch(null); }} />
        <div className="flow-tools" aria-label="Zoom">
          <button type="button" className="icon-btn" aria-label="Aproximar" data-tip="Aproximar" data-tip-align="end" disabled={view.z >= MAX_ZOOM} onClick={() => zoomCenter(1.2)}><ZoomIn size={17} /></button>
          <button type="button" className="icon-btn" aria-label="Afastar" data-tip="Afastar" data-tip-align="end" disabled={view.z <= MIN_ZOOM} onClick={() => zoomCenter(1 / 1.2)}><ZoomOut size={17} /></button>
          <button type="button" className="icon-btn" aria-label="Ajustar à tela" data-tip="Ajustar à tela" data-tip-align="end" onClick={fitView}><Maximize2 size={16} /></button>
          <button type="button" className="icon-btn" aria-label="Organizar cards" data-tip="Organizar cards" data-tip-align="end" onClick={resetLayout}><LayoutGrid size={16} /></button>
          <button type="button" className="flow-zoom" aria-label="Voltar para 100%" data-tip="Voltar para 100%" data-tip-align="end" onClick={() => setView(START_VIEW)}>{Math.round(view.z * 100)}%</button>
        </div>
      </div>
    </div>
  );
}
