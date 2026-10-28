'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Pencil, Archive, Users, User, Mail, Phone, Building2, MessageCircle, CalendarPlus, FileText } from 'lucide-react';
import { useList, usePage, useData, post, patch, remove, refreshAll } from '@/lib/api';
import { initials, rowOptions, hasRealName, formatPhone } from '@/lib/format';
import type { Field, Row, Contact, ContactPage } from '@/lib/types';
import { useSession, useNotify } from '@/components/providers';
import { Button, PageHeader, EmptyState, DataState, FormDialog, ConfirmDialog, Modal } from '@/components/ui';
import { PagedTable } from '@/components/fit';
import { CrmDataTools, metadataFields, metadataInitial, metadataPayload } from '@/components/contacts/crm-data-tools';
import { Card } from '@/components/blocks';
import { ContactFilterBar, emptyContactFilters } from '@/components/contacts/contact-filters';
import { RecordActivityDialog, type ActivityRecord } from '@/components/contacts/record-activity-dialog';
import { ContactTimeline } from '@/components/contacts/contact-timeline';

export default function ContactsPage() {
  const { user } = useSession();
  const { notify } = useNotify();
  const [filters, setFilters] = useState({ ...emptyContactFilters });
  // Relatórios links here with ?origem= to list the contacts of one source.
  useEffect(() => {
    const source = new URLSearchParams(window.location.search).get('origem');
    if (source) setFilters((f) => ({ ...f, source }));
  }, []);
  const { search, archived } = filters;
  const displayName = (row?: Contact | null) => (row && hasRealName(row.name) ? row.name : 'Sem nome');
  const hasFilters = Object.values(filters).some(Boolean);
  const [activityRecord, setActivityRecord] = useState<ActivityRecord | null>(null);
  const [activityMode, setActivityMode] = useState<'follow_up' | 'note'>('follow_up');
  const params = new URLSearchParams({ archived: String(archived), search,
    owner_id: filters.owner, company_id: filters.company, source: filters.source, has_email: filters.email, tag: filters.tag });
  const contacts = usePage<Contact, ContactPage>('/contacts?' + params);

  const companies = useList('/companies');
  const users = useList('/users');
  const [editing, setEditing] = useState<Contact | null | undefined>();
  const [deleting, setDeleting] = useState<Contact | null>(null);
  const [detail, setDetail] = useState<Contact | null>(null);
  const timeline = useData<Row>(detail ? '/contacts/' + detail.id + '/timeline' : null);
  const companyList = companies.data || [];
  const companyName = (id?: string | null) => companyList.find((c) => c.id === id)?.name;
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
  const sources = contacts.data?.sources || [];
  const rows = contacts.data?.items || [];
  return (
    <div className="page">
      <PageHeader title="Contatos">
        <CrmDataTools kind="contacts" />
        <Button onClick={() => setEditing(null)}>
          <Plus size={17} /> Novo contato
        </Button>
      </PageHeader>
      <Card fill>
        <ContactFilterBar value={filters} onChange={setFilters} companies={companyList} users={users.data || []} sources={sources} tags={contacts.data?.tags || []} />
        <DataState loading={contacts.isLoading} error={contacts.error}>
          {rows.length ? (
            <PagedTable
              rows={rows}
              className="contacts-table"
              pagination={contacts.data ? { ...contacts.data, onChange: contacts.setPage } : undefined}
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
                <tr key={row.id} className="clickable" onClick={() => setDetail(row)}>
                  <td>
                    <div className="contact-cell">
                      <button className="client-identity" onClick={(e) => { e.stopPropagation(); setDetail(row); }}>
                        <span className="avatar">{hasRealName(row.name) ? initials(row.name) : <User size={14} />}</span>
                        <span className={hasRealName(row.name) ? '' : 'contact-unnamed'}>{displayName(row)}</span>
                      </button>
                      {!!row.tags?.length && <span className="contact-tags">{row.tags.slice(0, 2).map(tag => <span className="deal-chip" key={tag}>{tag}</span>)}{row.tags.length > 2 && <small>+{row.tags.length - 2}</small>}</span>}
                    </div>
                  </td>
                  <td>{companyName(row.company_id)}</td>
                  <td>
                    <div className="contact-lines">
                      {row.phone && <span>{formatPhone(row.phone)}</span>}
                      {row.email && <span className="muted">{row.email}</span>}
                    </div>
                  </td>
                  <td>{row.source && <span className="deal-chip">{row.source}</span>}</td>
                  <td>
                    <div className="row-actions" onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" aria-label={'Editar ' + displayName(row)} onClick={() => setEditing(row)}>
                        <Pencil size={16} />
                      </Button>
                      {!archived && (
                        <Button variant="ghost" aria-label={'Arquivar ' + displayName(row)} onClick={() => setDeleting(row)}>
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
        description={`${deleting && hasRealName(deleting.name) ? deleting.name : 'O contato'} sairá da lista ativa. O histórico será preservado.`}
        onConfirm={async () => {
          await remove('/contacts/' + deleting!.id);
          await refreshAll();
          notify('Contato arquivado.');
          setDeleting(null);
        }}
      />
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail && hasRealName(detail.name) ? detail.name : formatPhone(detail?.phone) || 'Contato'} wide>
        <div className="stack">
          <dl className="record-details">
            <div><dt><Phone size={15} /> Telefone</dt><dd>{formatPhone(detail?.phone) || 'Não informado'}</dd></div>
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
                    const conv = await post<{ id: string }>('/whatsapp/conversations', { phone: detail.phone, contact_id: detail.id, contact_name: detail.name });
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
