import { useEffect, useState } from 'react';
import { useAppRouter } from '@/lib/navigation';
import { AlertCircle, ArrowRightLeft, CalendarDays, CheckCircle2, ExternalLink, FileText, FolderKanban, LayoutGrid, List, Plus, SlidersHorizontal, X } from 'lucide-react';
import { useData, useList, post, patch, refreshAll } from '@/lib/api';
import { brl, day, initials, rowOptions, searchMatch, today } from '@/lib/format';
import { useNotify, useSession } from '@/components/providers';
import { Badge, Button, DataState, EmptyState, FormDialog, PageHeader, Popover, SearchInput } from '@/components/ui';
import { Card, KanbanBoard, KanbanCard, KanbanCardMeta, KanbanCardText, KanbanCardTitle, KanbanColumn, Tabs, Toolbar, ToolbarEnd } from '@/components/blocks';
import { STATUS } from '@/components/projects/model';
import { RecordLink } from '@/components/record-link';
import type { Field, Row } from '@/lib/types';

export default function ProjectsPage() {
  const router = useAppRouter();
  const { user } = useSession();
  const { notify } = useNotify();
  const [status, setStatus] = useState('active');
  const [search, setSearch] = useState('');
  const [owner, setOwner] = useState('');
  const [lateOnly, setLateOnly] = useState(false);
  const [view, setView] = useState<'board' | 'list'>('board');
  const [creating, setCreating] = useState(false);
  const stages = useData<{ items: Row[] }>('/project-stages');
  const projects = useList('/projects?per_page=100');
  const users = useList('/users');
  const wonDeals = useList(creating ? '/opportunities?status=won' : null);
  useEffect(() => { try { if (localStorage.getItem('antares.projects.view') === 'list') setView('list'); } catch { /* optional */ } }, []);
  const changeView = (next: 'board' | 'list') => { setView(next); try { localStorage.setItem('antares.projects.view', next); } catch { /* optional */ } };
  const t0 = today();
  const overdue = (p: Row) => p.status === 'active' && p.due_date && p.due_date < t0;
  const activeFilters = [owner, lateOnly].filter(Boolean).length;
  const rows = (projects.data || [])
    .filter((p) => status === 'all' || p.status === status)
    .filter((p) => !owner || p.owner_id === owner)
    .filter((p) => !lateOnly || overdue(p))
    .filter((p) => searchMatch(search, [p.title, p.contact_name, p.company_name]));
  const stageList = stages.data?.items || [];
  const dealsWithoutProject = (wonDeals.data || []).filter((d) => !(projects.data || []).some((p) => p.opportunity_id === d.id));

  const fields: Field[] = [
    { name: 'opportunity_id', label: 'Negócio ganho (opcional)', type: 'select', options: rowOptions(dealsWithoutProject, 'title'), help: 'Preenche cliente, valor e título a partir do negócio.' },
    { name: 'title', label: 'Título do projeto', placeholder: 'Campanha de lançamento — Cliente Alfa' },
    { name: 'contact_id', label: 'Cliente', type: 'contact' },
    { name: 'stage_id', label: 'Etapa inicial', type: 'select', options: rowOptions(stageList) },
    { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions((users.data || []).filter((u) => u.active)) },
    { name: 'amount', label: 'Valor (R$)', type: 'money', min: 0 },
    { name: 'due_date', label: 'Prazo de entrega', type: 'date' },
    { name: 'description', label: 'Descrição', type: 'textarea', wide: true },
  ];

  async function move(project: Row, stageId: string) {
    if (project.stage?.id === stageId) return;
    try { await patch('/projects/' + project.id, { stage_id: stageId }); await refreshAll(); }
    catch (e) { notify((e as Error).message, 'error'); }
  }
  const shortDay = (value: string) => value.slice(8, 10) + '/' + value.slice(5, 7);
  const open = (p: Row) => router.push('/projetos/' + p.id);

  return (
    <div className="page projects-page">
      <PageHeader compact title="Projetos">
        <Button onClick={() => setCreating(true)}><Plus size={17} /> Novo projeto</Button>
      </PageHeader>
      <Toolbar>
        <Tabs label="Situação" value={status} onChange={setStatus} items={[{ value: 'active', label: 'Em andamento' }, { value: 'done', label: 'Concluídos' }, { value: 'all', label: 'Todos' }]} />
        <SearchInput value={search} onChange={setSearch} placeholder="Buscar projeto ou cliente" />
        <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" panelClassName="filter-panel"
          badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
          <label className="field"><span>Responsável</span>
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">Todos os responsáveis</option>
              {(users.data || []).filter((u) => u.active).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select></label>
          <label className="checkbox-label"><input type="checkbox" checked={lateOnly} onChange={(e) => setLateOnly(e.target.checked)} />Só atrasados</label>
        </>}</Popover>
        {(search || activeFilters > 0) && <Button variant="ghost" onClick={() => { setSearch(''); setOwner(''); setLateOnly(false); }}><X size={14} />Limpar</Button>}
        <Tabs label="Visualização" value={view} onChange={changeView} items={[{ value: 'board', label: 'Quadro', icon: <LayoutGrid size={14} /> }, { value: 'list', label: 'Lista', icon: <List size={14} /> }]} />
        <ToolbarEnd>
          <div className="summary-inline">
            <span><strong>{rows.length}</strong> {rows.length === 1 ? 'projeto' : 'projetos'}</span>
            <span>Valor <strong>{brl(rows.reduce((s, p) => s + Number(p.amount), 0))}</strong></span>
          </div>
        </ToolbarEnd>
      </Toolbar>

      <DataState loading={projects.isLoading || stages.isLoading} error={projects.error || stages.error}>
        {!(projects.data || []).length ? (
          <EmptyState icon={<FolderKanban />} title="Nenhum projeto ainda" description="Os projetos nascem sozinhos quando um negócio é ganho. Você também pode criar um manualmente."
            action={<Button onClick={() => setCreating(true)}><Plus size={16} /> Novo projeto</Button>} />
        ) : view === 'list' ? (
          <Card as="section" className="card-fill">
            <div className="table-wrap fill">
              <table className="data-table">
                <thead><tr><th>Projeto</th><th>Cliente</th><th>Etapa</th><th>Valor</th><th>Prazo</th><th>Responsável</th><th>Situação</th></tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id} className="clickable" onClick={() => router.push('/projetos/' + p.id)}>
                      <td><RecordLink href={'/projetos/' + p.id} onClick={(event) => event.stopPropagation()}><strong>{p.title}</strong></RecordLink>{p.pending_approvals > 0 && <small className="text-danger">{p.pending_approvals} {p.pending_approvals === 1 ? 'aprovação aguardando' : 'aprovações aguardando'}</small>}</td>
                      <td>{p.contact_name || p.company_name || '—'}</td>
                      <td><span className="stage-pill"><i style={{ background: p.stage?.color }} />{p.stage?.name}</span></td>
                      <td>{brl(p.amount)}</td>
                      <td className={overdue(p) ? 'text-danger' : ''}>{p.due_date ? day(p.due_date) : '—'}</td>
                      <td>{p.owner_name || '—'}</td>
                      <td><Badge value={STATUS[p.status]?.badge || 'skipped'} label={STATUS[p.status]?.label || p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!rows.length && <EmptyState title="Nenhum projeto encontrado" />}
            </div>
          </Card>
        ) : (
          <KanbanBoard>
            {stageList.map((stage) => {
              const cards = rows.filter((p) => p.stage?.id === stage.id);
              return (
                <KanbanColumn key={stage.id} title={stage.name} dot={stage.color} count={cards.length}
                  total={brl(cards.reduce((s, p) => s + Number(p.amount), 0))} items={cards} empty="Nenhum projeto"
                  onDropId={(id) => { const project = rows.find((p) => p.id === id); if (project) void move(project, stage.id); }}
                  render={(p) => {
                    const flag = p.pending_approvals > 0 ? 'awaiting_approval' : overdue(p) ? 'overdue_action' : undefined;
                    const flagLabel = p.pending_approvals > 0
                      ? (p.pending_approvals === 1 ? '1 aprovação aguardando o cliente' : `${p.pending_approvals} aprovações aguardando o cliente`)
                      : 'Prazo de entrega atrasado';
                    return (
                      <KanbanCard key={p.id} id={p.id} draggable={p.status === 'active'} attention={flag} done={p.status === 'done'} onOpen={() => open(p)}>
                        <div className="project-card-title">
                          <KanbanCardTitle title={p.title} onClick={() => open(p)} />
                          {p.status === 'done' && <span className="project-done" data-tip="Concluído" data-tip-align="end" aria-label="Concluído"><CheckCircle2 size={14} /></span>}
                        </div>
                        <KanbanCardText>{p.contact_name || p.company_name || 'Sem cliente'}</KanbanCardText>
                        <KanbanCardMeta>
                          <strong>{brl(p.amount)}</strong>
                          {p.due_date && <small className={'deal-date' + (overdue(p) ? ' overdue' : '')} data-tip={(overdue(p) ? 'Prazo atrasado: ' : 'Prazo de entrega: ') + day(p.due_date)}><CalendarDays size={12} />{shortDay(p.due_date)}</small>}
                          {p.files_count > 0 && <small data-tip={p.files_count === 1 ? '1 arquivo' : `${p.files_count} arquivos`}><FileText size={12} />{p.files_count}</small>}
                          {flag && <span className={'deal-flag ' + flag} data-tip={flagLabel} aria-label={flagLabel}><AlertCircle size={13} /></span>}
                          {p.owner_name && <span className="owner-avatar" data-tip={p.owner_name} aria-label={'Responsável: ' + p.owner_name}>{initials(p.owner_name)}</span>}
                        </KanbanCardMeta>
                        <div className="deal-actions">
                          <button type="button" className="icon-btn" data-tip="Abrir projeto" aria-label={'Abrir ' + p.title} onClick={() => open(p)}><ExternalLink size={15} /></button>
                          {p.status === 'active' && <label className="stage-menu" data-tip="Mover para outra etapa">
                            <ArrowRightLeft size={14} />
                            <select aria-label={'Mover ' + p.title + ' para outra etapa'} value={p.stage?.id || ''} onChange={(e) => void move(p, e.target.value)}>
                              {stageList.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}
                            </select>
                          </label>}
                        </div>
                      </KanbanCard>
                    );
                  }} />
              );
            })}
          </KanbanBoard>
        )}
      </DataState>

      <FormDialog open={creating} onClose={() => setCreating(false)} title="Novo projeto" fields={fields} initial={{ owner_id: user?.id, amount: '0.00' }} submitLabel="Criar projeto"
        onSubmit={async (data) => {
          if (!data.title && !data.opportunity_id) throw new Error('Informe o título ou escolha um negócio ganho.');
          const body: Record<string, any> = { ...data };
          for (const key of ['opportunity_id', 'contact_id', 'stage_id', 'owner_id', 'due_date', 'description', 'title']) if (!body[key]) delete body[key];
          const created = await post<{ id: string }>('/projects', body);
          await refreshAll();
          router.push('/projetos/' + created.id);
        }} />
    </div>
  );
}
