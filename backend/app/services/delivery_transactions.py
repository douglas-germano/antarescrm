"""Named transaction boundaries for durable delivery claims and provider outcomes.

These commits must not be collapsed into a request-wide transaction: a provider may
accept a message even when its HTTP reply or our subsequent database write fails.
"""

import logging

from ..extensions import db
from ..observability import event


def commit_delivery(stage, *, channel, workspace_id, resource_id):
    if stage not in ('claim', 'outcome'):
        raise ValueError('Delivery stage must be claim or outcome.')
    try:
        db.session.commit()
    except Exception as error:
        event(
            'delivery_commit_failed',
            level=logging.ERROR,
            stage=stage,
            channel=channel,
            workspace_id=workspace_id,
            resource_id=resource_id,
            error_type=type(error).__name__,
        )
        raise
    event(
        'delivery_committed',
        stage=stage,
        channel=channel,
        workspace_id=workspace_id,
        resource_id=resource_id,
    )
