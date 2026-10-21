from flask import Blueprint, request, g
from ..extensions import db
from sqlalchemy import func
from ..models import Company, Contact, Pipeline, PipelineStage, Opportunity, StageHistory, Activity, Task, WhatsAppConversation, now
from ..schemas import CompanySchema, ContactSchema, StageSchema, OpportunitySchema, CloseSchema, ActivitySchema
from ..common import require, payload, query, get, add, update, commit, page, APIError, user_ref, audit

bp = Blueprint('crm', __name__)


_ACCENTS = 'áàâãäéèêëíìîïóòôõöúùûüçñ'
_PLAIN = 'aaaaaeeeeiiiiooooouuuucn'


def fold(text):
    """Lower-case without accents, so "joao" finds "João"."""
    return str(text).lower().translate(str.maketrans(_ACCENTS, _PLAIN))


def search(q, model, *columns):
    term = (request.args.get('search') or '').strip()
    if not term:
        return q
    postgres = db.session.get_bind().dialect.name == 'postgresql'
    folded = '%' + fold(term) + '%'
    clauses = []
    for name in columns:
        column = getattr(model, name)
        clauses.append(func.translate(func.lower(column), _ACCENTS, _PLAIN).ilike(folded) if postgres else column.ilike('%' + term + '%'))
    digits = ''.join(ch for ch in term if ch.isdigit())
    if len(digits) >= 3 and 'phone' in columns:  # "(66) 99649-9089" matches +5566996499089
        phone = getattr(model, 'phone')
        clauses.append(func.regexp_replace(phone, r'\D', '', 'g').ilike('%' + digits + '%') if postgres else phone.ilike('%' + digits + '%'))
    return q.filter(db.or_(*clauses))


def active(model, identifier, label):
    row = get(model, identifier)
    if row.archived:
        raise APIError(f'{label} está arquivado.')
    return row


# ---------- companies ----------
@bp.get('/companies')
@require()
def companies():
    q = query(Company).filter_by(archived=request.args.get('archived') == 'true')
    return page(search(q, Company, 'name', 'document', 'email', 'phone').order_by(Company.name))


@bp.post('/companies')
@require()
def company_create():
    return commit(add(Company, payload(CompanySchema)), 201)


@bp.get('/companies/<uuid:company_id>')
@require()
def company_detail(company_id):
    row = get(Company, company_id)
    contacts = query(Contact).filter_by(company_id=row.id, archived=False).order_by(Contact.name).all()
    opportunities = query(Opportunity).filter_by(company_id=row.id).order_by(Opportunity.updated_at.desc()).all()
    return {**row.to_dict(), 'contacts': [c.to_dict() for c in contacts], 'opportunities': [o.to_dict() for o in opportunities]}


@bp.patch('/companies/<uuid:company_id>')
@require()
def company_update(company_id):
    row = get(Company, company_id)
    update(row, payload(CompanySchema, partial=True))
    return commit(row)


@bp.delete('/companies/<uuid:company_id>')
@require()
def company_archive(company_id):
    row = get(Company, company_id)
    update(row, {'archived': True})
    return commit(row)


# ---------- contacts ----------
@bp.get('/contacts')
@require()
def contacts():
    q = query(Contact).filter_by(archived=request.args.get('archived') == 'true')
    for field in ('company_id', 'owner_id'):
        if request.args.get(field):
            q = q.filter(getattr(Contact, field) == request.args[field])
    return page(search(q, Contact, 'name', 'phone', 'email').order_by(Contact.name))


def validate_contact(data):
    if data.get('company_id'):
        active(Company, data['company_id'], 'A empresa')
    user_ref(data.get('owner_id'))


@bp.post('/contacts')
@require()
def contact_create():
    data = payload(ContactSchema)
    validate_contact(data)
    row = add(Contact, data)
    from ..services.automations import emit
    emit(g.workspace_id, 'contact.created', row.id, row)
    return commit(row, 201)


@bp.get('/contacts/<uuid:contact_id>')
@require()
def contact_detail(contact_id):
    return get(Contact, contact_id).to_dict()


@bp.patch('/contacts/<uuid:contact_id>')
@require()
def contact_update(contact_id):
    row = get(Contact, contact_id)
    data = payload(ContactSchema, partial=True)
    validate_contact(data)
    update(row, data)
    return commit(row)


@bp.delete('/contacts/<uuid:contact_id>')
@require()
def contact_archive(contact_id):
    row = get(Contact, contact_id)
    update(row, {'archived': True})
    return commit(row)


