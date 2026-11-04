"""Instagram profiles: contact and account profile updates."""

from datetime import timedelta

from ...extensions import db
from ...models import now
from . import client


def apply_account(row, data):
    row.name = (data.get('name') or '').strip()[:150] or row.name
    row.profile_picture_url = data.get('profile_picture_url') or row.profile_picture_url
    row.profile_synced_at = now()
    if data.get('username'):
        row.username = data['username']


def refresh_account(row, max_age_hours=6):
    """Keeps the connection card current; picture links from Instagram expire, so they are renewed periodically."""
    if not row or not row.active or not row.encrypted_token:
        return
    if (
        row.profile_synced_at
        and row.name
        and row.profile_picture_url
        and row.profile_synced_at > now() - timedelta(hours=max_age_hours)
    ):
        return
    data = client.fetch_account(client.cipher().decrypt(row.encrypted_token.encode()).decode())
    if data:
        apply_account(row, data)
        db.session.commit()


def apply_profile(contact, scoped_id, profile):
    """Replaces the placeholder name; never overwrites a name someone typed."""
    if not profile:
        return
    fields = dict(contact.custom_fields or {})
    if profile['username']:
        fields['instagram_username'] = profile['username']
    if profile['name']:
        fields['instagram_name'] = profile['name']
    contact.custom_fields = fields
    if contact.name == 'Instagram ' + scoped_id:
        contact.name = (profile['name'] or '@' + profile['username'])[:180]
