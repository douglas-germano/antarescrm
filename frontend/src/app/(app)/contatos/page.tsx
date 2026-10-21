'use client';
import { useState } from 'react';
import Link from 'next/link';
import { Plus, Pencil, Archive, Users, Mail, Phone, Building2, MessageCircle, CalendarPlus, FileText } from 'lucide-react';
import { useList, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { initials, rowOptions, day, brl, kinds, searchMatch } from '@/lib/format';
import type { Field, Row } from '@/lib/types';
import { useSession, useNotify } from '@/components/providers';
import { Button, Badge, PageHeader, EmptyState, DataState, SearchInput, FormDialog, ConfirmDialog, Modal } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { CrmDataTools, metadataFields, metadataInitial, metadataPayload } from '@/components/crm-data-tools';
import { Card } from '@/components/blocks';
import { ContactFilterBar, emptyContactFilters } from '@/components/contact-filters';
import { RecordActivityDialog, type ActivityRecord } from '@/components/record-activity-dialog';
import { ContactTimeline } from '@/components/contact-timeline';

export default function ContactsPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const [filters, setFilters] = useState({ ...emptyContactFilters });
  const { search, archived } = filters;
  const hasFilters = Object.values(filters).some(Boolean);
  const [activityRecord, setActivityRecord] = useState<ActivityRecord | null>(null);
  const [activityMode, setActivityMode] = useState<'follow_up' | 'note'>('follow_up');
  const contacts = useList('/contacts?archived=' + archived);
  const companies = useList('/companies');
  const users = useList('/users');
  const [editing, setEditing] = useState<Row | null | undefined>();
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  const timeline = useData<Row>(detail ? '/contacts/' + detail.id + '/timeline' : null);
  const companyList = companies.data || [];
  const companyName = (id?: string) => companyList.find((c) => c.id === id)?.name;
  const fields: Field[] = [
    { name: 'name', label: 'Nome', required: true },
    { name: 'company_id', label: 'Empresa', type: 'company' },
    { name: 'position', label: 'Cargo' },
    { name: 'phone', label: 'Telefone / WhatsApp', placeholder: '(11) 99999-9999' },
    { name: 'email', label: 'E-mail', type: 'email' },
    { name: 'source', label: 'Origem', placeholder: 'Indicação, Instagram, site…' },
    { name: 'owner_id', label: 'Responsável', type: 'select', options: rowOptions((users.data || []).filter((u) => u.active)) },
    { name: 'notes', label: 'Observações', type: 'textarea', wide: true },
    ...metadataFields,
  ];
  const sources = [...new Set<string>((contacts.data || []).map(r => r.source).filter(Boolean))].sort();
  const rows = (contacts.data || []).filter(r =>
    (!filters.owner || (filters.owner === 'unassigned' ? !r.owner_id : r.owner_id === filters.owner)) &&
    (!filters.company || (filters.company === 'unassigned' ? !r.company_id : r.company_id === filters.company)) &&
    (!filters.source || r.source === filters.source)
  ).filter((r) =>
    searchMatch(search, [r.name, r.email, r.phone, ...(r.tags || []), ...Object.values(r.custom_fields || {}), companyName(r.company_id)]),
  );
  return (
    <div className="page">
      <PageHeader title="Contatos">
        <CrmDataTools kind="contacts" />
        <Button onClick={() => setEditing(null)}>
          <Plus size={17} /> Novo contato
        </Button>
      </PageHeader>
      <ContactFilterBar value={filters} onChange={setFilters} companies={companyList} users={users.data || []} sources={sources} total={rows.length} />
      <Card fill>
        <div className="toolbar clients-toolbar">
          <SearchInput value={search} onChange={search => setFilters(previous => ({ ...previous, search }))} placeholder="Buscar nome, telefone, e-mail ou empresa" />
          <div className="clients-toolbar-actions">
            <label className="checkbox-label">
              <input type="checkbox" checked={archived} onChange={(e) => setFilters(previous => ({ ...previous, archived: e.target.checked }))} />
              Ver arquivados
            </label>
          </div>
        </div>
        <DataState loading={contacts.isLoading} error={contacts.error}>
          {rows.length ? (
            <PagedTable
              rows={rows}
              header={
                <tr>
                  <th>Contato</th>
                  <th>Empresa</th>
                  <th>Telefone / e-mail</th>
                  <th>Origem</th>
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
                  <td>{companyName(row.company_id) || '—'}</td>
                  <td>
                    <div className="contact-lines">
                      <span>{row.phone || 'Sem telefone'}</span>
                      <span className="muted">{row.email || 'Sem e-mail'}</span>
                    </div>
                  </td>
                  <td>{row.source || '—'}</td>
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
              icon={<Users />}
              title={hasFilters ? 'Nenhum resultado' : 'Nenhum contato'}
              description={hasFilters ? 'Ajuste os filtros.' : undefined}
              action={!archived && !hasFilters ? <Button onClick={() => setEditing(null)}>Cadastrar contato</Button> : undefined}
            />
          )}
        </DataState>
      </Card>
      <RecordActivityDialog record={activityRecord} mode={activityMode} onClose={() => setActivityRecord(null)} opportunities={(timeline.data?.opportunities || []).filter((row: Row) => row.status === 'open')} />
      <FormDialog
        open={editing !== undefined}
        onClose={() => setEditing(undefined)}
        title={editing ? 'Editar contato' : 'Novo contato'}
        fields={fields}
        initial={metadataInitial(editing || { owner_id: user?.id })}
        onSubmit={async (data) => {
          const body: Record<string, any> = metadataPayload(data);
          for (const key of ['company_id', 'position', 'phone', 'email', 'source', 'owner_id', 'notes']) body[key] = data[key] || null;
          await (editing ? patch('/contacts/' + editing.id, body) : post('/contacts', body));
          await refreshAll();
          notify(editing ? 'Contato atualizado.' : 'Contato cadastrado.');
          setEditing(undefined);
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Arquivar contato?"
        description={`${deleting?.name || 'O contato'} sairá da lista ativa. O histórico será preservado.`}
        onConfirm={async () => {
          await remove('/contacts/' + deleting!.id);
          await refreshAll();
          notify('Contato arquivado.');
          setDeleting(null);
        }}
      />
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.name || 'Contato'} wide>
        <div className="stack">
          <dl className="record-details">
            <div><dt><Phone size={15} /> Telefone</dt><dd>{detail?.phone || 'Não informado'}</dd></div>
            <div><dt><Mail size={15} /> E-mail</dt><dd>{detail?.email || 'Não informado'}</dd></div>
            <div><dt><Building2 size={15} /> Empresa</dt><dd>{companyName(detail?.company_id) || 'Não informada'}</dd></div>
            <div><dt>Cargo / origem</dt><dd>{[detail?.position, detail?.source].filter(Boolean).join(' · ') || 'Não informados'}</dd></div>
          </dl>
          <section className="record-section"><h3>Tags e campos personalizados</h3><p>{(detail?.tags || []).join(' · ') || 'Sem tags'}</p><dl className="record-details">{Object.entries(detail?.custom_fields || {}).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></section>
          {detail?.notes && (
            <section className="record-section">
              <h3>Observações</h3>
              <p className="record-notes muted">{detail.notes}</p>
            </section>
          )}
          <DataState loading={timeline.isLoading} error={timeline.error}>
            <section className="record-section">
              <div className="record-actionbar">
                <h3>Histórico e próximos passos</h3>
                <div>
                  <Button variant="secondary" onClick={() => { setActivityMode('note'); setActivityRecord({ label: detail!.name, contact_id: detail!.id, company_id: detail!.company_id }); }}><FileText size={15} />Registrar nota</Button>
                  <Button onClick={() => { setActivityMode('follow_up'); setActivityRecord({ label: detail!.name, contact_id: detail!.id, company_id: detail!.company_id, owner_id: detail!.owner_id }); }}><CalendarPlus size={15} />Agendar retorno</Button>
                </div>
              </div>
              <ContactTimeline data={timeline.data} />
            </section>
          </DataState>
          <div className="modal-footer">
            {detail?.phone && (
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    const conv = await post('/whatsapp/conversations', { phone: detail.phone, contact_id: detail.id, contact_name: detail.name });
                    window.location.assign('/mensagens?conversation=' + conv.id);
                  } catch (e) {
                    notify((e as Error).message, 'error');
                  }
                }}
              >
                <MessageCircle size={16} /> Abrir WhatsApp
              </Button>
            )}
            <Link className="btn btn-primary" href="/crm">Ver funil</Link>
          </div>
        </div>
      </Modal>
    </div>
  );
}
