import csv
import io
import json
from test_growth import env
from app.extensions import db
from app.models import AuditLog, Contact, Company


def test_metadata_csv_scope_and_audit(env):
    client, d = env; headers = d['headers']()
    for kind, model in [('contacts', Contact), ('companies', Company)]:
        body = {'name': '=SUM(A1)', 'tags': ['Prioridade'], 'custom_fields': {'Segmento': 'Saúde'}}
        result = client.post('/api/v1/' + kind, headers=headers, json=body)
        assert result.status_code == 201 and result.json['custom_fields'] == body['custom_fields']
        identifier = result.json['id']
        assert client.patch(f'/api/v1/{kind}/{identifier}', headers=d['headers'](d['outsider']), json={'tags': ['bad']}).status_code == 404
        export = client.get(f'/api/v1/{kind}/export', headers=headers)
        assert export.status_code == 200
        rows = list(csv.DictReader(io.StringIO(export.json['csv'])))
        assert rows[0]['name'].startswith("'=") and json.loads(rows[0]['tags']) == ['Prioridade']
        assert client.get(f'/api/v1/{kind}/export', headers=d['headers'](d['outsider'])).json['count'] == 0
        assert client.post(f'/api/v1/{kind}/import', headers=headers, json={'csv': 'name,email\nImportado,import@example.test\n'}).status_code == 201
        count = model.query.count()
        assert client.post(f'/api/v1/{kind}/import', headers=headers, json={'csv': 'name,email\nVálido,ok@example.test\nInválido,broken\n'}).status_code == 422
        assert model.query.count() == count  # Atomic rollback, including audit/events.
        assert client.post(f'/api/v1/{kind}/import', headers=headers, json={'csv': 'name,workspace_id\nBad,' + d['other'].id}).status_code == 422
    audit = client.get('/api/v1/audit-logs', headers=headers)
    assert audit.status_code == 200
    assert all(row['workspace_id'] == d['ws'].id and row['user_id'] == d['owner'].id for row in audit.json['items'])
    assert client.get('/api/v1/audit-logs', headers=d['headers'](d['member'])).status_code == 403
    assert all(row['workspace_id'] == d['other'].id for row in client.get('/api/v1/audit-logs', headers=d['headers'](d['outsider'])).json['items'])


def test_metadata_limits_and_bad_csv(env):
    client, d = env; h = d['headers']()
    for body in [{'name': 'Test', 'tags': ['x'] * 51}, {'name': 'Test', 'custom_fields': {'nested': {'bad': True}}}]:
        assert client.post('/api/v1/contacts', headers=h, json=body).status_code == 422
    for content in ['name,name\na,b', 'name,email\nbad', 'name\na,b']:
        assert client.post('/api/v1/contacts/import', headers=h, json={'csv': content}).status_code == 422
    assert Contact.query.count() == 0

