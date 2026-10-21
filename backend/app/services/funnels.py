"""Page funnels: steps made of blocks, templates, publishing, public pages and conversion metrics."""

import re
import unicodedata
from datetime import timedelta

from sqlalchemy import func

from ..common import APIError, query
from ..extensions import db
from ..models import Funnel, FunnelEvent, FunnelStep, LeadForm, PipelineStage, Workspace, now
from .domains import detach_funnel, ensure_scope
from .funnel_blocks import clean_blocks, clean_settings, form_ids

VIEW_DEDUP_MINUTES = 30
DEFAULT_THEME = {
    'accent_color': '#e60000',
    'background': '#ffffff',
    'text_color': '#25282b',
    'font': 'sans',
    'radius': 6,
}


def slugify(text):
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_text.lower()).strip('-')[:50] or 'pagina'


def unique_slug(funnel_id, wanted, ignore_id=None):
    base = slugify(wanted)
    taken = {
        slug
        for (slug,) in db.session.query(FunnelStep.slug).filter(
            FunnelStep.funnel_id == funnel_id, FunnelStep.id != (ignore_id or '')
        )
    }
    slug, counter = base, 2
    while slug in taken:
        slug = f'{base}-{counter}'
        counter += 1
    return slug


def ordered_steps(funnel_id):
    return FunnelStep.query.filter_by(funnel_id=funnel_id).order_by(FunnelStep.position, FunnelStep.created_at).all()


def serialize(funnel, steps=None):
    data = funnel.to_dict()
    data['theme'] = {**DEFAULT_THEME, **(funnel.theme or {})}
    if steps is not None:
        data['steps'] = [step.to_dict() for step in steps]
    return data


# ---------- editing ----------
def prepare_step_data(funnel_id, data, step=None):
    if 'blocks' in data:
        data['blocks'] = clean_blocks(data['blocks'])
        owned = {row.id for row in query(LeadForm).filter(LeadForm.id.in_(form_ids(data['blocks'])))}
        if set(form_ids(data['blocks'])) - owned:
            raise APIError('Um dos formulários selecionados não existe nesta conta.', 422)
    if 'settings' in data:
        data['settings'] = clean_settings(data['settings'])
    if 'slug' in data:
        data['slug'] = unique_slug(funnel_id, data['slug'], step.id if step else None)
    return data


def add_step(funnel, name, kind='landing', blocks=None, settings=None):
    position = db.session.query(func.count(FunnelStep.id)).filter_by(funnel_id=funnel.id).scalar()
    step = FunnelStep(
        workspace_id=funnel.workspace_id,
        funnel_id=funnel.id,
        name=name,
        slug=unique_slug(funnel.id, name),
        kind=kind,
        position=position,
        blocks=blocks or [],
        settings=settings or {},
    )
    db.session.add(step)
    db.session.flush()
    return step


def reorder(funnel, ids):
    steps = {step.id: step for step in ordered_steps(funnel.id)}
    if set(map(str, ids)) != set(steps):
        raise APIError('Envie todas as etapas do funil na nova ordem.', 422)
    for position, identifier in enumerate(map(str, ids)):
        steps[identifier].position = position


def delete_step(funnel, step):
    FunnelEvent.query.filter_by(step_id=step.id).delete()
    db.session.delete(step)
    db.session.flush()
    for position, remaining in enumerate(ordered_steps(funnel.id)):
        remaining.position = position


def delete_funnel(funnel):
    detach_funnel(funnel.id)
    FunnelEvent.query.filter_by(funnel_id=funnel.id).delete()
    FunnelStep.query.filter_by(funnel_id=funnel.id).delete()
    db.session.delete(funnel)


def referenced_forms(funnel):
    ids = [identifier for step in ordered_steps(funnel.id) for identifier in form_ids(step.blocks)]
    return (
        LeadForm.query.filter(LeadForm.workspace_id == funnel.workspace_id, LeadForm.id.in_(ids)).all() if ids else []
    )


def funnels_using_form(form_id):
    """Names of the funnels (of the current account) whose pages embed the form."""
    names = set()
    for step in query(FunnelStep):
        if form_id in form_ids(step.blocks):
            funnel = db.session.get(Funnel, step.funnel_id)
            names.add(funnel.name if funnel else '—')
    return sorted(names)


def publish(funnel):
    """Publishing also turns on the forms its pages embed, otherwise visitors could not submit."""
    if not ordered_steps(funnel.id):
        raise APIError('Adicione ao menos uma página antes de publicar.', 422)
    for form in referenced_forms(funnel):
        form.active = True
    funnel.status = 'published'


# ---------- templates ----------
def _block(identifier, kind, props=None, style=None):
    return {'id': identifier, 'type': kind, 'props': props or {}, 'style': style or {}}


