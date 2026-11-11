"""Instagram metrics: account totals, daily series, audience and recent posts.

Every part is best effort: one refused metric (new account, too few followers, missing permission) does not
hide the others. Results are kept as one snapshot per account, day and period, which spares the hourly API
limit and builds a follower history longer than the window Instagram itself keeps.
"""

from datetime import date, timedelta

from flask import current_app

from ...common import APIError
from ...extensions import db
from ...models import InstagramConnection, InstagramInsightSnapshot, now
from . import client, connections

PERIODS = (7, 30)
CACHE = timedelta(hours=1)
_attempted = {}  # connection id -> day of the last automatic attempt (per worker process)
ACCOUNT_FIELDS = 'username,name,profile_picture_url,followers_count,follows_count,media_count,biography,website'
TOTAL_METRICS = (
    'reach',
    'views',
    'accounts_engaged',
    'total_interactions',
    'likes',
    'comments',
    'shares',
    'saves',
    'replies',
    'profile_links_taps',
    'follows_and_unfollows',
)
SERIES_METRICS = ('reach', 'follower_count')
MEDIA_FIELDS = (
    'id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count'
)
MEDIA_METRICS = 'reach,views,likes,comments,saved,shares,total_interactions'
RECENT_MEDIA = 12
AUDIENCE = ('age', 'gender', 'city')


class Collector:
    def __init__(self, token):
        self.token, self.errors = token, []

    def call(self, part, path, **params):
        try:
            return client.graph(path, self.token, params=params)
        except client.GraphError as error:
            reason = 'permission' if error.meta_code in client.PERMISSION_CODES else 'unavailable'
            if error.meta_code in client.RATE_LIMIT_CODES:
                reason = 'rate_limited'
            self.errors.append({'part': part, 'reason': reason})
        except APIError:
            self.errors.append({'part': part, 'reason': 'unavailable'})
        return None


def window(days):
    until = now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = until - timedelta(days=days)
    return int(since.timestamp()), int(until.timestamp())


def totals(collector, connection, days):
    since, until = window(days)
    base = {'period': 'day', 'metric_type': 'total_value', 'since': since, 'until': until}
    data = collector.call('totals', connection.instagram_id + '/insights', metric=','.join(TOTAL_METRICS), **base)
    rows = (data or {}).get('data')
    if rows is None:
        # One unsupported metric fails the whole request; retry one by one to keep the rest.
        collector.errors = [e for e in collector.errors if e['part'] != 'totals']
        rows = []
        for metric in TOTAL_METRICS:
            single = collector.call('metric:' + metric, connection.instagram_id + '/insights', metric=metric, **base)
            rows += (single or {}).get('data') or []
    result = {}
    for row in rows:
        value = (row.get('total_value') or {}).get('value')
        if isinstance(value, (int, float)):
            result[row.get('name')] = value
    return result


def series(collector, connection, days):
    since, until = window(days)
    result = {}
    for metric in SERIES_METRICS:
        data = collector.call(
            'series:' + metric,
            connection.instagram_id + '/insights',
            metric=metric,
            period='day',
            since=since,
            until=until,
        )
        for row in (data or {}).get('data') or []:
            result[metric] = [
                {'date': str(point.get('end_time', ''))[:10], 'value': point.get('value')}
                for point in row.get('values') or []
                if isinstance(point.get('value'), (int, float))
            ]
    return result


def audience(collector, connection, days):
    result = {}
    for breakdown in AUDIENCE:
        data = collector.call(
            'audience:' + breakdown,
            connection.instagram_id + '/insights',
            metric='follower_demographics',
            period='lifetime',
            metric_type='total_value',
            timeframe='last_30_days' if days >= 30 else 'last_14_days',
            breakdown=breakdown,
        )
        for row in (data or {}).get('data') or []:
            for group in (row.get('total_value') or {}).get('breakdowns') or []:
                values = [
                    {'key': ', '.join(item.get('dimension_values') or []), 'value': item.get('value', 0)}
                    for item in group.get('results') or []
                ]
                result[breakdown] = sorted(values, key=lambda item: -item['value'])[:10]
    return result


