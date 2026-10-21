'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowDown, ArrowLeft, ArrowUp, Copy, ExternalLink, Monitor, Plus, Smartphone, Trash2 } from 'lucide-react';
import { Badge, Button, ConfirmDialog } from '@/components/ui';
import { Tabs } from '@/components/blocks';
import { useNotify } from '@/components/providers';
import { patch, post, refreshAll, remove, useData, useList } from '@/lib/api';
import { usePublicOrigin } from '@/lib/public-origin';
import { Section, SelectInput, TextAreaInput, TextInput } from '@/components/builder/controls';
import { toPublicForm } from '@/components/forms/types';
import type { Row } from '@/lib/types';
import { BlockInspector } from './block-inspector';
import { PageRenderer } from './page-renderer';
import { FunnelSettings } from './funnel-settings';
import { FunnelStatsTab } from './funnel-stats';
import { BLOCK_DEFS, KIND_LABELS, blockLabel, newId, type Block, type BlockStyle, type Funnel, type Step, type StepKind, type StepSettings } from './types';

type Tab = 'editor' | 'stats' | 'settings';
const snapshot = (s: Step) => JSON.stringify({ name: s.name, slug: s.slug, kind: s.kind, blocks: s.blocks, settings: s.settings });
const metaSnapshot = (f: Funnel) => JSON.stringify({ name: f.name, description: f.description, theme: f.theme });

