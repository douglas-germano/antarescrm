'use client';
import { useState } from 'react';
import { Plus, Pencil, Archive, Building2, Globe, Phone, Mail } from 'lucide-react';
import { useList, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { initials, brl, searchMatch } from '@/lib/format';
import type { Field, Row } from '@/lib/types';
import { useNotify } from '@/components/providers';
import { Button, Badge, PageHeader, EmptyState, DataState, SearchInput, FormDialog, ConfirmDialog, Modal } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { CrmDataTools, metadataFields, metadataInitial, metadataPayload } from '@/components/crm-data-tools';
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
  const companies = useList('/companies?archived=' + archived);
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  const full = useData<Row>(detail ? '/companies/' + detail.id : null);
  const rows = (companies.data || []).filter((r) =>
    searchMatch(search, [r.name, r.document, r.industry, r.phone, r.email, ...(r.tags || []), ...Object.values(r.custom_fields || {})]),
  );
  return (
    <div className="page">
      <PageHeader title="Empresas">
        <CrmDataTools kind="companies" />
        <Button onClick={() => setEditing(null)}>
          <Plus size={17} /> Nova empresa
        </Button>
      </PageHeader>
      <Card fill>
        <div className="toolbar clients-toolbar">
          <SearchInput value={search} onChange={setSearch} placeholder="Buscar nome, CNPJ ou segmento" />
          <div className="clients-toolbar-actions">
            <label className="checkbox-label">
              <input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />
              Ver arquivadas
            </label>
          </div>
        </div>
        <DataState loading={companies.isLoading} error={companies.error}>
          {rows.length ? (
            <PagedTable
              rows={rows}
              header={
                <tr>
                  <th>Empresa</th>
                  <th>Segmento</th>
                  <th>Contato</th>
                  <th className="text-right">Ações</th>
                </tr>
              }
              renderRow={(row) => (
                <tr key={row.id}>
                  <td>
                    <button className="client-identity" onClick={() => setDetail(row)}>
                      <span className="avatar">{initials(row.name)}</span>
                      {row.name}
                    </button>
                  </td>
                  <td>{row.industry || '—'}</td>
                  <td>
                    <div className="contact-lines">
                      <span>{row.phone || 'Sem telefone'}</span>
                      <span className="muted">{row.email || 'Sem e-mail'}</span>
                    </div>
                  </td>
                  <td>
                    <div className="row-actions">
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
              title={search ? 'Nenhum resultado' : 'Nenhuma empresa'}
              description={search ? 'Tente outro termo.' : undefined}
              action={!archived && !search ? <Button onClick={() => setEditing(null)}>Cadastrar empresa</Button> : undefined}
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
            <div><dt><Phone size={15} /> Telefone</dt><dd>{detail?.phone || 'Não informado'}</dd></div>
            <div><dt><Mail size={15} /> E-mail</dt><dd>{detail?.email || 'Não informado'}</dd></div>
            <div><dt><Globe size={15} /> Site</dt><dd>{detail?.website || 'Não informado'}</dd></div>
            <div><dt>CNPJ</dt><dd>{detail?.document || 'Não informado'}</dd></div>
          </dl>
          <section className="record-section"><h3>Tags e campos personalizados</h3><p>{(detail?.tags || []).join(' · ') || 'Sem tags'}</p><dl className="record-details">{Object.entries(detail?.custom_fields || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></section>
          <DataState loading={full.isLoading} error={full.error}>
            <section className="record-section">
              <h3>Contatos</h3>
              {(full.data?.contacts || []).length ? (
                full.data!.contacts.map((c: Row) => (
                  <p key={c.id}>
                    <strong>{c.name}</strong> <span className="muted">{[c.position, c.phone].filter(Boolean).join(' · ')}</span>
                  </p>
                ))
              ) : (
                <p className="muted">Nenhum contato vinculado.</p>
              )}
            </section>
            <section className="record-section">
              <h3>Negócios</h3>
              {(full.data?.opportunities || []).length ? (
                full.data!.opportunities.map((o: Row) => (
                  <p key={o.id}>
                    <Badge value={o.status} /> <strong>{o.title}</strong> · {brl(o.amount)}
                  </p>
                ))
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
