'use client';
import { useEffect, useState } from 'react';
import { BookmarkPlus, Trash2, X } from 'lucide-react';
import { Button, FormDialog } from '@/components/ui';
import { useNotify, useSession } from '@/components/providers';
import { useList, post, remove, refreshAll } from '@/lib/api';
import type { Row } from '@/lib/types';
export type ContactFilters = { search: string; archived: boolean; owner: string; company: string; source: string };
export const emptyContactFilters: ContactFilters = { search: '', archived: false, owner: '', company: '', source: '' };
type SavedView = { id: string; name: string; filters: ContactFilters };
function validView(value: any): value is SavedView {
  return value && typeof value.id === 'string' && typeof value.name === 'string' && value.name.length <= 50 && value.filters
    && ['search', 'owner', 'company', 'source'].every(key => typeof value.filters[key] === 'string') && typeof value.filters.archived === 'boolean';
}
export function ContactFilterBar({ value, onChange, companies, users, sources, total }: {
  value: ContactFilters; onChange: (filters: ContactFilters) => void; companies: Row[]; users: Row[]; sources: string[]; total: number;
}) {
  const { user, workspace } = useSession();
  const { notify } = useNotify();
  const stored = useList('/contact-views');
  const [legacyViews, setLegacyViews] = useState<SavedView[]>([]);
  const views = (stored.data || []) as SavedView[];
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
  return <>
    <div className="contact-filterbar">
      <select aria-label="Filtrar contatos por responsável" value={value.owner} onChange={e => onChange({ ...value, owner: e.target.value })}>
        <option value="">Todos os responsáveis</option><option value="unassigned">Sem responsável</option>
        {users.filter(row => row.active).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
      <select aria-label="Filtrar contatos por origem" value={value.source} onChange={e => onChange({ ...value, source: e.target.value })}>
        <option value="">Todas as origens</option>{sources.map(source => <option key={source} value={source}>{source}</option>)}
      </select>
      <select aria-label="Filtrar contatos por empresa" value={value.company} onChange={e => onChange({ ...value, company: e.target.value })}>
        <option value="">Todas as empresas</option><option value="unassigned">Sem empresa</option>
        {companies.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
      <div className="saved-contact-views">
        <select aria-label="Filtros de contatos salvos" value={matches ? selected : ''} onChange={e => {
          const view = views.find(row => row.id === e.target.value); setSelected(e.target.value); if (view) onChange({ ...view.filters });
        }}><option value="">Filtros salvos</option>{views.map(view => <option value={view.id} key={view.id}>{view.name}</option>)}</select>
        <Button variant="ghost" disabled={!key || views.length >= 20 || stored.isLoading || !!stored.error} onClick={() => setSaving(true)} title="Salvar esta visão na sua conta"><BookmarkPlus size={16} />Salvar filtros</Button>
        {matches && <Button variant="ghost" aria-label={'Excluir filtro salvo ' + selectedView.name} onClick={async () => {
          try { await remove('/contact-views/' + selected); await refreshAll(); setSelected(''); }
          catch (error) { notify((error as Error).message, 'error'); }
        }}><Trash2 size={15} /></Button>}
      </div>
      <span className="filter-result-count" aria-live="polite">{total} {total === 1 ? 'contato' : 'contatos'}</span>
      {hasFilters && <Button variant="ghost" onClick={() => { setSelected(''); onChange({ ...emptyContactFilters }); }}><X size={14} />Limpar</Button>}
    </div>
    {!!legacyViews.length && <div className="account-summary"><p>{legacyViews.length} visão(ões) antiga(s) está(ão) guardada(s) neste navegador.</p><Button variant="secondary" onClick={async () => { try { for (const view of legacyViews) { if (!views.some(v => v.name.toLocaleLowerCase() === view.name.toLocaleLowerCase())) await post('/contact-views', { name:view.name, filters:view.filters }); } await refreshAll(); if (key) localStorage.removeItem(key); setLegacyViews([]); notify('Visões importadas.'); } catch (error) { await refreshAll(); notify((error as Error).message,'error'); } }}>Importar visões antigas</Button></div>}
    {stored.error && <p className="form-error" role="alert">Não foi possível carregar suas visões salvas.</p>}
    <FormDialog open={saving} onClose={() => setSaving(false)} title="Salvar filtros" description="Esta visão fica disponível nos seus dispositivos, só para seu usuário nesta conta. Até 20 visões."
      fields={[{ name: 'name', label: 'Nome da visão', placeholder: 'Ex.: Leads do Instagram', required: true, wide: true }]}
      onSubmit={async data => {
        if (data.name.length > 50) throw new Error('Use até 50 caracteres no nome.');
        if (views.some(view => view.name.toLocaleLowerCase() === data.name.toLocaleLowerCase())) throw new Error('Já existe uma visão com esse nome.');
        if (views.length >= 20) throw new Error('Você pode salvar até 20 visões nesta conta.');
        const view = await post('/contact-views', { name: data.name, filters: { ...value } });
        await refreshAll(); setSelected(view.id); notify('Filtros salvos na sua conta.');
      }} />
  </>;
}
