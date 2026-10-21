import csv
import io
import json

from flask import g, request

from ...common import APIError, add, audit, query, require
from ...extensions import db
from ...models import Company, Contact
from ...schemas import CompanySchema, ContactSchema
from ...services import contact_import as ci
from ...services.automations import emit
from . import bp

# CSV is transported as JSON so the existing authenticated gateway handles account guards.
# Imports are atomic and reject identifiers/references supplied by external spreadsheets.
CSV_FIELDS = {
    'contacts': ['name', 'email', 'phone', 'position', 'source', 'notes', 'tags', 'custom_fields'],
    'companies': [
        'name',
        'document',
        'website',
        'email',
        'phone',
        'industry',
        'address',
        'notes',
        'tags',
        'custom_fields',
    ],
}


@bp.get('/<kind>/export')
@require()
def export_csv(kind):

    if kind not in CSV_FIELDS:
        raise APIError('Recurso não encontrado.', 404)
    model = Contact if kind == 'contacts' else Company
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS[kind])
    writer.writeheader()
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
            mapping = {
                k: [c for c in v if c in headers]
                for k, v in mapping.items()
                if k in ci.FIELD_LABELS and isinstance(v, list)
            }
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
    if (
        fmt != 'vcard'
        and not mapping.get('full_name')
        and not mapping.get('first_name')
        and not mapping.get('last_name')
        and not mapping.get('company')
    ):
        summary['problems'].insert(
            0, {'line': 1, 'reason': 'Nenhuma coluna de nome foi reconhecida. Escolha uma no mapeamento.'}
        )
    sample = [
        {k: r[k] for k in ('name', 'phones', 'emails', 'company', 'position', 'tags', 'duplicate')} for r in records[:8]
    ]
    return {
        'format': fmt,
        'format_label': ci.FORMAT_LABELS[fmt],
        'headers': headers,
        'mapping': mapping,
        'field_labels': ci.FIELD_LABELS,
        'multi': sorted(ci.MULTI),
        'summary': summary,
        'sample': sample,
    }


@bp.post('/contacts/import/run')
@require()
def import_run():
    ci, fmt, headers, mapping, options, records, summary = import_request()

    mode = options.get('duplicates', 'skip')
    existing = {}
    if mode == 'update':
        for contact in query(Contact).filter_by(archived=False).all():
            for key in [contact.email.lower()] if contact.email else []:
                existing.setdefault(('e', key), contact)
            if contact.phone:
                number, _ = ci.normalize_phone(contact.phone, '')
                if number:
                    existing.setdefault(('p', number), contact)
    companies = {c.name.casefold(): c for c in query(Company).all()} if options.get('create_companies', True) else {}
    result = {
        'imported': 0,
        'updated': 0,
        'skipped_duplicates': 0,
        'skipped_invalid': summary['invalid'],
        'companies_created': 0,
    }
    for rec in records:
        company = None
        if rec['company'] and options.get('create_companies', True):
            company = companies.get(rec['company'].casefold())
            if not company:
                company = add(Company, {'name': rec['company']})
                companies[rec['company'].casefold()] = company
                result['companies_created'] += 1
        extra = {}
        if len(rec['phones']) > 1:
            extra['telefones_adicionais'] = ', '.join(rec['phones'][1:])[:500]
        if len(rec['emails']) > 1:
            extra['emails_adicionais'] = ', '.join(rec['emails'][1:])[:500]
        if rec['duplicate']:
            match = (existing.get(('p', rec['phones'][0])) if rec['phones'] else None) or (
                existing.get(('e', rec['emails'][0])) if rec['emails'] else None
            )
            if mode == 'update' and match:
                for field, value in (
                    ('email', rec['emails'][0] if rec['emails'] else None),
                    ('phone', rec['phones'][0] if rec['phones'] else None),
                    ('position', rec['position']),
                    ('notes', rec['notes']),
                ):
                    if value and not getattr(match, field):
                        setattr(match, field, value)
                if company and not match.company_id:
                    match.company_id = company.id
                match.tags = sorted({*(match.tags or []), *rec['tags']})
                match.custom_fields = {**extra, **(match.custom_fields or {})}
                result['updated'] += 1
            else:
                result['skipped_duplicates'] += 1
            continue
        row = add(
            Contact,
            {
                'name': rec['name'],
                'email': rec['emails'][0] if rec['emails'] else None,
                'phone': rec['phones'][0] if rec['phones'] else None,
                'position': rec['position'] or None,
                'notes': rec['notes'] or None,
                'source': rec['source'],
                'tags': rec['tags'],
                'custom_fields': extra,
                'company_id': company.id if company else None,
            },
        )
        if rec['phones']:
            existing[('p', rec['phones'][0])] = row
        if rec['emails']:
            existing[('e', rec['emails'][0])] = row
        result['imported'] += 1
        if options.get('trigger_automations'):
            emit(g.workspace_id, 'contact.created', row.id, row)
    audit('import_contacts', Contact(workspace_id=g.workspace_id), {**result, 'format': fmt})
    db.session.commit()
    return result, 201


@bp.post('/<kind>/import')
@require()
def import_csv(kind):

    from marshmallow import ValidationError

    if kind not in CSV_FIELDS:
        raise APIError('Recurso não encontrado.', 404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'csv'} or not isinstance(body['csv'], str):
        raise APIError('Envie o conteúdo CSV.')
    if len(body['csv'].encode()) > 2 * 1024 * 1024:
        raise APIError('CSV deve ter até 2 MB.', 413)
    reader = csv.DictReader(io.StringIO(body['csv'].lstrip('\ufeff')))
    if (
        not reader.fieldnames
        or 'name' not in reader.fieldnames
        or len(set(reader.fieldnames)) != len(reader.fieldnames)
        or set(reader.fieldnames) - set(CSV_FIELDS[kind])
    ):
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
                emit(g.workspace_id, 'contact.created', row.id, row)
    except (ValidationError, ValueError, csv.Error) as error:
        raise APIError(f'Linha {count + 1}: revise os dados do CSV.', 422) from error
    db.session.commit()
    return {'imported': count}, 201
