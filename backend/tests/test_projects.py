import io
from test_growth import env
from app.extensions import db
from app.models import Contact, Opportunity, Project, ProjectFile, ProjectApproval

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64


def h(d, user=None):
    return d['headers'](user) if user else d['headers']()


def make_deal(d, status='open', amount=1500):
    contact = Contact(workspace_id=d['ws'].id, name='Cliente Alfa', phone='+5566999990000')
    db.session.add(contact)
    db.session.flush()
    deal = Opportunity(
        workspace_id=d['ws'].id,
        contact_id=contact.id,
        stage_id=d['stage'].id,
        owner_id=d['owner'].id,
        title='Campanha de lançamento',
        amount=amount,
        status=status,
    )
    db.session.add(deal)
    db.session.commit()
    return deal


def upload(client, d, pid, data=None, name='layout.png', content=PNG, **extra):
    body = {'file': (io.BytesIO(content), name), **(data or {})}
    return client.post(
        f'/api/v1/projects/{pid}/files', data=body, headers=h(d), content_type='multipart/form-data', **extra
    )


def test_default_stages_and_won_deal_creates_one_project(env, tmp_path):
    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    stages = client.get('/api/v1/project-stages', headers=h(d)).json['items']
    assert [s['name'] for s in stages] == ['Briefing', 'Criação', 'Aprovação', 'Publicação', 'Relatório'] and stages[
        -1
    ]['is_final']
    deal = make_deal(d)
    assert (
        client.post(f'/api/v1/opportunities/{deal.id}/close', json={'status': 'won'}, headers=h(d)).status_code == 200
    )
    project = Project.query.one()
    assert (
        project.title == 'Campanha de lançamento'
        and project.contact_id == deal.contact_id
        and str(project.amount) == '1500.00'
    )
    assert (
        client.post('/api/v1/projects', json={'opportunity_id': deal.id}, headers=h(d)).status_code == 409
    )  # one project per deal
    listed = client.get('/api/v1/projects', headers=h(d)).json['items'][0]
    assert listed['contact_name'] == 'Cliente Alfa' and listed['stage']['name'] == 'Briefing'


def test_manual_project_stage_moves_complete_and_reopen(env, tmp_path):
    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    deal = make_deal(d)
    created = client.post(
        '/api/v1/projects', json={'opportunity_id': str(deal.id), 'title': 'Campanha — fase 1'}, headers=h(d)
    )
    assert created.status_code == 201
    pid = created.json['id']
    stages = {s['name']: s['id'] for s in client.get('/api/v1/project-stages', headers=h(d)).json['items']}
    assert (
        client.patch(f'/api/v1/projects/{pid}', json={'stage_id': stages['Relatório']}, headers=h(d)).json['status']
        == 'done'
    )
    assert (
        client.patch(f'/api/v1/projects/{pid}', json={'stage_id': stages['Criação']}, headers=h(d)).json['status']
        == 'active'
    )
    events = client.get(f'/api/v1/projects/{pid}', headers=h(d)).json['events']
    assert any('concluído' in e['text'] for e in events) and any('reaberto' in e['text'] for e in events)


def test_file_upload_versions_download_and_validation(env, tmp_path):
    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    pid = client.post('/api/v1/projects', json={'title': 'Projeto X'}, headers=h(d)).json['id']
    first = upload(client, d, pid, {'title': 'Arte do post', 'kind': 'layout'})
    assert (
        first.status_code == 201
        and first.json['version'] == 1
        and first.json['inline'] is True
        and 'storage_key' not in first.json
    )
    second = upload(client, d, pid, {'replaces_group_id': first.json['group_id']})
    assert (
        second.json['version'] == 2
        and second.json['group_id'] == first.json['group_id']
        and second.json['title'] == 'Arte do post'
    )
    detail = client.get(f'/api/v1/projects/{pid}', headers=h(d)).json
    assert len(detail['files']) == 1 and [v['version'] for v in detail['files'][0]['versions']] == [2, 1]
    download = client.get(f'/api/v1/projects/{pid}/files/{second.json["id"]}/download?inline=1', headers=h(d))
    assert (
        download.status_code == 200 and download.data == PNG and download.headers['X-Content-Type-Options'] == 'nosniff'
    )
    assert upload(client, d, pid, name='script.html', content=b'<script>').status_code == 422
    assert upload(client, d, pid, name='fake.png', content=b'not an image').status_code == 422
    assert upload(client, d, pid, name='vazio.png', content=b'').status_code == 422
    assert (
        client.get(
            f'/api/v1/projects/{pid}/files/{second.json["id"]}/download', headers=h(d, d['outsider'])
        ).status_code
        == 404
    )