export function FunnelEditor({ funnel: initial }: { funnel: Funnel }) {
  const { notify } = useNotify();
  const forms = useList('/forms');
  const stages = useData<{ items: Row[] }>('/pipeline/stages');
  const [funnel, setFunnel] = useState<Funnel>(initial);
  const [steps, setSteps] = useState<Step[]>(initial.steps || []);
  const [saved, setSaved] = useState<Record<string, string>>(() => Object.fromEntries((initial.steps || []).map((s) => [s.id, snapshot(s)])));
  const [savedMeta, setSavedMeta] = useState(() => metaSnapshot(initial));
  const [stepId, setStepId] = useState(initial.steps?.[0]?.id || '');
  const [blockId, setBlockId] = useState('');
  const [tab, setTab] = useState<Tab>('editor');
  const [mobile, setMobile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState<Step | null>(null);

  const step = steps.find((s) => s.id === stepId) || steps[0];
  const block = step?.blocks.find((b) => b.id === blockId);
  const dirtySteps = steps.filter((s) => saved[s.id] !== snapshot(s));
  const dirty = dirtySteps.length > 0 || metaSnapshot(funnel) !== savedMeta;
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const formMap = useMemo(() => Object.fromEntries((forms.data || []).map((f) => [f.id, toPublicForm(f)])), [forms.data]);
  const editStep = (id: string, fn: (s: Step) => Step) => setSteps((all) => all.map((s) => (s.id === id ? fn(s) : s)));
  const editBlocks = (fn: (blocks: Block[]) => Block[]) => step && editStep(step.id, (s) => ({ ...s, blocks: fn(s.blocks) }));
  const editBlock = (id: string, fn: (b: Block) => Block) => editBlocks((bs) => bs.map((b) => (b.id === id ? fn(b) : b)));

  function addBlock(type: Block['type']) {
    const def = BLOCK_DEFS.find((d) => d.type === type)!;
    const created: Block = { id: newId(), type, ...def.make() };
    editBlocks((bs) => {
      const at = bs.findIndex((b) => b.id === blockId);
      return at < 0 ? [...bs, created] : [...bs.slice(0, at + 1), created, ...bs.slice(at + 1)];
    });
    setBlockId(created.id);
  }
  const moveBlock = (id: string, delta: number) => editBlocks((bs) => {
    const from = bs.findIndex((b) => b.id === id), to = from + delta;
    if (from < 0 || to < 0 || to >= bs.length) return bs;
    const next = [...bs]; [next[from], next[to]] = [next[to], next[from]]; return next;
  });
  const duplicateBlock = (b: Block) => {
    const copy = { ...b, id: newId(), props: structuredClone(b.props), style: { ...b.style } };
    editBlocks((bs) => { const at = bs.findIndex((x) => x.id === b.id); return [...bs.slice(0, at + 1), copy, ...bs.slice(at + 1)]; });
    setBlockId(copy.id);
  };
  const deleteBlock = (id: string) => { editBlocks((bs) => bs.filter((b) => b.id !== id)); setBlockId(''); };

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function persist() {
    const updated: Record<string, Step> = {};
    for (const s of dirtySteps) {
      updated[s.id] = await patch<Step>(`/funnels/${funnel.id}/steps/${s.id}`, { name: s.name, slug: s.slug.replace(/^-+|-+$/g, '') || undefined, kind: s.kind, blocks: s.blocks, settings: s.settings });
    }
    if (metaSnapshot(funnel) !== savedMeta) {
      const { name, description, theme } = funnel;
      const result = await patch<Funnel>('/funnels/' + funnel.id, { name, description, theme });
      setFunnel((f) => ({ ...f, theme: result.theme }));
      setSavedMeta(metaSnapshot({ ...funnel, theme: result.theme }));
    }
    const merged = steps.map((s) => (updated[s.id] ? { ...s, slug: updated[s.id].slug } : s));
    setSteps(merged);
    setSaved(Object.fromEntries(merged.map((s) => [s.id, snapshot(s)])));
  }
  const save = () => run(async () => { await persist(); await refreshAll(); notify('Funil salvo.'); });
  const setStatus = (status: 'draft' | 'published') => run(async () => {
    await persist();
    const result = await patch<Funnel>('/funnels/' + funnel.id, { status });
    setFunnel((f) => ({ ...f, status: result.status }));
    await refreshAll();
    notify(status === 'published' ? 'Funil publicado.' : 'Funil despublicado.');
  });
  const addStep = () => run(async () => {
    const created = await post<Step>(`/funnels/${funnel.id}/steps`, { name: 'Nova página', kind: 'custom' });
    setSteps((all) => [...all, created]); setSaved((s) => ({ ...s, [created.id]: snapshot(created) })); setStepId(created.id); setBlockId('');
  });
  const moveStep = (id: string, delta: number) => run(async () => {
    const from = steps.findIndex((s) => s.id === id), to = from + delta;
    if (to < 0 || to >= steps.length) return;
    const next = [...steps]; [next[from], next[to]] = [next[to], next[from]];
    await post(`/funnels/${funnel.id}/steps/reorder`, { order: next.map((s) => s.id) });
    setSteps(next.map((s, i) => ({ ...s, position: i })));
  });
  const deleteStep = async (target: Step) => {
    await remove(`/funnels/${funnel.id}/steps/${target.id}`);
    const rest = steps.filter((s) => s.id !== target.id);
    setSteps(rest); setStepId(rest[0]?.id || ''); setBlockId(''); notify('Página excluída.');
  };
  const newForm = () => run(async () => {
    const stage = stages.data?.items[0];
    if (!stage) throw new Error('Crie uma etapa no funil de vendas antes de criar um formulário.');
    const created = await post<Row>('/forms', { name: `${funnel.name} — formulário ${(forms.data?.length || 0) + 1}`, headline: 'Fale com a gente', stage_id: stage.id, source: 'Funil: ' + funnel.name, description: '' });
    await refreshAll();
    if (block) editBlock(block.id, (b) => ({ ...b, props: { ...b.props, form_id: created.id } }));
    notify('Formulário criado e vinculado ao bloco.');
  });

  const origin = usePublicOrigin();
  const publicLink = `${origin}/p/${funnel.id}/${step?.slug || ''}`;
  const published = funnel.status === 'published';
  const stepSettings = (patchValues: Partial<StepSettings>) => step && editStep(step.id, (s) => ({ ...s, settings: { ...s.settings, ...patchValues } }));
  const hasForm = steps.some((s) => s.blocks.some((b) => b.type === 'form' && b.props.form_id));

  return <div className="page">
    <div className="bld-toolbar">
      <Link className="btn btn-ghost" href="/funis"><ArrowLeft size={16} /> Funis</Link>
      <input className="fe-title" aria-label="Nome do funil" value={funnel.name} maxLength={150} onChange={(e) => setFunnel((f) => ({ ...f, name: e.target.value }))} />
      <Badge value={published ? 'completed' : 'cancelled'} label={published ? 'Publicado' : 'Rascunho'} />
      <span className="spacer" />
      <span className="bld-status" data-dirty={dirty} role="status">{dirty ? 'Alterações não salvas' : 'Tudo salvo'}</span>
      {published && step && <>
        <Button variant="ghost" aria-label="Copiar link da página" onClick={async () => { try { await navigator.clipboard.writeText(publicLink); notify('Link copiado.'); } catch { notify('Não foi possível copiar.', 'error'); } }}><Copy size={16} /></Button>
        <a className="btn btn-secondary" href={publicLink} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Abrir</a>
      </>}
      <Button variant="secondary" disabled={!dirty || busy} onClick={save}>Salvar</Button>
      <Button disabled={busy || steps.length === 0} onClick={() => setStatus(published ? 'draft' : 'published')}>{published ? 'Despublicar' : 'Publicar'}</Button>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!published && !hasForm && tab === 'editor' && <p className="muted" style={{ marginBottom: 'var(--space-3)' }}>Dica: adicione um bloco de formulário para capturar contatos e medir conversões.</p>}
    <Tabs variant="line" label="Seções do funil" value={tab} onChange={setTab} items={[{ value: 'editor', label: 'Editor' }, { value: 'stats', label: 'Métricas' }, { value: 'settings', label: 'Configurações' }]} />

    {tab === 'stats' && <FunnelStatsTab funnelId={funnel.id} />}
    {tab === 'settings' && <FunnelSettings funnel={funnel} onChange={(values) => setFunnel((f) => ({ ...f, ...values }))} />}
    {tab === 'editor' && <div className="bld" style={{ marginTop: 'var(--space-4)' }}>
      <aside className="bld-panel bld-sticky" aria-label="Páginas e blocos">
        <header><h2>Páginas</h2><Button variant="ghost" aria-label="Adicionar página" disabled={busy || steps.length >= 50} onClick={addStep}><Plus size={16} /></Button></header>
        <div className="bld-panel-body">
          <ul className="bld-list">
            {steps.map((s, i) => <li key={s.id}>
              <div className="bld-item" role="button" tabIndex={0} aria-current={s.id === step?.id} onClick={() => { setStepId(s.id); setBlockId(''); }} onKeyDown={(e) => { if (e.key === 'Enter') { setStepId(s.id); setBlockId(''); } }}>
                <span className="fe-step-number">{i + 1}</span>
                <span className="name">{s.name}<small>{KIND_LABELS[s.kind]}</small></span>
                <span className="actions" onClick={(e) => e.stopPropagation()}>
                  <Button variant="ghost" aria-label="Mover página para cima" disabled={i === 0 || busy} onClick={() => moveStep(s.id, -1)}><ArrowUp size={14} /></Button>
                  <Button variant="ghost" aria-label="Mover página para baixo" disabled={i === steps.length - 1 || busy} onClick={() => moveStep(s.id, 1)}><ArrowDown size={14} /></Button>
                </span>
              </div>
            </li>)}
          </ul>
          {step && <Section title="Adicionar bloco">
            <div className="bld-palette">{BLOCK_DEFS.map((d) => <button type="button" key={d.type} onClick={() => addBlock(d.type)} disabled={step.blocks.length >= 80}><d.icon size={14} />{d.label}</button>)}</div>
          </Section>}
        </div>
      </aside>

      <div className="bld-canvas">
        <div className="bld-toolbar" style={{ marginBottom: 'var(--space-3)' }}>
          <div className="bld-segmented" role="group" aria-label="Tamanho da prévia">
            <button type="button" className={!mobile ? 'active' : ''} onClick={() => setMobile(false)}><Monitor size={14} /> Computador</button>
            <button type="button" className={mobile ? 'active' : ''} onClick={() => setMobile(true)}><Smartphone size={14} /> Celular</button>
          </div>
          <span className="bld-status">Clique em um bloco para editá-lo.</span>
        </div>
        {step ? <div className="bld-canvas-frame" style={{ width: mobile ? 390 : '100%', maxWidth: '100%' }} onClick={() => setBlockId('')}>
          <PageRenderer blocks={step.blocks} theme={funnel.theme} settings={step.settings} forms={formMap} mode="edit" selectedId={blockId} onSelect={setBlockId} />
        </div> : <p className="bld-empty">Este funil não tem páginas. Adicione uma para começar.</p>}
      </div>

      <aside className="bld-panel bld-sticky" aria-label="Propriedades">
        <header><h2>{block ? blockLabel(block.type) : step ? 'Página' : 'Propriedades'}</h2>
          {block && <span className="actions" style={{ display: 'flex' }}>
            <Button variant="ghost" aria-label="Mover bloco para cima" onClick={() => moveBlock(block.id, -1)}><ArrowUp size={14} /></Button>
            <Button variant="ghost" aria-label="Mover bloco para baixo" onClick={() => moveBlock(block.id, 1)}><ArrowDown size={14} /></Button>
            <Button variant="ghost" aria-label="Duplicar bloco" onClick={() => duplicateBlock(block)}><Copy size={14} /></Button>
            <Button variant="ghost" aria-label="Excluir bloco" onClick={() => deleteBlock(block.id)}><Trash2 size={14} /></Button>
          </span>}
        </header>
        <div className="bld-panel-body">
          {block
            ? <BlockInspector block={block} forms={forms.data || []} busy={busy} onNewForm={newForm}
                onProps={(values) => editBlock(block.id, (b) => ({ ...b, props: { ...b.props, ...values } }))}
                onStyle={(values: Partial<BlockStyle>) => editBlock(block.id, (b) => ({ ...b, style: { ...b.style, ...values } }))} />
            : step && <>
              <Section title="Página">
                <TextInput label="Nome" value={step.name} maxLength={150} onChange={(name) => editStep(step.id, (s) => ({ ...s, name }))} />
                <TextInput label="Endereço" help={`/p/…/${step.slug}`} value={step.slug} maxLength={60} onChange={(slug) => editStep(step.id, (s) => ({ ...s, slug: slug.toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-') }))} />
                <SelectInput<StepKind> label="Tipo" value={step.kind} onChange={(kind) => editStep(step.id, (s) => ({ ...s, kind }))} options={Object.entries(KIND_LABELS).map(([value, label]) => ({ value: value as StepKind, label }))} />
              </Section>
              <Section title="Busca e compartilhamento">
                <TextInput label="Título da aba" value={step.settings.title || ''} maxLength={120} onChange={(title) => stepSettings({ title })} />
                <TextAreaInput label="Descrição" value={step.settings.description || ''} maxLength={300} rows={3} onChange={(description) => stepSettings({ description })} />
              </Section>
              <Section title="Aparência">
                <SelectInput label="Largura da página" value={step.settings.width || 'normal'} onChange={(width) => stepSettings({ width })} options={[{ value: 'narrow', label: 'Estreita' }, { value: 'normal', label: 'Normal' }, { value: 'wide', label: 'Larga' }]} />
              </Section>
              <Button variant="danger" disabled={busy || steps.length <= 1} onClick={() => setDeleting(step)}><Trash2 size={14} /> Excluir página</Button>
            </>}
        </div>
      </aside>
    </div>}
    <ConfirmDialog open={!!deleting} onClose={() => setDeleting(null)} title="Excluir página" description={`A página "${deleting?.name}" e as métricas dela serão removidas. Esta ação não pode ser desfeita.`} onConfirm={async () => { if (deleting) await deleteStep(deleting); }} />
  </div>;
}
