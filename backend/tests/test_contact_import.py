from test_growth import env
from app.extensions import db
from app.models import Contact, Company, AutomationRule
from app.services import contact_import as ci

GOOGLE = (
    'First Name,Middle Name,Last Name,Organization Name,Organization Title,Notes,Labels,E-mail 1 - Label,E-mail 1 - Value,Phone 1 - Label,Phone 1 - Value,Phone 2 - Label,Phone 2 - Value\n'
    'Ana,,Souza,Acme,Gerente,Cliente antigo,Importado em 26/12 ::: * myContacts ::: VIP,,ana@example.com,Mobile,+55 66 99615-6555,Other,3421-1234 ::: 66996156555\n'
    '.,,,,,,* myContacts,,,Mobile,02166996254233,,\n'
    ',,,,,,,,,Mobile,123,,\n'
)


def post(client, d, path, body):
    return client.post('/api/v1/contacts/import/' + path, json=body, headers=d['headers']())


def test_phone_normalisation_covers_brazilian_formats():
    assert ci.normalize_phone('+55 66 99615-6555') == ('+5566996156555', 'mobile')
    assert ci.normalize_phone('(66) 3421-1234') == ('+556634211234', 'landline')
    assert ci.normalize_phone('066997195459')[0] == '+5566997195459'
    assert ci.normalize_phone('0216536423343')[0] == '+556536423343'
    assert ci.normalize_phone('6696156555')[0] == '+5566996156555'  # old 8-digit mobile gains the ninth digit
    assert ci.normalize_phone('99649-9089') == (None, 'sem DDD')
    assert ci.normalize_phone('99649-9089', '66')[0] == '+5566996499089'
    assert ci.normalize_phone('+1 415 555 2671')[0] == '+14155552671'


def test_google_export_is_detected_and_previewed(env):
    client, d = env
    response = post(client, d, 'preview', {'content': GOOGLE, 'options': {'default_ddd': '66'}})
    assert response.status_code == 200
    data = response.get_json()
    assert data['format'] == 'google'
    assert data['mapping']['phone'] == ['Phone 1 - Value', 'Phone 2 - Value']
    assert data['summary']['total'] == 3 and data['summary']['valid'] == 2 and data['summary']['invalid'] == 1
    assert data['sample'][0]['name'] == 'Ana Souza' and data['sample'][0]['phones'][0] == '+5566996156555'
    assert {'label': '* myContacts', 'count': 2} in data['summary']['labels']


def test_run_creates_contacts_companies_tags_and_skips_duplicates(env):
    client, d = env
    body = {'content': GOOGLE, 'options': {'default_ddd': '66', 'source': 'Google Contatos', 'ignored_tags': ['VIP']}}
    first = post(client, d, 'run', body)
    assert first.status_code == 201
    assert first.get_json() == {
        'imported': 2,
        'updated': 0,
        'skipped_duplicates': 0,
        'skipped_invalid': 1,
        'companies_created': 1,
    }
    ana = Contact.query.filter_by(name='Ana Souza').one()
    assert ana.phone == '+5566996156555' and ana.email == 'ana@example.com' and ana.source == 'Google Contatos'
    assert ana.tags == ['Importado em 26/12'] and ana.custom_fields['telefones_adicionais'] == '+556634211234'
    assert ana.company_id == Company.query.filter_by(name='Acme').one().id
    again = post(client, d, 'run', body).get_json()
    assert again['imported'] == 0 and again['skipped_duplicates'] == 2


def test_update_mode_fills_blanks_without_overwriting(env):
    client, d = env
    existing = Contact(
        workspace_id=d['ws'].id, name='Ana existente', phone='66996156555', notes='Manter', tags=['antigo']
    )
    db.session.add(existing)
    db.session.commit()
    result = post(
        client, d, 'run', {'content': GOOGLE, 'options': {'default_ddd': '66', 'duplicates': 'update'}}
    ).get_json()
    assert result['updated'] == 1 and result['imported'] == 1
    db.session.refresh(existing)
    assert existing.name == 'Ana existente' and existing.notes == 'Manter'
    assert existing.email == 'ana@example.com' and 'antigo' in existing.tags and 'Importado em 26/12' in existing.tags


def test_generic_semicolon_latin1_file_and_manual_mapping(env):
    client, d = env
    raw = 'Cliente;Celular;E-mail comercial;Observações\nJoão da Silva;(65) 99999-1111;joao@x.com;Indicação\n'.encode(
        'cp1252'
    )
    assert ci.decode(raw).startswith('Cliente')
    text = ci.decode(raw)
    body = {
        'content': text,
        'mapping': {
            'full_name': ['Cliente'],
            'phone': ['Celular'],
            'email': ['E-mail comercial'],
            'notes': ['Observações'],
        },
    }
    result = post(client, d, 'run', body).get_json()
    assert result['imported'] == 1
    row = Contact.query.filter_by(name='João da Silva').one()
    assert row.phone == '+5565999991111' and row.notes == 'Indicação'


def test_vcard_import(env):
    client, d = env
    card = 'BEGIN:VCARD\nVERSION:3.0\nFN:Maria Lima\nORG:Beta Ltda\nTITLE:Diretora\nTEL;TYPE=CELL:+55 65 98888-7777\nEMAIL:maria@beta.com\nCATEGORIES:Parceiro,VIP\nEND:VCARD\n'
    assert post(client, d, 'preview', {'content': card}).get_json()['format'] == 'vcard'
    assert post(client, d, 'run', {'content': card}).status_code == 201
    row = Contact.query.filter_by(name='Maria Lima').one()
    assert row.phone == '+5565988887777' and row.position == 'Diretora' and row.tags == ['Parceiro', 'VIP']


def test_import_does_not_trigger_automations_unless_asked(env):
    client, d = env
    db.session.add(
        AutomationRule(workspace_id=d['ws'].id, name='r', event='contact.created', task_title='t', active=True)
    )
    db.session.commit()
    from app.models import AutomationRun

    post(client, d, 'run', {'content': GOOGLE, 'options': {'default_ddd': '66'}})
    assert AutomationRun.query.count() == 0
    post(
        client,
        d,
        'run',
        {
            'content': GOOGLE.replace('ana@example.com', 'ana2@example.com')
            .replace('99615-6555', '99111-0000')
            .replace('66996156555', '66991110000'),
            'options': {'default_ddd': '66', 'trigger_automations': True},
        },
    )
    assert AutomationRun.query.count() >= 1


def test_invalid_payloads_are_rejected_and_cross_account_isolated(env):
    client, d = env
    assert post(client, d, 'preview', {'content': ''}).status_code == 400
    assert post(client, d, 'run', {'content': 'a,b\n'}).status_code in (200, 201, 422)
    post(client, d, 'run', {'content': GOOGLE, 'options': {'default_ddd': '66'}})
    other = client.post(
        '/api/v1/contacts/import/preview',
        json={'content': GOOGLE, 'options': {'default_ddd': '66'}},
        headers=d['headers'](d['outsider']),
    ).get_json()
    assert other['summary']['duplicates'] == 0  # another account never sees these as duplicates