def _capture_form(funnel, name, headline, description, button):
    stage = PipelineStage.query.filter_by(workspace_id=funnel.workspace_id).order_by(PipelineStage.position).first()
    if not stage:
        raise APIError('Crie uma etapa no funil de vendas antes de usar um modelo com formulário.', 422)
    form = LeadForm(
        workspace_id=funnel.workspace_id,
        name=f'{funnel.name} — {name}',
        headline=headline,
        description=description,
        stage_id=stage.id,
        source='Funil: ' + funnel.name,
        active=False,
        accent_color=(funnel.theme or {}).get('accent_color', DEFAULT_THEME['accent_color']),
        fields=[],
        design={'layout': 'plain', 'button_label': button, 'button_width': 'full'},
        settings={},
    )
    db.session.add(form)
    db.session.flush()
    return form


def _thank_you_blocks():
    return [
        _block('t1', 'heading', {'text': 'Tudo certo!', 'level': 1}, {'align': 'center', 'padding': 'lg'}),
        _block('t2', 'text', {'text': 'Recebemos seus dados e entraremos em contato em breve.'}, {'align': 'center'}),
    ]


def build_template(funnel, template):
    if template == 'lead_magnet':
        form = _capture_form(funnel, 'captura', 'Receba o material', '', 'Quero receber')
        add_step(
            funnel,
            'Captura',
            'optin',
            [
                _block(
                    'c1', 'heading', {'text': 'Baixe o guia gratuito', 'level': 1}, {'align': 'center', 'padding': 'lg'}
                ),
                _block(
                    'c2', 'text', {'text': 'Preencha os dados e receba o material no seu e-mail.'}, {'align': 'center'}
                ),
                _block(
                    'c3', 'list', {'items': ['Passo a passo prático', 'Modelos prontos para usar'], 'icon': 'check'}
                ),
                _block('c4', 'form', {'form_id': form.id, 'on_submit': 'next'}),
            ],
        )
        add_step(funnel, 'Obrigado', 'thankyou', _thank_you_blocks())
    elif template == 'sales':
        form = _capture_form(funnel, 'interesse', 'Quero saber mais', '', 'Falar com um especialista')
        add_step(
            funnel,
            'Página de vendas',
            'sales',
            [
                _block(
                    's1',
                    'heading',
                    {'text': 'Uma oferta pensada para o seu negócio', 'level': 1},
                    {'align': 'center', 'padding': 'lg'},
                ),
                _block(
                    's2',
                    'text',
                    {'text': 'Explique em duas frases o resultado que o cliente alcança.', 'size': 'lg'},
                    {'align': 'center'},
                ),
                _block('s3', 'video', {'url': ''}),
                _block(
                    's4',
                    'list',
                    {'items': ['Benefício principal', 'Benefício secundário', 'Garantia ou prova'], 'icon': 'check'},
                ),
                _block(
                    's5',
                    'testimonial',
                    {'quote': 'Depoimento de um cliente satisfeito.', 'author': 'Nome do cliente', 'role': 'Empresa'},
                ),
                _block('s6', 'faq', {'items': [{'q': 'Como funciona?', 'a': 'Descreva o processo.'}]}),
                _block('s7', 'form', {'form_id': form.id, 'on_submit': 'next'}),
            ],
        )
        add_step(funnel, 'Obrigado', 'thankyou', _thank_you_blocks())
    else:
        add_step(
            funnel,
            'Página inicial',
            'landing',
            [_block('b1', 'heading', {'text': 'Seu título aqui', 'level': 1}, {'align': 'center', 'padding': 'lg'})],
        )


def duplicate(funnel, name):
    """Copies pages and clones the embedded forms (inactive) so the copy can be edited independently."""
    copy = Funnel(workspace_id=funnel.workspace_id, name=name, description=funnel.description, theme=funnel.theme)
    db.session.add(copy)
    db.session.flush()
    clones = {}
    for form in referenced_forms(funnel):
        clone = LeadForm(
            workspace_id=form.workspace_id,
            name=f'{name} — {form.name}'[:150],
            headline=form.headline,
            description=form.description,
            success_message=form.success_message,
            stage_id=form.stage_id,
            source='Funil: ' + name,
            active=False,
            fields=form.fields,
            brand_name=form.brand_name,
            accent_color=form.accent_color,
            design=form.design,
            settings=form.settings,
        )
        db.session.add(clone)
        db.session.flush()
        clones[form.id] = clone.id
    for step in ordered_steps(funnel.id):
        blocks = [
            {**b, 'props': {**b['props'], 'form_id': clones.get(b['props'].get('form_id'), b['props'].get('form_id'))}}
            if b['type'] == 'form'
            else b
            for b in step.blocks
        ]
        add_step(copy, step.name, step.kind, blocks, step.settings)
        copy_step = ordered_steps(copy.id)[-1]
        copy_step.slug = step.slug
    return copy


# ---------- public pages ----------
def published_funnel(funnel_id):
    row = (
        Funnel.query.join(Workspace, Funnel.workspace_id == Workspace.id)
        .filter(Funnel.id == str(funnel_id), Funnel.status == 'published', Workspace.active.is_(True))
        .first()
    )
    if not row:
        raise APIError('Página indisponível.', 404)
    ensure_scope(row.workspace_id)
    return row


