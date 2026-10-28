'use client';
import { useEffect, useState } from 'react';
import { BookmarkPlus, Bookmark, SlidersHorizontal, Trash2, X } from 'lucide-react';
import { Button, FormDialog, Popover, SearchInput } from '@/components/ui';
import { useNotify, useSession } from '@/components/providers';
import { useList, post, remove, refreshAll } from '@/lib/api';
import type { Row } from '@/lib/types';
export type ContactFilters = { search: string; archived: boolean; owner: string; company: string; source: string; tag: string; email: string };
export const emptyContactFilters: ContactFilters = { search: '', archived: false, owner: '', company: '', source: '', tag: '', email: '' };
type SavedView = { id: string; name: string; filters: ContactFilters };
function validView(value: any): value is SavedView {
  return value && typeof value.id === 'string' && typeof value.name === 'string' && value.name.length <= 50 && value.filters
    && ['search', 'owner', 'company', 'source'].every(key => typeof value.filters[key] === 'string') && typeof value.filters.archived === 'boolean';
}
export function ContactFilterBar({ value, onChange, companies, users, sources, tags }: {
  value: ContactFilters; onChange: (filters: ContactFilters) => void; companies: Row[]; users: Row[]; sources: string[]; tags: string[];
}) {
  const { user, workspace } = useSession();
  const { notify } = useNotify();
  const stored = useList('/contact-views');
  const [legacyViews, setLegacyViews] = useState<SavedView[]>([]);
  const views = ((stored.data || []) as SavedView[]).map(view => ({ ...view, filters: { ...emptyContactFilters, ...view.filters } }));
  const [selected, setSelected] = useState('');
  const [saving, setSaving] = useState(false);
  const key = user && workspace ? `antares.contact-views.v1:${workspace.id}:${user.id}` : null;
  useEffect(() => {
    setSelected('');
    try {
      const data = key ? JSON.parse(localStorage.getItem(key) || '[]') : [];
      setLegacyViews(Array.isArray(data) ? data.filter(validView).slice(0, 8) : []);
    } catch { setLegacyViews([]); }
  }, [key]);
  const selectedView = views.find(view => view.id === selected);
  const matches = selectedView && Object.keys(emptyContactFilters).every(field => selectedView.filters[field as keyof ContactFilters] === value[field as keyof ContactFilters]);
  const hasFilters = Object.values(value).some(Boolean);
  const activeFilters = (['owner', 'source', 'company', 'email', 'tag', 'archived'] as const).filter(field => value[field]).length;
  return <>
    <div className="toolbar contact-toolbar">
      <SearchInput value={value.search} onChange={search => onChange({ ...value, search })} placeholder="Buscar nome, telefone, e-mail ou empresa" />
      <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" panelClassName="filter-panel"
        badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
        <label className="field"><span>Responsável</span>
          <select value={value.owner} onChange={e => onChange({ ...value, owner: e.target.value })}>
            <option value="">Todos os responsáveis</option><option value="unassigned">Sem responsável</option>
            {users.filter(row => row.active).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select></label>
        <label className="field"><span>Origem</span>
          <select value={value.source} onChange={e => onChange({ ...value, source: e.target.value })}>
            <option value="">Todas as origens</option>{sources.map(source => <option key={source} value={source}>{source}</option>)}
          </select></label>
        <label className="field"><span>Empresa</span>
          <select value={value.company} onChange={e => onChange({ ...value, company: e.target.value })}>
            <option value="">Todas as empresas</option><option value="unassigned">Sem empresa</option>
            {companies.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
          </select></label>
        <label className="field"><span>E-mail</span>
          <select value={value.email} onChange={e => onChange({ ...value, email: e.target.value })}>
            <option value="">Com ou sem e-mail</option><option value="true">Com e-mail</option><option value="false">Sem e-mail</option>
          </select></label>
        <label className="field"><span>Tag</span>
          <select value={value.tag} onChange={e => onChange({ ...value, tag: e.target.value })}>
            <option value="">Todas as tags</option>{tags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
          </select></label>
        <label className="checkbox-label">
          <input type="checkbox" checked={value.archived} onChange={e => onChange({ ...value, archived: e.target.checked })} />
          Ver arquivados
        </label>
      </>}</Popover>
      <Popover label={matches ? selectedView.name : 'Salvos'} icon={<Bookmark size={15} />} variant="soft" panelClassName="menu-panel">{close => <>
        {views.map(view => <div className="menu-row" key={view.id}>
          <button type="button" className={view.id === selected && matches ? 'active' : ''} onClick={() => { setSelected(view.id); onChange({ ...emptyContactFilters, ...view.filters }); close(); }}>{view.name}</button>
          <button type="button" className="menu-icon" aria-label={'Excluir filtro salvo ' + view.name} onClick={async () => {
            try { await remove('/contact-views/' + view.id); await refreshAll(); if (view.id === selected) setSelected(''); }
            catch (error) { notify((error as Error).message, 'error'); }
          }}><Trash2 size={14} /></button>
        </div>)}
        {!views.length && <p className="menu-empty">Nenhum filtro salvo ainda.</p>}
        <button type="button" className="menu-action" disabled={!key || views.length >= 20 || stored.isLoading || !!stored.error}
          onClick={() => { close(); setSaving(true); }}><BookmarkPlus size={15} />Salvar filtros atuais</button>
      </>}</Popover>
      {hasFilters && <Button variant="ghost" onClick={() => { setSelected(''); onChange({ ...emptyContactFilters }); }}><X size={14} />Limpar</Button>}
    </div>
    {!!legacyViews.length && <div className="account-summary"><p>{legacyViews.length} visão(ões) antiga(s) está(ão) guardada(s) neste navegador.</p><Button variant="secondary" onClick={async () => { try { for (const view of legacyViews) { if (!views.some(v => v.name.toLocaleLowerCase() === view.name.toLocaleLowerCase())) await post<{ id: string }>('/contact-views', { name:view.name, filters:view.filters }); } await refreshAll(); if (key) localStorage.removeItem(key); setLegacyViews([]); notify('Visões importadas.'); } catch (error) { await refreshAll(); notify((error as Error).message,'error'); } }}>Importar visões antigas</Button></div>}
    {stored.error && <p className="form-error" role="alert">Não foi possível carregar suas visões salvas.</p>}
    <FormDialog open={saving} onClose={() => setSaving(false)} title="Salvar filtros" description="Esta visão fica disponível nos seus dispositivos, só para seu usuário nesta conta. Até 20 visões."
      fields={[{ name: 'name', label: 'Nome da visão', placeholder: 'Ex.: Leads do Instagram', required: true, wide: true }]}
      onSubmit={async data => {
        if (data.name.length > 50) throw new Error('Use até 50 caracteres no nome.');
        if (views.some(view => view.name.toLocaleLowerCase() === data.name.toLocaleLowerCase())) throw new Error('Já existe uma visão com esse nome.');
        if (views.length >= 20) throw new Error('Você pode salvar até 20 visões nesta conta.');
        const view = await post<{ id: string }>('/contact-views', { name: data.name, filters: { ...value } });
        await refreshAll(); setSelected(view.id); notify('Filtros salvos na sua conta.');
      }} />
  </>;
}
