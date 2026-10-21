from flask import request
from sqlalchemy import func

from ...extensions import db

_ACCENTS = 'áàâãäéèêëíìîïóòôõöúùûüçñ'
_PLAIN = 'aaaaaeeeeiiiiooooouuuucn'


def fold(text):
    """Lower-case without accents, so "joao" finds "João"."""
    return str(text).lower().translate(str.maketrans(_ACCENTS, _PLAIN))


def search(q, model, *columns):
    term = (request.args.get('search') or '').strip()
    if not term:
        return q
    postgres = db.session.get_bind().dialect.name == 'postgresql'
    folded = '%' + fold(term) + '%'
    clauses = []
    for name in columns:
        column = getattr(model, name)
        clauses.append(
            func.translate(func.lower(column), _ACCENTS, _PLAIN).ilike(folded)
            if postgres
            else column.ilike('%' + term + '%')
        )
    digits = ''.join(ch for ch in term if ch.isdigit())
    if len(digits) >= 3 and 'phone' in columns:  # "(66) 99649-9089" matches +5566996499089
        phone = model.phone
        clauses.append(
            func.regexp_replace(phone, r'\D', '', 'g').ilike('%' + digits + '%')
            if postgres
            else phone.ilike('%' + digits + '%')
        )
    return q.filter(db.or_(*clauses))
