"""Subscription state, access rules and Asaas webhook processing.

Access: no subscription row (or BILLING_ENABLED off) => full access. trialing => full until trial end.
active => full. past_due => full for BILLING_GRACE_DAYS, then read-only. canceled => read-only.
Client accounts of an agency follow the agency's subscription.
"""

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import current_app
from sqlalchemy.exc import IntegrityError

from ..common import APIError
from ..extensions import db
from ..models import BillingEvent, Subscription, User, Workspace, now
from . import asaas

PAID_EVENTS = {'PAYMENT_RECEIVED', 'PAYMENT_CONFIRMED'}
CANCEL_EVENTS = {'SUBSCRIPTION_DELETED', 'SUBSCRIPTION_INACTIVATED'}
READ_ONLY_MESSAGE = 'Sua assinatura está inativa. Regularize o pagamento para voltar a criar e enviar.'


def enabled():
    return bool(current_app.config.get('BILLING_ENABLED'))


def billed_workspace_id(workspace):
    return workspace.parent_workspace_id or workspace.id


def subscription_for(workspace_id):
    return Subscription.query.filter_by(workspace_id=workspace_id).first()


def start_trial(workspace_id):
    if not enabled():
        return None
    row = Subscription(
        workspace_id=workspace_id,
        status='trialing',
        trial_ends_at=now() + timedelta(days=current_app.config['BILLING_TRIAL_DAYS']),
    )
    db.session.add(row)
    return row


def access_state(sub):
    """Return 'full' or 'read_only' for a subscription row."""
    if sub is None:
        return 'full'
    current = now()
    if sub.status == 'active':
        return 'full'
    if sub.status == 'trialing':
        return 'full' if sub.trial_ends_at and current < sub.trial_ends_at else 'read_only'
    if sub.status == 'past_due':
        since = sub.past_due_since or current
        return 'full' if current < since + timedelta(days=current_app.config['BILLING_GRACE_DAYS']) else 'read_only'
    return 'read_only'


def workspace_access(workspace):
    if not enabled() or workspace is None:
        return 'full'
    return access_state(subscription_for(billed_workspace_id(workspace)))


def status_payload(workspace):
    sub = subscription_for(billed_workspace_id(workspace))
    price = current_app.config.get('BILLING_PRICE_BRL')
    return {
        'enabled': enabled(),
        'managed_by_agency': bool(workspace.parent_workspace_id),
        'status': sub.status if sub else None,
        'access': workspace_access(workspace),
        'trial_ends_at': sub.trial_ends_at.isoformat() if sub and sub.trial_ends_at else None,
        'next_due_date': sub.next_due_date.isoformat() if sub and sub.next_due_date else None,
        'invoice_url': sub.invoice_url if sub else None,
        'price': price,
        'can_subscribe': bool(price) and not (sub and sub.asaas_subscription_id and sub.status != 'canceled'),
    }


def normalize_cpf_cnpj(value):
    digits = re.sub(r'\D', '', str(value or ''))
    if len(digits) not in (11, 14):
        raise APIError('Informe um CPF (11 dígitos) ou CNPJ (14 dígitos) válido.', 422)
    return digits


def subscribe(workspace, user, cpf_cnpj):
    """Create the Asaas customer and monthly subscription; first charge is due when the trial ends."""
    if workspace.parent_workspace_id:
        raise APIError('A cobrança desta conta é feita pela agência.', 403)
    price = current_app.config.get('BILLING_PRICE_BRL')
    try:
        value = Decimal(str(price))
        if value <= 0:
            raise InvalidOperation
    except (InvalidOperation, TypeError) as exc:
        raise APIError('O preço da assinatura não está configurado.', 503) from exc
    cpf_cnpj = normalize_cpf_cnpj(cpf_cnpj)
    sub = subscription_for(workspace.id) or Subscription(workspace_id=workspace.id, status='trialing')
    if sub.asaas_subscription_id and sub.status != 'canceled':
        raise APIError('Esta conta já possui uma assinatura.', 409)
    db.session.add(sub)
    owner = db.session.get(User, user.id)
    customer_id = (
        sub.asaas_customer_id or asaas.create_customer(workspace.name, owner.email, cpf_cnpj, workspace.id)['id']
    )
    today = now().date()
    first_due = max(sub.trial_ends_at.date() if sub.trial_ends_at else today, today + timedelta(days=1))
    created = asaas.create_subscription(
        customer_id, float(value), first_due, workspace.id, f'Antares CRM - {workspace.name}'[:200]
    )
    sub.asaas_customer_id, sub.asaas_subscription_id, sub.next_due_date = customer_id, created['id'], first_due
    if sub.status == 'canceled':
        sub.status = 'trialing'
        sub.trial_ends_at = now()
    payments = asaas.subscription_payments(created['id'])
    if payments:
        sub.invoice_url = payments[0].get('invoiceUrl')
    db.session.commit()
    return sub


def _parse_date(value):
    from datetime import date

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def apply_event(body):
    """Apply one Asaas webhook body. Returns 'applied', 'duplicate' or 'ignored'."""
    event_id, event = str(body.get('id') or ''), str(body.get('event') or '')
    payment = body.get('payment') if isinstance(body.get('payment'), dict) else {}
    subscription = body.get('subscription') if isinstance(body.get('subscription'), dict) else {}
    asaas_sub_id = payment.get('subscription') or subscription.get('id')
    if not event_id or not event or not asaas_sub_id:
        return 'ignored'
    sub = Subscription.query.filter_by(asaas_subscription_id=str(asaas_sub_id)).with_for_update().first()
    if sub is None:
        return 'ignored'
    db.session.add(BillingEvent(event_id=event_id[:80], event_type=event[:60], workspace_id=sub.workspace_id))
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return 'duplicate'
    status = str(payment.get('status') or '')
    if event in PAID_EVENTS:
        sub.status, sub.past_due_since, sub.last_paid_at = 'active', None, now()
    elif (
        event == 'PAYMENT_OVERDUE'
        and status == 'OVERDUE'
        and sub.status != 'canceled'
        or event in ('PAYMENT_REFUNDED', 'PAYMENT_CHARGEBACK_REQUESTED')
        and sub.status != 'canceled'
    ):
        sub.status = 'past_due'
        sub.past_due_since = sub.past_due_since or now()
    elif event in CANCEL_EVENTS:
        sub.status = 'canceled'
    if payment.get('invoiceUrl') and status not in ('RECEIVED', 'CONFIRMED', 'REFUNDED'):
        sub.invoice_url = str(payment['invoiceUrl'])[:500]
    due = _parse_date(payment.get('dueDate')) if payment else None
    if due and event in ('PAYMENT_CREATED', 'PAYMENT_UPDATED'):
        sub.next_due_date = due
    db.session.commit()
    return 'applied'


def check_webhook_token(header_value):
    import hmac

    expected = current_app.config.get('ASAAS_WEBHOOK_TOKEN') or ''
    return bool(expected) and hmac.compare_digest(str(header_value or ''), expected)


def workspace_by_id(workspace_id):
    return db.session.get(Workspace, workspace_id)