def test_public_approval_flow_is_single_use_and_records_who_decided(env, tmp_path):
    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    pid = client.post('/api/v1/projects', json={'title': 'Projeto X'}, headers=h(d)).json['id']
    file = upload(client, d, pid, {'title': 'Arte principal'}).json
    created = client.post(
        f'/api/v1/projects/{pid}/approvals',
        json={'title': 'Aprovar arte principal', 'message': 'Confira', 'file_id': file['id']},
        headers=h(d),
    )
    assert created.status_code == 201
    token = created.json['token']
    assert 'token_hash' not in created.json and ProjectApproval.query.one().token_hash != token
    info = client.get(f'/api/v1/public/approvals/{token}')
    assert (
        info.status_code == 200
        and info.json['project'] == 'Projeto X'
        and info.json['file']['inline'] is True
        and info.json['status'] == 'pending'
    )
    assert client.get(f'/api/v1/public/approvals/{token}/file?inline=1').data == PNG
    assert client.get('/api/v1/public/approvals/inexistente').status_code == 404
    assert (
        client.post(
            f'/api/v1/public/approvals/{token}/decide', json={'decision': 'changes_requested', 'name': 'Ana'}
        ).status_code
        == 422
    )  # needs a comment
    ok = client.post(
        f'/api/v1/public/approvals/{token}/decide',
        json={'decision': 'approved', 'name': 'Ana Souza', 'comment': 'Perfeito'},
        headers={'X-Client-IP': '203.0.113.9'},
    )
    assert ok.status_code == 200 and ok.json['status'] == 'approved'
    row = ProjectApproval.query.one()
    assert row.decided_by == 'Ana Souza' and row.decided_ip == '203.0.113.9' and row.token_hash is None
    assert (
        client.post(f'/api/v1/public/approvals/{token}/decide', json={'decision': 'approved', 'name': 'x'}).status_code
        == 404
    )  # link is single-use
    events = client.get(f'/api/v1/projects/{pid}', headers=h(d)).json['events']
    assert any('Ana Souza aprovou' in e['text'] for e in events)


def test_expired_cancelled_and_internal_approvals(env, tmp_path):
    from datetime import timedelta
    from app.models import now

    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    pid = client.post('/api/v1/projects', json={'title': 'Projeto X'}, headers=h(d)).json['id']
    a = client.post(f'/api/v1/projects/{pid}/approvals', json={'title': 'A'}, headers=h(d)).json
    row = db.session.get(ProjectApproval, a['id'])
    row.expires_at = now() - timedelta(days=1)
    db.session.commit()
    assert (
        client.post(
            f'/api/v1/public/approvals/{a["token"]}/decide', json={'decision': 'approved', 'name': 'x'}
        ).status_code
        == 410
    )
    assert client.get(f'/api/v1/public/approvals/{a["token"]}').json['status'] == 'expired'
    regen = client.post(f'/api/v1/projects/{pid}/approvals/{a["id"]}/regenerate', headers=h(d)).json['token']
    assert client.get(f'/api/v1/public/approvals/{regen}').json['status'] == 'pending'
    assert client.post(f'/api/v1/projects/{pid}/approvals/{a["id"]}/cancel', headers=h(d)).status_code == 200
    assert client.get(f'/api/v1/public/approvals/{regen}').status_code == 404
    b = client.post(f'/api/v1/projects/{pid}/approvals', json={'title': 'B', 'channel': 'internal'}, headers=h(d)).json
    assert b['token'] is None
    done = client.post(
        f'/api/v1/projects/{pid}/approvals/{b["id"]}/decide',
        json={'decision': 'approved', 'name': 'Cliente (WhatsApp)'},
        headers=h(d),
    )
    assert done.status_code == 200
    assert (
        client.post(
            f'/api/v1/projects/{pid}/approvals/{b["id"]}/decide',
            json={'decision': 'approved', 'name': 'x'},
            headers=h(d),
        ).status_code
        == 409
    )


def test_stage_management_and_account_isolation(env, tmp_path):
    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    client.get('/api/v1/project-stages', headers=h(d))
    assert client.post('/api/v1/project-stages', json={'name': 'Medição'}, headers=h(d, d['member'])).status_code == 403
    created = client.post('/api/v1/project-stages', json={'name': 'Medição', 'color': '#2f6f8f'}, headers=h(d))
    assert created.status_code == 201
    assert client.post('/api/v1/project-stages', json={'name': 'medição'}, headers=h(d)).status_code == 409
    pid = client.post(
        '/api/v1/projects', json={'title': 'Projeto X', 'stage_id': created.json['id']}, headers=h(d)
    ).json['id']
    assert (
        client.delete(f'/api/v1/project-stages/{created.json["id"]}', headers=h(d)).status_code == 409
    )  # still in use
    assert client.get('/api/v1/projects', headers=h(d, d['outsider'])).json['items'] == []
    assert client.get(f'/api/v1/projects/{pid}', headers=h(d, d['outsider'])).status_code == 404
    assert client.delete(f'/api/v1/projects/{pid}', headers=h(d, d['member'])).status_code == 403
    assert client.delete(f'/api/v1/projects/{pid}', headers=h(d)).status_code == 204
    assert client.delete(f'/api/v1/project-stages/{created.json["id"]}', headers=h(d)).status_code == 204


def test_deal_amount_is_kept_when_the_form_sends_zero(env, tmp_path):
    client, d = env
    client.application.config['PROJECT_FILES_DIR'] = str(tmp_path)
    deal = make_deal(d, amount=30000)
    created = client.post('/api/v1/projects', json={'opportunity_id': str(deal.id), 'amount': '0.00'}, headers=h(d))
    assert created.status_code == 201 and created.json['amount'] == '30000.00'