@bp.get('/contacts/<uuid:contact_id>/timeline')
@require()
def contact_timeline(contact_id):
    """Everything that happened with a contact: activities, deals, tasks and the WhatsApp thread."""
    row = get(Contact, contact_id)
    conversation = query(WhatsAppConversation).filter_by(contact_id=row.id).first()
    return {
        'activities': [x.to_dict() for x in query(Activity).filter_by(contact_id=row.id).order_by(Activity.scheduled_at.desc()).limit(100)],
        'opportunities': [x.to_dict() for x in query(Opportunity).filter_by(contact_id=row.id).order_by(Opportunity.updated_at.desc())],
        'tasks': [x.to_dict() for x in query(Task).filter_by(contact_id=row.id).order_by(Task.due_date)],
        'whatsapp_conversation_id': conversation.id if conversation else None,
    }


# ---------- pipeline ----------
@bp.get('/pipeline/stages')
@require()
def stages():
    q = query(PipelineStage)
    identifier = request.args.get('pipeline_id')
    if identifier:
        if identifier != 'default': get(Pipeline, identifier)
        q = q.filter_by(pipeline_id=None if identifier == 'default' else identifier)
    names = {row.id: row.name for row in query(Pipeline).all()}
    return {'items': [{**x.to_dict(), 'pipeline_name': names.get(x.pipeline_id, 'Principal')} for x in q.order_by(PipelineStage.position).all()]}


@bp.post('/pipeline/stages')
@require('owner', 'admin')
def stage_create():
    data = payload(StageSchema)
    if data.get('pipeline_id'): get(Pipeline, data['pipeline_id'])
    validate_stage_name(data)
    return commit(add(PipelineStage, data), 201)


