from test_growth import env
from app.extensions import db
from app.models import Contact, Company


def seed(d):
    db.session.add_all([Contact(workspace_id=d['ws'].id, name='João da Silva', phone='+5566996499089', email='joao@x.com'),
                        Contact(workspace_id=d['ws'].id, name='Maria Souza', phone='65999990000'),
                        Company(workspace_id=d['ws'].id, name='Açaí Norte Ltda')])
    db.session.commit()


def names(client, d, path):
    return sorted(r['name'] for r in client.get(path, headers=d['headers']()).json['items'])


def test_search_by_name_email_and_phone_digits(env):
    client, d = env; seed(d)
    assert names(client, d, '/api/v1/contacts?search=silva') == ['João da Silva']
    assert names(client, d, '/api/v1/contacts?search=joao@') == ['João da Silva']
    assert names(client, d, '/api/v1/contacts?search=99649') == ['João da Silva']
    assert names(client, d, '/api/v1/contacts?search=') == ['João da Silva', 'Maria Souza']
    assert names(client, d, '/api/v1/contacts?search=zzz') == []
    assert names(client, d, '/api/v1/contacts?search=silva', ) and client.get('/api/v1/contacts?search=silva', headers=d['headers'](d['outsider'])).json['items'] == []


def test_accent_insensitive_search_on_postgres_translate():
    from app.routes.crm import fold
    assert fold('JOÃO Açaí') == 'joao acai'