def public_page(funnel_id, slug=None):
    from .form_submission import public_payload

    funnel = published_funnel(funnel_id)
    steps = ordered_steps(funnel.id)
    index = next((i for i, s in enumerate(steps) if s.slug == slug), None) if slug else (0 if steps else None)
    if index is None:
        raise APIError('Página indisponível.', 404)
    step = steps[index]
    wanted = form_ids(step.blocks)
    forms = (
        LeadForm.query.filter(
            LeadForm.id.in_(wanted), LeadForm.workspace_id == funnel.workspace_id, LeadForm.active.is_(True)
        )
        if wanted
        else []
    )
    return {
        'funnel': {'id': funnel.id, 'name': funnel.name, 'theme': {**DEFAULT_THEME, **(funnel.theme or {})}},
        'step': {
            'id': step.id,
            'slug': step.slug,
            'name': step.name,
            'kind': step.kind,
            'blocks': step.blocks,
            'settings': step.settings,
        },
        'next_slug': steps[index + 1].slug if index + 1 < len(steps) else None,
        'forms': {form.id: public_payload(form) for form in forms},
    }


# ---------- metrics ----------
def record_view(funnel_id, step_id, visitor_id):
    funnel = published_funnel(funnel_id)
    step = FunnelStep.query.filter_by(id=str(step_id), funnel_id=funnel.id).first()
    if not step:
        raise APIError('Página indisponível.', 404)
    recent = FunnelEvent.query.filter(
        FunnelEvent.step_id == step.id,
        FunnelEvent.visitor_id == str(visitor_id),
        FunnelEvent.kind == 'view',
        FunnelEvent.created_at > now() - timedelta(minutes=VIEW_DEDUP_MINUTES),
    ).first()
    if not recent:
        db.session.add(
            FunnelEvent(
                workspace_id=funnel.workspace_id,
                funnel_id=funnel.id,
                step_id=step.id,
                kind='view',
                visitor_id=str(visitor_id),
            )
        )
        db.session.commit()


def record_conversion(workspace_id, attribution):
    """Called inside the form-submission transaction; ignores attribution that does not match this account."""
    funnel_id, step_id, visitor = (attribution.get(k) for k in ('funnel_id', 'funnel_step_id', 'visitor_id'))
    if not (funnel_id and step_id and visitor):
        return
    step = FunnelStep.query.filter_by(id=step_id, funnel_id=funnel_id, workspace_id=workspace_id).first()
    if step:
        db.session.add(
            FunnelEvent(
                workspace_id=workspace_id, funnel_id=funnel_id, step_id=step.id, kind='conversion', visitor_id=visitor
            )
        )


def stats(funnel):
    steps = ordered_steps(funnel.id)
    counts = {}
    for step_id, kind, total, visitors in (
        query(FunnelEvent)
        .filter_by(funnel_id=funnel.id)
        .with_entities(
            FunnelEvent.step_id, FunnelEvent.kind, func.count(), func.count(func.distinct(FunnelEvent.visitor_id))
        )
        .group_by(FunnelEvent.step_id, FunnelEvent.kind)
    ):
        counts[(step_id, kind)] = (total, visitors)
    rows, previous = [], None
    for step in steps:
        views, visitors = counts.get((step.id, 'view'), (0, 0))
        conversions = counts.get((step.id, 'conversion'), (0, 0))[1]
        rows.append(
            {
                'step_id': step.id,
                'name': step.name,
                'slug': step.slug,
                'kind': step.kind,
                'views': views,
                'visitors': visitors,
                'conversions': conversions,
                'conversion_rate': round(conversions / visitors, 4) if visitors else 0,
                'drop_off': round(1 - visitors / previous, 4) if previous else 0,
            }
        )
        previous = visitors or previous
    converted = (
        query(FunnelEvent)
        .filter_by(funnel_id=funnel.id, kind='conversion')
        .with_entities(func.count(func.distinct(FunnelEvent.visitor_id)))
        .scalar()
    )
    entered = rows[0]['visitors'] if rows else 0
    return {
        'steps': rows,
        'visitors': entered,
        'conversions': converted,
        'conversion_rate': round(converted / entered, 4) if entered else 0,
    }


def totals_for(funnel_ids):
    """Views and distinct converted visitors per funnel for the listing, in two grouped queries."""
    if not funnel_ids:
        return {}
    result = {i: {'views': 0, 'conversions': 0, 'steps': 0} for i in funnel_ids}
    for funnel_id, kind, total, visitors in (
        query(FunnelEvent)
        .filter(FunnelEvent.funnel_id.in_(funnel_ids))
        .with_entities(
            FunnelEvent.funnel_id, FunnelEvent.kind, func.count(), func.count(func.distinct(FunnelEvent.visitor_id))
        )
        .group_by(FunnelEvent.funnel_id, FunnelEvent.kind)
    ):
        result[funnel_id]['views' if kind == 'view' else 'conversions'] = total if kind == 'view' else visitors
    for funnel_id, total in (
        query(FunnelStep)
        .filter(FunnelStep.funnel_id.in_(funnel_ids))
        .with_entities(FunnelStep.funnel_id, func.count())
        .group_by(FunnelStep.funnel_id)
    ):
        result[funnel_id]['steps'] = total
    return result
