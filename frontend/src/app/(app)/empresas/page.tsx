'use client';
import { useState } from 'react';
import { Plus, Pencil, Archive, Building2, Globe, Phone, Mail, MapPin, SlidersHorizontal, X } from 'lucide-react';
import { useList, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { initials, brl, searchMatch, formatPhone, formatCnpj, hasRealName } from '@/lib/format';
import type { Field, Row } from '@/lib/types';
import { useNotify } from '@/components/providers';
import { Button, Badge, PageHeader, EmptyState, DataState, SearchInput, FormDialog, ConfirmDialog, Modal, Popover } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { CrmDataTools, metadataFields, metadataInitial, metadataPayload } from '@/components/contacts/crm-data-tools';
import { Card } from '@/components/blocks';

const fields: Field[] = [
  { name: 'name', label: 'Razão social / nome fantasia', required: true },
  { name: 'document', label: 'CNPJ' },
  { name: 'industry', label: 'Segmento' },
  { name: 'phone', label: 'Telefone' },
  { name: 'email', label: 'E-mail', type: 'email' },
  { name: 'website', label: 'Site', placeholder: 'https://' },
  { name: 'address', label: 'Endereço', type: 'textarea', wide: true },
  { name: 'notes', label: 'Observações', type: 'textarea', wide: true },
    ...metadataFields,
];
const nullable = ['document', 'industry', 'phone', 'email', 'website', 'address', 'notes'];

export default function CompaniesPage() {
  const { notify } = useNotify();
  const [search, setSearch] = useState('');
  const [archived, setArchived] = useState(false);
  const [industry, setIndustry] = useState('');
  const [tag, setTag] = useState('');
  const companies = useList('/companies?archived=' + archived);
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  const full = useData<Row>(detail ? '/companies/' + detail.id : null);
  const all = companies.data || [];
  const industries = [...new Set(all.map((r) => r.industry).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  const tags = [...new Set(all.flatMap((r) => r.tags || []))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  const activeFilters = [industry, tag, archived].filter(Boolean).length;
  const hasFilters = Boolean(search || activeFilters);
  const rows = all.filter((r) =>
    (!industry || r.industry === industry) && (!tag || (r.tags || []).includes(tag)) &&
    searchMatch(search, [r.name, r.document, formatCnpj(r.document), r.industry, r.phone, r.email, ...(r.tags || []), ...Object.values(r.custom_fields || {})]),
  );
  const site = (url?: string | null) => (url && !/^https?:\/\//i.test(url) ? 'https://' + url : url || '');
  return (
    <div className="page">
      <PageHeader title="Empresas">
        <CrmDataTools kind="companies" />
        <Button onClick={() => setEditing(null)}>
          <Plus size={17} /> Nova empresa
        </Button>
      </PageHeader>
      <Card fill>
        <div className="toolbar contact-toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar nome, CNPJ ou segmento" />
          <Popover label="Filtros" icon={<SlidersHorizontal size={15} />} variant="soft" panelClassName="filter-panel"
            badge={activeFilters ? <span className="popover-badge">{activeFilters}</span> : undefined}>{() => <>
            <label className="field"><span>Segmento</span>
              <select value={industry} onChange={(e) => setIndustry(e.target.value)}>
                <option value="">Todos os segmentos</option>{industries.map((name) => <option key={name} value={name}>{name}</option>)}
              </select></label>
            <label className="field"><span>Tag</span>
              <select value={tag} onChange={(e) => setTag(e.target.value)}>
                <option value="">Todas as tags</option>{tags.map((name) => <option key={name} value={name}>{name}</option>)}
              </select></label>
            <label className="checkbox-label">
              <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
              Ver arquivadas
            </label>
          </>}</Popover>
          {hasFilters && <Button variant="ghost" onClick={() => { setSearch(''); setIndustry(''); setTag(''); setArchived(false); }}><X size={14} />Limpar</Button>}
        </div>
        <DataState loading={companies.isLoading} error={companies.error}>
          {rows.length ? (
            <PagedTable
              rows={rows}
              className="contacts-table"
              header={
                <tr>
                  <th>Empresa</th>
                  <th>Segmento</th>
                  <th>Contato</th>
                  <th className="text-right">Ações</th>
                </tr>
              }
              renderRow={(row) => (
                <tr key={row.id} className="clickable" onClick={() => setDetail(row)}>
                  <td>
                    <div className="contact-cell">
                      <button className="client-identity" onClick={(e) => { e.stopPropagation(); setDetail(row); }}>
                        <span className="avatar">{initials(row.name) || <Building2 size={14} />}</span>
                        <span>{row.name}</span>
                      </button>
                      {!!row.tags?.length && <span className="contact-tags">{row.tags.slice(0, 2).map((name: string) => <span className="deal-chip" key={name}>{name}</span>)}{row.tags.length > 2 && <small>+{row.tags.length - 2}</small>}</span>}
                    </div>
                  </td>
                  <td>{row.industry && <span className="deal-chip">{row.industry}</span>}</td>
                  <td>
                    <div className="contact-lines">
                      {row.phone && <span>{formatPhone(row.phone)}</span>}
                      {row.email && <span className="muted">{row.email}</span>}
                    </div>
                  </td>
                  <td>
                    <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" aria-label={'Editar ' + row.name} onClick={() => setEditing(row)}>
                        <Pencil size={16} />
                      </Button>
                      {!archived && (
                        <Button variant="ghost" aria-label={'Arquivar ' + row.name} onClick={() => setDeleting(row)}>
                          <Archive size={16} />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            />
          ) : (
            <EmptyState
              icon={<Building2 />}
              title={hasFilters ? 'Nenhum resultado' : 'Nenhuma empresa'}
              description={hasFilters ? 'Ajuste a busca ou os filtros.' : undefined}
              action={!hasFilters ? <Button onClick={() => setEditing(null)}>Cadastrar empresa</Button> : undefined}
            />
          )}
        </DataState>
      </Card>
      <FormDialog
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
        title={editing ? 'Editar empresa' : 'Nova empresa'}
        fields={fields}
        initial={metadataInitial(editing)}
        onSubmit={async (data) => {
          const body: Record<string, any> = metadataPayload(data);
          for (const key of nullable) body[key] = data[key] || null;
          await (editing ? patch('/companies/' + editing.id, body) : post('/companies', body));
          await refreshAll();
          notify(editing ? 'Empresa atualizada.' : 'Empresa cadastrada.');
          setEditing(undefined);
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Arquivar empresa?"
        description={`${deleting?.name || 'A empresa'} sairá da lista ativa. Contatos e negócios serão preservados.`}
        onConfirm={async () => {
          await remove('/companies/' + deleting!.id);
          await refreshAll();
          notify('Empresa arquivada.');
          setDeleting(null);
        }}
      />
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.name || 'Empresa'} wide>
        <div className="stack">
          <dl className="record-details">
            <div><dt><Phone size={15} /> Telefone</dt><dd>{formatPhone(detail?.phone) || 'Não informado'}</dd></div>
            <div><dt><Mail size={15} /> E-mail</dt><dd>{detail?.email || 'Não informado'}</dd></div>
            <div><dt><Globe size={15} /> Site</dt><dd>{detail?.website ? <a className="record-link" href={site(detail.website)} target="_blank" rel="noopener noreferrer">{detail.website.replace(/^https?:\/\//i, '')}</a> : 'Não informado'}</dd></div>
            <div><dt>CNPJ</dt><dd>{formatCnpj(detail?.document) || 'Não informado'}</dd></div>
            {detail?.address && <div className="record-wide"><dt><MapPin size={15} /> Endereço</dt><dd>{detail.address}</dd></div>}
          </dl>
          <section className="record-section"><h3>Tags e campos personalizados</h3><p>{(detail?.tags || []).join(' · ') || 'Sem tags'}</p><dl className="record-details">{Object.entries(detail?.custom_fields || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></section>
          <DataState loading={full.isLoading} error={full.error}>
            <section className="record-section">
              <h3>Contatos</h3>
              {(full.data?.contacts || []).length ? (
                <ul className="record-list">{full.data!.contacts.map((c: Row) => (
                  <li key={c.id}>
                    <span className="avatar">{hasRealName(c.name) ? initials(c.name) : '—'}</span>
                    <div><strong className={hasRealName(c.name) ? '' : 'contact-unnamed'}>{hasRealName(c.name) ? c.name : 'Sem nome'}</strong>
                      <small>{[c.position, formatPhone(c.phone)].filter(Boolean).join(' · ')}</small></div>
                  </li>
                ))}</ul>
              ) : (
                <p className="muted">Nenhum contato vinculado.</p>
              )}
            </section>
            <section className="record-section">
              <h3>Negócios</h3>
              {(full.data?.opportunities || []).length ? (
                <ul className="record-list">{full.data!.opportunities.map((o: Row) => (
                  <li key={o.id}>
                    <Badge value={o.status} />
                    <strong>{o.title}</strong>
                    <span className="record-amount">{brl(o.amount)}</span>
                  </li>
                ))}</ul>
              ) : (
                <p className="muted">Nenhum negócio.</p>
              )}
            </section>
          </DataState>
        </div>
      </Modal>
    </div>
  );
}