def recent_media(collector, connection):
    data = collector.call('media', connection.instagram_id + '/media', fields=MEDIA_FIELDS, limit=RECENT_MEDIA)
    items = []
    for media in (data or {}).get('data') or []:
        row = {key: media.get(key) for key in MEDIA_FIELDS.split(',')}
        row['caption'] = (row.get('caption') or '')[:300]
        stats = collector.call('media_insights', str(media.get('id')) + '/insights', metric=MEDIA_METRICS)
        row['insights'] = {
            item.get('name'): (item.get('values') or [{}])[0].get('value') for item in (stats or {}).get('data') or []
        }
        items.append(row)
    # Repeated per-post refusals (e.g. old posts without metrics) are noise, keep one.
    seen, unique = set(), []
    for error in collector.errors:
        key = (error['part'], error['reason'])
        if key not in seen:
            seen.add(key)
            unique.append(error)
    collector.errors = unique
    return items


def collect(connection, days):
    collector = Collector(connections.token(connection))
    account = collector.call('account', connection.instagram_id, fields=ACCOUNT_FIELDS) or {}
    data = {
        'account': {key: account.get(key) for key in ACCOUNT_FIELDS.split(',')},
        'totals': totals(collector, connection, days),
        'series': series(collector, connection, days),
        'audience': audience(collector, connection, days),
        'media': recent_media(collector, connection),
    }
    data['errors'] = collector.errors
    return data


def history(connection, limit=90):
    """Followers per day from stored snapshots: kept by the Antares, not by Instagram."""
    rows = (
        InstagramInsightSnapshot.query.filter_by(connection_id=connection.id)
        .order_by(InstagramInsightSnapshot.day.desc())
        .limit(limit * len(PERIODS))
        .all()
    )
    days = {}
    for row in rows:
        followers = ((row.data or {}).get('account') or {}).get('followers_count')
        if isinstance(followers, int):
            days.setdefault(row.day.isoformat(), followers)
    return [{'date': day, 'followers': value} for day, value in sorted(days.items())][-limit:]


def snapshot(connection, days=30, force=False):
    if days not in PERIODS:
        raise APIError('Período inválido.', 422)
    if not connection.to_dict()['can_read_insights']:
        raise APIError('Reconecte este Instagram para autorizar as métricas.', 409)
    today = date.today()
    row = InstagramInsightSnapshot.query.filter_by(connection_id=connection.id, day=today, period=days).first()
    age = now() - row.updated_at if row else None
    if row and (age < timedelta(minutes=5) or (not force and age < CACHE)):
        return row  # Manual refresh still waits 5 minutes: each refresh costs about 20 API calls.
    data = collect(connection, days)
    if not row:
        row = InstagramInsightSnapshot(
            workspace_id=connection.workspace_id, connection_id=connection.id, day=today, period=days
        )
        db.session.add(row)
    row.data = data
    row.updated_at = now()
    db.session.flush()
    return row


def public(row, connection):
    return {
        **(row.data or {}),
        'period': row.period,
        'fetched_at': row.updated_at.isoformat(),
        'history': history(connection),
    }


def process():
    """One daily snapshot per account with metric permission, so follower history grows without anyone opening
    the screen. A failed day still stores what came back, so each account is tried at most once a day."""
    today = date.today()
    done = 0
    for connection in InstagramConnection.query.filter_by(active=True).all():
        if not connections.usable(connection) or not connection.to_dict()['can_read_insights']:
            continue
        if _attempted.get(connection.id) == today:
            continue
        if InstagramInsightSnapshot.query.filter_by(connection_id=connection.id, day=today, period=30).first():
            continue
        _attempted[connection.id] = today
        try:
            snapshot(connection, 30)
            db.session.commit()
            done += 1
        except Exception as error:  # worker boundary: one account never blocks the others
            db.session.rollback()
            current_app.logger.warning('instagram_insights_failed type=%s', type(error).__name__)
        if done >= 3:
            break  # Spread the work across passes.
    return done