@bp.patch('/pipeline/stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_update(stage_id):
    row = get(PipelineStage, stage_id)
    data = payload(StageSchema, partial=True)
    if 'pipeline_id' in data and data['pipeline_id'] != row.pipeline_id:
        raise APIError('Não é possível mover uma etapa para outro funil.', 422)
    validate_stage_name(data, row)
    update(row, data)
    return commit(row)


@bp.delete('/pipeline/stages/<uuid:stage_id>')
@require('owner', 'admin')
def stage_delete(stage_id):
    row = get(PipelineStage, stage_id)
    if query(Opportunity).filter_by(stage_id=row.id).first() or query(StageHistory).filter(db.or_(StageHistory.from_stage_id == row.id, StageHistory.to_stage_id == row.id)).first():
        raise APIError('Etapa com negócios ou histórico não pode ser excluída.', 409)
    from ..models import LeadForm
    if query(LeadForm).filter_by(stage_id=row.id).first():
        raise APIError('Etapa vinculada a um formulário não pode ser excluída.', 409)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204


# ---------- opportunities ----------
@bp.get('/opportunities')
@require()
def opportunities():
    q = query(Opportunity)
    identifier = request.args.get('pipeline_id')
    if identifier:
        if identifier != 'default': get(Pipeline, identifier)
        q = q.join(PipelineStage, PipelineStage.id == Opportunity.stage_id).filter(PipelineStage.pipeline_id.is_(None) if identifier == 'default' else PipelineStage.pipeline_id == identifier)
    for field in ('status', 'stage_id', 'contact_id', 'company_id', 'owner_id'):
        if request.args.get(field):
            q = q.filter(getattr(Opportunity, field) == request.args[field])
    q = search(q, Opportunity, 'title')
    result = page(q.order_by(Opportunity.updated_at.desc()))
    enrich_opportunities(result['items'])
    return result


def enrich_opportunities(items):
    """Adds `stage_changed_at` (last stage move) and `last_contact_at` (last completed activity) to listed deals."""
    ids = [row['id'] for row in items]
    if not ids:
        return
    moved = dict(query(StageHistory).filter(StageHistory.opportunity_id.in_(ids))
                 .with_entities(StageHistory.opportunity_id, func.max(StageHistory.created_at)).group_by(StageHistory.opportunity_id).all())
    touched = dict(query(Activity).filter(Activity.opportunity_id.in_(ids), Activity.status == 'completed')
                   .with_entities(Activity.opportunity_id, func.max(Activity.scheduled_at)).group_by(Activity.opportunity_id).all())
    for row in items:
        when = moved.get(row['id'])
        row['stage_changed_at'] = when.isoformat() if when else row.get('created_at')
        last = touched.get(row['id'])
        row['last_contact_at'] = last.isoformat() if last else None


def validate_opportunity(data):
    if data.get('contact_id'):
        active(Contact, data['contact_id'], 'O contato')
    if data.get('company_id'):
        active(Company, data['company_id'], 'A empresa')
    if data.get('stage_id'):
        get(PipelineStage, data['stage_id'])
    user_ref(data.get('owner_id'))


@bp.post('/opportunities')
@require()
def opportunity_create():
    data = payload(OpportunitySchema)
    validate_opportunity(data)
    if not data.get('company_id') and data.get('contact_id'):
        data['company_id'] = get(Contact, data['contact_id']).company_id
    row = add(Opportunity, data)
    add(StageHistory, {'opportunity_id': row.id, 'to_stage_id': row.stage_id, 'user_id': g.user.id})
    if row.contact_id:
        from ..services.automations import emit
        emit(g.workspace_id, 'opportunity.created', row.id, get(Contact, row.contact_id), row.id)
    return commit(row, 201)


@bp.get('/opportunities/<uuid:opportunity_id>')
@require()
def opportunity_detail(opportunity_id):
    row = get(Opportunity, opportunity_id)
    history = query(StageHistory).filter_by(opportunity_id=row.id).order_by(StageHistory.created_at).all()
    return {**row.to_dict(), 'pipeline_id': get(PipelineStage, row.stage_id).pipeline_id, 'history': [x.to_dict() for x in history]}


@bp.patch('/opportunities/<uuid:opportunity_id>')
@require()
def opportunity_update(opportunity_id):
    row = get(Opportunity, opportunity_id, lock=True)
    if row.status != 'open':
        raise APIError('Negócios encerrados não podem ser alterados.', 409)
    data = payload(OpportunitySchema, partial=True)
    validate_opportunity(data)
    history = None
    if data.get('stage_id', row.stage_id) != row.stage_id:
        history = add(StageHistory, {'opportunity_id': row.id, 'from_stage_id': row.stage_id, 'to_stage_id': data['stage_id'], 'user_id': g.user.id})
    update(row, data)
    if history and row.contact_id:
        from ..services.automations import emit
        emit(g.workspace_id, 'opportunity.stage_changed', history.id, get(Contact, row.contact_id), row.id)
    return commit(row)


@bp.post('/opportunities/<uuid:opportunity_id>/close')
@require()
def opportunity_close(opportunity_id):
    row = get(Opportunity, opportunity_id, lock=True)
    data = payload(CloseSchema)
    if row.status != 'open':
        raise APIError('Negócio já encerrado.', 409)
    if data['status'] == 'lost' and not data.get('loss_reason'):
        raise APIError('Informe o motivo da perda.')
    if data['status'] == 'won' and row.amount <= 0:
        raise APIError('Informe um valor positivo para fechar a venda.')
    update(row, {'status': data['status'], 'closed_at': now(), 'loss_reason': data.get('loss_reason')})
    if data['status'] == 'won':
        from ..services.projects import create_from_deal  # A won sale becomes a client project, once.
        create_from_deal(row, g.user.id)
    if row.contact_id:
        from ..services.automations import emit
        emit(g.workspace_id, 'opportunity.' + data['status'], row.id, get(Contact, row.contact_id), row.id)
    return commit(row)


# ---------- activities ----------
def validate_activity(data):
    if data.get('opportunity_id'):
        get(Opportunity, data['opportunity_id'])
    if data.get('contact_id'):
        get(Contact, data['contact_id'])
    if data.get('company_id'):
        get(Company, data['company_id'])
    user_ref(data.get('owner_id'))


@bp.get('/activities')
@require()
def activities():
    q = query(Activity)
    for field in ('opportunity_id', 'contact_id', 'company_id', 'owner_id', 'status', 'kind'):
        if request.args.get(field):
            q = q.filter(getattr(Activity, field) == request.args[field])
    return page(q.order_by(Activity.scheduled_at.desc()))


@bp.post('/activities')
@require()
def activity_create():
    data = payload(ActivitySchema)
    validate_activity(data)
    data.setdefault('owner_id', g.user.id)
    return commit(add(Activity, data), 201)


@bp.patch('/activities/<uuid:activity_id>')
@require()
def activity_update(activity_id):
    row = get(Activity, activity_id)
    data = payload(ActivitySchema, partial=True)
    validate_activity(data)
    update(row, data)
    return commit(row)


@bp.delete('/activities/<uuid:activity_id>')
@require()
def activity_delete(activity_id):
    row = get(Activity, activity_id)
    audit('delete', row)
    db.session.delete(row)
    db.session.commit()
    return '', 204


# CSV is transported as JSON so the existing authenticated gateway handles account guards.
# Imports are atomic and reject identifiers/references supplied by external spreadsheets.
CSV_FIELDS = {
    'contacts': ['name', 'email', 'phone', 'position', 'source', 'notes', 'tags', 'custom_fields'],
    'companies': ['name', 'document', 'website', 'email', 'phone', 'industry', 'address', 'notes', 'tags', 'custom_fields'],
}


@bp.get('/<kind>/export')
@require()
def export_csv(kind):
    import csv, io, json
    if kind not in CSV_FIELDS:
        raise APIError('Recurso não encontrado.', 404)
    model = Contact if kind == 'contacts' else Company
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS[kind]); writer.writeheader()
    rows = query(model).filter_by(archived=False).order_by(model.name).limit(10001).all()
    if len(rows) > 10000:
        raise APIError('Exporte até 10.000 registros por vez.', 422)
    for row in rows:
        data = {}
        for field in CSV_FIELDS[kind]:
            value = getattr(row, field)
            value = json.dumps(value, ensure_ascii=False) if field in ('tags', 'custom_fields') else (value or '')
            # Neutralize spreadsheet formula injection, including whitespace-prefixed values.
            data[field] = "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value
        writer.writerow(data)
    audit('export_csv', model(workspace_id=g.workspace_id), {'count': len(rows)})
    db.session.commit()
    return {'csv': output.getvalue(), 'filename': kind + '.csv', 'count': len(rows)}


