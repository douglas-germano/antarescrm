from uuid import uuid4

import pytest
from test_growth import env  # noqa: F401  (shared fixture)

from app.extensions import db
from app.models import FormSubmission, LeadForm


def create_funnel(client, d, template='lead_magnet', name='Captação'):
    response = client.post('/api/v1/funnels', headers=d['headers'](), json={'name': name, 'template': template})
    assert response.status_code == 201, response.json
    return response.json


def funnel_form(funnel):
    return db.session.get(LeadForm, funnel['steps'][0]['blocks'][-1]['props']['form_id'])


def publish(client, d, funnel):
    response = client.patch(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers'](), json={'status': 'published'})
    assert response.status_code == 200, response.json
    return response.json


def test_templates_create_steps_and_form(env):
    client, d = env
    funnel = create_funnel(client, d)
    assert [s['slug'] for s in funnel['steps']] == ['captura', 'obrigado']
    form = funnel_form(funnel)
    assert form.active is False and funnel['steps'][0]['blocks'][-1]['props']['form_id'] == form.id
    assert create_funnel(client, d, 'blank', 'Vazio')['steps'][0]['kind'] == 'landing'


def test_only_admins_edit_funnels(env):
    client, d = env
    response = client.post('/api/v1/funnels', headers=d['headers'](d['member']), json={'name': 'X'})
    assert response.status_code == 403
    funnel = create_funnel(client, d)
    assert client.get(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers'](d['member'])).status_code == 200
    assert client.get(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers'](d['outsider'])).status_code == 404


@pytest.mark.parametrize(
    'block',
    [
        {'id': 'a', 'type': 'button', 'props': {'label': 'Ir', 'action': 'url', 'url': 'javascript:alert(1)'}},
        {'id': 'a', 'type': 'image', 'props': {'src': 'data:text/html;base64,AAAA'}},
        {'id': 'a', 'type': 'video', 'props': {'url': 'https://evil.example/video'}},
        {'id': 'a', 'type': 'script', 'props': {}},
        {'id': 'a', 'type': 'text', 'props': {'html': '<b>x</b>'}},
        {'id': 'bad id', 'type': 'divider'},
        {'id': 'a', 'type': 'heading', 'props': {'level': 9}},
        {'id': 'a', 'type': 'text', 'style': {'background': 'red; x'}},
    ],
)
def test_unsafe_blocks_are_rejected(env, block):
    client, d = env
    funnel = create_funnel(client, d, 'blank')
    url = f'/api/v1/funnels/{funnel["id"]}/steps/{funnel["steps"][0]["id"]}'
    assert client.patch(url, headers=d['headers'](), json={'blocks': [block]}).status_code == 422


def test_duplicate_block_ids_and_foreign_forms_are_rejected(env):
    client, d = env
    funnel = create_funnel(client, d, 'blank')
    url = f'/api/v1/funnels/{funnel["id"]}/steps/{funnel["steps"][0]["id"]}'
    twin = [{'id': 'a', 'type': 'divider'}, {'id': 'a', 'type': 'divider'}]
    assert client.patch(url, headers=d['headers'](), json={'blocks': twin}).status_code == 422
    foreign = [{'id': 'f', 'type': 'form', 'props': {'form_id': str(uuid4())}}]
    assert client.patch(url, headers=d['headers'](), json={'blocks': foreign}).status_code == 422


def test_step_slugs_reorder_and_delete(env):
    client, d = env
    funnel = create_funnel(client, d, 'blank')
    base = f'/api/v1/funnels/{funnel["id"]}/steps'
    one = client.post(base, headers=d['headers'](), json={'name': 'Página inicial'}).json
    two = client.post(base, headers=d['headers'](), json={'name': 'Oferta', 'kind': 'sales'}).json
    assert one['slug'] == 'pagina-inicial-2' and two['position'] == 2
    first = funnel['steps'][0]['id']
    order = [two['id'], first, one['id']]
    reordered = client.post(base + '/reorder', headers=d['headers'](), json={'order': order}).json
    assert [s['id'] for s in reordered['steps']] == order
    assert client.post(base + '/reorder', headers=d['headers'](), json={'order': order[:2]}).status_code == 422
    assert client.delete(f'{base}/{first}', headers=d['headers']()).status_code == 204
    detail = client.get(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers']()).json
    assert [s['position'] for s in detail['steps']] == [0, 1]


def test_public_pages_require_publication_and_publish_activates_forms(env):
    client, d = env
    funnel = create_funnel(client, d)
    assert client.get(f'/api/v1/public/funnels/{funnel["id"]}').status_code == 404
    publish(client, d, funnel)
    form_id = funnel_form(funnel).id
    assert funnel_form(funnel).active is True
    page = client.get(f'/api/v1/public/funnels/{funnel["id"]}').json
    assert page['step']['slug'] == 'captura' and page['next_slug'] == 'obrigado'
    assert 'map_to' not in str(page['forms'][form_id]) and page['forms'][form_id]['design']['layout'] == 'plain'
    last = client.get(f'/api/v1/public/funnels/{funnel["id"]}/obrigado').json
    assert last['next_slug'] is None and last['forms'] == {}
    assert client.get(f'/api/v1/public/funnels/{funnel["id"]}/nao-existe').status_code == 404
    client.patch(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers'](), json={'status': 'draft'})
    assert client.get(f'/api/v1/public/funnels/{funnel["id"]}').status_code == 404


def test_views_conversions_and_stats(env):
    client, d = env
    funnel = create_funnel(client, d)
    publish(client, d, funnel)
    first, last = funnel['steps']
    visitors = [str(uuid4()) for _ in range(4)]
    for visitor in visitors:
        url = f'/api/v1/public/funnels/{funnel["id"]}/steps/{first["id"]}/view'
        assert client.post(url, json={'visitor_id': visitor}).status_code == 204
    client.post(f'/api/v1/public/funnels/{funnel["id"]}/steps/{first["id"]}/view', json={'visitor_id': visitors[0]})
    client.post(f'/api/v1/public/funnels/{funnel["id"]}/steps/{last["id"]}/view', json={'visitor_id': visitors[0]})
    body = {
        'submission_key': str(uuid4()),
        'name': 'Lead',
        'email': 'lead@example.com',
        'consent': True,
        'attribution': {'funnel_id': funnel['id'], 'funnel_step_id': first['id'], 'visitor_id': visitors[0]},
    }
    form_id = funnel_form(funnel).id
    assert client.post(f'/api/v1/public/forms/{form_id}/submit', json=body).status_code == 200
    stats = client.get(f'/api/v1/funnels/{funnel["id"]}/stats', headers=d['headers']()).json
    capture, thanks = stats['steps']
    assert (capture['views'], capture['visitors'], capture['conversions']) == (4, 4, 1)
    assert capture['conversion_rate'] == 0.25 and thanks['visitors'] == 1 and thanks['drop_off'] == 0.75
    assert stats['visitors'] == 4 and stats['conversions'] == 1
    listed = client.get('/api/v1/funnels', headers=d['headers']()).json['items'][0]
    assert listed['totals'] == {'views': 5, 'conversions': 1, 'steps': 2}


def test_conversion_ignores_attribution_from_other_accounts(env):
    client, d = env
    funnel = create_funnel(client, d)
    publish(client, d, funnel)
    other = client.post(
        '/api/v1/funnels', headers=d['headers'](d['outsider']), json={'name': 'Outro', 'template': 'blank'}
    )
    assert other.status_code == 201
    body = {
        'submission_key': str(uuid4()),
        'name': 'Lead',
        'email': 'lead@example.com',
        'consent': True,
        'attribution': {
            'funnel_id': other.json['id'],
            'funnel_step_id': other.json['steps'][0]['id'],
            'visitor_id': str(uuid4()),
        },
    }
    assert client.post(f'/api/v1/public/forms/{funnel_form(funnel).id}/submit', json=body).status_code == 200
    stats = client.get(f'/api/v1/funnels/{other.json["id"]}/stats', headers=d['headers'](d['outsider'])).json
    assert stats['conversions'] == 0


def test_duplicate_clones_forms_inactive(env):
    client, d = env
    funnel = create_funnel(client, d)
    publish(client, d, funnel)
    copy = client.post(f'/api/v1/funnels/{funnel["id"]}/duplicate', headers=d['headers']()).json
    assert copy['status'] == 'draft' and [s['slug'] for s in copy['steps']] == ['captura', 'obrigado']
    clone = funnel_form(copy)
    assert clone.id != funnel_form(funnel).id and clone.active is False


def test_delete_funnel_removes_pages_and_events(env):
    client, d = env
    funnel = create_funnel(client, d)
    assert client.delete(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers']()).status_code == 204
    assert client.get(f'/api/v1/funnels/{funnel["id"]}', headers=d['headers']()).status_code == 404


# ---------- flexible forms ----------
def form_url(d):
    return f'/api/v1/forms/{d["form"].id}'


def submit(client, d, **extra):
    body = {'submission_key': str(uuid4()), 'name': 'Lead', 'email': 'lead@example.com', 'consent': True, **extra}
    return client.post(f'/api/v1/public/forms/{d["form"].id}/submit', json=body)


def test_new_field_types_are_validated(env):
    client, d = env
    fields = [
        {'key': 'intro', 'label': 'Conte sobre você', 'type': 'heading'},
        {'key': 'site', 'label': 'Site', 'type': 'url', 'required': True},
        {'key': 'extra_mail', 'label': 'E-mail financeiro', 'type': 'email'},
        {
            'key': 'interesses',
            'label': 'Interesses',
            'type': 'multiselect',
            'options': ['Ads', 'SEO'],
            'map_to': 'tags_in',
        },
        {'key': 'porte', 'label': 'Porte', 'type': 'radio', 'options': ['Micro', 'Pequena']},
    ]
    assert client.patch(form_url(d), headers=d['headers'](), json={'fields': fields}).status_code == 200
    ok = {'site': 'https://exemplo.com', 'extra_mail': 'Fin@Exemplo.com', 'interesses': ['Ads'], 'porte': 'Micro'}
    assert submit(client, d, answers=ok).status_code == 200
    saved = FormSubmission.query.one().answers
    assert saved['extra_mail'] == 'fin@exemplo.com' and saved['interesses'] == ['Ads'] and 'intro' not in saved
    for bad in (
        {**ok, 'site': 'javascript:alert(1)'},
        {**ok, 'interesses': ['Outro']},
        {**ok, 'porte': 'Gigante'},
        {**ok, 'extra_mail': 'nao-e-email'},
        {**ok, 'intro': 'x'},
    ):
        assert submit(client, d, answers=bad).status_code == 422, bad


def test_form_design_settings_and_redirect(env):
    client, d = env
    patch = {
        'design': {'background': '#112233', 'font': 'serif', 'button_label': 'Quero!', 'radius': 12, 'max_width': 640},
        'settings': {
            'consent_text': 'Aceito receber contato por e-mail.',
            'after_submit': {'type': 'redirect', 'url': 'https://exemplo.com/obrigado'},
            'base_fields': {'phone': {'visible': True, 'required': True, 'label': 'WhatsApp'}},
        },
    }
    assert client.patch(form_url(d), headers=d['headers'](), json=patch).status_code == 200
    public = client.get(f'/api/v1/public/forms/{d["form"].id}').json
    assert public['design']['font'] == 'serif' and public['design']['layout'] == 'card'
    assert public['consent_text'] == 'Aceito receber contato por e-mail.'
    assert public['base_fields']['phone']['label'] == 'WhatsApp'
    assert submit(client, d).status_code == 422  # phone became mandatory
    response = submit(client, d, phone='65999999999')
    assert response.status_code == 200 and response.json['redirect_url'] == 'https://exemplo.com/obrigado'
    assert FormSubmission.query.one().consent_text == 'Aceito receber contato por e-mail.'


@pytest.mark.parametrize(
    'patch',
    [
        {'design': {'background': 'red'}},
        {'design': {'logo_url': 'javascript:alert(1)'}},
        {'design': {'font': 'comic'}},
        {'design': {'unknown': 1}},
        {'settings': {'after_submit': {'type': 'redirect', 'url': ''}}},
        {'settings': {'after_submit': {'type': 'redirect', 'url': 'data:text/html,x'}}},
    ],
)
def test_invalid_design_is_rejected(env, patch):
    client, d = env
    assert client.patch(form_url(d), headers=d['headers'](), json=patch).status_code == 422


def test_form_fields_keep_layout_hints(env):
    client, d = env
    field = {
        'key': 'cidade',
        'label': 'Cidade',
        'type': 'text',
        'placeholder': 'Cuiabá',
        'help_text': 'Onde você mora',
        'width': 'half',
    }
    saved = client.patch(form_url(d), headers=d['headers'](), json={'fields': [field]}).json
    assert saved['fields'][0]['width'] == 'half' and saved['fields'][0]['placeholder'] == 'Cuiabá'


# ---------- deleting forms ----------
def test_unused_form_can_be_deleted(env):
    client, d = env
    form = LeadForm(workspace_id=d['ws'].id, name='Teste', headline='Oi', stage_id=d['stage'].id, fields=[])
    db.session.add(form)
    db.session.commit()
    assert client.delete(f'/api/v1/forms/{form.id}', headers=d['headers'](d['member'])).status_code == 403
    assert client.delete(f'/api/v1/forms/{form.id}', headers=d['headers'](d['outsider'])).status_code == 404
    assert client.delete(f'/api/v1/forms/{form.id}', headers=d['headers']()).status_code == 204
    assert client.get(f'/api/v1/forms/{form.id}', headers=d['headers']()).status_code == 404


def test_form_with_submissions_is_kept(env):
    client, d = env
    d['form'].active = True
    db.session.commit()
    assert submit(client, d).status_code == 200
    response = client.delete(form_url(d), headers=d['headers']())
    assert response.status_code == 409 and '1 solicitação' in response.json['error']['message']
    assert FormSubmission.query.count() == 1 and db.session.get(LeadForm, d['form'].id)


def test_form_used_by_a_funnel_is_kept_until_the_block_is_removed(env):
    client, d = env
    funnel = create_funnel(client, d, name='Meu funil')
    form = funnel_form(funnel)
    response = client.delete(f'/api/v1/forms/{form.id}', headers=d['headers']())
    assert response.status_code == 409 and 'Meu funil' in response.json['error']['message']
    step_url = f'/api/v1/funnels/{funnel["id"]}/steps/{funnel["steps"][0]["id"]}'
    blocks = [b for b in funnel['steps'][0]['blocks'] if b['type'] != 'form']
    assert client.patch(step_url, headers=d['headers'](), json={'blocks': blocks}).status_code == 200
    assert client.delete(f'/api/v1/forms/{form.id}', headers=d['headers']()).status_code == 204