def import_request():
    """Shared parsing for the contact import preview and run endpoints."""
    from ..services import contact_import as ci
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('content'), str) or not body['content'].strip():
        raise APIError('Envie o conteúdo do arquivo.')
    if len(body['content'].encode()) > 8 * 1024 * 1024:
        raise APIError('O arquivo deve ter até 8 MB.', 413)
    options = body.get('options') if isinstance(body.get('options'), dict) else {}
    mapping = body.get('mapping') if isinstance(body.get('mapping'), dict) else None
    try:
        text, fmt, headers, rows, suggested = ci.load(body['content'], body.get('filename'), mapping)
        if mapping is not None:
            mapping = {k: [c for c in v if c in headers] for k, v in mapping.items() if k in ci.FIELD_LABELS and isinstance(v, list)}
        else:
            mapping = suggested
        phones, emails = ci.existing_keys(g.workspace_id)
        records, summary = ci.process(text, fmt, headers, rows, mapping, options, phones, emails)
    except ValueError as error:
        raise APIError(str(error), 422) from error
    return ci, fmt, headers, mapping, options, records, summary


@bp.post('/contacts/import/preview')
@require()
def import_preview():
    ci, fmt, headers, mapping, options, records, summary = import_request()
    if fmt != 'vcard' and not mapping.get('full_name') and not mapping.get('first_name') and not mapping.get('last_name') and not mapping.get('company'):
        summary['problems'].insert(0, {'line': 1, 'reason': 'Nenhuma coluna de nome foi reconhecida. Escolha uma no mapeamento.'})
    sample = [{k: r[k] for k in ('name', 'phones', 'emails', 'company', 'position', 'tags', 'duplicate')} for r in records[:8]]
    return {'format': fmt, 'format_label': ci.FORMAT_LABELS[fmt], 'headers': headers, 'mapping': mapping,
            'field_labels': ci.FIELD_LABELS, 'multi': sorted(ci.MULTI), 'summary': summary, 'sample': sample}


@bp.post('/contacts/import/run')
@require()
def import_run():
    ci, fmt, headers, mapping, options, records, summary = import_request()
    from ..services.automations import emit
    mode = options.get('duplicates', 'skip')
    existing = {}
    if mode == 'update':
        for contact in query(Contact).filter_by(archived=False).all():
            for key in ([contact.email.lower()] if contact.email else []):
                existing.setdefault(('e', key), contact)
            if contact.phone:
                number, _ = ci.normalize_phone(contact.phone, '')
                if number: existing.setdefault(('p', number), contact)
    companies = {c.name.casefold(): c for c in query(Company).all()} if options.get('create_companies', True) else {}
    result = {'imported': 0, 'updated': 0, 'skipped_duplicates': 0, 'skipped_invalid': summary['invalid'], 'companies_created': 0}
    for rec in records:
        company = None
        if rec['company'] and options.get('create_companies', True):
            company = companies.get(rec['company'].casefold())
            if not company:
                company = add(Company, {'name': rec['company']})
                companies[rec['company'].casefold()] = company
                result['companies_created'] += 1
        extra = {}
        if len(rec['phones']) > 1: extra['telefones_adicionais'] = ', '.join(rec['phones'][1:])[:500]
        if len(rec['emails']) > 1: extra['emails_adicionais'] = ', '.join(rec['emails'][1:])[:500]
        if rec['duplicate']:
            match = (existing.get(('p', rec['phones'][0])) if rec['phones'] else None) or (existing.get(('e', rec['emails'][0])) if rec['emails'] else None)
            if mode == 'update' and match:
                for field, value in (('email', rec['emails'][0] if rec['emails'] else None), ('phone', rec['phones'][0] if rec['phones'] else None),
                                     ('position', rec['position']), ('notes', rec['notes'])):
                    if value and not getattr(match, field):
                        setattr(match, field, value)
                if company and not match.company_id: match.company_id = company.id
                match.tags = sorted({*(match.tags or []), *rec['tags']})
                match.custom_fields = {**extra, **(match.custom_fields or {})}
                result['updated'] += 1
            else:
                result['skipped_duplicates'] += 1
            continue
        row = add(Contact, {'name': rec['name'], 'email': rec['emails'][0] if rec['emails'] else None, 'phone': rec['phones'][0] if rec['phones'] else None,
                            'position': rec['position'] or None, 'notes': rec['notes'] or None, 'source': rec['source'], 'tags': rec['tags'],
                            'custom_fields': extra, 'company_id': company.id if company else None})
        if rec['phones']: existing[('p', rec['phones'][0])] = row
        if rec['emails']: existing[('e', rec['emails'][0])] = row
        result['imported'] += 1
        if options.get('trigger_automations'):
            emit(g.workspace_id, 'contact.created', row.id, row)
    audit('import_contacts', Contact(workspace_id=g.workspace_id), {**result, 'format': fmt})
    db.session.commit()
    return result, 201


@bp.post('/<kind>/import')
@require()
def import_csv(kind):
    import csv, io, json
    from marshmallow import ValidationError
    if kind not in CSV_FIELDS:
        raise APIError('Recurso não encontrado.', 404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'csv'} or not isinstance(body['csv'], str):
        raise APIError('Envie o conteúdo CSV.')
    if len(body['csv'].encode()) > 2 * 1024 * 1024:
        raise APIError('CSV deve ter até 2 MB.', 413)
    reader = csv.DictReader(io.StringIO(body['csv'].lstrip('\ufeff')))
    if not reader.fieldnames or 'name' not in reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or set(reader.fieldnames) - set(CSV_FIELDS[kind]):
        raise APIError('Cabeçalho inválido. Use o modelo de exportação e inclua name.', 422)
    model, schema = (Contact, ContactSchema) if kind == 'contacts' else (Company, CompanySchema)
    count = 0
    try:
        for count, record in enumerate(reader, 1):
            if count > 2000:
                raise APIError('Importe até 2.000 registros por vez.', 422)
            if None in record or None in record.values():
                raise APIError(f'Linha {count + 1}: número de colunas inválido.', 422)
            data = {key: value for key, value in record.items() if value != ''}
            for key in ('tags', 'custom_fields'):
                if key in data:
                    data[key] = json.loads(data[key])
            row = add(model, schema().load(data))
            if model is Contact:
                from ..services.automations import emit
                emit(g.workspace_id, 'contact.created', row.id, row)
    except (ValidationError, ValueError, csv.Error) as error:
        raise APIError(f'Linha {count + 1}: revise os dados do CSV.', 422) from error
    db.session.commit()
    return {'imported': count}, 201


def validate_stage_name(data, row=None):
    name = data.get('name', row.name if row else '').strip()
    pipeline_id = row.pipeline_id if row else data.get('pipeline_id')
    from ..services.booking import lock
    lock('stage:' + g.workspace_id + ':' + str(pipeline_id) + ':' + name)
    duplicate = query(PipelineStage).filter_by(pipeline_id=pipeline_id, name=name)
    if row: duplicate = duplicate.filter(PipelineStage.id != row.id)
    if duplicate.first(): raise APIError('Já existe uma etapa com este nome no funil.', 409)
    data['name'] = name


@bp.get('/pipelines')
@require()
def pipelines():
    return {'items': [{'id': 'default', 'name': 'Principal'}] + [row.to_dict() for row in query(Pipeline).order_by(Pipeline.name)]}


@bp.post('/pipelines')
@require('owner', 'admin')
def create_pipeline():
    from ..schemas import StrictSchema, text
    class Schema(StrictSchema): name = text(150, required=True)
    row = add(Pipeline, payload(Schema))
    for index, name in enumerate(('Novo lead', 'Qualificação', 'Proposta', 'Negociação')):
        add(PipelineStage, {'pipeline_id': row.id, 'name': name, 'position': index})
    return commit(row, 201)
